/**
 * d-reach 插件版（与 skill 并行，不替代）
 *
 * 定位：skill 里那些「要读 SKILL.md 才知道怎么拼」的操作，在这里变成一次工具调用。
 *
 *   d_reach         并发检索（auto 按场景选路 / quick / base / deep）
 *   d_reach_fetch   抓一个 URL：微信直连 / cookie 注入 / curl / Playwright / TinyFish / Jina / BrightData / archive.today
 *                   八档降级，失败按网络·反爬·付费墙·登录墙·解析分类，能说清「该不该重试」
 *   d_reach_quota   额度与通道健康（可选顺带跑一次官方校准）
 *
 *   /reach、/reach-deep   交互式跑一轮，结果只弹通知
 *
 * 所有检索/记账逻辑仍在 skill 的 scripts/ 里，插件不复制一份。
 */

import { execFile } from "node:child_process";
import { mkdir, readFile, stat, unlink, writeFile } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

const run = promisify(execFile);
const SKILL_DIR = join(homedir(), ".agents/skills/d-reach");
const FANOUT = join(SKILL_DIR, "scripts", "fanout.sh");
const KEY_SH = join(SKILL_DIR, "scripts", "load_key.sh");
const PROBE = join(SKILL_DIR, "scripts", "quota_probe.py");
const HERE = dirname(fileURLToPath(import.meta.url));
const RENDER = join(HERE, "scripts", "render.mjs");
const PDF2TEXT = join(HERE, "scripts", "pdf2text.py");
const DATA_DIR = join(homedir(), ".agent-reach");
const LAST_RUN = join(DATA_DIR, "last-run.md");
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36";

// ---------------------------------------------------------------- 检索

const PROFILES = {
  auto: { label: "auto · 按场景选路", on: "" },
  quick: { label: "quick · 3 路固定", on: "qianfan,fcdev,tf" },
  base: { label: "base · 9 路", on: "" },
  deep: { label: "deep · 13 路", on: "" },
} as const;

type Profile = keyof typeof PROFILES;

/** 按 query 特征选通道。命中不准时用 channels 参数覆盖。 */
// 场景路由：按真实使用场景（旅行/本地、对比选型、官方文档、硬件 AV…）分档。
// 规则来自 40 次历史 d_reach 调用的实际 query 分布 —— 之前「中文通用」走
// qianfan,jj,segfault，查酒店/门票/天气全落到掘金和 SegmentFault 两个程序员
// 社区，是最大的误判来源。
const SCENES: { re: RegExp; on: string; why: string }[] = [
  {
    re: /(paper|arxiv|论文|文献|survey|benchmark|sota|研究综述|doi|citation)/i,
    on: "oalex,crossref,fcres",
    why: "学术：OpenAlex + Crossref + Research Index",
  },
  {
    // 「宜兴 窑湖小镇 万圣节 活动 门票 2026」也含 2026，本地生活必须排在时效前面，
    // 否则「汉庭 窑湖小镇 携程 价格 距离」会被「价格」抢去走时效通道
    re: /(攻略|门票|开放时间|景点|酒店|民宿|住宿|自驾|美食|餐厅|咖啡|附近|地址|门店|营业|入住|景点|演出|展览|活动|烟花|周末去哪)/,
    on: "serper,fcs,qianfan",
    why: "本地生活/旅行：Serper Google + Firecrawl + 千帆",
  },
  {
    re: /(\bvs\.?\b|对比|区别|哪个好|哪个更|替代|选型|值得买|值不值|还是)/i,
    on: "fcs,exa,tf",
    why: "对比/选型：Firecrawl + Exa 语义 + TinyFish",
  },
  {
    re: /(最新|今天|昨天|本周|明天|后天|发布|上线|价格|股价|行情|天气|气温|降雨|预报|weather|forecast|release|changelog|政策|固件|版本更新|202[5-9])/i,
    on: "langsearch,tf,qianfan",
    why: "时效/天气/政策：LangSearch + TinyFish + 千帆",
  },
  {
    re: /(\bapi\b|\bsdk\b|文档|参数|接口|用法|怎么用|how to use|reference|man ?page|\buri\b|callnative|示例代码|官方文档)/i,
    on: "fcdev,fcs,qianfan",
    why: "官方文档/API：Firecrawl Dev 索引 + Firecrawl 搜索 + 千帆",
  },
  {
    // 「什么是 X / X 是谁 / X 的历史」—— 维基百科 0.7s、免费无限量，比任何搜索通道都快
    re: /(什么是|是什么|是谁|的定义|定义是什么|原理是什么|历史沿革|由来|起源于|维基百科|百科)/,
    on: "wiki,qianfan",
    why: "概念/百科：Wikipedia + 千帆",
  },
  {
    re: /(error|exception|traceback|stack ?trace|报错|排查|卡住|报错|不生效|失败|编译|部署|配置|安装|依赖|端口冲突|超时|崩溃)/i,
    on: "se,fcdev,qianfan",
    why: "排障：StackExchange + Firecrawl Dev + 千帆",
  },
];

function pickByIntent(query: string): { on: string; why: string; unclear?: boolean } {
  const zh = /[\u4e00-\u9fff]/.test(query);
  for (const s of SCENES) {
    if (s.re.test(query)) return { on: s.on, why: s.why };
  }
  // 技术词表：加了 AV/硬件/自建服务，否则「mpv-android truehd passthrough」
  // 这种会掉进通用兜底，拿不到 SuperUser 那类讨论
  const tech =
    /\b(mtu|wireguard|docker|compose|k8s|kubernetes|python|java|rust|golang|node|api|sdk|http|tcp|udp|sql|git|nginx|redis|kafka|postgres|mysql|linux|bug|fix|mqtt|spdif|passthrough|bitstream|truehd|atmos|dts|codec|hdr|ffmpeg|mpv|vlc|plex|jellyfin|home ?assistant|nas|ssh|systemd|curl|json|yaml)\b/i.test(
      query,
    );
  const code =
    /(error|exception|traceback|compile|build|报错|编译|部署|配置|安装|依赖|函数)/i.test(
      query,
    );
  if (zh && (code || tech))
    return {
      on: "qianfan,se,jj",
      why: "中文技术：千帆 + StackExchange + 掘金",
    };
  if (zh)
    return {
      on: "qianfan,tf",
      why: "中文通用：千帆 + TinyFish",
    };
  if (code || tech)
    return {
      on: "se,fcdev,hn",
      why: "英文技术/硬件：StackExchange + Firecrawl Dev + HN",
    };
  return {
    on: "tf,fcs,qianfan",
    why: "未命中已知场景，先用 TinyFish + Firecrawl + 千帆兜底",
    unclear: true,
  };
}

interface Hit {
  title: string;
  url: string;
  note: string;
}

interface ChannelResult {
  name: string;
  mark: string;
  status: "ok" | "zero" | "fail" | "skip";
  note: string;
  hits: Hit[];
}

interface Parsed {
  channels: ChannelResult[];
  summary: string;
  next: string;
  health: string;
}

const MARK_STATUS: Record<string, ChannelResult["status"]> = {
  "✅": "ok",
  "💬": "ok",
  "⚪": "zero",
  "❌": "fail",
  "⚠️": "fail",
  "🔇": "skip",
};

function parseFanout(md: string): Parsed {
  const channels: ChannelResult[] = [];
  let cur: ChannelResult | null = null;
  let summary = "";
  let next = "";
  let health = "";

  for (const raw of md.split("\n")) {
    const line = raw.trimEnd();

    const head = line.match(/^###\s+(✅|⚪|❌|⚠️|🔇|💬)\s+(.+)$/);
    if (head) {
      const mark = head[1];
      let rest = head[2];
      let note = "";
      const dash = rest.match(/^(.*?)\s*——\s*(.+)$/);
      if (dash) {
        rest = dash[1];
        note = dash[2];
      }
      cur = {
        name: rest.trim(),
        mark,
        status: MARK_STATUS[mark] ?? "zero",
        note,
        hits: [],
      };
      channels.push(cur);
      continue;
    }
    if (line.startsWith("**汇总**")) {
      summary = line
        .replace(/^\*\*汇总\*\*：/, "")
        .replace(/\*\*/g, "")
        .trim();
      cur = null;
      continue;
    }
    if (line.startsWith("**通道健康**")) {
      health = line
        .replace(/^\*\*通道健康\*\*：/, "")
        .replace(/\*\*/g, "")
        .trim();
      continue;
    }
    if (line.startsWith("**下一步**")) {
      next = line
        .replace(/^\*\*下一步\*\*：/, "")
        .replace(/\*\*/g, "")
        .trim();
      cur = null;
      continue;
    }
    if (cur) {
      const item = line.match(/^-\s+\[(.+?)\]\((.+?)\)(?:\s+—\s+(.*))?$/);
      if (item) {
        cur.hits.push({
          title: item[1],
          url: item[2],
          note: (item[3] ?? "").trim(),
        });
        continue;
      }
      const plain = line.match(/^-\s+(.+)$/);
      if (plain) cur.hits.push({ title: plain[1], url: "", note: "" });
    }
  }
  return { channels, summary, next, health };
}

function stateOf(ch: ChannelResult): string {
  if (ch.mark === "💬") return "AI 摘要（非来源，可当线索）";
  if (ch.status === "ok") return `${ch.hits.length} 条`;
  if (ch.status === "zero") return "0 命中";
  if (ch.status === "skip") return `跳过${ch.note ? `（${ch.note}）` : ""}`;
  return `失败${ch.note ? `（${ch.note}）` : ""}`;
}

function renderSearch(
  parsed: Parsed,
  perChannel: number,
  title: string,
): string {
  const lines: string[] = [title];
  for (const ch of parsed.channels) {
    lines.push(`- ${ch.name}：${stateOf(ch)}`);
    if (ch.status !== "ok" && ch.status !== "zero") continue;
    for (const hit of ch.hits.slice(0, perChannel)) {
      lines.push(`  · ${hit.title}${hit.url ? ` — ${hit.url}` : ""}`);
    }
    if (ch.hits.length > perChannel) {
      lines.push(`  · …另有 ${ch.hits.length - perChannel} 条`);
    }
  }
  if (parsed.summary) lines.push("", `汇总：${parsed.summary}`);
  if (parsed.health) lines.push(`通道健康：${parsed.health}`);
  return lines.join("\n");
}

/**
 * 这次查询是谁发起的 —— 网关的历史列表靠它区分「哪个会话、哪个项目」。
 * 拿不到就退成 pi:unknown，不影响检索本身。
 */
function sourceTag(ctx: any): string {
  try {
    const sm = ctx?.sessionManager;
    const id: string = sm?.getSessionId?.() ?? "";
    const name: string = sm?.getSessionName?.() ?? "";
    const cwd: string = sm?.getCwd?.() ?? "";
    const base = cwd ? cwd.split("/").filter(Boolean).pop() ?? "" : "";
    const who = name || base;
    const bits = [who, id.slice(0, 8)].filter(Boolean);
    return "pi:" + (bits.join("@") || "unknown");
  } catch {
    return "pi:unknown";
  }
}

async function runFanout(
  query: string,
  profile: Profile,
  channels: string,
  source = "",
): Promise<{ md: string; secs: number; on: string; why: string; unclear?: boolean }> {
  const args = [FANOUT, query];
  if (profile === "deep") args.push("--deep");
  let why = "";
  let unclear = false;
  let on = channels || PROFILES[profile].on;
  if (!on && profile === "auto") {
    const picked = pickByIntent(query);
    on = picked.on;
    why = picked.why;
    unclear = picked.unclear === true;
  }
  if (on) args.push("--on", on);

  const t0 = Date.now();
  const env: NodeJS.ProcessEnv = { ...process.env };
  if (source) env.D_REACH_SOURCE = source;
  // 插件这边的 t0 比 fanout.sh 自己算的准（含进程启动），history 里的耗时以它为准
  env.D_REACH_T0 = String(Math.floor(t0 / 1000));
  const { stdout } = await run("bash", args, {
    timeout: 200_000,
    maxBuffer: 8 << 20,
    env,
  });
  return { md: stdout, secs: (Date.now() - t0) / 1000, on, why, unclear };
}

async function persist(md: string, tag: string): Promise<string> {
  await mkdir(DATA_DIR, { recursive: true });
  await writeFile(LAST_RUN, `<!-- ${tag} -->\n${md}`, "utf8");
  return LAST_RUN;
}

// ---------------------------------------------------------------- 抓 URL

/** 走 load_key.sh 拿 key，与整个技能同一条查找链 */
async function loadKey(name: string): Promise<string | null> {
  try {
    const { stdout } = await run("sh", [KEY_SH, name, ""], { timeout: 8000 });
    return stdout.trim() || null;
  } catch {
    return null;
  }
}

/**
 * 去掉内联 base64 图片与 markdown 图片语法。
 * BrightData 转 markdown 时会把 `![](data:image/gif;base64,...)` 原样带回来，
 * 一个占位图就能撑出上万字符，把「这个页其实只有骨架」掩盖成「内容很长」。
 */
function stripInlineMedia(text: string): string {
  return text
    .replace(/!\[[^\]]*\]\(data:[^)]*\)/gi, "")
    .replace(/data:image\/[a-z+]+;base64,[A-Za-z0-9+/=]+/gi, "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "");
}

