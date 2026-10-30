# 抓取与网页阅读

BrightData / Jina / Firecrawl / browser_use。本机**没有注册 BrightData 或 Exa 的 MCP**，
一律走 REST（`minis-mcp-cli call brightdata ...` 这类命令是历史遗留，不要用）。

## 抓取顺序：先便宜后贵，每档都过同一套判据

**别一上来就 BrightData。** 按下面顺序走，一档拿不到就降一档；每档拿回文本后先过
「假成功的六种形态」（见文末），过了才算成。

| # | 档 | 成本 | 什么时候用它 |
|---|---|---|---|
| ① | 微信直连 | 免费 | `mp.weixin.qq.com/s/...`，见下节 |
| ② | cookie 注入 | 免费 | 飞书 / 小红书等登录态站点 |
| ③ | curl 直连 | 免费，0.1s | **默认起点**。桌面 UA + `--compressed` |
| ④ | 本地 Playwright | 免费，1.5s | curl 拿回空壳（正文靠 JS 渲染） |
| ⑤ | TinyFish fetch | 免费额度 | ④ 也失败时的托管渲染 |
| ⑥ | Jina Reader | 免费额度 | 零配置兜底 |
| ⑦ | BrightData | 5000 次/月 | 真反爬站 |
| ⑧ | archive.today | 免费 | 公开存档兜底（本机这条出站不通，见下） |

③ 的模板：

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
curl -sL --compressed --max-time 25 -A "$UA" \
  -H 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8' \
  -w '\n%{http_code}\t%{content_type}\t%{url_effective}' \
  "$URL" -o /tmp/page.body
# 先看状态码和 content-type 再决定怎么读：429/503 停手，application/pdf 走 pymupdf，image/* 直接放弃
```

④ 的模板（需要 node + playwright；没装就跳过这档）：

```bash
node "$SKILLS/d-reach/plugin/scripts/render.mjs" "$URL"
# 输出单行 JSON：{ok,text,html,chars,lines,avgLine,linkDen,finalUrl,ms,err}
# avgLine / linkDen 是判骨架页用的，别丢
```

渲染档比 curl 多拿三样东西：**跑完 JS 的 DOM**、**子框架里的正文**、**Shadow DOM 里的正文**。
`<noscript>` 在真浏览器里是没意义的，渲染前要整块删掉 —— 脚本启用时浏览器把它当原始文本，
innerText 会把里面的整段 JS 吐出来（实测淘宝搜索页吐了 4 万字 JS 冒充正文）。

装了 pi 插件就直接 `d_reach_fetch`，上面八档和判据它内部都做了，不用手写。

## BrightData Web Unlocker（反爬主力，5000 次/月）

```bash
# 抓成 Markdown
curl -s --max-time 120 -X POST https://api.brightdata.com/request \
  -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" -H "Content-Type: application/json" \
  -d '{"zone":"mcp_unlocker","format":"raw","data_format":"markdown","url":"https://example.com"}'

# 抓成 HTML：data_format 换成 "html"
# Google 搜索结果：data_format 用 "parsed_light"（才返回 JSON），url 自己拼
#   https://www.google.com/search?q=<urlencoded>&num=10   （&gl=cn 指定地区，&start=<cursor> 翻页）
```

- `zone` 默认 `mcp_unlocker`；可用 zone 列表：`curl -s -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" https://api.brightdata.com/zone/get_active_zones`
- 批量：没有单次多 URL 端点，循环调用即可（一次别超过 10 个，记得每个都 `quota.py use brightdata`）
- 慎用解锁浏览器类接口（一次交互消耗 3–5 次请求）
- 真实用量对账：`curl -s -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" https://api.brightdata.com/account/usage`

## Jina Reader（零配置兜底）

```bash
curl -s --max-time 30 "https://r.jina.ai/https://example.com/article"
```

只吃 URL，不吃关键词。微信公众号走单独一条直连档（见下），别用 Jina。

## 微信公众号

