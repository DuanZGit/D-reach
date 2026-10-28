/**
 * d-reach 插件版（与 skill 并行，不替代）
 *
 * 定位：skill 里那些「要读 SKILL.md 才知道怎么拼」的操作，在这里变成一次工具调用。
 *
 *   d_reach         并发检索（auto 按意图选路 / quick / base / deep）
 *   d_reach_fetch   抓一个 URL，自动在 curl → TinyFish → Jina → BrightData 之间降级
 *   d_reach_quota   额度与通道健康（可选顺带跑一次官方校准）
 *
 *   /reach、/reach-deep   交互式跑一轮，结果只弹通知
 *
 * 所有检索/记账逻辑仍在 skill 的 scripts/ 里，插件不复制一份。
 */

import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

const run = promisify(execFile);
const SKILL_DIR = join(homedir(), ".agents/skills/d-reach");
const FANOUT = join(SKILL_DIR, "scripts", "fanout.sh");
const KEY_SH = join(SKILL_DIR, "scripts", "load_key.sh");
const PROBE = join(SKILL_DIR, "scripts", "quota_probe.py");
const DATA_DIR = join(homedir(), ".agent-reach");
const LAST_RUN = join(DATA_DIR, "last-run.md");
const UA =
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36";

// ---------------------------------------------------------------- 检索

const PROFILES = {
	auto: { label: "auto · 按意图选 3 路", on: "" },
	quick: { label: "quick · 3 路固定", on: "qianfan,fcdev,tf" },
	base: { label: "base · 9 路", on: "" },
	deep: { label: "deep · 13 路", on: "" },
} as const;

type Profile = keyof typeof PROFILES;

