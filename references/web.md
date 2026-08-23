# 网页阅读

通用网页、微信公众号、RSS。

## BrightData MCP 网页抓取（已配置）

BrightData MCP 提供 2 个默认启用的抓取工具：

| 工具 | 说明 | 调用示例 |
|------|------|---------|
| `scrape_as_markdown` | 单 URL 抓取，返回 Markdown | `minis-mcp-cli call brightdata scrape_as_markdown --input '{"url":"https://example.com"}'` |
| `scrape_batch` | 批量抓取（最多 10 个 URL） | `minis-mcp-cli call brightdata scrape_batch --input '{"urls":["https://a.com","https://b.com"]}'` |

**适用场景**：任何公开网页，自动处理 bot detection、CAPTCHA、代理轮换。

## Firecrawl（已安装）

```python
from firecrawl import Firecrawl

app = Firecrawl(api_key="YOUR_API_KEY")

# 抓取单页
result = app.scrape("https://example.com")
```

**适用场景**：需要将网页转为 Markdown/JSON，适合批量抓取。

## 通用网页 (Jina Reader)

```bash
# 读取任意网页内容
curl -s "https://r.jina.ai/URL"

# 示例
curl -s "https://r.jina.ai/https://example.com/article"
```

**适用场景**: 大多数网页可以直接用 Jina Reader 读取。

## Web Reader (MCP)

```bash
# 读取网页内容 (Markdown 格式)
mcporter call 'web-reader.webReader(url: "https://example.com")'

# 保留图片
mcporter call 'web-reader.webReader(url: "https://example.com", retain_images: true)'

# 纯文本格式
mcporter call 'web-reader.webReader(url: "https://example.com", return_format: "text")'
```

**适用场景**: 需要更精确控制输出格式时使用。

## 微信公众号 / WeChat Articles

### 搜索公众号文章（通过 Exa）

```bash
# 搜索微信公众号文章
mcporter call 'exa.web_search_exa(query: "搜索关键词", numResults: 5, includeDomains: ["mp.weixin.qq.com"])'
```

### 阅读公众号文章全文（通过 Exa）

```bash
# 抓取文章全文
mcporter call 'exa.crawling_exa(urls: ["https://mp.weixin.qq.com/s/ARTICLE_ID"], maxCharacters: 10000)'
```

### 可选：Camoufox 阅读（反爬更强）

```bash
cd ~/.agent-reach/tools/wechat-article-for-ai && python3 main.py "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

> **注意**: Jina Reader 无法读取微信文章（被 CAPTCHA 拦截），推荐用 Exa。

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**适用场景**: 订阅博客、新闻源、播客等 RSS feed。

## 选择指南

| 场景 | 推荐工具 |
|-----|---------|
| 通用网页 | Jina Reader (`curl r.jina.ai`) |
| 需要图片/格式控制 | web-reader MCP |
| 微信公众号 | Exa (搜索+阅读) / Camoufox (可选阅读) |
| RSS 订阅 | feedparser |
| 微博/知乎等 | Jina Reader |