**永久链 `/s/*` 先走直连，不要一上来就 BrightData。** 2026-10-29 实测：桌面 UA、
不带 cookie、不开浏览器，`curl -A "<桌面 Chrome UA>"` 直接拿回完整 HTML，正文是服务端渲染进
`#js_content` 的（测的两条链接分别得 1463 字 / 9968 字正文），不触发验证码。

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
curl -sL --compressed --max-time 25 -A "$UA" "https://mp.weixin.qq.com/s/xxx" -o /tmp/wx.html
# 判成败看标记，不看字数：验证码页也很长
grep -q 'id="js_content"' /tmp/wx.html && echo 正文在 || echo 被风控了
# 抽正文：从外层 <div 起按 div 开合配平，取出整个子树，再剥标签
#   ✗ 不要「切到下一个 <script>」：微信正文里自带 script，实测会砍掉近半正文（1231 vs 1383 字）
#   ✗ 也不要贪婪到页尾：会把相关推荐、页尾全吃进来
```

- 装了插件就直接 `d_reach_fetch`，它内部就是这个逻辑（`viaWeixinDirect`），免费不耗额度。
- **两种链接形态都要认**：永久链是 `/s/<token>`，历史文章和分享链是 `/s?__biz=...&sn=...`。
  只按 `/s/` 判断会把长链漏到通用档去，白跑完八档才拿到导航。
- **老文章链接缺 `chksm` 参数会拿到验证页**，这不是限流也不是工具问题：
  微信只接受带 `chksm` 的旧文章链接。要从文章页复制完整链接，别自己拼 `__biz/mid/idx/sn`。
- **安全验证页要当场认出**：响应里出现 `secitptpage/verify`（约 17KB、只有 JS、没有 `#js_content`）
  就是被风控了，立刻停手（0.3s），别把八档跑一遍（实测 37–43 秒且只会加重）。
  加 `Referer`、加 `Accept-Language` 实测都无效。
- **批量仍会撞风控**：实测每抓 13~21 篇后要锁 15~27 分钟。批量任务必须有退避，不要并发轰。
- 主页 / 视频号 / 历史推送列表（`/mp/profile_ext`、`/mp/homepage`、`/cgi-bin/`、`/finder/`）
  是 JS 渲染 + 强反爬，直连必失败，这些才需要浏览器会话或 BrightData。
- 备用：BrightData 抓 `mp.weixin.qq.com/s/xxx`。**注意未过 KYC 的账户会被 robots.txt 合规拒绝**
  （实测返回 `bad_endpoint`），这条只有你完成 KYC 后才可用。

```bash
# 搜公众号文章：Exa 限定域名
curl -s --max-time 30 -X POST https://api.exa.ai/search \
  -H "x-api-key: $EXA_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"关键词","numResults":5,"includeDomains":["mp.weixin.qq.com"]}'
```

## Firecrawl

```bash
# Developer Index：编程文档/issue/PR，免 key
curl -s --max-time 40 "https://api.firecrawl.dev/v2/search/developer?query=tokio+retry&k=5"

# Research Index：学术论文，需 FIRECRAWL_API_KEY，不耗 credits
curl -s --max-time 40 -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  "https://api.firecrawl.dev/v2/search/research/papers?query=LLM+agent+memory&k=5"
```

SDK（`firecrawl-py`）本机已装，但 Free plan 1000 credits/月会消耗 —— 默认不用它抓取，
显式要用再 `python3 -c "from firecrawl import Firecrawl; print(Firecrawl().scrape('https://example.com').markdown)"`。

## 需要登录的站点

**优先 cookie 注入，其次 browser_use。** cookie 由 `cookie-getter` 油猴脚本在自己浏览器里抓、
推送到面板，落到 `~/.secrets/console_cookies.txt`；`load_key.sh` 已把该文件加进查找链，
所以直接按槽位名取，值不经过对话：