/** 按 query 特征选通道。命中不准时用 channels 参数覆盖。 */
function pickByIntent(query: string): { on: string; why: string } {
	const zh = /[\u4e00-\u9fff]/.test(query);
	const paper = /(paper|arxiv|论文|文献|survey|benchmark|sota|研究综述)/i.test(query);
	const news = /(最新|今天|昨天|本周|发布|上线|价格|股价|行情|release|changelog|202[5-9])/i.test(query);
	const code = /(error|exception|traceback|stack ?trace|compile|build|报错|编译|部署|配置|安装|依赖|函数)/i.test(query);
	const tech = /\b(mtu|wireguard|docker|k8s|kubernetes|python|java|rust|golang|node|api|sdk|http|tcp|udp|sql|git|nginx|redis|kafka|postgres|mysql|linux|bug|fix)\b/i.test(query);

	if (paper) return { on: "oalex,crossref,fcres", why: "学术：OpenAlex + Crossref + Research Index" };
	if (news) return { on: "langsearch,tf,qianfan", why: "时效：LangSearch + TinyFish + 千帆" };
	if (zh && (code || tech)) return { on: "qianfan,se,jj", why: "中文技术：千帆 + StackExchange + 掘金" };
	if (zh) return { on: "qianfan,jj,segfault", why: "中文通用：千帆 + 掘金 + SegmentFault" };
	if (code || tech) return { on: "se,fcdev,tf", why: "英文技术：StackExchange + Firecrawl Dev + TinyFish" };
	return { on: "tf,fcdev,qianfan", why: "通用兜底：TinyFish + Firecrawl Dev + 千帆" };
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
			cur = { name: rest.trim(), mark, status: MARK_STATUS[mark] ?? "zero", note, hits: [] };
			channels.push(cur);
			continue;
		}
		if (line.startsWith("**汇总**")) {
			summary = line.replace(/^\*\*汇总\*\*：/, "").replace(/\*\*/g, "").trim();
			cur = null;
			continue;
		}
		if (line.startsWith("**通道健康**")) {
			health = line.replace(/^\*\*通道健康\*\*：/, "").replace(/\*\*/g, "").trim();
			continue;
		}
		if (line.startsWith("**下一步**")) {
			next = line.replace(/^\*\*下一步\*\*：/, "").replace(/\*\*/g, "").trim();
			cur = null;
			continue;
		}
		if (cur) {
			const item = line.match(/^-\s+\[(.+?)\]\((.+?)\)(?:\s+—\s+(.*))?$/);
			if (item) {
				cur.hits.push({ title: item[1], url: item[2], note: (item[3] ?? "").trim() });
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

function renderSearch(parsed: Parsed, perChannel: number, title: string): string {
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

async function runFanout(
	query: string,
	profile: Profile,
	channels: string,
): Promise<{ md: string; secs: number; on: string; why: string }> {
	const args = [FANOUT, query];
	if (profile === "deep") args.push("--deep");
	let why = "";
	let on = channels || PROFILES[profile].on;
	if (!on && profile === "auto") {
		const picked = pickByIntent(query);
		on = picked.on;
		why = picked.why;
	}
	if (on) args.push("--on", on);

	const t0 = Date.now();
	const { stdout } = await run("bash", args, { timeout: 200_000, maxBuffer: 8 << 20 });
	return { md: stdout, secs: (Date.now() - t0) / 1000, on, why };
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

/** 粗转文本：优先只取 <main>/<article>，去掉脚本样式再剥标签。精细转换交给 Jina。 */
function htmlToText(html: string): string {
	const scoped = html.match(/<(main|article)\b[\s\S]*?<\/\1>/i);
	return (scoped ? scoped[0] : html)
		.replace(/<script[\s\S]*?<\/script>/gi, " ")
		.replace(/<style[\s\S]*?<\/style>/gi, " ")
		.replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
		.replace(/<\/(p|div|li|tr|h[1-6]|br)>/gi, "\n")
		.replace(/<[^>]+>/g, " ")
		.replace(/&nbsp;/g, " ")
		.replace(/&amp;/g, "&")
		.replace(/&lt;/g, "<")
		.replace(/&gt;/g, ">")
		.replace(/[ \t]+/g, " ")
		.replace(/\n{3,}/g, "\n\n")
		.trim();
}

function looksLikeShell(html: string): boolean {
	const s = html.slice(0, 4000).toLowerCase();
	return (
		s.includes("enable javascript") ||
		s.includes("请开启 javascript") ||
		s.includes("cf-challenge") ||
		s.includes("just a moment") ||
		html.length < 1200
	);
}

interface Fetched {
	via: string;
	text: string;
	chars: number;
}

async function viaCurl(url: string): Promise<Fetched | null> {
	const { stdout } = await run(
		"curl",
		["-sL", "--compressed", "--max-time", "15", "-A", UA, url],
		{ maxBuffer: 8 << 20, timeout: 20_000 },
	);
	if (looksLikeShell(stdout)) return null;
	const text = /<html|<!doctype/i.test(stdout) ? htmlToText(stdout) : stdout.trim();
	if (text.length < 400) return null;
	return { via: "curl 直连", text, chars: text.length };
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
		const res = await fetch(endpoint, { method: "POST", headers: hdr, body: JSON.stringify(payload) });
		return { sid: res.headers.get("mcp-session-id") ?? undefined, body: await res.text() };
	};
	const init = await call({
		jsonrpc: "2.0",
		id: 1,
		method: "initialize",
		params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "d-reach-plugin", version: "1" } },
	});
	const out = await call(
		{
			jsonrpc: "2.0",
			id: 2,
			method: "tools/call",
			params: { name: "fetch_content", arguments: { urls: [url], format: "markdown" } },
		},
		init.sid,
	);
	const m = out.body.match(/\{[\s\S]*\}/);
	if (!m) return null;
	const parsed = JSON.parse(m[0]) as { result?: { content?: Array<{ text?: string }> } };
	const text = (parsed.result?.content ?? []).map((c) => c.text ?? "").join("\n").trim();
	if (text.length < 200) return null;
	return { via: "TinyFish fetch", text, chars: text.length };
}

async function viaJina(url: string): Promise<Fetched | null> {
	const key = await loadKey("JINA_API_KEY");
	const hdr = ["-H", "X-Return-Format: markdown"];
	if (key) hdr.push("-H", `Authorization: Bearer ${key}`);
	const { stdout } = await run(
		"curl",
		["-sL", "--compressed", "--max-time", "25", "-A", UA, ...hdr, `https://r.jina.ai/${url}`],
		{ maxBuffer: 8 << 20, timeout: 30_000 },
	);
	const text = stdout.trim();
	if (text.length < 200) return null;
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
		["-sL", "--max-time", "30", "-X", "POST", "https://api.brightdata.com/request",
			"-H", `Authorization: Bearer ${key}`, "-H", "Content-Type: application/json", "-d", body],
		{ maxBuffer: 8 << 20, timeout: 35_000 },
	);
	const text = stdout.trim();
	if (text.length < 200 || text.startsWith("{")) return null;
	return { via: "BrightData", text, chars: text.length };
}

/** 依次尝试，第一个拿到达标内容的就返回；全部失败如实报告每一档的原因。 */
async function fetchUrl(url: string, maxChars: number) {
	const attempts: Array<[string, () => Promise<Fetched | null>]> = [
		["curl 直连", () => viaCurl(url)],
		["TinyFish fetch", () => viaTinyfish(url)],
		["Jina Reader", () => viaJina(url)],
		["BrightData", () => viaBrightdata(url)],
	];
	const failed: string[] = [];
	for (const [name, fn] of attempts) {
		try {
			const got = await fn();
			if (got) {
				const text = got.text.length > maxChars ? got.text.slice(0, maxChars) + "\n…（已截断）" : got.text;
				return { ok: true as const, got: { ...got, text }, failed };
			}
			failed.push(`${name}: 内容过短或需 JS`);
		} catch (e) {
			failed.push(`${name}: ${e instanceof Error ? e.message.slice(0, 60) : "失败"}`);
		}
	}
	return { ok: false as const, failed };
}

