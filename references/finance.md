# 金融行情

雪球股票行情、搜索与热门内容。行情可能延迟，不构成投资建议。

## OpenCLI（**本机不可用**：需要桌面 Chrome + Bridge 扩展）

> 2026-09-05 实测 `opencli xueqiu whoami` → `BROWSER_CONNECT / Browser Bridge extension not connected`。
> Minis 沙箱没有 Chrome，这条通道在这里必然失败 —— 直接跳到下面的「本环境推荐路径」。
> 在装了 Chrome 且登录过雪球的桌面机上，它是最省事的：

```bash
opencli xueqiu whoami -f yaml                  # 验证登录态
opencli xueqiu search "英伟达" -f yaml
opencli xueqiu stock NVDA -f yaml              # 实时行情
opencli xueqiu hot -f yaml ; opencli xueqiu hot-stock -f yaml
opencli xueqiu comments SH600519 -f yaml       # 个股讨论
opencli xueqiu kline SH600519 -f yaml          # 历史K线
```

OpenCLI 只复用用户已经存在且明确控制的浏览器会话。不要自动执行
`opencli xueqiu login`；没有现成登录态时，让用户先在 Chrome 登录，或显式导入
雪球所需的最小 Cookie：

```bash
# 本机没有 agent-reach CLI。要 cookie 就用 browser_use：
# 先在浏览器登录雪球，再 browser_use get_cookies（keywords: xq_a_token）
```

该配置只读取并保存 `xq_a_token`，不会顺带采集其他平台 Cookie。

## 验收与失败处理

- 以返回股票名称、代码、价格或非空内容列表为成功；退出码 0 但字段为空不算成功。
- HTTP 400 通常是会话/Cookie 问题，不表示股票代码不存在。
- `whoami` 成功而 `stock`/`hot` 失败时，按适配器解析或平台接口问题报告，不要误诊成未登录。

## 本环境推荐路径

### ✅ 免 Key 免费财经通道（不记账）

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

# 巨潮资讯 cninfo —— A 股【法定披露】权威公告源（比任何二手转述都硬）
#   返回 announcements[]：secCode/secName/announcementTitle/announcementTime/adjunctUrl
#   原文 PDF = http://static.cninfo.com.cn/ + adjunctUrl
curl -s -X POST "http://www.cninfo.com.cn/new/hisAnnouncement/query" \
  -H "User-Agent: $UA" -H "Content-Type: application/x-www-form-urlencoded" \
  -d "pageNum=1&pageSize=20&column=szse&tabName=fulltext&searchkey=回购&seDate="
#   column: szse=深/沪(含全市场全文检索)；另可用 sse / third / bj
#   searchkey 支持公司名或公告标题词；需要精确到公司用 stock=<code>,<orgId>

# 雪球热帖（⚠️ 需登录 cookie xq_a_token，无 token 会被 WAF 拦）
#   listV3.json 已 404 废弃；listV2.json 返回 200 但内容是 WAF renderData 页（不是帖子数据）
curl -s "https://xueqiu.com/query/v1/statuses/hot/listV2.json" \
  -H "User-Agent: $UA" -H "Referer: https://xueqiu.com/" -H "Cookie: xq_a_token=$XQ_TOKEN"
#   无 token 时降级：BrightData 抓 https://xueqiu.com/ 页面，或直接走 gushen 的行情（不需要 cookie）

# 东方财富 / 同花顺 —— ✅ 可达（页面级，行情与研报摘要）
```

| 需求 | 首选 | 说明 |
|------|------|------|
| A股公告/回购/减持/年报 | **巨潮 cninfo** ✅免 | 法定披露原文 PDF，可引用 |
| 行情（A股/美股） | gushen（`cn_market.py`） | 已封装，不需 cookie |
| 社区观点/情绪 | 雪球（⚠️ 需 xq_a_token） | 非事实源，只作情绪参考 |
| 实时快讯 | 财联社页面（⚠️ 旧 nodeapi 已失效） | 需现场探接口 |

> ⚠️ **实测（2026-09-11）**：雪球 `query/v1/statuses/hot/listV3.json` → **404 已废弃**；
> `statuses/hot/listV2.json` → 200 但返回 WAF 页；`stock.xueqiu.com/v5/stock/hot_stock` → 400 要登录。
> 结论：**雪球免 Key 通道已废**，要么给 `xq_a_token`，要么走 BrightData 抓页面。

### 行情与页面抓取

```bash
# 1) A股/美股实时行情（gushen）
<gushen_path>/tools/cn_market.py a 600519          # A股（gushen 需自行安装）
<gushen_path>/tools/cn_market.py quote usNVDA usQQQ # 美股

# 2) 雪球页面/社区内容（jina_reader 或统一爬取）
curl -s -X POST https://api.brightdata.com/request -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" \
  -H "Content-Type: application/json" \
  -d '{"zone":"mcp_unlocker","format":"raw","data_format":"markdown","url":"https://xueqiu.com/S/SH600519"}'
```