```bash
CK=$(sh scripts/load_key.sh FEISHU_COOKIE "") || echo "没配，去 cookie-getter 抓一次"
curl -sL -A "$UA" -H "Cookie: $CK" "https://xxx.feishu.cn/docx/xxx"
```

- 已映射槽位：`FEISHU_COOKIE`（飞书/飞书国际版）、`XHS_COOKIE`（小红书）。
- cookie 过期表现为「抓回来是登录页」，`d_reach_fetch` 会把这档分类成 `login` 并提示。
- **不要把 cookie 值 echo / 写进 markdown / 贴进对话**；要查存在与否走 `safe_inspect`。
- 拿不到 cookie 时退到 `browser_use`（Minis 内置）：navigate → wait_for_dom_stable → get_readable / screenshot。

## 抓取失败了怎么分诊（别无脑重试）

`d_reach_fetch` 现在按六类报错，用途是决定「该不该再试」：

| 分类 | 含义 | 正确动作 |
|---|---|---|
| 网络不通 | 超时 / 000 / 证书过期（curl 退出码 60） | 先重试 1 次（本机出口有间歇抖动），仍不行才换通道 |
| 反爬/验证码 | 风控页、Cloudflare 挑战、登录页 | **不要重试**，越试越狠。转人工或换 BrightData |
| 登录墙 | 登录后才可见、cookie 过期 | 补 cookie，或让用户贴正文 |
| 付费墙 | 订阅/会员才给全文 | 别硬绕；问用户要不要公开存档的版本 |
| 限流/429 | 服务端明说「太快了」 | **立即停手**，等 `Retry-After` 再说；换通道/换域名都没用 |
| 重定向环 | 页面把自己重定向回自己 | 别重试，先看原始链接是不是坏了 |
| 站点太慢 | curl 和本地浏览器都超时 | 别继续跑限额通道（实测救不回来，只烧额度）；换时段再试 |
| 解析不出 | 拿到了但提取失败 | 换解析通道（TinyFish 真渲染 / Jina） |

另有两种「不是失败、是不该抓」的短路：`不是网页正文`（PDF 无文字层 / 图片 / 二进制直链）
会直接停掉剩下七档 —— 一个 PNG 走完全部档要 20 秒以上，最后还会把图片字节当 markdown 返回。

**骨架页判据**（借鉴 trafilatura 的「长度 + 链接密度」打分）：有 DOM 指标时看「平均每行字符数」
与「链接文本占比」，纯文本通道看「平均行长 + 长行数量」。实测正文页平均行长是骨架页的 4–18 倍
（微信公众号 52.5 vs 贴吧列表 8.9），所以贴吧那种「两万字但全是链接」的页面会被正确判成骨架。

**最后一档兜底是公开存档** `https://archive.ph/newest/<url>`：不改请求头、不冒充爬虫、不花额度。
**⚠️ 本机实测不可达**（2026-10-29：`archive.ph` 两次 GET 均 000、0 字节；
对照 `github.com` 同为 fake-ip 却可用，所以不是解析器问题，是这条出站路由不通）。
代码里这档保留了（失败会快速跳过并归类），别指望它在当前网络下真的救回来。

**不做 UA 伪装和 X-Forwarded-For 伪造** —— 那是冒充搜索引擎骗内容授权，风控打在共用出口 IP 上，
封的是本机不是别人，且本机无法自行解封。

## RSS

`d_reach_fetch` 直接吃 RSS/Atom，会按条目展开成「标题 + 摘要」，不用自己 feedparser。

```bash
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')"
```

## 不只是网页：PDF / JSON / 纯文本

`d_reach_fetch` 按响应头分派，这些都不用另外起通道：

| 类型 | 行为 |
|---|---|
| `application/pdf` | 抽文字层（pymupdf，本机已装）。100 页技术报告 2.1s / 28 万字符。无文字层（扫描件）直接报「需 OCR」并停手 —— 本机没有 tesseract |
| `application/json` | 格式化返回；>4MB 不解析（防爆内存），>40 万字符截断 |
| RSS / Atom | 按 `<item>`/`<entry>` 展开标题 + 摘要；描述里转义过的 HTML 会先反转义再剥标签 |
| `text/plain` | 原样返回 |
| `image/*` `video/*` `audio/*` zip/office | 立刻判「不是网页正文」并停手，不走降级链 |