/**
 * HTML → 文本。
 *
 * 容器选择是借鉴 trafilatura 的第一步（先挑正文区，再抽文本）：
 *   1. <main> / <article>（语义标签）
 *   2. id/class 带 content|article|post|entry|detail 的 div，用开合配平切出来
 *   3. 都没有就整页
 * 第 2 步必须带守卫：命中的可能是 `class="content-sidebar"`，
 * 所以要求切出来 > 800 字且至少 2 个 <p>，否则退回整页。
 *
 * 不这么做的时候，老式中文站（div 导航 40 条 + 友情链接 30 条）
 * 会把正文埋在导航后面，实测前 1200 字全是「政务公开栏目N」。
 */
function htmlToText(html: string): string {
  let source = html.match(/<(main|article)\b[\s\S]*?<\/\1>/i)?.[0] ?? "";
  if (!source) {
    // 候选容器可能不止一个（正文区 + 侧栏 content-sidebar），挑 <p> 最多的那个：
    // 正文段落多，侧栏/导航通常只有链接。单个候选就只校验下限。
    const re =
      /<div[^>]+(?:id|class)\s*=\s*["'][^"']*\b(?:content|article|post|entry|detail|main)\b[^"']*["']/gi;
    let best = "";
    let bestP = 1; // 至少要 2 个 <p>
    for (const m of html.matchAll(re)) {
      const sliced = sliceBalancedDiv(html, m.index ?? 0);
      if (sliced.length < 300) continue;
      const p = sliced.match(/<p\b/gi)?.length ?? 0;
      if (p > bestP) {
        best = sliced;
        bestP = p;
      }
    }
    if (best) source = best;
  }
  const clean = (src: string): string =>
    src
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
      // 语义标签里的导航/页脚/表单一定不是正文（<header> 留着：它常包标题）
      .replace(/<(nav|aside|footer|form)\b[\s\S]*?<\/\1>/gi, " ")
      .replace(/<\/(p|div|li|tr|h[1-6]|br|td|th)>/gi, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/[ \t]+/g, " ")
      // 上一行把只含空格的行变成了 " "，必须先把行内首尾空格去掉，
      // 否则 "\n \n \n" 不会命中下面的 \n{3,}，导航多的页会吐出一堆空行白烧 token。
      .replace(/ *\n */g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

  const main = clean(source || html);
  if (main.length >= 200) return main;
  // 有些站把正文整段塞进 <noscript>（给爬虫看的那种）。上面为了避开
  // 「请开启 JavaScript」这类提示已经把它剔掉，主文本太短时再单独捞一次兜底。
  const ns = [...html.matchAll(/<noscript\b[^>]*>([\s\S]*?)<\/noscript>/gi)]
    .map((m) => m[1])
    .join("\n");
  if (!ns) return main;
  const fromNs = clean(ns);
  return fromNs.length > main.length ? fromNs : main;
}

function looksLikeShell(html: string): boolean {
  // 只认「真·挑战页」的标记。不能把 `enable javascript` 算进来：
  // 大量正常站点在 <noscript> 里写这句话，拿来当判据会把 2 万字的正常文章判成反爬。
  // JS 空壳交给字符数/骨架判据去管。
  const s = html.slice(0, 6000).toLowerCase();
  return /cf-challenge|cf_chl_opt|challenge-platform|just a moment|checking your browser|attention required|verify you are (a )?human/.test(
    s,
  );
}

interface Fetched {
  via: string;
  text: string;
  chars: number;
}

// ---------------------------------------------------------------- 抓取判定
//
// 三件事：
//   1. SITE_MARKERS —— 站点「内容真的在」时必然出现的 DOM 特征。
//      比「字符数够不够」可靠：验证码页、风控页往往又长又完整。
//   2. ERROR_PAGE —— 假成功的主要来源：404 / 已删除 / 封禁页，字符数并不少。
//   3. FailClass —— 失败分诊。撞验证码/登录墙时重试只会加重风控，
//      这类必须转人工，而不是无脑换下一档。

/** 失败分类。ratelimit 单独一类：不是站点挡我们，是对方嫌我们太快，重试只会更糟。 */
type FailClass =
  | "network"
  | "antibot"
  | "paywall"
  | "login"
  | "parse"
  | "empty"
  | "nocred"
  | "ratelimit";

const FAIL_LABEL: Record<FailClass, string> = {
  network: "网络不通",
  antibot: "反爬/验证码",
  paywall: "付费墙",
  login: "登录墙",
  parse: "解析不出正文",
  empty: "空内容/不存在",
  nocred: "缺凭据",
  ratelimit: "限流/429",
};

/** 这几类重试无益，必须人或浏览器会话介入。 */
const NEEDS_HUMAN: FailClass[] = ["antibot", "login", "nocred"];

class StageFail extends Error {
  constructor(
    readonly cls: FailClass,
    readonly detail: string,
    /**
     * fatal：这个输入本来就不是「网页正文」，所有降级档都没意义，必须立刻停。
     * 目前用于「二进制直链」：2026-10-29 实测，一个 PNG 走完全部 8 档花了 22.8s，
     * 最后 BrightData 把 PNG 字节当 markdown 返回，反而「成功」了 —— 比失败更糟。
     */
    readonly fatal?: "binary",
  ) {
    super(detail);
  }
}

/**
 * 站点内容标记。
 *
 * strict=true 的是实测过的：微信永久链 /s/* 直连必现 `id="js_content"`（2026-10-29 实测
 * 两条链接均命中，9853 字正文），而验证码页必缺 —— 缺失即可判反爬。
 * 其余标记未逐一实测，只作诊断提示、不单独否决，避免误杀正常抓取。
 */
const SITE_MARKERS: Array<{
  site: RegExp;
  name: string;
  marker: string;
  strict: boolean;
  /** 正文里必须出现的东西（远程通道只给 markdown，拿不到 DOM，只能看文本） */
  textMarker?: RegExp;
}> = [
  {
    // 电商列表页/详情页：有商品就一定有价格符号。只剩导航 + 「加载中...」时没有。
    // 远程通道（Jina/TinyFish）拿到的也是这堆导航，字符数够、行长也够，只能靠价格判。
    site: /(^|\.)(taobao|tmall|1688)\.com/,
    name: "淘宝",
    marker: "¥",
    strict: false,
    textMarker: /[¥￥]\s*\d/,
  },
  {
    site: /(^|\.)jd\.com/,
    name: "京东",
    marker: "¥",
    strict: false,
    textMarker: /[¥￥]\s*\d/,
  },
  {
    site: /mp\.weixin\.qq\.com/,
    name: "微信",
    marker: 'id="js_content"',
    strict: true,
  },
  { site: /zhihu\.com/, name: "知乎", marker: "RichText", strict: false },
  {
    site: /bilibili\.com/,
    name: "B站",
    marker: "read-article-holder",
    strict: false,
  },
  {
    site: /xiaohongshu\.com/,
    name: "小红书",
    marker: "note-content",
    strict: false,
  },
  { site: /juejin\.cn/, name: "掘金", marker: "article-root", strict: false },
  { site: /csdn\.net/, name: "CSDN", marker: "content_views", strict: false },
  {
    site: /(feishu\.cn|larksuite\.com)/,
    name: "飞书",
    marker: "docx",
    strict: false,
  },
  {
    site: /weibo\.(com|cn)/,
    name: "微博",
    marker: "feed_list_content",
    strict: false,
  },
  { site: /github\.com/, name: "GitHub", marker: "<main", strict: false },
];

/** 错误页模式。只在正文「短」的时候判，避免长文里偶然出现关键词被误杀。 */
const ERROR_PAGE: Array<{ re: RegExp; cls: FailClass; label: string }> = [
  {
    re: /(404|页面不存在|页面没有找到|找不到该页面|页面走丢了)/i,
    cls: "empty",
    label: "404/页面不存在",
  },
  {
    re: /(内容不存在|内容已被删除|已被发布者删除|该文章已被删除|此内容因违规无法查看|内容已失效)/,
    cls: "empty",
    label: "内容已删除",
  },
  {
    re: /(帐号已被封禁|账号已被封禁|該公眾號已遷移|该公众号已迁移)/,
    cls: "empty",
    label: "账号被封禁/迁移",
  },
  {
    re: /(请先登录|登录后查看|登录后阅读|sign in to continue|log ?in required)/i,
    cls: "login",
    label: "登录墙",
  },
  // 京东/淘宝把「未登录」做成登录表单页，措辞和英文站完全不同，且字数不少，不补就会假成功
  {
    re: /(个人用户登录|企业用户登录|手机扫码安全登录|短信登录|密码登录)/,
    cls: "login",
    label: "登录墙（电商登录表单）",
  },
  {
    re: /(登录探索更多内容|登录后参与|登录查看更多)/,
    cls: "login",
    label: "登录墙（内容站）",
  },
  // 知乎的风控不是页面而是 JSON：{"error":{"message":"您当前请求存在异常…","code":40362}}
  {
    re: /(当前请求存在异常|没有知识存在的荒原|unusual traffic|access denied)/i,
    cls: "antibot",
    label: "风控拦截",
  },
  {
    re: /(付费阅读|订阅后查看|会员专享|仅限会员|subscribe to (read|continue))/i,
    cls: "paywall",
    label: "付费墙",
  },
];

/**
 * 抓取器自己承认「没加载完 / 是缓存快照」。
 * Jina 在 JS 空壳页上就是这样：返回 500 多字的标题+导航+一句 "maybe not yet fully loaded"，
 * 正文一条都没有，却因为字数够而判成成功。限定短正文才判，避免长文里偶然提一句被误杀。
 */
const STUB_WARNING =
  /(maybe not yet fully loaded|cached snapshot|enable javascript|请开启 ?javascript|requires? javascript)/i;

function siteOf(url: string) {
  return SITE_MARKERS.find((s) => s.site.test(url));
}

/**
 * 渲染页的形态指标，用来识别「页面结构在、内容没在」的骨架页。
 *
 * 2026-10-29 实测（本机 chromium）：
 *   贴吧列表骨架   chars=3972 avgLine=8.9  linkDen=1.00
 *   淘宝搜索骨架   chars= 139 avgLine=2.9  linkDen=1.05
 *   36kr 首页      chars=5097 avgLine=13.4 linkDen=0.61
 *   微信公众号     chars=2228 avgLine=52.5 linkDen=0.00
 *   CSDN 文章      chars= 226 avgLine=44.4 linkDen=0.00
 *   quotes/js      chars=1499 avgLine=41.7 linkDen=0.03
 * 正文页的平均行长是骨架页的 4–18 倍，所以 avgLine 是主判据、linkDen 做二次确认。
 * 但贴吧单次取样波动大（限流程度不同，avgLine 4.9–8.9、linkDen 0.64–1.00），
 * 所以 12 字以下不看链接密度硬判，12–18 才要求 linkDen 配合。
 */
export interface RenderMetrics {
  lines?: number;
  avgLine?: number;
  linkDen?: number;
  finalUrl?: string;
}

const SKELETON_MAX_CHARS = 5000;
const SKELETON_HARD_AVG_LINE = 12;
const SKELETON_MAX_AVG_LINE = 18;
const SKELETON_MIN_LINK_DEN = 0.5;
/** 纯文本通道没有 DOM 指标，阈值收紧到 12，并要求「几乎没有长行」。 */
const SKELETON_TEXT_AVG_LINE = 12;

/** 四判合一：错误页 → 站点标记 → 骨架页 → 字符数。不过关就抛带分类的 StageFail。 */
function judge(
  text: string,
  rawHtml: string,
  site: { name: string; marker: string; strict: boolean } | undefined,
  metrics?: RenderMetrics,
): void {
  const chars = text.length;

  assertNotErrorPage(text);
  // 原始 HTML 冒充正文：实测 TinyFish 对淘宝直接吐出 21 万字网页源码（连 `<meta charset>` 都在），
  // 长度足够、既不像登录墙也不像骨架，就这么判成成功了。
  if (/<meta[^>]+charset|<!doctype html|<html[\s>]|<body[\s>]/i.test(text)) {
    throw new StageFail(
      "parse",
      "拿到的是网页源码（原始 HTML），不是渲染后的正文",
    );
  }
  // Cloudflare 挑战页从 curl 到远程通道都能拿到「Just a moment...」，字符数还不少，
  // 不当场认出来就会被归成「内容为空」，让人误以为换个写法就能过。
  if (looksLikeShell(rawHtml)) {
    throw new StageFail(
      "antibot",
      "Cloudflare 挑战页 / JS 校验页（要浏览器跑完挑战，静态通道无解）",
    );
  }
  // 微信安全验证页：17KB 只有 JS，没有 #js_content。
  // 不单独认出来就会被当成普通「缺 marker」，八档全跑一遍（实测 37–43 秒），
  // 而它是 IP 级限流，换通道只会加重。加 Referer / Accept-Language 实测也无效。
  if (/secitptpage\/verify|环境异常.{0,20}完成验证/i.test(rawHtml)) {
    throw new StageFail(
      "ratelimit",
      "微信安全验证页（该文被风控，或同一出口 IP 请求过多；等 15–30 分钟再试，仍不行就在微信里打开一次）",
    );
  }
  if (site?.strict && !rawHtml.includes(site.marker)) {
    throw new StageFail(
      "antibot",
      `缺 ${site.name} 内容标记 \`${site.marker}\`（验证码/风控页）`,
    );
  }
  if (site?.textMarker && !site.textMarker.test(text)) {
    throw new StageFail(
      "antibot",
      `${site.name} 页面只有导航，没有实际内容（要登录，或要浏览器渲染完商品列表）`,
    );
  }

  // 「太短」要排在「骨架」前面：真骨架页面（贴吧 3972 字、淘宝 139 字）两者都命中时，
  // 宁说「内容不足」也不要说「反爬」，后者会让人去搞 cookie，而其实只是页面没东西。
  // 阈值别定太高：公告、卡片页、极简博客的正文本来就短，
  // 300 字符会把这些真内容全判成「空内容」。骨架页由下面的平均行长判据兜底。
  if (chars < 120) throw new StageFail("empty", `正文只有 ${chars} 字符`);

  // 骨架页：导航/列表在，正文不在。字符数能过 300 的坎，但全是短行。
  // 有 DOM 指标的（Playwright）用真实 avgLine + linkDen；
  // 纯文本通道（curl/远程）自己从换行算 avgLine，再用「长行数」防误杀：
  // 正文页几乎总有几句 30 字以上的整句，导航页一句也没有。
  if (chars < SKELETON_MAX_CHARS) {
    const body = text
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    const avgLine =
      metrics?.avgLine ??
      (body.length ? body.reduce((s, l) => s + l.length, 0) / body.length : 0);
    const longLines = body.filter((l) => l.length >= 30).length;
    const hasDom = metrics?.avgLine !== undefined;
    const isSkeleton = hasDom
      ? avgLine < SKELETON_HARD_AVG_LINE ||
        (avgLine < SKELETON_MAX_AVG_LINE &&
          (metrics?.linkDen ?? 0) > SKELETON_MIN_LINK_DEN)
      : avgLine < SKELETON_TEXT_AVG_LINE && longLines < 3;
    if (isSkeleton) {
      throw new StageFail(
        "antibot",
        `只拿到导航/列表骨架（平均每行 ${Math.round(avgLine * 10) / 10} 字、长度≥30 的行 ${longLines} 行，无正文段落）`,
      );
    }
  }
}

/**
 * 错误页/空壳页的文本判据，单独抽出来给结构化直链（JSON/XML/纯文本）复用：
 * 它们不该过「字符数够不够」这套网页判据，但也同样不该把 403 页当数据返回。
 */
function assertNotErrorPage(text: string): void {
  const chars = text.length;
  // 登录墙 / 风控提示一定在页面顶部，所以看开头；
  // 而 404 / 付费墙这类短页标记才看全文（否则长文里偶然提到就会被误杀）。
  // 贴吧就是前者：无登录时帖子列表被换成一句「登录探索更多内容」，页面依然 2 万字，
  // 只看「总字符数」的旧规则直接放过它。
  const head = chars > 3000 ? text.slice(0, 3000) : text;
  for (const p of ERROR_PAGE) {
    const scoped = p.cls === "login" || p.cls === "antibot";
    if (scoped ? p.re.test(head) : chars < 2500 && p.re.test(text)) {
      throw new StageFail(p.cls, `${p.label}（${chars} 字符）`);
    }
  }
  if (chars < 3000 && STUB_WARNING.test(text)) {
    throw new StageFail(
      "antibot",
      "抓取方自报「页面未加载完 / 是缓存快照」，拿到的是空壳",
    );
  }
}

/** 一组常见的 HTML 实体反转义。RSS description 里塞的是转义后的 HTML，不先反转义就剔不出正文。 */
function unescapeEntities(s: string): string {
  return s
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&#x([\da-f]+);/gi, (_, h) =>
      String.fromCodePoint(parseInt(h, 16)),
    )
    .replace(/&nbsp;/g, " ")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

/**
 * 结构化直链（JSON / XML / RSS / Atom / 纯文本）。
 * 它们根本不是网页：htmlToText 会把它们当标签剔个精光，`chars < 300` 又会把它们判成空壳。
 * 实测：一条 RSS 源和一个 JSON 接口在修前都是「八档全失败」，而它们真是一字不差的数据。
 */
function asStructured(body: string, ctype: string): Fetched | null {
  const t = body.trim();
  if (!t) return null;

  // JSONP：`cb({...});` 包了一层函数调用。真实接口很常见（尤其是给跨域用的），
  // 不剥壳就只能当网页处理，然后被标签清洗和字符数判据全部判死。
  const jsonp = /^[\w$.]+\s*\(\s*([\[{][\s\S]*[\]}])\s*\)\s*;?$/.exec(t);
  const jsonText = jsonp ? jsonp[1] : t;

  if (
    /application\/json|\+json|text\/javascript/.test(ctype) ||
    /^[[{]/.test(jsonText)
  ) {
    try {
      // 大 JSON 先卡一道：parse + 重排会把几十 MB 的响应直接撈进内存
      if (jsonText.length <= 4_000_000) {
        const pretty = JSON.stringify(JSON.parse(jsonText), null, 2);
        const capped =
          pretty.length > 400_000
            ? `${pretty.slice(0, 400_000)}\n\n…（JSON 太长，已截到 40 万字符）`
            : pretty;
        return {
          via: jsonp ? "JSONP 直链" : "JSON 直链",
          text: capped,
          chars: capped.length,
        };
      }
    } catch {
      /* 不是合法 JSON：当普通文本走 */
    }
  }

  const isXml =
    /application\/(rss|atom|xml)|text\/xml/.test(ctype) ||
    /^<\?xml|<rss|<feed[\s>]|<urlset|<sitemapindex/i.test(t.slice(0, 500));
  if (isXml) {
    // RSS/Atom 里真正有用的是条目标题 + 摘要，直接剥标签会得到一堆 <channel> 残渣
    const entries = [...t.matchAll(/<(item|entry)\b[\s\S]*?<\/\1>/gi)].map(
      (m) => m[0],
    );
    // 顺序很关键：RSS 的 description 常是「转义过的 HTML」，先反转义才能把 <a> 当标签剔掉；
    // 而它又可能是双重转义，所以剔完再解一次。反过来（先剔标签后反转义）会把 <a href=…> 当正文交出去。
    const pick = (x: string, tag: string) =>
      unescapeEntities(
        unescapeEntities(
          (
            x.match(
              new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"),
            )?.[1] ?? ""
          ).replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1"),
        ).replace(/<[^>]+>/g, " "),
      )
        .replace(/\s+/g, " ")
        .trim();
    let text: string;
    let via: string;
    if (entries.length) {
      const lines = entries.map((e, i) => {
        const title = pick(e, "title") || pick(e, "name") || `条目 ${i + 1}`;
        const desc =
          pick(e, "description") || pick(e, "summary") || pick(e, "content");
        return `## ${title}${desc ? `\n${desc}` : ""}`;
      });
      const feedTitle = pick(t, "title");
      text = `${feedTitle ? `# ${feedTitle}\n\n` : ""}${lines.join("\n\n")}`;
      via = /<feed[\s>]/i.test(t)
        ? `Atom 源（${entries.length} 条）`
        : `RSS 源（${entries.length} 条）`;
    } else {
      text = t
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim();
      via = "XML";
    }
    return { via, text, chars: text.length };
  }

  // text/plain：正文就是全文，但得短得像个文件，不能是「403 Forbidden」那种网关页
  if (/^text\/plain/.test(ctype) && t.length > 20 && !/^[\d\s]*$/.test(t)) {
    return { via: "纯文本", text: t, chars: t.length };
  }
  return null;
}

const HTTP_MARK = "__DREACH_HTTP__";

/** 二进制响应头（PDF/图片/压缩包）。哪怕经过远程通道拿回来，也不能当正文。 */
const BINARY_CTYPE =
  /^(application\/(pdf|octet-stream|zip|x-zip-compressed|msword|vnd\.)|image\/|video\/|audio\/)/;

/** 正文里嵌了二进制魔数的痕迹（BrightData 转 markdown 会把图片字节原样塞进来）。 */
const BINARY_SNIFF = /(\uFFFDPNG|\uFFFD\uFFFD|^PNG\u001a|^%PDF-)/;

/**
 * 远程通道（TinyFish/Jina/BrightData/archive）的错误体不是「抓到了短正文」，
 * 而是「对方拒绝了」。不先认出来，它会被当成 300 字的空壳页，
 * 结果就是八档全试一遍（实测知乎 25.7s、贴吧 60.7s）后才给出毫无意义的失败。
 */
const UPSTREAM_REFUSAL: Array<{ re: RegExp; cls: FailClass; label: string }> = [
  {
    re: /bad_endpoint|robots\.txt|KYC form/i,
    cls: "antibot",
    label: "上游通道拒绝（robots/KYC 限制）",
  },
  {
    re: /(quota|rate.?limit|too many requests)/i,
    cls: "ratelimit",
    label: "上游额度用尽/限流",
  },
  // 只认认证类错误。不能把 forbidden/403 算进来：那是「目标站」挡上游通道，
  // 不是我们的 key 失效（实测 Jina 对贴吧返回 `Target URL returned error 403: Forbidden`，
  // 误判成 nocred 会归到「要你出手」，其实是这个站根本不给爬）。
  {
    re: /(unauthor|invalid (?:token|api key)|missing api key|authentication (?:required|failed))/i,
    cls: "nocred",
    label: "上游凭据失效",
  },
  {
    re: /(captcha|security verification|verification failed|安全验证|access denied|unusual traffic|forbidden|\b403\b)/i,
    cls: "antibot",
    label: "上游通道撞到验证码/封禁",
  },
];

/** 识别「通道自带的错误体」，命中就抛对应分类，不往下当正文处理。 */
function assertNotUpstreamError(text: string, stage: string): void {
  const trimmed = text.trim();
  // 错误体都不长；但 Jina 会在正文前附 Title/URL Source/Warning 头，所以上限放宽到 1200
  if (trimmed.length > 1200) return;
  for (const p of UPSTREAM_REFUSAL) {
    if (p.re.test(trimmed))
      throw new StageFail(
        p.cls,
        `${stage}：${p.label}（${trimmed.slice(0, 100).replace(/\s+/g, " ")}）`,
      );
  }
}

/**
 * 字符集解码。Node 默认把响应体当 UTF-8，但中文老站大量是 GB2312/GBK，
 * 直接 utf8 读会得到一整页乱码——而且乱码足够长，judge 会判「成功」，比失败更糟。
 * 2026-10-30 实测：`Content-Type: text/html`（不声明 charset）+ GB2312 正文，
 * curl 档直接丢掉，只能指望 Playwright 兜底（2.3s vs 0.3s，且渲染被墙时彻底丢失）。
 * 判定顺序：响应头 charset → meta charset（只扫前 4KB）→ 按 U+FFFD 比例在 UTF-8/GB18030 里择一。
 */
function decodeWith(buf: Buffer, label: string): string | null {
  try {
    return new TextDecoder(label, { fatal: false }).decode(buf);
  } catch {
    return null;
  }
}

function badCount(s: string): number {
  return (s.match(/\uFFFD/g) ?? []).length;
}

function decodeBody(buf: Buffer, ctype: string): string {
  // BOM 优先：UTF-16 的页面几乎都是 BOM 开头，而且它的 NUL 字节会让下面所有
  // 编码探测都失效（UTF-8 解码结果里每个字之间夹一个 \u0000）。
  if (buf.length >= 2 && buf[0] === 0xff && buf[1] === 0xfe)
    return buf.subarray(2).toString("utf16le");
  if (buf.length >= 2 && buf[0] === 0xfe && buf[1] === 0xff)
    return buf.subarray(2).swap16().toString("utf16le");
  const fromHeader =
    /charset\s*=\s*["']?([\w-]+)/i.exec(ctype)?.[1]?.toLowerCase() ?? "";
  // meta 用 latin1 读：字节等值，且不会因为多字节被截成半个字而报错
  const head = buf.subarray(0, 4096).toString("latin1");
  const fromMeta =
    /<meta[^>]+charset\s*=\s*["']?([\w-]+)/i.exec(head)?.[1]?.toLowerCase() ??
    "";
  const declared = fromHeader || fromMeta;
  const asUtf8 = buf.toString("utf8");

  if (!declared || /^utf-?8$/.test(declared)) {
    if (badCount(asUtf8) === 0) return asUtf8;
    // 声明 UTF-8（或干脆不声明）却解出一堆替换字符：基本就是 GBK 站错标/漏标
    const gb = decodeWith(buf, "gb18030");
    return gb && badCount(gb) < badCount(asUtf8) ? gb : asUtf8;
  }
  const alt = decodeWith(buf, declared);
  // 声明的字符集 Node 不认识（比如某些私有标签）→ 退回 UTF-8
  return alt ?? asUtf8;
}

async function viaCurl(url: string): Promise<Fetched | null> {
  // 正文用 -o 落盘、元信息走 -w：
  //   1) 二进制（PDF/图片）进 stdout 会被 UTF-8 解码毁掉，而且没法再当文件用；
  //   2) execFile 拿不到响应头，只能靠 -w，只看 stdout 长度会把 429（空 body）误判成「空内容」。
  // curl>=7.84 才有 %header{}，>=7.76 才有 %{content_type}。
  const tmp = join(tmpdir(), `dreach-curl-${process.pid}-${Date.now()}.body`);
  try {
    const { stdout } = await run(
      "curl",
      [
        "-sL",
        "--compressed",
        "--max-time",
        "15",
        "-o",
        tmp,
        "-A",
        UA,
        "-w",
        `\n${HTTP_MARK}%{http_code}\t%{content_type}\t%{url_effective}\t%header{retry-after}`,
        url,
      ],
      { maxBuffer: 1 << 20, timeout: 25_000 },
    );
    const cut = stdout.lastIndexOf(HTTP_MARK);
    const meta = cut < 0 ? "" : stdout.slice(cut + HTTP_MARK.length);
    const [codeRaw, ctypeRaw, effective, retryAfter] = meta.split("\t");
    const status = Number(codeRaw) || 0;
    const ctype = (ctypeRaw ?? "").toLowerCase();

    if (status === 429 || status === 503) {
      const wait = retryAfter?.trim();
      throw new StageFail(
        "ratelimit",
        `HTTP ${status}` +
          (wait ? `，对方要求等 ${wait}` : "，对方没给 Retry-After") +
          "（继续换通道或重试只会加重限流）",
      );
    }
    if (status === 404 || status === 410)
      throw new StageFail("empty", `HTTP ${status}，页面不存在`);
    if (status >= 400) throw new StageFail("network", `HTTP ${status}`);

    const size = (await stat(tmp).catch(() => null))?.size ?? 0;
    if (size === 0) throw new StageFail("empty", "响应为空");
    if (size > 60 << 20)
      throw new StageFail(
        "parse",
        `响应 ${Math.round(size / 1048576)}MB，太大不解析`,
      );

    // PDF：本机有 pymupdf，直接抽文字层。不做这一步就会得到上百万字符的乱码并被判成功。
    if (/application\/pdf/.test(ctype)) {
      const { stdout: pdfOut } = await run("python3", [PDF2TEXT, tmp], {
        maxBuffer: 32 << 20,
        timeout: 40_000,
      });
      let parsed: {
        ok?: boolean;
        text?: string;
        pages?: number;
        err?: string;
      } = {};
      try {
        parsed = JSON.parse(pdfOut.trim().split("\n").pop() ?? "{}");
      } catch {
        throw new StageFail(
          "parse",
          `PDF 解析输出异常：${pdfOut.slice(0, 80)}`,
        );
      }
      if (!parsed.ok)
        throw new StageFail("parse", `PDF 解析失败：${parsed.err ?? "未知"}`);
      const text = String(parsed.text ?? "").trim();
      if (text.length < 200) {
        // 扫描件没有文字层：换任何 HTTP 通道都是同一份字节，八档里剩下七档全是浪费
        throw new StageFail(
          "parse",
          `PDF 没有文字层（${parsed.pages ?? "?"} 页，扫描件需 OCR，不在本工具范围）`,
          "binary",
        );
      }
      return {
        via: `PDF 直解（${parsed.pages ?? "?"} 页）`,
        text,
        chars: text.length,
      };
    }
    if (BINARY_CTYPE.test(ctype)) {
      throw new StageFail(
        "parse",
        `这不是网页（${ctype}），要的是文件本身，当前工具只交付文本`,
        "binary",
      );
    }

    const body = decodeBody(await readFile(tmp), ctype);
    // 结构化直链：JSON / XML / RSS 是「正文」而不是网页，不能走 htmlToText + 网页判据
    // （它们天生很短，`chars < 300` 会把它们全判成空壳）。
    const structured = asStructured(body, ctype);
    if (structured) {
      assertNotErrorPage(structured.text);
      return structured;
    }
    // 极短响应是空壳而不是反爬，别混为一谈（否则会误报「需要人工」）
    if (body.length < 80) {
      const where =
        effective && effective !== url
          ? `，落到了 ${new URL(effective).host}`
          : "";
      throw new StageFail("empty", `响应只有 ${body.length} 字符${where}`);
    }
    if (looksLikeShell(body))
      throw new StageFail("antibot", "JS 校验页 / Cloudflare 挑战页");
    // 判 HTML 看 ctype，而不是看有没有 <html>：
    // 很多接口只返回 HTML 片段（无 doctype 无 <html>），按正文猜会把标签原样交付（实测 chunked 响应）。
    const isHtml =
      /text\/html|application\/xhtml/.test(ctype) ||
      /<html|<!doctype/i.test(body);
    const text = isHtml ? htmlToText(body) : body.trim();
    judge(text, body, siteOf(url));
    return { via: "curl 直连", text, chars: text.length };
  } finally {
    await unlink(tmp).catch(() => {});
  }
}

/**
 * 本地 Playwright 渲染（免费、真 JS）。
 *
 * 排在 curl 之后、任何远程/限额通道之前：curl 只能拿服务端渲染的 HTML，
 * 撞上 JS 壳或 SPA 就废了；而远程渲染要花钱或耗额度，本机 chromium 免费。
 * 2026-10-29 实测：冷启到出正文约 0.9–2s，example.com 917 字符。
 * 找不到 playwright 时返回 null（该档不适用），不算失败。
 */
async function viaPlaywright(url: string): Promise<Fetched | null> {
  const { stdout } = await run("node", [RENDER, url], {
    maxBuffer: 8 << 20,
    timeout: 40_000,
  });
  const line = stdout.trim().split("\n").pop() ?? "";
  let out: {
    ok: boolean;
    text?: string;
    html?: string;
    err?: string;
    ms?: number;
  } & RenderMetrics;
  try {
    out = JSON.parse(line);
  } catch {
    throw new StageFail("parse", `渲染器输出无法解析：${line.slice(0, 80)}`);
  }
  if (!out.ok) {
    const err = out.err ?? "";
    // 没装 playwright 属于「本机不具备这一档」，不是这个站抓不到
    if (/找不到 playwright|Cannot find package/.test(err)) return null;
    // PDF/图片直链：浏览器只会弹下载，后面七档同样白跑
    if (err.startsWith("NOT_A_PAGE"))
      throw new StageFail("parse", err.replace("NOT_A_PAGE: ", ""), "binary");
    if (
      /TOO_MANY_REDIRECTS|too many redirects|redirect count exceeded/i.test(err)
    )
      throw new StageFail("network", "重定向环（页面把自己重定向回自己）");
    if (/Timeout|timeout/i.test(err))
      throw new StageFail("network", `渲染超时：${err.slice(0, 80)}`);
    throw new StageFail("parse", `渲染失败：${err.slice(0, 80)}`);
  }
  // 渲染器会跟跳转走：被重定向到 passport./login. 这类域名就是明确的登录墙，
  // 比在正文里猜关键词可靠（京东的登录页正文里一个「请先登录」都没有）。
  if (out.finalUrl && out.finalUrl !== url) {
    try {
      const from = new URL(url);
      const to = new URL(out.finalUrl);
      if (
        from.host !== to.host &&
        /^(passport|login|signin|sso|account|accounts)\.|\/havanaone\//i.test(
          to.host + to.pathname,
        )
      ) {
        throw new StageFail("login", `被重定向到登录页 ${to.host}`);
      }
    } catch (e) {
      if (e instanceof StageFail) throw e;
    }
  }
  const text = (out.text ?? "").trim();
  judge(text, out.html ?? "", siteOf(url), out);
  return { via: "Playwright 本地渲染", text, chars: text.length };
}

async function viaTinyfish(url: string): Promise<Fetched | null> {
  const key = await loadKey("TINYFISH_API_KEY");
  if (!key) return null;
  const endpoint = "https://agent.tinyfish.ai/mcp";
  const call = async (payload: unknown, sid?: string) => {
    const hdr: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      "X-API-Key": key,
    };
    if (sid) hdr["Mcp-Session-Id"] = sid;
    const res = await fetch(endpoint, {
      method: "POST",
      headers: hdr,
      body: JSON.stringify(payload),
    });
    return {
      sid: res.headers.get("mcp-session-id") ?? undefined,
      body: await res.text(),
    };
  };
  const init = await call({
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "d-reach-plugin", version: "1" },
    },
  });
  const out = await call(
    {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: {
        name: "fetch_content",
        arguments: { urls: [url], format: "markdown" },
      },
    },
    init.sid,
  );
  const m = out.body.match(/\{[\s\S]*\}/);
  if (!m) return null;
  const parsed = JSON.parse(m[0]) as {
    result?: { content?: Array<{ text?: string }> };
  };
  let text = (parsed.result?.content ?? [])
    .map((c) => c.text ?? "")
    .join("\n")
    .trim();
  // TinyFish 的 fetch_content 实际会把结构化结果再序列化成一段 JSON 字符串塞进 text，
  // 并非纯 markdown。不拆开就会把 `{"results":[{"text":"..."}]}` 当成正文返回（实测贴吧）。
  if (text.startsWith("{")) {
    try {
      const inner = JSON.parse(text) as {
        results?: Array<{ text?: string; title?: string; final_url?: string }>;
        errors?: Array<{ url?: string; error?: string }>;
      };
      const first = inner.results?.[0];
      const errMsg = (inner.errors ?? []).map((e) => e.error ?? "").join(" ");
      if (errMsg && !first?.text)
        throw new StageFail(
          "antibot",
          `TinyFish 报告抓取失败：${errMsg.slice(0, 100)}`,
        );
      if (first?.text) text = first.text.trim();
    } catch (e) {
      if (e instanceof StageFail) throw e;
      /* 不是这个结构就原样往下走 */
    }
  }
  text = stripInlineMedia(text).trim();
  assertNotUpstreamError(text, "TinyFish");
  judge(text, out.body, siteOf(url));
  return { via: "TinyFish fetch", text, chars: text.length };
}

async function viaJina(url: string): Promise<Fetched | null> {
  const key = await loadKey("JINA_API_KEY");
  const hdr = ["-H", "X-Return-Format: markdown"];
  if (key) hdr.push("-H", `Authorization: Bearer ${key}`);
  const { stdout } = await run(
    "curl",
    [
      "-sL",
      "--compressed",
      "--max-time",
      "25",
      "-A",
      UA,
      ...hdr,
      `https://r.jina.ai/${url}`,
    ],
    { maxBuffer: 8 << 20, timeout: 30_000 },
  );
  const text = stripInlineMedia(stdout).trim();
  if (/^(Missing API key|Unauthorized|Authentication required)/i.test(text)) {
    throw new StageFail("nocred", "Jina 拒绝：缺 key 或 key 失效");
  }
  assertNotUpstreamError(text, "Jina Reader");
  judge(text, stdout, siteOf(url));
  return { via: "Jina Reader", text, chars: text.length };
}

async function viaBrightdata(url: string): Promise<Fetched | null> {
  const key = await loadKey("BRIGHTDATA_APITOKEN");
  if (!key) return null;
  const body = JSON.stringify({
    zone: process.env.BRIGHTDATA_ZONE || "mcp_unlocker",
    format: "raw",
    data_format: "markdown",
    url,
  });
  const { stdout } = await run(
    "curl",
    [
      "-sL",
      "--max-time",
      "30",
      "-X",
      "POST",
      "https://api.brightdata.com/request",
      "-H",
      `Authorization: Bearer ${key}`,
      "-H",
      "Content-Type: application/json",
      "-d",
      body,
    ],
    { maxBuffer: 8 << 20, timeout: 35_000 },
  );
  const raw = stdout.trim();
  // 错误体不一定以 { 开头：residential 模式的 bad_endpoint 是裸文本，
  // 而且它前面还可能有一行空行（实测 stdout 以 \n 开头）。
  if (!raw)
    throw new StageFail(
      "empty",
      "BrightData 返回空响应（可能是这条通道对这个站不可用）",
    );
  const text = stripInlineMedia(raw).trim();
  if (text.startsWith("{")) {
    // 官方错误体：kyc 未通过 / bad_endpoint / 额度用尽
    const cls: FailClass = /kyc|unauthor|token|quota|limit/i.test(text)
      ? "nocred"
      : "antibot";
    throw new StageFail(cls, `BrightData 拒绝：${text.slice(0, 80)}`);
  }
  assertNotUpstreamError(text, "BrightData");
  if (BINARY_SNIFF.test(text)) {
    throw new StageFail(
      "parse",
      "返回的是二进制文件内容，不是网页正文",
      "binary",
    );
  }
  judge(text, stdout, siteOf(url));
  return { via: "BrightData", text, chars: text.length };
}

// ---------------------------------------------------------------- 专用档

/**
 * 从某个 `<div` 起，按 div 开合配平取出完整子树。
 *
 * 不能用「切到下一个 `<script>`」：微信正文里本身带 script，实测这样会砍掉近半正文
 * （同一条链接：切 script 1231 字 vs 配平 1382 字）。也不能贪婪到最后那个 `</div><script`，
 * 那会把相关推荐、页尾全吃进来。
 */
function sliceBalancedDiv(html: string, from: number): string {
  const re = /<(\/?)div\b/gi;
  re.lastIndex = from;
  let depth = 0;
  for (let m = re.exec(html); m; m = re.exec(html)) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) {
      const gt = html.indexOf(">", m.index);
      return html.slice(from, gt < 0 ? html.length : gt + 1);
    }
    if (m.index - from > 400_000) break; // 防跑飞
  }
  return html.slice(from, from + 300_000);
}

