# 抓取与网页阅读

BrightData / Jina / Firecrawl / browser_use。本机**没有注册 BrightData 或 Exa 的 MCP**，
一律走 REST（`minis-mcp-cli call brightdata ...` 这类命令是历史遗留，不要用）。

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

只吃 URL，不吃关键词。**读不了微信公众号**（被 CAPTCHA 拦）→ 改用 BrightData。

## 微信公众号

```bash
# 搜公众号文章：Exa 限定域名
curl -s --max-time 30 -X POST https://api.exa.ai/search \
  -H "x-api-key: $EXA_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"关键词","numResults":5,"includeDomains":["mp.weixin.qq.com"]}'

# 读全文：BrightData 抓 mp.weixin.qq.com/s/xxx
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

`browser_use`（Minis 内置）：navigate → wait_for_dom_stable → get_readable / screenshot。

## RSS

```bash
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')"
```
