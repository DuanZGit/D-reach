# pi-web 内嵌 d-reach 抽屉

两条路，**优先用第一条**（改 pi-web 产物，不用装浏览器插件，手机 Chrome 也能用）。

## 一、注入 client chunk（推荐）

`scripts/patch-piweb.py` 在 pi-web 的 client chunk 末尾追加一段加载器，
加载器再去取网关下发的 `/reach/drawer.js`。

```bash
python3 scripts/patch-piweb.py            # 打补丁
python3 scripts/patch-piweb.py --check    # 看有没有
python3 scripts/patch-piweb.py --revert   # 撤销
```

为什么这么做：pi-web 的 npm 包只发编译产物（`files: bin/.next/public`），没有源码；
首页是 SSR，改 `index.html` 没效果。chunk 末尾追加是唯一不改 React 代码的稳定注入点。

**真正的 UI 代码在 `/reach/drawer.js`（网关下发）**，以后改抽屉只改网关，
不用再动 pi-web 产物。pi-web 升级后 chunk hash 会变，重跑一次脚本即可。

打完要**强刷一次**（Ctrl+Shift+R）——chunk 文件名没变，普通刷新可能吃缓存。

## 二、油猴脚本（备选）

浏览器装 Tampermonkey，粘贴 `d-reach-drawer.user.js`。适合不想动 node_modules 的情况；
手机 Chrome 不支持油猴。

## 行为

- 右下角「路由」按钮 / 侧边栏「d-reach 路由」 / `Alt+R` → 右侧滑出 `/reach/`
- 复用 pi-web 登录态，不再要网关 key
- 不点不加载（`iframe.src` 第一次打开才赋值）