/**
 * 微信永久链直连（第 0 档，仅 mp.weixin.qq.com/s/*）。
 *
 * 2026-10-29 实测：桌面 UA、无 cookie、不开浏览器，curl 直接拿回完整 HTML，
 * 正文是服务端渲染进 `#js_content` 的，不触发验证码。
 * 这档免费且不耗任何限额通道，所以排在 BrightData 前面。
 */
async function viaWeixinDirect(url: string): Promise<Fetched | null> {
  // 两种链都认：短链 `/s/<token>` 和长链 `/s?__biz=…&sn=…`（后者在历史文章、
  // 分享链接里更常见，只认 `/s/` 会让它们绕过专档、去走普通 curl
  if (!/mp\.weixin\.qq\.com\/s(\/|\?)/.test(url)) return null;
  // 正文落盘而不是进 stdout：
  // 微信的「总目录」类文章实测 8.8MB HTML（1152 条链接），而 execFile 的 maxBuffer
  // 上限是 8<<20，多一个字节就抛 `stdout maxBuffer length exceeded` —— 那是个普通 Error，
  // 会被归成「解析不出正文」，然后白降到 curl 档只拿到 1745 字（丢掉 1152 条链接）。
  const tmp = join(tmpdir(), `dreach-wx-${process.pid}-${Date.now()}.body`);
  try {
    const { stdout } = await run(
      "curl",
      [
        "-sL",
        "--compressed",
        "--max-time",
        "25",
        "-o",
        tmp,
        "-A",
        UA,
        "-w",
        `\n${HTTP_MARK}%{http_code}\t%{content_type}`,
        url,
      ],
      { maxBuffer: 1 << 20, timeout: 30_000 },
    );
    const meta = stdout
      .slice(stdout.lastIndexOf(HTTP_MARK) + HTTP_MARK.length)
      .split("\t");
    const status = Number(meta[0]) || 0;
    if (status === 429 || status === 503)
      throw new StageFail("ratelimit", `HTTP ${status}（微信风控限流）`);
    if (status >= 400) throw new StageFail("network", `HTTP ${status}`);

    const html = decodeBody(await readFile(tmp), meta[1] ?? "");
    // 验证页先认，否则会落到下面「缺 js_content」的 generic 反爬档，
    // 而这一档是唯一应该立刻停手、不再降级的
    if (/secitptpage\/verify/i.test(html)) {
      throw new StageFail(
        "ratelimit",
        "微信安全验证页（该文被风控，或同一出口 IP 请求过多；等 15–30 分钟再试）",
      );
    }
    const marker = html.indexOf('id="js_content"');
    if (marker < 0) {
      throw new StageFail(
        "antibot",
        "微信风控页：没有 #js_content（需要你在微信里打开一次过验证）",
      );
    }
    // 回到标签开头再切，否则会从属性中间开始，把 id/style 露进正文
    const open = html.lastIndexOf("<", marker);
    const body = htmlToText(sliceBalancedDiv(html, open < 0 ? marker : open));
    const title =
      html.match(/id="activity-name"[^>]*>([\s\S]*?)<\/h1>/)?.[1] ?? "";
    const text = `${title ? `${htmlToText(title)}\n\n` : ""}${body}`.trim();
    judge(text, html, siteOf(url));
    return { via: "微信直连", text, chars: text.length };
  } finally {
    await unlink(tmp).catch(() => {});
  }
}

