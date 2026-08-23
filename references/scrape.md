# 爬虫工具

BrightData MCP、Firecrawl、Jina Reader 的统一入口。

## BrightData MCP（已配置）

BrightData MCP 提供 69 个工具，覆盖搜索、爬虫、结构化提取、浏览器自动化。
当前已安装并连接，基础 5 工具默认启用，其他组可按需开启。

### 搜索类（默认启用）

| 工具 | 说明 | 调用示例 |
|------|------|---------|
| `search_engine` | Google/Bing/Yandex 搜索，返回 JSON/Markdown | `minis-mcp-cli call brightdata search_engine --input '{"query":"xxx","engine":"google"}'` |
| `search_engine_batch` | 批量搜索（最多 10 个查询） | `minis-mcp-cli call brightdata search_engine_batch --input '{"queries":[{"query":"q1"},{"query":"q2"}]}'` |
| `discover` | AI 相关性排序搜索，支持 intent、geo、日期过滤 | `minis-mcp-cli call brightdata discover --input '{"query":"xxx","num_results":5}'` |

### 爬虫类（默认启用）

| 工具 | 说明 | 调用示例 |
|------|------|---------|
| `scrape_as_markdown` | 单 URL 抓取，返回 Markdown | `minis-mcp-cli call brightdata scrape_as_markdown --input '{"url":"https://example.com"}'` |
| `scrape_batch` | 批量抓取（最多 10 个 URL） | `minis-mcp-cli call brightdata scrape_batch --input '{"urls":["https://a.com","https://b.com"]}'` |

### 结构化提取（需启用对应组）

| 工具组 | 说明 | 启用方式 |
|--------|------|---------|
| `ecommerce` | Amazon、Walmart、eBay 等电商数据 | `GROUPS=ecommerce` |
| `social` | LinkedIn、Instagram、TikTok、YouTube、X、Reddit | `GROUPS=social` |
| `browser` | 远程浏览器自动化（13 个工具） | `GROUPS=browser` |
| `business` | Crunchbase、ZoomInfo、Google Maps 评论 | `GROUPS=business` |
| `finance` | Yahoo Finance | `GROUPS=finance` |
| `research` | GitHub 文件读取 | `GROUPS=research` |
| `app_stores` | Google Play、Apple App Store | `GROUPS=app_stores` |
| `travel` | Booking.com | `GROUPS=travel` |
| `geo` | ChatGPT/Grok/Perplexity 响应收集 | `GROUPS=geo` |
| `code` | npm/PyPI 包数据 | `GROUPS=code` |
| `advanced_scraping` | HTML 抓取、AI 提取、会话统计 | `GROUPS=advanced_scraping` |

**启用多组示例：**
```bash
# 本地 npx 方式
GROUPS="ecommerce,social,business,research,code,advanced_scraping" npx @brightdata/mcp

# Minis MCP 配置方式：在 servers.json 的 env 里加 GROUPS 环境变量
```

### 免费额度策略

- 每月 5,000 次免费请求
- 优先用 `search_engine_batch` / `scrape_batch`（一次顶 10 次）
- 慎用 `scraping_browser_*`（一次交互消耗 3-5 次请求）

---

## Firecrawl（已安装）

Firecrawl Python SDK 已安装（`firecrawl-py`），适合将任意网页转为 Markdown/JSON。

### 基本用法

```python
from firecrawl import Firecrawl

app = Firecrawl(api_key="YOUR_API_KEY")  # 需要 API key

# 抓取单页
result = app.scrape("https://example.com")

# 搜索
results = app.search("query")

# 提取结构化数据
result = app.extract("https://example.com", params={...})
```

### 免费额度

Firecrawl 有免费 tier，具体额度取决于账号。如无 API key，可用 BrightData MCP 替代。

---

## Jina Reader（零配置）

```bash
# 通用网页阅读
curl -s "https://r.jina.ai/URL"

# 示例
curl -s "https://r.jina.ai/https://example.com/article"
```

适用场景：大多数网页可以直接用 Jina Reader 读取，无需认证。

---

## 选择指南

| 场景 | 首选 | 备选 | 兜底 |
|------|------|------|------|
| 通用网页抓取 | BrightData `scrape_as_markdown` | Jina Reader | Firecrawl |
| 批量网页抓取 | BrightData `scrape_batch` | Firecrawl | - |
| 结构化数据（电商/社交/商业） | BrightData `web_data_*` | 无 | 手动解析 |
| 需要登录/交互的站点 | BrightData `scraping_browser_*` | browser_use | - |
| 纯文本提取 | Jina Reader | BrightData | - |
