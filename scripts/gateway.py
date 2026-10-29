#!/usr/bin/env python3
"""d-reach 本地可视化网关（标准库，零依赖）。

  python3 scripts/gateway.py                 # 只绑 127.0.0.1，无需 key
  python3 scripts/gateway.py --lan           # 绑 0.0.0.0，局域网可访问，要 ?k=<key>
                                             # 且请求源 IP 必须在 127/192.168.5/10.7 段内

  GET  /                页面（视觉照 magpie 的路由页）
  GET  /api/state       通道 + 额度状态
  POST /api/search      {"q":"...","deep":true,"on":"hn,exa"}

--lan 模式下 key 存在 ~/.agent-reach/gateway.key（首次自动生成，600）。
"""
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SKILL = Path(__file__).resolve().parent.parent
FANOUT = SKILL / "scripts" / "fanout.sh"
DATA = Path.home() / ".agent-reach"
QUOTA = DATA / "quota.json"
HEALTH = DATA / "channels.json"
KEYFILE = DATA / "gateway.key"
PORT = int(os.environ.get("D_REACH_GATEWAY_PORT", "3426"))

LAN = False
KEY = ""

NO_KEY_PAGE = """<!doctype html><meta charset="utf-8"><title>需要访问 key</title>
<body style="background:#f2f2f5;color:#1c1c21;font:14px/1.7 system-ui,'PingFang SC',sans-serif;
             display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<div style="max-width:520px;padding:28px;border:1px solid rgba(0,0,0,.07);border-radius:14px;background:#fff;
            box-shadow:0 0 0 1px rgba(0,0,0,.05),0 1px 2px rgba(0,0,0,.04)">
  <div style="font-size:16px;font-weight:600;margin-bottom:10px">需要访问 key</div>
  <p style="color:#6b6b74;margin:0 0 12px">网关对局域网开放，必须带 <code>?k=&lt;key&gt;</code> 才能打开。</p>
  <p style="color:#6b6b74;margin:0">key 在机器上的 <code>~/.agent-reach/gateway.key</code>，
     或在能登录的终端跑 <code>cat ~/.agent-reach/gateway.key</code> 取。</p>
</div></body>"""


DRAWER_JS = r"""
/* d-reach 侧滑抽屉（由 /reach/drawer.js 下发）
   注入方式：pi-web 的 client chunk 末尾加载本文件，不修改它的 React 代码。 */
(function () {
  if (window.__DREACH_DRAWER__) return;
  window.__DREACH_DRAWER__ = 1;
  if (window.top !== window.self) return;

  function boot() {

  var REACH = "/reach/";
  var style = document.createElement("style");
  style.textContent = [
    "#dreach-fab{position:fixed;right:18px;bottom:18px;z-index:2147483000;width:46px;height:46px;",
    "border-radius:50%;background:#1c1c21;color:#fff;border:0;cursor:pointer;",
    "display:flex;align-items:center;justify-content:center;",
    "box-shadow:0 6px 18px rgba(0,0,0,.22);font:600 13px/1 system-ui,sans-serif;",
    "transition:transform .18s cubic-bezier(.2,.8,.2,1),opacity .18s}",
    "#dreach-fab:hover{transform:translateY(-2px)}",
    "#dreach-fab.hide{opacity:0;pointer-events:none}",
    "#dreach-mask{position:fixed;inset:0;z-index:2147482999;background:rgba(0,0,0,.28);",
    "opacity:0;pointer-events:none;transition:opacity .24s}",
    "#dreach-mask.on{opacity:1;pointer-events:auto}",
    "#dreach-panel{position:fixed;top:0;right:0;bottom:0;z-index:2147483000;",
    "width:min(460px,92vw);background:#f2f2f5;display:flex;flex-direction:column;",
    "transform:translateX(102%);transition:transform .3s cubic-bezier(.3,.9,.3,1);",
    "box-shadow:-8px 0 28px rgba(0,0,0,.16)}",
    "#dreach-panel.on{transform:translateX(0)}",
    "#dreach-head{display:flex;align-items:center;gap:8px;padding:10px 12px;",
    "border-bottom:1px solid rgba(0,0,0,.08);background:#fff;",
    "font:600 13px/1.4 system-ui,-apple-system,'PingFang SC',sans-serif;color:#1c1c21}",
    "#dreach-head .d{width:7px;height:7px;border-radius:50%;background:#189a58}",
    "#dreach-head .g{flex:1}",
    "#dreach-head button{border:1px solid rgba(0,0,0,.12);background:#fff;color:#4b4b53;",
    "border-radius:7px;font:500 12px/1 system-ui,sans-serif;padding:6px 9px;cursor:pointer}",
    "#dreach-frame{flex:1;width:100%;border:0;background:#f2f2f5}",
  ].join("");
  document.head.appendChild(style);

  // 放大镜：跟「检索」的语义对齐，比一个「路由」二字更轻
  var LENS = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="1.9"/>' +
    '<path d="M15.6 15.6 L20.5 20.5" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/>' +
    '</svg>';

  var fab = document.createElement("button");
  fab.id = "dreach-fab"; fab.innerHTML = LENS; fab.title = "d-reach 路由（Alt+R）";
  var mask = document.createElement("div"); mask.id = "dreach-mask";
  var panel = document.createElement("section"); panel.id = "dreach-panel";
  panel.innerHTML = '<div id="dreach-head"><span class="d"></span><span>d-reach · 路由与额度</span>' +
    '<span class="g"></span><button id="dreach-tab">新窗口</button>' +
    '<button id="dreach-close">关闭</button></div>' +
    '<iframe id="dreach-frame" title="d-reach 网关"></iframe>';
  document.body.appendChild(fab); document.body.appendChild(mask); document.body.appendChild(panel);

  var frame = panel.querySelector("#dreach-frame"), loaded = false;
  function open() {
    if (!loaded) { frame.src = REACH; loaded = true; }
    panel.classList.add("on"); mask.classList.add("on"); fab.classList.add("hide");
  }
  function close() {
    panel.classList.remove("on"); mask.classList.remove("on"); fab.classList.remove("hide");
  }
  fab.onclick = open; mask.onclick = close;
  panel.querySelector("#dreach-close").onclick = close;
  panel.querySelector("#dreach-tab").onclick = function () { window.open(REACH, "_blank", "noopener"); };
  document.addEventListener("keydown", function (e) {
    if (e.altKey && (e.key === "r" || e.key === "R")) { e.preventDefault(); panel.classList.contains("on") ? close() : open(); }
    else if (e.key === "Escape" && panel.classList.contains("on")) close();
  });

  // 侧边栏识别得到就再挂一个文字入口
  function menuEntry() {
    var menu = document.querySelector(".sidebar-menu");
    if (!menu || menu.querySelector("[data-dreach-entry]")) return;
    var b = document.createElement("button");
    b.type = "button"; b.textContent = "d-reach 路由"; b.dataset.dreachEntry = "1";
    b.style.cssText = "display:block;width:100%;text-align:left;padding:7px 12px;margin:2px 0;border:0;border-radius:7px;background:transparent;color:inherit;font:inherit;cursor:pointer";
    b.onmouseenter = function () { b.style.background = "rgba(0,0,0,.05)"; };
    b.onmouseleave = function () { b.style.background = "transparent"; };
    b.onclick = open;
    menu.appendChild(b);
  }
  // 顶部工具栏：找到文本是「工具」的那个按钮，克隆一个放它后面，
  // 这样样式和 pi-web 自己的一模一样，也不依赖它的类名（改了也能用）
  function topEntry() {
    if (document.querySelector("[data-dreach-top]")) return;
    var btns = Array.prototype.slice.call(document.querySelectorAll("button, a"));
    var anchor = btns.filter(function (b) {
      var tx = (b.textContent || "").replace(/\s+/g, "");
      return tx === "工具" || tx === "系统";
    })[0];
    if (!anchor || !anchor.parentElement) return;
    var b = anchor.cloneNode(false);
    b.innerHTML = '<span style="display:inline-flex;align-items:center;gap:5px">' +
      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true" style="flex:none">' +
      '<circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="2"/>' +
      '<path d="M15.6 15.6 L20.5 20.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>' +
      '</svg><span>路由</span></span>';
    b.setAttribute("data-dreach-top", "1");
    b.removeAttribute("id");
    b.title = "d-reach 路由（Alt+R）";
    b.onclick = open;
    anchor.parentElement.insertBefore(b, anchor.nextSibling);
  }

  function attach() {
    menuEntry();
    topEntry();
  }

  var queued = false;
  new MutationObserver(function () {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; attach(); });
  }).observe(document.body, { childList: true, subtree: true });
  attach();

  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { try { boot(); } catch (e) {} });
  } else {
    try { boot(); } catch (e) {}
  }
})();
"""

