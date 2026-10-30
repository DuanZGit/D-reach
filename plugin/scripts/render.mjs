#!/usr/bin/env node
/**
 * 本地 Playwright 渲染档（d_reach_fetch 的免费真渲染兜底）。
 *
 * 为什么单独一个进程：扩展由 pi 用 TS 加载，直接 import playwright 会撞模块解析；
 * 起子进程最省事，也让「没装 playwright」变成可判定的 fail class 而不是崩溃。
 *
 * 用法：node render.mjs <url>
 * 输出：单行 JSON { ok, text, html, chars, lines, avgLine, linkDen, finalUrl, ms, err }
 *   - text 是正文（优先 article/main/#js_content，退回 body.innerText），保留换行
 *   - html 只截前 200KB，够做站点标记判定
 *   - lines / avgLine / linkDen 是「骨架页」判据，调用方据此拒绝假装成功
 *   - finalUrl 是跳转后的真实地址，登录墙（passport./login./sso.）靠它识别
 */
import { pathToFileURL } from "node:url";

const url = process.argv[2];
if (!url) {
  console.log(JSON.stringify({ ok: false, err: "no_url" }));
  process.exit(0);
}

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36";

// 微信正文是服务端渲染的，但部分站点要等 XHR 回填，统一给一个短的静默窗口
const SETTLE_MS = 1200;
const TIMEOUT_MS = 25_000;

// ESM 的 package 解析不认 NODE_PATH，得自己找全局安装位置
async function loadChromium() {
  const candidates = [
    "playwright",
    ...(process.env.DREACH_PLAYWRIGHT ? [process.env.DREACH_PLAYWRIGHT] : []),
    `${process.env.HOME}/.npm-global/lib/node_modules/playwright/index.mjs`,
    "/usr/lib/node_modules/playwright/index.mjs",
    "/usr/local/lib/node_modules/playwright/index.mjs",
  ];
  let last;
  for (const c of candidates) {
    try {
      const spec = c.startsWith("/") ? pathToFileURL(c).href : c;
      return (await import(spec)).chromium;
    } catch (e) {
      last = e;
    }
  }
  throw new Error(
    `找不到 playwright（设 DREACH_PLAYWRIGHT=<...>/playwright/index.mjs）：${last?.message ?? ""}`,
  );
}

/**
 * 取页面快照。
 *
 * 页面在 evaluate 途中跳转（风控页重定向到首页/验证页）时，chromium 会抛
 * `Execution context was destroyed`。这不是抓取失败，是「取样时页面换了」，
 * 等跳转落地后重取一次通常就正常 —— 之前直接把这个异常往上抛，豆瓣那类站必崩。
 */
async function snapshot(page) {
  let lastErr;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      return await page.evaluate(() => {
        // 真浏览器里 <noscript> 里的东西本来就该忽略。但脚本启用时浏览器把它当**原始文本**解析，
        // innerText 会把里面的整段 JS 吐出来（实测淘宝搜索页吐了 4 万字 JS 冒充正文）。
        document.querySelectorAll("noscript").forEach((e) => e.remove());
        const pick = document.querySelector("article, main, #js_content");
        const node =
          pick && pick.innerText.trim().length > 200 ? pick : document.body;
        const bodyText = document.body.innerText || "";
        const links = [...document.querySelectorAll("a[href]")];
        let linkChars = 0;
        for (const a of links) linkChars += (a.innerText || "").trim().length;
        const lines = bodyText
          .split("\n")
          .map((s) => s.trim())
          .filter((s) => s.length > 0);
        const totalChars = lines.reduce((s, l) => s + l.length, 0);
        return {
          text: node.innerText,
          html: document.documentElement.outerHTML.slice(0, 200_000),
          lines: lines.length,
          avgLine: lines.length ? totalChars / lines.length : 0,
          // 嵌套 <a> 会让比率略微超过 1，取 min 无所谓，只要远大于 0 就是导航页
          linkDen: bodyText.length ? linkChars / bodyText.length : 0,
        };
      });
    } catch (e) {
      lastErr = e;
      if (
        !/Execution context was destroyed|navigat|Target closed/i.test(
          String(e?.message ?? e),
        )
      )
        throw e;
      await page.waitForTimeout(700);
    }
  }
  throw lastErr;
}