/** 登录墙站点的 cookie 注入档。cookie 由 cookie-getter 推送、经 load_key.sh 取，永不打印。 */
const COOKIE_SLOTS: Array<{ site: RegExp; slot: string; name: string }> = [
  { site: /(feishu\.cn|larksuite\.com)/, slot: "FEISHU_COOKIE", name: "飞书" },
  { site: /xiaohongshu\.com/, slot: "XHS_COOKIE", name: "小红书" },
];

async function viaCookieInject(url: string): Promise<Fetched | null> {
  const hit = COOKIE_SLOTS.find((s) => s.site.test(url));
  if (!hit) return null;
  const cookie = await loadKey(hit.slot);
  if (!cookie) {
    throw new StageFail(
      "nocred",
      `没有 ${hit.slot} —— 用 cookie-getter 在 ${hit.name} 页面抓一次并推送`,
    );
  }
  const { stdout } = await run(
    "curl",
    [
      "-sL",
      "--compressed",
      "--max-time",
      "25",
      "-A",
      UA,
      "-H",
      `Cookie: ${cookie}`,
      url,
    ],
    { maxBuffer: 8 << 20, timeout: 30_000 },
  );
  const text = htmlToText(stdout);
  if (/(登录|sign ?in)/i.test(text.slice(0, 2000)) && text.length < 800) {
    throw new StageFail("login", `${hit.name} cookie 已过期或权限不足`);
  }
  judge(text, stdout, siteOf(url));
  return { via: `${hit.name} cookie 注入`, text, chars: text.length };
}

