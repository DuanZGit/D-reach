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

```bash
# 1) A股/美股实时行情（gushen）
<gushen_path>/tools/cn_market.py a 600519          # A股（gushen 需自行安装）
<gushen_path>/tools/cn_market.py quote usNVDA usQQQ # 美股

# 2) 雪球页面/社区内容（jina_reader 或统一爬取）
curl -s -X POST https://api.brightdata.com/request -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" \
  -H "Content-Type: application/json" \
  -d '{"zone":"mcp_unlocker","format":"raw","data_format":"markdown","url":"https://xueqiu.com/S/SH600519"}'

# 3) 雪球热帖（公开 JSON API）
curl -s "https://xueqiu.com/query/v1/statuses/hot/listV3.json" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" \
  -H "Referer: https://xueqiu.com/" 2>/dev/null | head -c 2000
```