/**
 * 把子框架（iframe）的正文拼起来。
 *
 * 主文档只有导航、正文在 iframe 里时，单看 body.innerText 会得到一个「骨架页」，
 * 而页面本身并不反爬 —— 之前直接判失败。子框架读不到（跨域限制、已销毁）就跳过。
 */
// 子框架/影子树里的文本不一定可信：实测淘宝把一个 JS bundle 塞进子框架，
// innerText 拿到 15 万字源码冒充正文。符号密度是最便宜的区分方式（源码里 ;{}()=> 满地都是）。
function codey(t) {
	const sym = (t.match(/[;{}()\[\]=<>|&$]/g) || []).length;
	return t.length > 0 && sym / t.length > 0.04;
}

async function shadowText(page) {
  // innerText 不穿透 shadow root，用 Web Components 写的站点正文会整段拿不到。
  // 递归下去把每层 shadowRoot 的文本捞出来。
  try {
    return await page.evaluate(() => {
      const SKIP = new Set([
        "STYLE",
        "SCRIPT",
        "TEMPLATE",
        "NOSCRIPT",
        "LINK",
        "META",
      ]);
      const out = [];
      const collect = (root) => {
        let s = "";
        for (const n of root.childNodes) {
          if (n.nodeType === 3) s += n.nodeValue || "";
          else if (n.nodeType === 1 && !SKIP.has(n.tagName)) s += collect(n);
        }
        return s;
      };
      const walk = (root) => {
        for (const el of root.querySelectorAll("*")) {
          const sr = el.shadowRoot;
          if (!sr) continue;
          const t = collect(sr).replace(/\s+/g, " ").trim();
          if (t.length > 40) out.push(t);
          walk(sr);
        }
      };
      walk(document);
      return out.join("\n\n");
    });
  } catch {
    return "";
  }
}

async function iframeText(page) {
  const parts = [];
  for (const frame of page.frames()) {
    if (frame === page.mainFrame()) continue;
    try {
      const t = await frame.evaluate(() => document.body?.innerText ?? "");
      if (t.trim().length > 200 && !codey(t)) parts.push(t.trim());
    } catch {
      /* 跨域/已卸载：正常，跳过 */
    }
  }
  return parts.join("\n\n");
}

const t0 = Date.now();
let browser;
try {
  const chromium = await loadChromium();
  browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    userAgent: UA,
    locale: "zh-CN",
    viewport: { width: 1440, height: 900 },
    extraHTTPHeaders: { "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8" },
  });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: TIMEOUT_MS });
  await page.waitForTimeout(SETTLE_MS);
  const out = await snapshot(page);
  let text = out.text;
  // 正文被塞进 iframe：老政府站、招聘站、文档预览都这么干。
  // 主文档只有导航时，把子框架的 innerText 接上。
  if (text.trim().length < 300) {
    const inner = await iframeText(page);
    if (inner) text = `${text.trim()}\n\n${inner}`;
  }
  if (text.trim().length < 400) {
    const sh = await shadowText(page);
    if (!codey(sh) && sh.trim().length > text.trim().length) text = sh;
  }
  // 行长指标必须跟着最终的 text 走：主文档是一片导航（avgLine=2），
  // 但把 iframe 正文接上后它就该按真实正文算，否则还会被判成「骨架页」。
  const finalLines = text
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const finalChars = finalLines.reduce((s, l) => s + l.length, 0);
  console.log(
    JSON.stringify({
      ok: true,
      text,
      html: out.html,
      chars: text.trim().length,
      lines: finalLines.length,
      avgLine:
        Math.round(
          (finalLines.length ? finalChars / finalLines.length : 0) * 10,
        ) / 10,
      linkDen: Math.round(out.linkDen * 100) / 100,
      finalUrl: page.url(),
      ms: Date.now() - t0,
    }),
  );
} catch (e) {
  const msg = e instanceof Error ? e.message.slice(0, 200) : String(e);
  // PDF/图片直链：chromium 不渲染，它直接开始下载
  const err = /Download is starting/i.test(msg)
    ? "NOT_A_PAGE: 直接下载，不是网页"
    : msg;
  console.log(JSON.stringify({ ok: false, err, ms: Date.now() - t0 }));
} finally {
  if (browser) await browser.close().catch(() => {});
}