/** 最后一档：公开存档。不改请求头、不冒充爬虫，风险最低的兜底。 */
async function viaArchiveToday(url: string): Promise<Fetched | null> {
  const { stdout } = await run(
    "curl",
    [
      "-sL",
      "--compressed",
      "--max-time",
      "25",
      "-A",
      UA,
      `https://archive.ph/newest/${url}`,
    ],
    { maxBuffer: 8 << 20, timeout: 30_000 },
  );
  if (
    /We don't have that page archived|No results|Page cannot be crawled/i.test(
      stdout,
    )
  ) {
    throw new StageFail("empty", "archive.today 没有这份存档");
  }
  const text = htmlToText(stdout);
  assertNotUpstreamError(text, "archive.today");
  judge(text, stdout, siteOf(url));
  return { via: "archive.today", text, chars: text.length };
}

/**
 * 依次尝试，第一个达标就返回。每一档失败都带分类，全部失败时能说清「该不该重试」。
 * 返回 null 表示该档不适用（域名不匹配 / 没配 key），不计入失败。
 */
async function fetchUrl(url: string, maxChars: number) {
  const attempts: Array<[string, () => Promise<Fetched | null>]> = [
    ["微信直连", () => viaWeixinDirect(url)],
    ["cookie 注入", () => viaCookieInject(url)],
    ["curl 直连", () => viaCurl(url)],
    ["Playwright 渲染", () => viaPlaywright(url)],
    ["TinyFish fetch", () => viaTinyfish(url)],
    ["Jina Reader", () => viaJina(url)],
    ["BrightData", () => viaBrightdata(url)],
    ["archive.today", () => viaArchiveToday(url)],
  ];
  const skipped: Array<{ stage: string; cls: FailClass; detail: string }> = [];
  for (const [stage, fn] of attempts) {
    try {
      const got = await fn();
      if (!got) continue;
      const text =
        got.text.length > maxChars
          ? got.text.slice(0, maxChars) + "\n…（已截断）"
          : got.text;
      return { ok: true as const, got: { ...got, text }, skipped };
    } catch (e) {
      if (e instanceof StageFail) {
        skipped.push({ stage, cls: e.cls, detail: e.detail });
        // 429/503 是对「我们这个 IP + 此刻这个节奏」的信号。换通道、换域名格式都没用，
        // 唯一正确答案是停下等。实测继续把 TinyFish/Jina/BrightData/archive 走完要 50s+。
        if (e.cls === "ratelimit")
          return {
            ok: false as const,
            skipped,
            needHuman: [],
            ratelimited: e.detail,
            slow: undefined as boolean | undefined,
          };
        // 二进制直链：不是「这一档没成」，是这个 URL 根本不是网页，后面七档全是浪费
        if (e.fatal === "binary")
          return {
            ok: false as const,
            skipped,
            needHuman: [],
            ratelimited: undefined,
            fatal: e.detail,
            slow: undefined as boolean | undefined,
          };
        // 自己直连和本地浏览器都超时：站点就是慢，不是封我们。
        // 继续把 TinyFish/Jina/BrightData/archive 走完要再等 30s 并烧额度，实测救不回来。
        if (
          e.cls === "network" &&
          /超时|timed out/i.test(e.detail) &&
          skipped.filter(
            (s) => s.cls === "network" && /超时|timed out/i.test(s.detail),
          ).length >= 1
        )
          return {
            ok: false as const,
            skipped,
            needHuman: [],
            ratelimited: undefined,
            slow: true,
          };
      } else {
        // execFile 抛的错（curl 超时 / HTTP2 stream error / DNS）：归 network，不归 parse。
        // 实测 BrightData 对同一 URL 时成时败，失败时 curl 退出码 92（HTTP/2 stream error），
        // 说成「解析不出正文」会让人以为内容格式不对。
        const err = e as { code?: number | string; message?: string };
        const curlCode = typeof err.code === "number" ? err.code : 0;
        const isNet =
          [6, 7, 28, 35, 47, 52, 56, 92].includes(curlCode) ||
          /timed out|Could not resolve|Connection (refused|reset)|stream error|TOO_MANY_REDIRECTS|too many redirects|redirect count exceeded/i.test(
            err.message ?? "",
          );
        const loop =
          /TOO_MANY_REDIRECTS|too many redirects|redirect count exceeded/i.test(
            err.message ?? "",
          );
        const timedOut =
          curlCode === 28 || /timed out/i.test(err.message ?? "");
        skipped.push({
          stage,
          cls: isNet ? "network" : "parse",
          detail: (loop
            ? "重定向环（页面把自己重定向回自己）"
            : (err.message ?? "失败")
          )
            .slice(0, 100)
            .replace(/\s+/g, " "),
        });
        if (
          timedOut &&
          skipped.filter(
            (s) => s.cls === "network" && /超时|timed out/i.test(s.detail),
          ).length >= 2
        )
          return {
            ok: false as const,
            skipped,
            needHuman: [],
            ratelimited: undefined,
            slow: true,
          };
      }
    }
  }
  const needHuman = skipped.filter((s) => NEEDS_HUMAN.includes(s.cls));
  return {
    ok: false as const,
    skipped,
    needHuman,
    ratelimited: undefined as string | undefined,
    fatal: undefined as string | undefined,
    slow: undefined as boolean | undefined,
  };
}