// ---------------------------------------------------------------- 工具

const searchTool = defineTool({
	name: "d_reach",
	label: "d-reach 检索",
	description:
		"多通道并发检索：中文走百度千帆、代码走 Firecrawl/StackExchange、通用走 TinyFish/LangSearch。" +
		"profile=auto（默认）按 query 意图自动选 3 路；quick 固定 3 路；base 9 路；deep 13 路含限额通道。" +
		"返回精简摘要，完整来源写到 details.file。",
	parameters: Type.Object({
		query: Type.String({ description: "检索词，中英文均可" }),
		profile: Type.Optional(
			Type.Union(
				[Type.Literal("auto"), Type.Literal("quick"), Type.Literal("base"), Type.Literal("deep")],
				{ description: "auto=按意图选 3 路（默认）；quick=固定 3 路；base=9 路；deep=13 路" },
			),
		),
		channels: Type.Optional(Type.String({ description: "显式指定通道，逗号分隔，如 hn,exa；覆盖 profile" })),
		detail: Type.Optional(
			Type.Union([Type.Literal("brief"), Type.Literal("full")], {
				description: "brief=每路 2-3 条（默认）；full=每路最多 8 条",
			}),
		),
	}),

	async execute(_id, params) {
		const query = params.query.trim();
		if (!query) return { content: [{ type: "text", text: "query 不能为空" }], isError: true };
		const profile = (params.profile ?? "auto") as Profile;
		try {
			const { md, secs, on, why } = await runFanout(query, profile, params.channels ?? "");
			const parsed = parseFanout(md);
			const file = await persist(md, query);
			const perChannel = params.detail === "full" ? 8 : profile === "quick" ? 3 : 2;
			const head = `d-reach ${PROFILES[profile].label} · ${secs.toFixed(1)}s` + (why ? ` · ${why}` : on ? ` · ${on}` : "");
			return {
				content: [{ type: "text", text: `${renderSearch(parsed, perChannel, head)}\n\n完整结果：${file}` }],
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
			return { content: [{ type: "text", text: `d-reach 执行失败：${msg.slice(0, 300)}` }], isError: true };
		}
	},
});

const fetchTool = defineTool({
	name: "d_reach_fetch",
	label: "d-reach 抓网页",
	description:
		"抓一个 URL 的正文，自动在 curl 直连 → TinyFish（真渲染，$0）→ Jina Reader → BrightData 之间降级，" +
		"返回 markdown/纯文本。适合读文章、文档、issue。反爬站也能拿到（会走 BrightData，消耗额度）。",
	parameters: Type.Object({
		url: Type.String({ description: "要抓的完整 URL" }),
		max_chars: Type.Optional(Type.Number({ description: "正文最多返回多少字符，默认 12000" })),
	}),

	async execute(_id, params) {
		const url = params.url.trim();
		if (!/^https?:\/\//i.test(url)) {
			return { content: [{ type: "text", text: "url 必须以 http:// 或 https:// 开头" }], isError: true };
		}
		const maxChars = Math.min(Math.max(params.max_chars ?? 12000, 500), 40000);
		const t0 = Date.now();
		const r = await fetchUrl(url, maxChars);
		const secs = ((Date.now() - t0) / 1000).toFixed(1);

		if (!r.ok) {
			return {
				content: [
					{
						type: "text",
						text: `四档都失败了（${secs}s）：\n${r.failed.map((x) => `- ${x}`).join("\n")}\n\n` +
							"如果是登录墙/强反爬，换 browser 会话或让用户贴正文。",
					},
				],
				isError: true,
			};
		}

		const skipped = r.failed.length ? `\n先试过：${r.failed.join("；")}` : "";
		return {
			content: [
				{
					type: "text",
					text: `来源：${r.got.via} · ${r.got.chars} 字符 · ${secs}s${skipped}\n\n${r.got.text}`,
				},
			],
			details: { url, via: r.got.via, chars: r.got.chars, secs: Number(secs) },
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
		refresh: Type.Optional(Type.Boolean({ description: "是否重新校准官方额度" })),
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
			{ state?: string; remaining?: number; total?: number; balance?: string; currency?: string; probed_at?: string }
		>;

		const bad = Object.entries(health)
			.filter(([, v]) => ((v as { streak_fail?: number }).streak_fail ?? 0) >= 3)
			.map(([k]) => k);

		const lines: string[] = ["通道健康：", bad.length ? `  连败 ≥3（下轮自动跳过）：${bad.join(", ")}` : "  全部正常"];
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
		if (stamp) lines.push("", `官方数据时间：${stamp.slice(0, 16).replace("T", " ")}`);
		return { content: [{ type: "text", text: lines.join("\n") }], details: { quota, health } };
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
			const { md, secs } = await runFanout(query, profile, "");
			const parsed = parseFanout(md);
			await persist(md, query);
			ctx.ui.notify(`完成 ${secs.toFixed(1)}s · ${parsed.summary || "见 last-run.md"}`, "info");
		} catch (err) {
			ctx.ui.notify(`失败：${err instanceof Error ? err.message : String(err)}`, "error");
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
	if (/not_authenticated|Not logged in|"logged_in"\s*:\s*false/i.test(out)) return "expired";
	if (/"logged_in"\s*:\s*true/i.test(out)) return "ok";
	if (/ok:\s*true/.test(out) && !/logged_in/.test(out)) return "ok";
	return null;
}

const SOCIAL = {
	bili: {
		bin: "bilibili",
		whoami: ["bilibili", "auth", "status", "--json"],
		search: (q: string, n: number) => [
			"bilibili", "video", "search", "--keyword", q, "--num", String(n), "--json",
		],
		authFile: join(homedir(), ".config", "bilibili-skill"),
		hint: "bilibili auth login start（扫码）",
	},
	xhs: {
		bin: "xhs",
		whoami: ["xhs", "status"],
		search: (q: string, _n: number) => ["xhs", "search", q, "--json"],
		authFile: join(homedir(), ".config", "xhs-cli"),
		hint: "xhs login（扫码）",
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
	if (!installed) return { platform: p, state: "missing" as const, detail: `${meta.bin} 未安装` };

	let authFileAge: string | null = null;
	try {
		const { stdout } = await run("stat", ["-c", "%y", meta.authFile], { timeout: 5000 });
		authFileAge = stdout.trim().slice(0, 10);
	} catch {
		/* 文件不存在也算信息 */
	}

	let out = "";
	try {
		const r = await run(meta.whoami[0], meta.whoami.slice(1), { timeout: 25_000 });
		out = r.stdout + r.stderr;
	} catch (e) {
		// 未登录时通常非 0 退出码，真因在 stdout/stderr 里，别把 "Command failed" 当结论
		out = String((e as { stdout?: string; stderr?: string })?.stdout ?? "") +
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
			Type.Union([Type.Literal("bili"), Type.Literal("xhs")], { description: "不传 = 只体检" }),
		),
		query: Type.Optional(Type.String({ description: "搜索关键词；传了才会搜" })),
		limit: Type.Optional(Type.Number({ description: "返回条数，默认 8，最多 20" })),
	}),

	async execute(_id, params) {
		const platforms = params.platform ? [params.platform] : (Object.keys(SOCIAL) as SocialPlatform[]);
		const probes = await Promise.all(platforms.map(probeSocial));

		const lines: string[] = [];
		for (const pr of probes) {
			const meta = SOCIAL[pr.platform];
			const tail = pr.authFileAge ? ` · 凭据文件 ${pr.authFileAge}` : "";
			lines.push(`- ${pr.platform}: ${pr.detail}${tail}`);
			if (pr.state === "expired" || pr.state === "missing" || pr.state === "error") {
				lines.push(`  修复：${meta.hint}`);
			}
		}

		if (!params.query) {
			const usable = probes.filter((p) => p.state === "ok").map((p) => p.platform);
			lines.push("", usable.length ? `可直接搜：${usable.join(", ")}` : "当前没有可用的社交通道");
			return { content: [{ type: "text", text: lines.join("\n") }], details: { probes } };
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
			const { stdout } = await run(meta.bin, meta.search(params.query, n).slice(1), {
				timeout: 40_000,
				maxBuffer: 4 << 20,
			});
			let rendered = stdout.trim();
			try {
				const parsed = JSON.parse(rendered) as { data?: unknown };
				rendered = "```json\n" + JSON.stringify(parsed.data ?? parsed, null, 2).slice(0, 6000) + "\n```";
			} catch {
				/* 非 JSON 就原样给 */
			}
			return {
				content: [{ type: "text", text: `[${target.platform}] 搜索「${params.query}」\n\n${rendered}` }],
				details: { platform: target.platform, query: params.query, limit: n },
			};
		} catch (e) {
			return {
				content: [
					{
						type: "text",
						text: `[${target.platform}] 搜索失败：${e instanceof Error ? e.message.slice(0, 200) : "未知"}。` +
							`\n如果是风控/限流，隔几分钟再试；登录态问题是另一类，先跑 d_reach_social 体检。`,
					},
				],
				isError: true,
			};
		}
	},
});
