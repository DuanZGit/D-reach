# pi-web 侧滑抽屉（油猴脚本）

在 pi-web 页面里点一下（侧边栏入口 / 右下角"路由"按钮 / `Alt+R`），从右侧滑出 d-reach 网关面板。

## 为什么是油猴，不是 pi-web 插件

pi-web 是 Next.js 打包产物，扩展点只到服务端会话事件，**没有 UI 插件槽**；
它渲染 markdown 时还会把 `<iframe>` strip 掉。想在不改它产物的前提下加自定义界面，
只能从浏览器侧注入。

## 安装

1. 浏览器装 Tampermonkey（或 Violentmonkey）
2. 新建脚本，粘贴 `d-reach-drawer.user.js` 全文，保存
3. 打开 `https://pi.duanz.xin:1218/`，点右下角"路由"或按 `Alt+R`

## 行为

- 面板里是 iframe 加载的 `/reach/`，复用 pi-web 登录态，不需要再输网关 key
- **默认不加载**：不点开就不发请求
- 侧边栏能识别就挂一个入口；识别不到只留悬浮按钮（pi-web 重渲染后会自动补回）
- 样式走 Shadow DOM，不会污染 pi-web 自己的样式

## 限制

- 手机 Chrome 不支持油猴（需要 Kiwi / Firefox）。手机用 PWA：浏览器开 `/reach/` →
  菜单 →「添加到主屏幕」