// ---------------------------------------------------------------- 工具

const searchTool = defineTool({
  name: "d_reach",
  label: "d-reach 检索",
  description:
    "多通道并发检索。profile=auto（默认）按场景自动选 2-3 路，场景→通道对照表：" +
    "本地生活/旅行（酒店/门票/攻略/美食/地址）→ qianfan,tf；" +
    "对比选型（vs/对比/哪个好/值得）→ tf,exa,qianfan；" +
    "时效天气政策（最新/发布/价格/固件/年份）→ langsearch,tf,qianfan；" +
    "官方文档/API（api/sdk/文档/参数/用法）→ fcdev,qianfan,tf；" +
    "排障（报错/卡住/不生效/端口冲突）→ se,fcdev,qianfan；" +
    "学术（论文/arxiv/survey）→ oalex,crossref,fcres；" +
    "中文技术 → qianfan,se,jj；中文通用 → qianfan,tf；英文技术/硬件 → se,fcdev,hn；兜底 → tf,fcdev,qianfan。" +
    "规则覆盖不到时用 channels 显式指定（如 channels='hn,exa'）。" +
    "quick 固定 3 路；base 12 路；deep 16 路含限额通道。返回精简摘要，完整来源写到 details.file。",
  parameters: Type.Object({
    query: Type.String({ description: "检索词，中英文均可" }),
    profile: Type.Optional(
      Type.Union(
        [
          Type.Literal("auto"),
          Type.Literal("quick"),
          Type.Literal("base"),
          Type.Literal("deep"),
        ],
        {
          description:
            "auto=按场景选 2-3 路（默认）；quick=固定 3 路；base=12 路；deep=16 路",
        },
      ),
    ),
    channels: Type.Optional(
      Type.String({
        description: "显式指定通道，逗号分隔，如 hn,exa；覆盖 profile",
      }),
    ),
    detail: Type.Optional(
      Type.Union([Type.Literal("brief"), Type.Literal("full")], {
        description: "brief=每路 2-3 条（默认）；full=每路最多 8 条",
      }),
    ),
  }),

  async execute(_id, params, _signal, _onUpdate, ctx) {
    const query = params.query.trim();
    if (!query)
      return {
        content: [{ type: "text", text: "query 不能为空" }],
        isError: true,
      };
    const profile = (params.profile ?? "auto") as Profile;
    try {
      const { md, secs, on, why, unclear } = await runFanout(
        query,
        profile,
        params.channels ?? "",
        sourceTag(ctx),
      );
      const parsed = parseFanout(md);
      const file = await persist(md, query);
      const perChannel =
        params.detail === "full" ? 8 : profile === "quick" ? 3 : 2;
      // 规则没命中时必须明说自己没把握，并当场给出通道菜单 —— 让调用方
      // 一眼能看出「工具在猜」还是「按经验走」，不用再翻文档
      const MENU =
        "想自己指定就传 channels：qianfan 中文综述(非来源) / tf 全网 / " +
        "fcdev 官方文档 / se 报错 / hn 技术观点 / jj,segfault 中文技术(仅技术) / " +
        "oalex,crossref 学术元数据 / langsearch 时效 / exa 英文语义 / " +
        "fcres 论文全文 / serper Google(本地生活/电商) / fcs Firecrawl全文搜索 / wiki 维基百科 / bd Google(最贵最慢)";
      const head =
        `d-reach ${PROFILES[profile].label} · ${secs.toFixed(1)}s` +
        (why ? ` · ${why}` : on ? ` · ${on}` : "") +
        (unclear ? `\n> ${MENU}` : "");
      return {
        content: [
          {
            type: "text",
            text: `${renderSearch(parsed, perChannel, head)}\n\n完整结果：${file}`,
          },
        ],
        details: {
          query,
          profile,
          secs,
          file,
          summary: parsed.summary,
          channels: parsed.channels.map((c) => ({
            name: c.name,
            mark: c.mark,
            status: c.status,
            note: c.note,
            count: c.hits.length,
          })),
        },
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        content: [
          { type: "text", text: `d-reach 执行失败：${msg.slice(0, 300)}` },
        ],
        isError: true,
      };
    }
  },
});