MANIFEST = """{
  "name": "d-reach 路由",
  "short_name": "d-reach",
  "start_url": "./",
  "scope": "./",
  "display": "standalone",
  "background_color": "#f2f2f5",
  "theme_color": "#1c1c21",
  "icons": [
    { "src": "./icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any" }
  ]
}"""

ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
  <rect width="192" height="192" rx="42" fill="#1c1c21"/>
  <circle cx="60" cy="96" r="12" fill="#189a58"/>
  <circle cx="132" cy="60" r="9" fill="#ffffff" opacity=".85"/>
  <circle cx="132" cy="96" r="9" fill="#ffffff" opacity=".85"/>
  <circle cx="132" cy="132" r="9" fill="#ffffff" opacity=".85"/>
  <path d="M72 96 H120" stroke="#189a58" stroke-width="4" fill="none"/>
  <path d="M72 96 C 96 96 96 60 120 60" stroke="#ffffff" stroke-width="3" fill="none" opacity=".55"/>
  <path d="M72 96 C 96 96 96 132 120 132" stroke="#ffffff" stroke-width="3" fill="none" opacity=".55"/>
</svg>"""

PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>d-reach</title>
<link rel="manifest" href="./manifest.webmanifest">
<meta name="theme-color" content="#1c1c21">
<link rel="apple-touch-icon" href="./icon.svg">
<style>
  :root{
    --font: system-ui,-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
    --code: "Cascadia Mono",Consolas,"SF Mono",ui-monospace,monospace;
    --bg:#f2f2f5; --card:#ffffff; --card-2:#f8f8fa;
    --fg:#1c1c21; --fg-2:#4b4b53; --muted:#6b6b74; --faint:#9a9aa3;
    --line:rgba(0,0,0,.07); --line-2:#ececf0;
    --green:#189a58; --red:#c0392b; --amber:#b45309;
    --card-edge:0 0 0 1px rgba(0,0,0,.05),0 1px 2px rgba(0,0,0,.04);
    --morph-t:.32s; --morph-ease:cubic-bezier(.42,0,.58,1);
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#1b1c20; --card:#25262c; --card-2:#212227;
      --fg:#ededf1; --fg-2:#b9b9c1; --muted:#9c9ca6; --faint:#7c7c87;
      --line:rgba(255,255,255,.07); --line-2:#2c2c32;
      --green:#6fd99b; --red:#f87171; --amber:#f2b544;
      --card-edge:inset 0 0 0 1px rgba(255,255,255,.06); }
  }
  *{box-sizing:border-box}
  html,body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--font);
    font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased;
    overflow-x:hidden;max-width:100%}
  .wrap{max-width:1240px;margin:0 auto;padding:22px 20px 48px}

  .topbar{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
  .topbar h1{font-size:14px;font-weight:600;margin:0;letter-spacing:.01em}
  .live{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--muted)}
  .live i{width:7px;height:7px;border-radius:50%;background:var(--green);display:inline-block}
  .live.off i{background:var(--red)}
  .grow{flex:1}
  .ghost{background:transparent;border:1px solid var(--line);border-radius:8px;color:var(--fg-2);
    font-size:12.5px;padding:5px 10px;cursor:pointer;font-family:inherit}
  .ghost:hover{background:var(--card-2)}

  /* ---- 主卡片：照 magpie 的 .rt ---- */
  .rt{background:var(--card);border:1px solid var(--line);border-radius:14px;
      padding:14px 16px 12px;margin:0 0 16px;box-shadow:var(--card-edge);overflow:hidden;
      container-type:inline-size}

  /* magpie 的做法：按「容器自身宽度」适配，而不是视口。塞进 460px 抽屉时
     视口仍是 1400px，media query 不触发，原来会挤成三列 —— 所以用容器查询。 */
  @container (max-width: 560px) {
    .rt-stage{grid-template-columns:minmax(0,1fr) minmax(0,1fr);column-gap:20px;
      row-gap:18px;padding:14px 0 4px}
    .rt-stage .rt-node{padding:10px 6px 8px}
    .rt-stage .rt-node .glyph{font-size:17px;margin-bottom:1px}
    .rt-accts{grid-column:1 / -1;padding-left:18px;max-height:none}
    .rt-wires{overflow:visible}
    .rt-accts li{grid-template-columns:10px minmax(0,1fr);row-gap:4px}
    .rt-accts li .right{grid-column:2;text-align:left}
    .rt-accts li .bar{grid-column:2}
    .rt-foot{flex-direction:column;align-items:stretch;gap:10px}
    .stats{justify-content:flex-start;text-align:left;gap:20px}
    .stats b{font-size:20px}
    .rt-what,.rt-mode{font-size:12.5px}
  }
  @container (max-width: 380px) {
    .rt-accts li .nm small{display:none}
    .rt-stage{grid-template-columns:1fr;row-gap:10px}
  }

  @media (prefers-reduced-motion: reduce){
    .card,.rt-node,iframe{animation:none!important;transition:none!important}
    .rt-wires path.live{animation:none}
  }
  .rt-top{display:flex;flex-direction:column;gap:3px}
  .rt-what{font-size:13px;color:var(--muted);margin:0}
  .rt-what b{color:var(--fg);font-weight:600}
  .rt-mode{margin:0;font-size:12.5px;color:var(--fg-2);line-height:1.45}

  .rt-stage{position:relative;display:grid;grid-template-columns:124px 124px minmax(0,1fr);
    column-gap:56px;align-items:center;padding:22px 2px}
  .rt-wires{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none;z-index:0}
  /* 飞行层：放大镜沿 wire 从 hub 飞到通道行（magpie 用喜鹊，这里用放大镜） */
  .rt-sky{position:absolute;inset:0;width:100%;height:100%;overflow:visible;
    pointer-events:none;z-index:2}
  .rt-sky .mag{opacity:0}
  .rt-sky .mag circle,.rt-sky .mag path{stroke:var(--fg-2);stroke-width:2.2;fill:none;stroke-linecap:round}
  .rt-sky .mag.on{opacity:1;filter:drop-shadow(0 1px 4px rgba(28,28,33,.28))}
  .rt-sky .mag.done circle,.rt-sky .mag.done path{stroke:var(--green)}
  .rt-sky .mag.done{filter:drop-shadow(0 0 5px rgba(24,154,88,.45))}
  .rt-sky .mag.fail circle,.rt-sky .mag.fail path{stroke:var(--red)}
  .rt-sky .mag.fail{filter:drop-shadow(0 0 5px rgba(192,57,43,.45))}
  .rt-wires path{fill:none;stroke:var(--line);stroke-width:1.5;transition:stroke .3s,opacity .3s}
  .rt-wires path.live{stroke:var(--green);stroke-dasharray:3 5;animation:rtflow .7s linear infinite}
  .rt-wires path.ok{stroke:var(--green);opacity:.55}
  .rt-wires path.fail{stroke:var(--red);stroke-dasharray:2 6;opacity:.6}
  @keyframes rtflow{to{stroke-dashoffset:-8}}

  .rt-node{position:relative;z-index:1;min-width:0;display:flex;flex-direction:column;
    align-items:center;gap:2px;padding:12px 8px 10px;background:var(--card);
    border:1px solid var(--line);border-radius:12px;text-align:center}
  .rt-node b{font-size:13px;font-weight:600;max-width:100%;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap}
  .rt-node small{font-size:11px;color:var(--muted);max-width:100%;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap}
  .rt-node .glyph{font-size:20px;line-height:1;margin-bottom:3px}
  .rt-hub{border-color:var(--fg);box-shadow:0 0 0 4px var(--card-2)}
  .rt-hub i{font-style:normal;font-size:10.5px;font-weight:560;margin-top:5px;
    padding:1px 8px;border-radius:999px;background:var(--fg);color:var(--card)}

  .rt-accts{position:relative;z-index:1;list-style:none;margin:0;padding:0;
    display:grid;gap:7px;min-width:0;max-height:330px;overflow:auto}
  .rt-accts li{display:grid;grid-template-columns:10px minmax(0,1fr) auto;align-items:center;
    column-gap:10px;row-gap:6px;padding:9px 12px;background:var(--card);
    border:1px solid var(--line);border-radius:10px;font-size:13px;
    transition:opacity var(--morph-t),border-color var(--morph-t)}
  .rt-accts li .st{width:7px;height:7px;border-radius:50%;background:var(--faint)}
  .rt-accts li.ok .st{background:var(--green)}
  .rt-accts li.fail .st{background:var(--red)}
  .rt-accts li.idle .st{background:var(--faint);opacity:.5}
  .rt-accts li.hit{border-color:rgba(24,154,88,.5)}
  .rt-accts li .nm{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .rt-accts li .nm small{color:var(--muted);font-size:11.5px;margin-left:6px}
  .rt-accts li .right{text-align:right;font-size:11.5px;color:var(--muted);
    font-variant-numeric:tabular-nums;white-space:nowrap;max-width:46%;
    overflow:hidden;text-overflow:ellipsis}
  .rt-accts li .bar{grid-column:2 / -1;height:3px;background:var(--line-2);border-radius:99px;overflow:hidden}
  .rt-accts li .bar>i{display:block;height:100%;background:var(--green);width:0}
  .rt-accts li .bar>i.warn{background:var(--amber)}
  .rt-accts li .bar>i.bad{background:var(--red)}

  .rt-foot{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;
    border-top:1px solid var(--line);margin-top:8px;padding-top:12px;flex-wrap:wrap}
  .rt-foot p{margin:0;font-size:12.5px;color:var(--fg-2);line-height:1.5}
  .stats{display:flex;gap:26px;text-align:right}
  .stats div{min-width:44px}
  .stats b{display:block;font-size:24px;line-height:1.1;font-weight:600;
    font-family:var(--code);font-variant-numeric:tabular-nums}
  .stats span{font-size:11px;color:var(--muted)}

  .rt-log{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}
  .rt-log h3{font-size:12.5px;margin:0 0 8px;color:var(--fg-2);font-weight:600}
  .rt-log ol{list-style:none;margin:0;padding:0;display:grid;gap:5px;font-size:12.5px;color:var(--fg-2)}
  .rt-log li{display:flex;gap:8px;align-items:baseline}
  .rt-log li .st{width:7px;height:7px;border-radius:50%;background:var(--faint);flex:none;position:relative;top:-1px}
  .rt-log li.ok .st{background:var(--green)}
  .rt-log li.fail .st{background:var(--red)}
  .rt-log li .tx{min-width:0}
  .rt-log li b{font-weight:600;color:var(--fg)}

  /* ---- 搜索条 ---- */
  .bar2{display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:var(--card);
    border:1px solid var(--line);border-radius:12px;padding:10px;margin-bottom:16px;
    box-shadow:var(--card-edge)}
  .bar2 input{flex:1;min-width:200px;background:transparent;border:none;outline:none;
    color:var(--fg);font-size:14px;font-family:inherit;padding:6px 8px}
  .bar2 input::placeholder{color:var(--faint)}
  .bar2 select{background:var(--card-2);border:1px solid var(--line);border-radius:8px;
    color:var(--fg-2);font-size:12.5px;padding:6px 8px;font-family:inherit;cursor:pointer}
  .bar2 button{background:var(--fg);color:var(--card);border:none;border-radius:8px;
    font-size:13px;font-weight:600;padding:8px 16px;cursor:pointer;font-family:inherit}
  .bar2 button:disabled{opacity:.5;cursor:default}

  /* ---- 来源明细 ---- */
  .src{background:var(--card);border:1px solid var(--line);border-radius:14px;
    padding:2px 16px 6px;box-shadow:var(--card-edge)}
  .src summary{cursor:pointer;font-size:12.5px;color:var(--fg-2);padding:11px 0;
    list-style:none;display:flex;align-items:center;gap:8px}
  .src summary::-webkit-details-marker{display:none}
  .src summary::before{content:"›";color:var(--faint);transition:transform var(--morph-t) var(--morph-ease)}
  .src[open] summary::before{transform:rotate(90deg)}
  .src summary .cnt{color:var(--muted);font-size:11.5px;margin-left:auto;
    font-variant-numeric:tabular-nums}

  .grp{padding:12px 0 10px;border-top:1px solid var(--line)}
  .grp:first-of-type{border-top:none}
  .grp h5{font-size:12.5px;margin:0;font-weight:600;color:var(--fg);
    display:flex;align-items:center;gap:7px;flex-wrap:wrap}
  .grp h5 i{width:7px;height:7px;border-radius:50%;background:var(--faint);flex:none}
  .grp.ok h5 i{background:var(--green)}
  .grp.bad h5 i{background:var(--red)}
  .grp h5 .cnt{font-weight:400;color:var(--muted);font-size:11.5px;margin-left:auto;
    font-variant-numeric:tabular-nums}
  .grp .note{color:var(--muted);font-size:11.5px;margin-top:3px;line-height:1.5}
  .grp ul{margin:7px 0 0;padding:0;list-style:none;display:grid;gap:5px}
  .grp li{font-size:12.5px;line-height:1.5;color:var(--fg-2);padding-left:13px;position:relative}
  .grp li::before{content:"";position:absolute;left:2px;top:.62em;width:4px;height:4px;
    border-radius:50%;background:var(--line-2)}
  .grp li a{color:var(--fg);text-decoration:none;border-bottom:1px solid transparent}
  .grp li a:hover{border-bottom-color:var(--fg-2)}
  .grp li .meta{color:var(--muted);font-size:11.5px;margin-left:4px}
  .grp .txt{margin:7px 0 0;font-size:12.5px;line-height:1.65;color:var(--fg-2);
    white-space:pre-wrap;max-height:260px;overflow:auto}
  .grp details{margin-top:6px}
  .grp details summary{font-size:11.5px;color:var(--muted);padding:2px 0}

  @media(max-width:860px){
    .wrap{padding:14px 12px 36px}
    .bar2 input{flex:1 1 100%;min-width:0}
    .bar2 select,.bar2 button{flex:0 0 auto}
  }
  @media(max-width:420px){
    .rt-accts li .nm small{display:none}   /* 极窄屏先藏档位，保名称和数字 */
  }
</style></head><body>
<div class="wrap">
  <div class="topbar">
    <h1>d-reach</h1>
    <span class="live" id="live"><i></i><span id="livetxt">读取中</span></span>
    <span class="grow"></span>
    <button class="ghost" id="refresh">刷新</button>
  </div>

  <div class="bar2">
    <input id="q" placeholder="要查什么？回车直接跑" autocomplete="off">
    <select id="mode">
      <option value="base">默认档 · 9 路</option>
      <option value="deep">deep · +4 路限额</option>
    </select>
    <button id="go">跑一轮</button>
  </div>

  <div class="rt">
    <div class="rt-top">
      <p class="rt-what" id="what"><b>还没有查询</b> · 通道状态来自上一轮</p>
      <p class="rt-mode" id="mode-why">免费优先：9 路免 Key 通道不限量不限次；deep 才追加 LangSearch / Exa / Firecrawl-Research / BrightData，按次记账、失败不扣。</p>
    </div>

    <div class="rt-stage" id="stage">
      <svg class="rt-wires" id="wires"></svg>
      <svg class="rt-sky" id="sky" aria-hidden="true"></svg>
      <div class="rt-node">
        <div class="glyph">⌕</div>
        <b id="node-q">查询</b>
        <small id="node-tier">—</small>
      </div>
      <div class="rt-node rt-hub">
        <div class="glyph">⌘</div>
        <b>fanout</b>
        <small>并发铺开</small>
        <i id="node-pill">待命</i>
      </div>
      <ul class="rt-accts" id="accts"></ul>
    </div>

    <div class="rt-foot">
      <p id="foot-note">通道健康与额度每 5 秒刷新；跑一轮后这里显示本轮走向。</p>
      <div class="stats">
        <div><b id="s-req">0</b><span>路有结果</span></div>
        <div><b id="s-fail">0</b><span>失败</span></div>
        <div><b id="s-skip">0</b><span>跳过</span></div>
      </div>
    </div>

    <div class="rt-log" id="logbox" hidden>
      <h3>这一轮是怎么跑的</h3>
      <ol id="log"></ol>
    </div>
  </div>

  <details class="src" id="srcbox" hidden>
    <summary>来源明细 <span class="cnt" id="srccnt"></span></summary>
    <div id="src"></div>
  </details>
</div>

<script>
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const K = new URLSearchParams(location.search).get('k') || '';
// 挂在反代子路径（如 https://pi.duanz.xin:1218/reach/）时，API 跟着带前缀
const BASE = location.pathname.replace(/\/(index\.html)?$/, "");
const api = p => BASE + p + (K ? (p.includes('?') ? '&' : '?') + 'k=' + encodeURIComponent(K) : '');

let channels = [];      // /api/state 的通道
let quota = {};         // key -> {used, limit, official}
let lastRun = null;     // {q, deep, cells: {key: {status, count, note}}, stats}

function cellFor(ch){
  const run = lastRun && lastRun.cells[ch.key];
  if (run) return run;
  if (ch.streak_fail >= 3) return {status:'fail', count:0, note:'连败 ' + ch.streak_fail + ' 次，默认跳过'};
  if (ch.streak_fail > 0)  return {status:'warn', count:0, note:'上次失败 ' + ch.streak_fail + ' 次'};
  if (ch.last_ok)          return {status:'idle', count:0, note:'上次 ' + ch.last_ok.slice(5,16).replace('T',' ')};
  return {status:'idle', count:0, note:'还没跑过'};
}

// ---- 放大镜飞行：照 magpie 的 fly/pose（分段路径 + getPointAtLength + 长度缓存），
//      magpie 用喜鹊叼着请求飞，这里换成放大镜；无翅膀，靠轻微缩放呼吸补节奏。
const STILL = matchMedia("(prefers-reduced-motion: reduce)").matches;
const lenCache = new WeakMap();          // magpie 也缓存：每帧重算 getTotalLength 会拖慢页面
function pathLen(el) {
  const d = el.getAttribute("d");
  if (!d) return 0;
  let m = lenCache.get(el);
  if (!m || m.d !== d) { m = { d, L: el.getTotalLength() }; lenCache.set(el, m); }
  return m.L;
}

const LENS = '<circle cx="-5" cy="-5" r="5.2"/><path d="M-1.4 -1.4 L3.8 3.8"/>';

function flyLens(wire, ms, fail) {
  if (STILL || !wire || !pathLen(wire)) return;
  const ns = "http://www.w3.org/2000/svg";
  const g = document.createElementNS(ns, "g");
  g.setAttribute("class", "mag");
  g.innerHTML = LENS;
  $("#sky").appendChild(g);

  const L = pathLen(wire);
  const t0 = performance.now();
  requestAnimationFrame(function step(now) {
    const e = Math.min(1, (now - t0) / ms);
    const eased = 1 - Math.pow(1 - e, 2.2);           // 起步快、收尾稳
    const pt = wire.getPointAtLength(eased * L);
    const beat = 1 + Math.sin(e * Math.PI * 3) * 0.12;
    g.setAttribute("transform",
      "translate(" + pt.x.toFixed(1) + " " + pt.y.toFixed(1) + ") scale(" + beat.toFixed(3) + ")");
    g.classList.add("on");
    if (e < 1) { requestAnimationFrame(step); return; }
    g.classList.add(fail ? "fail" : "done");
    setTimeout(function () {
      g.style.transition = "opacity .35s"; g.style.opacity = "0";
      setTimeout(function () { g.remove(); }, 380);
    }, 260);
  });
}

// 一轮跑完，按通道依次把放大镜放出去 —— 视觉上就是「请求从 hub 分发到各节点」
function flyAll() {
  if (STILL) return;
  const wires = Array.prototype.slice.call(document.querySelectorAll("#wires path"));
  const rows = Array.prototype.slice.call(document.querySelectorAll("#accts li"));
  let i = 0;
  wires.forEach(function (w, idx) {
    const row = rows[idx];
    if (!row) return;
    const hit = row.classList.contains("hit") || row.classList.contains("ok");
    const fail = row.classList.contains("fail");
    if (!hit && !fail) return;
    setTimeout(function () { flyLens(w, 620, fail); }, (i++) * 55);
  });
}

function render(){
  const ul = $('#accts');
  ul.innerHTML = channels.map(ch => {
    const c = cellFor(ch);
    const q = quota[ch.key] || {};
    const pct = q.limit ? Math.min(100, (q.used || 0) / q.limit * 100) : 0;
    const barCls = pct > 85 ? 'bad' : pct > 70 ? 'warn' : '';
    const cls = c.status === 'ok' ? 'ok' : c.status === 'fail' ? 'fail' : 'idle';
    const right = q.limit
      ? (q.used || 0) + ' / ' + q.limit + (c.count ? ' · 本轮 ' + c.count + ' 条' : '')
      : (c.count ? '本轮 ' + c.count + ' 条' : '免 Key 不限量');
    return '<li class="' + cls + (c.count ? ' hit' : '') + '">' +
      '<span class="st"></span>' +
      '<span class="nm">' + esc(ch.name) + '<small>' + ch.tier + '</small></span>' +
      '<span class="right">' + esc(right) + '</span>' +
      (q.limit ? '<span class="bar"><i class="' + barCls + '" style="width:' + pct.toFixed(1) + '%"></i></span>' : '') +
      '</li>';
  }).join('');
  drawWires();
}

function drawWires(){
  const stage = $('#stage'), hub = document.querySelector('.rt-hub'), svg = $('#wires');
  if (!stage || !hub || !svg) return;
  const box = stage.getBoundingClientRect();
  if (box.width < 400) { svg.innerHTML = ''; return; }
  svg.setAttribute('viewBox', '0 0 ' + box.width + ' ' + box.height);
  const hb = hub.getBoundingClientRect();
  const x1 = hb.right - box.left + 4, y1 = hb.top + hb.height/2 - box.top;
  const narrow = box.width <= 560;
  const all = [...document.querySelectorAll('#accts li')];
  // 窄屏（抽屉里）只画本轮真正分发到的行，否则十几条线挤在一起反而看不清
  const rows = narrow ? all.filter(li => li.classList.contains('hit') || li.classList.contains('fail'))
                      : all.slice(0, 10);
  const paths = rows.map((li, i) => {
    const rb = li.getBoundingClientRect();
    const x2 = rb.left - box.left - 4, y2 = rb.top + rb.height/2 - box.top;
    const cx = (x1 + x2) / 2;
    const cls = li.classList.contains('ok') ? 'ok' : li.classList.contains('fail') ? 'fail' : '';
    const live = lastRun && i === 0 ? ' live' : '';
    return '<path class="' + cls + live + '" d="M' + x1 + ',' + y1 + ' C' + cx + ',' + y1 + ' ' +
           cx + ',' + y2 + ' ' + x2 + ',' + y2 + '"/>';
  });
  svg.innerHTML = paths.join('');
}

async function loadState(){
  try {
    const s = await (await fetch(api('/api/state'))).json();
    channels = s.channels;
    quota = {};
    for (const q of s.quota) quota[q.svc] = q;
    // 把 quota 的 key 名对齐到通道 key（brightdata <- bd 等）
    const alias = {bd: 'brightdata', fcres: 'firecrawl'};
    for (const ch of channels) {
      if (!quota[ch.key] && alias[ch.key]) quota[ch.key] = quota[alias[ch.key]];
    }
    $('#live').className = 'live';
    $('#livetxt').textContent = '实时 · 通道健康与额度' + (s.lan ? ' · 局域网' : '');
    render();
  } catch (e) {
    $('#live').className = 'live off';
    $('#livetxt').textContent = '网关无响应';
  }
}

function parseRun(md){
  const cells = {};
  const lines = md.split('\n');
  let cur = null;
  for (const raw of lines) {
    const line = raw.trimEnd();
    const m = line.match(/^###\s+(✅|⚪|❌|⚠️|🔇|💬)\s+([^—-]+)(?:——\s*(.*))?$/);
    if (m) {
      cur = {status: 'ok', count: 0, note: (m[3] || '').trim()};
      if (m[1] === '⚪') { cur.status = 'ok'; cur.note = cur.note || '0 命中'; }
      if (m[1] === '❌' || m[1] === '⚠️') { cur.status = 'fail'; cur.note = cur.note || '失败'; }
      if (m[1] === '🔇') { cur.status = 'skip'; cur.note = cur.note || '跳过'; }
      if (m[1] === '💬') { cur.note = cur.note || 'AI 摘要（非来源）'; }
      const key = matchChannel(m[2].trim());
      if (key) cells[key] = cur;
      continue;
    }
    if (cur && /^- \[/.test(line)) cur.count++;
    const sum = line.match(/\*\*汇总\*\*：([\s\S]+)/);
    if (sum) cur = cur; // 汇总行单独处理
  }
  let okc = 0, fail = 0, skip = 0;
  Object.values(cells).forEach(c => {
    if (c.status === 'ok') okc++;
    else if (c.status === 'fail') fail++;
    else skip++;
  });
  return {cells, stats: {ok: okc, fail, skip}};
}

function matchChannel(name){
  const n = name.replace(/[（(].*$/, '').trim();
  for (const ch of channels) {
    if (ch.name.startsWith(n) || n.startsWith(ch.name.replace(/[（(].*$/, '').trim())) return ch.key;
  }
  return null;
}

async function run(){
  const q = $('#q').value.trim();
  if (!q) return;
  const deep = $('#mode').value === 'deep';
  const btn = $('#go'); btn.disabled = true; btn.textContent = '跑…';
  $('#node-pill').textContent = '运行中';
  $('#what').innerHTML = '<b>' + esc(q) + '</b> · ' + (deep ? 'deep 13 路' : '默认 9 路');
  $('#node-q').textContent = q.length > 10 ? q.slice(0, 10) + '…' : q;
  $('#node-tier').textContent = deep ? 'deep' : 'L2';
  const t0 = Date.now();
  try {
    const r = await fetch(api('/api/search'), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({q, deep})
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || '失败');
    lastRun = Object.assign({q, deep}, parseRun(d.markdown));
    $('#s-req').textContent = lastRun.stats.ok;
    $('#s-fail').textContent = lastRun.stats.fail;
    $('#s-skip').textContent = lastRun.stats.skip;
    $('#node-pill').textContent = '完成';
    $('#foot-note').textContent = '本轮耗时 ' + d.secs + 's · ' +
      (deep ? 'deep 含 4 路限额通道（成功才记账）' : '默认档 9 路，7 路完全免 Key');
    renderLog(d.markdown);
    $('#src').innerHTML = renderSources(d.markdown);
    $('#srccnt').textContent = lastRun.stats.ok + ' 路有结果 · ' + lastRun.stats.fail + ' 路失败';
    $('#srcbox').hidden = false;
    $('#srcbox').open = true;
    render();
    requestAnimationFrame(function () { flyAll(); });   // 等连线画好再飞
  } catch (e) {
    $('#node-pill').textContent = '失败';
    $('#foot-note').textContent = '失败：' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = '跑一轮';
    loadState();
  }
}

function renderLog(md){
  const rows = [];
  let cur = null;
  for (const raw of md.split('\n')) {
    const line = raw.trimEnd();
    const m = line.match(/^###\s+(✅|⚪|❌|⚠️|🔇|💬)\s+(.+)$/);
    if (m) {
      cur = {mark: m[1], name: m[2].replace(/——.*$/, '').trim(), items: [], note: ''};
      const tail = m[2].match(/——\s*(.+)$/);
      if (tail) cur.note = tail[1];
      rows.push(cur);
      continue;
    }
    if (cur && /^- \[/.test(line)) cur.items.push(line);
  }
  $('#log').innerHTML = rows.map(r => {
    const cls = r.mark === '✅' || r.mark === '💬' ? 'ok' : (r.mark === '❌' || r.mark === '⚠️') ? 'fail' : '';
    const desc = r.items.length ? r.items.length + ' 条' : (r.note || (r.mark === '⚪' ? '0 命中' : '跳过'));
    return '<li class="' + cls + '"><span class="st"></span><span class="tx"><b>' +
      esc(r.name) + '</b> ' + esc(desc) + '</span></li>';
  }).join('');
  $('#logbox').hidden = rows.length === 0;
}

function renderSources(md){
  const blocks = [];
  let cur = null;
  const flush = () => { if (cur) blocks.push(cur); cur = null; };
  const lines = md.replace(/\\n/g, '\n').split('\n');
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (/^## /.test(line)) continue;
    const h = line.match(/^### (.+)$/);
    if (h) { flush(); cur = {title: h[1], note: '', items: [], text: ''}; continue; }
    if (!cur) continue;
    if (/^_.+_$/.test(line.trim())) { cur.note = line.trim().slice(1, -1); continue; }
    const it = line.match(/^- \[(.+?)\]\((.+?)\)(?: — (.*))?$/);
    if (it) { cur.items.push({t: it[1], u: it[2], x: it[3] || ''}); continue; }
    if (line.startsWith('- ')) { cur.items.push({t: line.slice(2), u: '', x: ''}); continue; }
    if (/^(\*\*|---)/.test(line)) continue;
    if (line.trim()) cur.text += line.trim() + '\n';
  }
  flush();

  return blocks.map(b => {
    // emoji 里 💬/🔇 是代理对，字符类只吃一个码点会把半个字符留在名字里 → 用 startsWith
    const MARKS = ['✅', '⚪', '❌', '⚠️', '🔇', '💬'];
    const mark = MARKS.find(m => b.title.startsWith(m)) || '';
    const name = b.title.slice(mark.length).replace(/ —— .*$/, '').trim();
    const cls = '✅💬'.includes(mark) ? 'ok' : ('❌⚠️'.includes(mark) ? 'bad' : 'idle');
    const cnt = b.items.length ? b.items.length + ' 条'
              : (mark === '⚪' ? '0 命中' : mark === '🔇' ? '跳过' : '');
    let body = '';
    if (b.items.length) {
      const shown = b.items.slice(0, 8);
      body = '<ul>' + shown.map(i => '<li>' +
        (i.u ? '<a href="' + i.u + '" target="_blank" rel="noreferrer">' + esc(i.t) + '</a>' : esc(i.t)) +
        (i.x ? '<span class="meta">' + esc(i.x) + '</span>' : '') + '</li>').join('') + '</ul>';
      if (b.items.length > shown.length) {
        body += '<div class="note">另有 ' + (b.items.length - shown.length) + ' 条未显示</div>';
      }
    } else if (b.text.trim()) {
      const txt = b.text.trim();
      body = '<p class="txt">' + esc(txt.slice(0, 900)) + (txt.length > 900 ? '…' : '') + '</p>';
    }
    const noteHtml = (b.note && b.items.length) ? '<div class="note">' + esc(b.note) + '</div>' : '';
    return '<section class="grp ' + cls + '"><h5><i></i>' + esc(name) +
           (cnt ? '<span class="cnt">' + cnt + '</span>' : '') + '</h5>' + noteHtml + body + '</section>';
  }).join('');
}

$('#go').onclick = run;
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter') run(); });
$('#refresh').onclick = loadState;
window.addEventListener('resize', () => drawWires());
loadState();
setInterval(loadState, 5000);
</script></body></html>
"""