**编码**：GBK / GB2312 老站（政府、老论坛）按「响应头 charset → meta charset → UTF-8/GB18030 自动择一」解码。
响应头不声明 charset 的中文站是常态，别假设 UTF-8。
**UTF-16 页面看 BOM**（`FF FE` 小端 / `FE FF` 大端），按 UTF-8 读出来每个字之间夹一个空字节，
下面的 U+FFFD 比例探测也会失效。

**JSONP**（`cb({...});` 包一层函数调用）要先把外层剥掉再按 JSON 解析 ——
跨域接口常见，不剥就只能当网页处理，然后被标签清洗和字符数判据全部判死。

**iframe 内嵌正文**（老政府站、招聘站、文档预览）：Playwright 档会遍历子框架取正文，
主文档只有导航时自动拼接。curl 档看不到 iframe 里的内容，这种站必须走渲染档。

**同样是「正文不在主文档里」的还有四种**，都要走渲染档：

| 形态 | 特征 | 怎么拿 |
|---|---|---|
| `<frameset>` | 老站，没有 `<body>`，直接 `104 字符` | 渲染档自动遍历 `page.frames()` |
| `meta refresh` | `<meta http-equiv=refresh content="0;url=...">`，curl 不跟随 | 渲染档会自动跳，但要等跳完再取 |
| Shadow DOM | Web Components，`innerText` 拿不到影子树 | 递归 `shadowRoot` 逐层取文本 |
| 正文在 `<noscript>` | 给爬虫看的那种 | curl 档直接取；渲染档先删 `<noscript>` 再取 |

渲染档从子框架/影子树取到的文本要过一道「像不像源码」的检查：符号密度（`;{}()[]=<>|&$`）
超过 4% 就不要 —— 实测淘宝把 JS bundle 塞进子框架，innerText 拿到 15 万字源码冒充正文。

## 假成功的六种形态（这节最重要）

抓回来的东西「非空」不等于「拿到了」。下面六种都是又长又完整、按字数判会过关的假成功：

| # | 形态 | 怎么认 | 实测样本 |
|---|---|---|---|
| 1 | **登录页** | 页头出现「个人用户登录/企业用户登录/手机扫码安全登录」「登录探索更多内容」 | 京东搜索页 194 字符；贴吧列表 1367 字符零帖子 |
| 2 | **骨架页** | 平均每行 < 12 字，或「平均每行 < 18 字 + 链接文本占比 > 50%」 | 贴吧 3972 字符 / 平均 8.9 字；淘宝 139 字符 / 2.9 字 |
| 3 | **原始 HTML 冒充正文** | 正文里出现 `<meta charset`、`<!doctype html`、`<html>`、`<body>` | TinyFish 对淘宝吐出 21 万字源码 |
| 4 | **JS 源码冒充正文** | 符号密度异常高，出现 `function(`、`!function(e)` | 淘宝子框架 15 万字 bundle |
| 5 | **抓取方自报空壳** | 正文里有 `maybe not yet fully loaded`、`cached snapshot` | Jina 对纯 JS 页返回 526 字符 + 这句 |
| 6 | **扫描件 PDF** | PDF 有页数但抽不出文字 | arxiv 论文没事，扫描件必须报「需 OCR」 |

**电商页另外加一条**：淘宝/天猫/京东的列表页和详情页有商品就一定有价格符号（`¥` / `￥`）。
只剩导航 + 「加载中...」而没有价格时，就是空壳，不管字符数多长。

判据的顺序很重要：**先看「太短」（< 120 字符）再看「骨架」**。两者都命中时
宁说「内容不足」也不要说「反爬」—— 后者会让人去搞 cookie，而其实只是页面没东西。
