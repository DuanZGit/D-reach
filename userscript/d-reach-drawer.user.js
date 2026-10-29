// ==UserScript==
// @name         pi-web · d-reach 路由抽屉
// @namespace    duanz.local.dreach-drawer
// @version      1.0.0
// @description  在 pi-web 里侧滑出一个 d-reach 网关面板（通道健康 / 额度 / 直接检索）。复用 pi-web 登录态，不碰它的构建产物，升级不丢。
// @match        https://pi.duanz.xin:1218/*
// @match        https://pi.duanz.xin:12180/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";
  if (window.top !== window.self) return; // 不在 pi-web 自己的 iframe 里跑

  const REACH = "/reach/";
  const HOST_ID = "dreach-drawer-host";
  if (document.getElementById(HOST_ID)) return;

  const host = document.createElement("div");
  host.id = HOST_ID;
  document.documentElement.appendChild(host);
  const root = host.attachShadow({ mode: "open" });

  root.innerHTML = `
    <style>
      :host { all: initial; }
      .fab {
        position: fixed; right: 18px; bottom: 18px; z-index: 2147483000;
        width: 46px; height: 46px; border-radius: 50%;
        background: #1c1c21; color: #fff; border: none; cursor: pointer;
        box-shadow: 0 6px 18px rgba(0,0,0,.22);
        font: 600 13px/1.1 system-ui, -apple-system, "PingFang SC", sans-serif;
        display: flex; align-items: center; justify-content: center;
        transition: transform .18s cubic-bezier(.2,.8,.2,1), opacity .18s;
      }
      .fab:hover { transform: translateY(-2px); }
      .fab.hidden { opacity: 0; pointer-events: none; }
      .mask {
        position: fixed; inset: 0; z-index: 2147482999;
        background: rgba(0,0,0,.28); opacity: 0; pointer-events: none;
        transition: opacity .24s ease;
      }
      .mask.on { opacity: 1; pointer-events: auto; }
      .panel {
        position: fixed; top: 0; right: 0; bottom: 0; z-index: 2147483000;
        width: min(460px, 92vw); background: #f2f2f5;
        transform: translateX(102%); transition: transform .3s cubic-bezier(.3,.9,.3,1);
        box-shadow: -8px 0 28px rgba(0,0,0,.16);
        display: flex; flex-direction: column;
      }
      .panel.on { transform: translateX(0); }
      .head {
        display: flex; align-items: center; gap: 8px;
        padding: 10px 12px; border-bottom: 1px solid rgba(0,0,0,.08);
        background: #fff;
        font: 600 13px/1.4 system-ui, -apple-system, "PingFang SC", sans-serif;
        color: #1c1c21;
      }
      .head .dot { width: 7px; height: 7px; border-radius: 50%; background: #189a58; }
      .head .grow { flex: 1; }
      .head button {
        border: 1px solid rgba(0,0,0,.12); background: #fff; color: #4b4b53;
        border-radius: 7px; font: 500 12px/1 system-ui, sans-serif;
        padding: 6px 9px; cursor: pointer;
      }
      .head button:hover { background: #f4f4f7; }
      iframe { flex: 1; width: 100%; border: 0; background: #f2f2f5; }
    </style>
    <button class="fab" id="fab" title="d-reach 路由（Alt+R）">路由</button>
    <div class="mask" id="mask"></div>
    <section class="panel" id="panel" aria-label="d-reach 网关">
      <div class="head">
        <span class="dot"></span>
        <span>d-reach · 路由与额度</span>
        <span class="grow"></span>
        <button id="openTab" title="在新标签页打开">新窗口</button>
        <button id="close" title="关闭（Esc）">关闭</button>
      </div>
      <iframe id="frame" title="d-reach 网关"></iframe>
    </section>
  `;

  const $ = (s) => root.querySelector(s);
  const fab = $("#fab"), mask = $("#mask"), panel = $("#panel"), frame = $("#frame");
  let loaded = false;

  function open() {
    if (!loaded) {
      frame.src = REACH; // 延迟加载：不开就不请求
      loaded = true;
    }
    panel.classList.add("on");
    mask.classList.add("on");
    fab.classList.add("hidden");
  }

  function close() {
    panel.classList.remove("on");
    mask.classList.remove("on");
    fab.classList.remove("hidden");
  }

  fab.addEventListener("click", open);
  mask.addEventListener("click", close);
  $("#close").addEventListener("click", close);
  $("#openTab").addEventListener("click", () => window.open(REACH, "_blank", "noopener"));

  document.addEventListener("keydown", (e) => {
    if (e.altKey && (e.key === "r" || e.key === "R")) {
      e.preventDefault();
      panel.classList.contains("on") ? close() : open();
    } else if (e.key === "Escape" && panel.classList.contains("on")) {
      close();
    }
  });

  // 侧边栏里也挂一个入口（找得到就挂，找不到就只留悬浮按钮；pi-web 重渲染后自动补回）
  const MENU_TEXT = "d-reach 路由";
  function injectMenuItem() {
    const menu = document.querySelector(".sidebar-menu");
    if (!menu || menu.querySelector('[data-dreach-entry="1"]')) return;
    const item = document.createElement("button");
    item.type = "button";
    item.dataset.dreachEntry = "1";
    item.textContent = MENU_TEXT;
    item.style.cssText = [
      "display:block", "width:100%", "text-align:left", "padding:7px 12px",
      "margin:2px 0", "border:0", "border-radius:7px", "background:transparent",
      "color:inherit", "font:inherit", "cursor:pointer", "opacity:.9",
    ].join(";");
    item.addEventListener("mouseenter", () => (item.style.background = "rgba(0,0,0,.05)"));
    item.addEventListener("mouseleave", () => (item.style.background = "transparent"));
    item.addEventListener("click", open);
    menu.appendChild(item);
  }

  let scheduled = false;
  const obs = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      injectMenuItem();
    });
  });
  obs.observe(document.body, { childList: true, subtree: true });
  injectMenuItem();
})();