def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def channel_meta():
    try:
        out = subprocess.run(["bash", str(FANOUT), "--list"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return []
    items = []
    for line in out.splitlines():
        m = re.match(r"\s{2}([a-z]+)\s+(base|deep)\s+(.+)$", line)
        if m:
            items.append({"key": m.group(1), "tier": m.group(2), "name": m.group(3)})
    return items


def state():
    h = load_json(HEALTH)
    q = load_json(QUOTA)
    official = q.get("_official") or {}
    chans = []
    for meta in channel_meta():
        v = h.get(meta["key"]) or {}
        chans.append({
            "name": meta["name"], "key": meta["key"], "tier": meta["tier"],
            "streak_fail": v.get("streak_fail", 0),
            "last_ok": v.get("last_ok"), "last_fail": v.get("last_fail"),
        })
    quota_rows = []
    for svc, v in q.items():
        if svc.startswith("_") or not isinstance(v, dict):
            continue
        off = official.get(svc) or {}
        if off.get("state") == "ok" and svc == "firecrawl":
            s = f"{off.get('remaining')}/{off.get('total')}"
        elif off.get("state") == "ok" and svc == "tinyfish":
            s = f"{off.get('balance')} {off.get('currency')}"
        elif off.get("state") in ("unavailable", "no_permission"):
            s = "查不到"
        else:
            s = "·"
        quota_rows.append({"svc": svc, "used": v.get("monthly", 0),
                           "limit": {"firecrawl": 1000, "exa": 2500, "brightdata": 5000}.get(svc, 0),
                           "official": s})
    stamp = next((v.get("probed_at") for v in official.values() if v.get("probed_at")), None)
    return {"channels": chans, "quota": quota_rows, "official_at": stamp, "lan": LAN}


def search(body):
    q = (body.get("q") or "").strip()
    if not q:
        return {"ok": False, "error": "缺少 q"}
    cmd = ["bash", str(FANOUT), q]
    if body.get("deep"):
        cmd.append("--deep")
    if body.get("on"):
        cmd += ["--on", str(body["on"])]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "超时（180s）"}
    return {"ok": r.returncode == 0, "markdown": r.stdout,
            "secs": round(time.time() - t0, 1),
            "error": (r.stderr or "")[-400:] if r.returncode else None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self):
        if not LAN:
            return True
        try:
            ip = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        # 反代（Caddy）从回环进来：前面已做过认证与 IP 守卫，不再要 key
        if ip.is_loopback:
            return True
        if not any(ip in net for net in ALLOWED):
            return False
        given = self.headers.get("X-Gateway-Key")
        if not given:
            given = (parse_qs(urlparse(self.path).query).get("k") or [None])[0]
        return given == KEY

    def do_GET(self):
        path = urlparse(self.path).path
        if not self._allowed():
            if path == "/":
                return self._send(403, NO_KEY_PAGE, "text/html; charset=utf-8")
            return self._send(403, '{"error":"forbidden"}', "application/json")
        if path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path == "/manifest.webmanifest":
            self._send(200, MANIFEST, "application/manifest+json; charset=utf-8")
        elif path == "/drawer.js":
            self._send(200, DRAWER_JS, "application/javascript; charset=utf-8")
        elif path in ("/icon.svg", "/icons/icon.svg"):
            self._send(200, ICON, "image/svg+xml; charset=utf-8")
        elif path == "/api/state":
            self._send(200, json.dumps(state(), ensure_ascii=False), "application/json")
        else:
            self._send(404, '{"error":"not found"}', "application/json")

    def do_POST(self):
        if urlparse(self.path).path != "/api/search":
            return self._send(404, '{"error":"not found"}', "application/json")
        if not self._allowed():
            return self._send(403, '{"error":"forbidden"}', "application/json")
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, '{"error":"bad json"}', "application/json")
        self._send(200, json.dumps(search(body), ensure_ascii=False), "application/json")


ALLOWED = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "192.168.5.0/24", "10.7.0.0/24")]


def main(argv):
    global LAN, KEY
    port = PORT
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    LAN = "--lan" in argv
    if LAN:
        DATA.mkdir(parents=True, exist_ok=True)
        if not KEYFILE.exists() or not KEYFILE.read_text().strip():
            KEYFILE.write_text(secrets.token_urlsafe(16), encoding="utf-8")
            KEYFILE.chmod(0o600)
        KEY = KEYFILE.read_text().strip()
    host = "0.0.0.0" if LAN else "127.0.0.1"
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"d-reach gateway → http://{host}:{port}/" + (f"?k={KEY}" if LAN else ""))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main(sys.argv[1:])