const fetchTool = defineTool({
  name: "d_reach_fetch",
  label: "d-reach 抓网页",
  description:
    "抓一个 URL 的正文，八档降级：微信直连（免费）→ cookie 注入（登录站）→ curl 直连 → " +
    "Playwright 本地渲染（免费真 JS）→ TinyFish → Jina Reader → BrightData（消耗额度）→ archive.today 存档兜底。" +
    "返回 markdown/纯文本。除了网页，也直接支持：PDF（抽文字层，扫描件会明说需要 OCR）、" +
    "JSON 接口（格式化返回）、RSS/Atom 源（按条目展开标题+摘要）、纯文本。" +
    "自动处理 GBK/GB2312 等非 UTF-8 编码、iframe 内嵌正文、无 Content-Length 的流式响应。" +
    "失败会按网络/反爬/付费墙/登录墙/解析/限流分类，并说清是否该重试。",
  parameters: Type.Object({
    url: Type.String({ description: "要抓的完整 URL" }),
    max_chars: Type.Optional(
      Type.Number({ description: "正文最多返回多少字符，默认 12000" }),
    ),
  }),

  async execute(_id, params) {
    const url = params.url.trim();
    if (!/^https?:\/\//i.test(url)) {
      return {
        content: [
          { type: "text", text: "url 必须以 http:// 或 https:// 开头" },
        ],
        isError: true,
      };
    }
    const maxChars = Math.min(Math.max(params.max_chars ?? 12000, 500), 40000);
    const t0 = Date.now();
    const r = await fetchUrl(url, maxChars);
    const secs = ((Date.now() - t0) / 1000).toFixed(1);

    if (!r.ok) {
      const lines = r.skipped
        .map((s) => `- ${s.stage}：${FAIL_LABEL[s.cls]} — ${s.detail}`)
        .join("\n");
      const advice = r.ratelimited
        ? `\n\n**被限流，已停手**：${r.ratelimited}\n继续换通道或重试只会加重限流。等一会儿再试，或换一个出口 IP。`
        : r.fatal
          ? `\n\n**这个链接不是网页**：${r.fatal}。降级档对它没有意义，不再尝试。`
          : r.slow
            ? "\n\n**站点太慢**：自己直连和本地浏览器都超时，后面的限额通道也救不回来，已提前停手。稍后再试或换时段。"
            : r.needHuman.length
              ? `\n\n**要你出手**：${[...new Set(r.needHuman.map((s) => FAIL_LABEL[s.cls]))].join("、")} 挡着，` +
                "继续重试只会加重风控。请在浏览器里打开一次该链接（把验证码过掉 / 登录好），再把正文贴给我。"
              : "\n\n都是网络/解析类失败，可以稍后重试一次；仍不行就换通道或让用户贴正文。";
      return {
        content: [
          {
            type: "text",
            text: `${r.ratelimited ? "被限流" : r.fatal ? "不是网页正文" : r.slow ? "站点太慢" : "八档都没拿到正文"}（${secs}s）：\n${lines || "- 无适用档位"}${advice}`,
          },
        ],
        details: {
          url,
          failures: r.skipped,
          needsHuman: r.needHuman.length > 0,
          ratelimited: r.ratelimited ?? null,
          fatal: r.fatal ?? null,
          slow: r.slow ?? null,
        },
        isError: true,
      };
    }

    const skipped = r.skipped.length
      ? `\n先试过：${r.skipped.map((s) => `${s.stage}（${FAIL_LABEL[s.cls]}）`).join("；")}`
      : "";
    return {
      content: [
        {
          type: "text",
          text: `来源：${r.got.via} · ${r.got.chars} 字符 · ${secs}s${skipped}\n\n${r.got.text}`,
        },
      ],
      details: {
        url,
        via: r.got.via,
        chars: r.got.chars,
        secs: Number(secs),
        skipped: r.skipped,
      },
    };
  },
});

const quotaTool = defineTool({
  name: "d_reach_quota",
  label: "d-reach 额度",
  description:
    "看限额通道已用/上限、官方真实剩余（Firecrawl/TinyFish）、以及哪些通道因连败被自动跳过。" +
    "refresh=true 会去官方接口重新校准（约 1-2s）。",
  parameters: Type.Object({
    refresh: Type.Optional(
      Type.Boolean({ description: "是否重新校准官方额度" }),
    ),
  }),

  async execute(_id, params) {
    if (params.refresh) {
      try {
        await run("python3", [PROBE, "--max-age", "0"], { timeout: 30_000 });
      } catch {
        /* 校准失败不影响本地账本展示 */
      }
    }
    const readJson = async (p: string) => {
      try {
        return JSON.parse(await readFile(p, "utf8")) as Record<string, unknown>;
      } catch {
        return {};
      }
    };
    const quota = await readJson(join(DATA_DIR, "quota.json"));
    const health = await readJson(join(DATA_DIR, "channels.json"));
    const official = (quota._official ?? {}) as Record<
      string,
      {
        state?: string;
        remaining?: number;
        total?: number;
        balance?: string;
        currency?: string;
        probed_at?: string;
      }
    >;

    const bad = Object.entries(health)
      .filter(
        ([, v]) => ((v as { streak_fail?: number }).streak_fail ?? 0) >= 3,
      )
      .map(([k]) => k);

    const lines: string[] = [
      "通道健康：",
      bad.length
        ? `  连败 ≥3（下轮自动跳过）：${bad.join(", ")}`
        : "  全部正常",
    ];
    lines.push("", "限额通道：");
    for (const [svc, v] of Object.entries(quota)) {
      if (svc.startsWith("_") || typeof v !== "object" || v === null) continue;
      const used = (v as { monthly?: number }).monthly ?? 0;
      const off = official[svc];
      const tail =
        off?.state === "ok" && svc === "firecrawl"
          ? ` | 官方剩余 ${off.remaining}/${off.total}`
          : off?.state === "ok" && svc === "tinyfish"
            ? ` | 钱包 ${off.balance} ${off.currency}`
            : off?.state === "unavailable" || off?.state === "no_permission"
              ? " | 官方查不到"
              : "";
      lines.push(`  ${svc}: 本月已用 ${used}${tail}`);
    }
    const stamp = Object.values(official)[0]?.probed_at;
    if (stamp)
      lines.push("", `官方数据时间：${stamp.slice(0, 16).replace("T", " ")}`);
    return {
      content: [{ type: "text", text: lines.join("\n") }],
      details: { quota, health },
    };
  },
});

export default function dReachExtension(pi: ExtensionAPI) {
  pi.registerTool(searchTool);
  pi.registerTool(fetchTool);
  pi.registerTool(quotaTool);
  pi.registerTool(socialTool);

  const runCommand = async (args: string, ctx: any, profile: Profile) => {
    const query = args.trim();
    if (!query) return ctx.ui.notify("用法：/reach <检索词>", "warning");
    ctx.ui.notify(`d-reach ${profile} 检索中：${query}`, "info");
    try {
      const { md, secs } = await runFanout(query, profile, "", sourceTag(ctx));
      const parsed = parseFanout(md);
      await persist(md, query);
      ctx.ui.notify(
        `完成 ${secs.toFixed(1)}s · ${parsed.summary || "见 last-run.md"}`,
        "info",
      );
    } catch (err) {
      ctx.ui.notify(
        `失败：${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    }
  };

  pi.registerCommand("reach", {
    description: "d-reach 检索（auto 按意图选路）",
    handler: (args, ctx) => runCommand(args, ctx, "auto"),
  });
  pi.registerCommand("reach-deep", {
    description: "d-reach 检索（deep 13 路含限额通道）",
    handler: (args, ctx) => runCommand(args, ctx, "deep"),
  });
}

// ---------------------------------------------------------------- 社交平台

/**
 * 登录态是这类通道的命门：cookie 过期后 CLI 会回 not_authenticated，
 * 但原始报错对模型毫无指导意义。所以这里先 whoami 探活，再决定能不能搜，
 * 失败时直接给「去哪刷新」而不是把 CLI 错误原样抛回去。
 */
/** 三家 CLI 的登录态判定各写各的：老 bili 用 ok:true，bilibili 用 logged_in，
 *  xhs-cli 未登录时直接 exit 1 + 文案。统一按输出内容判，不按退出码。 */
function judgeAuth(out: string): "ok" | "expired" | null {
  if (/not_authenticated|Not logged in|"logged_in"\s*:\s*false/i.test(out))
    return "expired";
  if (/"logged_in"\s*:\s*true/i.test(out)) return "ok";
  if (/ok:\s*true/.test(out) && !/logged_in/.test(out)) return "ok";
  return null;
}

const SOCIAL = {
  bili: {
    bin: "bilibili",
    whoami: ["bilibili", "auth", "status", "--json"],
    search: (q: string, n: number) => [
      "bilibili",
      "video",
      "search",
      "--keyword",
      q,
      "--num",
      String(n),
      "--json",
    ],
    authFile: join(homedir(), ".config", "bilibili-skill"),
    hint: "bilibili auth login start（扫码）",
  },
  xhs: {
    // 用回 xiaohongshu-cli（纯 HTTP + cookie）：xhs-cli 逆向版连 search 都要
    // 下载 200MB 的 camoufox，反而不如旧包轻
    bin: "xhs",
    whoami: ["xhs", "whoami"],
    search: (q: string, _n: number) => ["xhs", "search", q, "--json"],
    authFile: join(homedir(), ".xiaohongshu-cli", "cookies.json"),
    hint: "浏览器取 a1 + web_session 写进 ~/.xiaohongshu-cli/cookies.json",
  },
} as const;

type SocialPlatform = keyof typeof SOCIAL;

async function probeSocial(p: SocialPlatform) {
  const meta = SOCIAL[p];
  let installed = true;
  try {
    await run(meta.bin, ["--version"], { timeout: 6000 });
  } catch {
    installed = false;
  }
  if (!installed)
    return {
      platform: p,
      state: "missing" as const,
      detail: `${meta.bin} 未安装`,
    };

  let authFileAge: string | null = null;
  try {
    const { stdout } = await run("stat", ["-c", "%y", meta.authFile], {
      timeout: 5000,
    });
    authFileAge = stdout.trim().slice(0, 10);
  } catch {
    /* 文件不存在也算信息 */
  }

  let out = "";
  try {
    const r = await run(meta.whoami[0], meta.whoami.slice(1), {
      timeout: 25_000,
    });
    out = r.stdout + r.stderr;
  } catch (e) {
    // 未登录时通常非 0 退出码，真因在 stdout/stderr 里，别把 "Command failed" 当结论
    out =
      String((e as { stdout?: string; stderr?: string })?.stdout ?? "") +
      String((e as { stderr?: string })?.stderr ?? "");
  }
  const verdict = judgeAuth(out);
  if (verdict) {
    return {
      platform: p,
      state: verdict === "ok" ? ("ok" as const) : ("expired" as const),
      authFileAge,
      detail: verdict === "ok" ? "登录态有效" : "登录态失效",
    };
  }
  return {
    platform: p,
    state: "error" as const,
    authFileAge,
    detail: `探活无结论：${out.trim().slice(0, 80) || "无输出"}`,
  };
}

const socialTool = defineTool({
  name: "d_reach_social",
  label: "d-reach 社交平台",
  description:
    "B站 / 小红书 的登录态体检与内容搜索（B站用 bilibili 2.x，小红书用 xhs-cli 逆向 API 版）。不传 platform 只看状态；" +
    "传 platform + query 才真的搜。登录态失效时会直接告诉你该跑哪条命令，不会把 CLI 原始报错丢回来。" +
    "Twitter/X 目前本机没装 CLI，返回缺失。",
  parameters: Type.Object({
    platform: Type.Optional(
      Type.Union([Type.Literal("bili"), Type.Literal("xhs")], {
        description: "不传 = 只体检",
      }),
    ),
    query: Type.Optional(
      Type.String({ description: "搜索关键词；传了才会搜" }),
    ),
    limit: Type.Optional(
      Type.Number({ description: "返回条数，默认 8，最多 20" }),
    ),
  }),

  async execute(_id, params) {
    const platforms = params.platform
      ? [params.platform]
      : (Object.keys(SOCIAL) as SocialPlatform[]);
    const probes = await Promise.all(platforms.map(probeSocial));

    const lines: string[] = [];
    for (const pr of probes) {
      const meta = SOCIAL[pr.platform];
      const tail = pr.authFileAge ? ` · 凭据文件 ${pr.authFileAge}` : "";
      lines.push(`- ${pr.platform}: ${pr.detail}${tail}`);
      if (
        pr.state === "expired" ||
        pr.state === "missing" ||
        pr.state === "error"
      ) {
        lines.push(`  修复：${meta.hint}`);
      }
    }

    if (!params.query) {
      const usable = probes
        .filter((p) => p.state === "ok")
        .map((p) => p.platform);
      lines.push(
        "",
        usable.length
          ? `可直接搜：${usable.join(", ")}`
          : "当前没有可用的社交通道",
      );
      return {
        content: [{ type: "text", text: lines.join("\n") }],
        details: { probes },
      };
    }

    // 搜索不强制登录态：B 站公开内容免登录，小红书未登录会让 CLI 自己报错，
    // 由下面 catch 翻译。登录态只影响「能不能拿到个人数据/字幕」。
    const target = probes.find((p) => p.platform === params.platform);
    if (!target) {
      return {
        content: [
          {
            type: "text",
            text: `${lines.join("\n")}\n\n登录态不可用，换个通道或先修登录态再搜。`,
          },
        ],
        isError: true,
      };
    }

    const n = Math.min(Math.max(params.limit ?? 8, 1), 20);
    const meta = SOCIAL[target.platform];
    try {
      const { stdout } = await run(
        meta.bin,
        meta.search(params.query, n).slice(1),
        {
          timeout: 40_000,
          maxBuffer: 4 << 20,
        },
      );
      let rendered = stdout.trim();
      try {
        const parsed = JSON.parse(rendered) as { data?: unknown };
        rendered =
          "```json\n" +
          JSON.stringify(parsed.data ?? parsed, null, 2).slice(0, 6000) +
          "\n```";
      } catch {
        /* 非 JSON 就原样给 */
      }
      return {
        content: [
          {
            type: "text",
            text: `[${target.platform}] 搜索「${params.query}」\n\n${rendered}`,
          },
        ],
        details: { platform: target.platform, query: params.query, limit: n },
      };
    } catch (e) {
      return {
        content: [
          {
            type: "text",
            text:
              `[${target.platform}] 搜索失败：${e instanceof Error ? e.message.slice(0, 200) : "未知"}。` +
              `\n如果是风控/限流，隔几分钟再试；登录态问题是另一类，先跑 d_reach_social 体检。`,
          },
        ],
        isError: true,
      };
    }
  },
});
