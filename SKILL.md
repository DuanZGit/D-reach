---
name: d-reach
description: >
  统一搜索与爬取路由器，覆盖中英文网页搜索、社交媒体（小红书/B站/微博/Twitter/Reddit）、
  GitHub 仓库、视频字幕、股票行情和任意网页抓取。整合百度千帆、Exa、BrightData、Firecrawl、
  Jina Reader、gh CLI、DeepWiki、yt-dlp、bili、xhs 等全部通道，内置免费配额门控与自动降级。
  只要用户想搜（搜/查/找/search/搜索/查一下/帮我搜）、想爬或抓网页内容（爬/抓/scrape/提取数据）、
  想读一篇文章或链接（读一下/打开这个/看看链接）、想查社交平台内容（小红书/B站/微博/推特/Reddit）、
  想找 GitHub 仓库或代码、想要视频字幕、想查股票行情，或者需要任何需要当前网络信息的调研——
  即使用户没有点名具体平台，也使用本技能。
  不要用于有独立触发词的领域技能：食谱/健康（DK）、个股分析流程（gushen）、深度研究报告（research）。
license: MIT
metadata:
  openclaw:
    homepage: https://github.com/DuanZGit/D-reach
---

# D-Reach — 搜索与爬取统一路由

把"用户想找信息"翻译成"用哪个通道、怎么调用"。所有通道共享一套配额门控，超限时自动降级，用户无感知。

## 决策流程

1. **判断意图**：搜索 / 爬取 / 社交 / 代码 / 视频 / 行情 → 查下方路由表
2. **走统一入口** `scripts/unified_entry.py`（自动配额检查 + 通道选择 + 降级），或按表直接调通道
3. **首选失败或超限** → 捉同一行的备选，不要停下来问用户
4. **全部超限** → 明确告知用户哪些额度用完，不静默失败，不偷偷调付费 API

配额门控存在的意义：这些服务都有免费上限（BrightData 5000/月、百度千帆 400/日、Brave 2000/月等），超限后会产生费用。统一入口在每次调用前查 `scripts/quota_manager.py status`，确保永远不越过免费线。

## 路由表

| 意图 | 首选 | 备选 | 兜底 |
|------|------|------|------|
| 中文搜索 | 百度千帆 `smart_search_pro` | Exa MCP | BrightData `search_engine` |
| 英文/技术搜索 | Exa MCP | 百度千帆 | BrightData |
| 网页抓取（反爬） | BrightData `scrape_as_markdown` | Firecrawl | Jina Reader |
| 批量网页抓取 | BrightData `scrape_batch` | Firecrawl | — |
| AI 相关性排序 | BrightData `discover` | Exa | — |
| GitHub 仓库/代码 | gh CLI | DeepWiki `ask_question` | Exa |
| 仓库语义问答 | DeepWiki | gh CLI 读源码 | — |
| B站 | bili CLI | yt-dlp（⚠️ B站走 yt-dlp 会被 412 拦）| — |
| YouTube 字幕 | yt-dlp | — | — |
| 小红书 | xhs CLI（需 cookie）| browser_use | — |
| 股票行情 | 雪球（走 gushen 技能）| 百度千帆 | — |
| 需要登录的站点 | browser_use | BrightData `scraping_browser_*` | — |

## 统一入口

```bash
# 搜索（自动配额检查 + 路由 + 降级）
python3 scripts/unified_entry.py search '查询内容'
python3 scripts/unified_entry.py search 'query' --lang en

# 爬取
python3 scripts/unified_entry.py scrape 'https://example.com'

# 查所有服务额度
python3 scripts/quota_manager.py status
```

直接调用通道也可以，但要自己留意配额。最常用的几条：

```bash
# 百度千帆（400 次/日免费）
python3 /var/minis/skills/baiduaisearchwithquota/scripts/smart_search.py search '查询'

# Exa（英文/技术）
minis-mcp-cli call exa web_search_exa --input '{"query":"...","numResults":5}'

# BrightData（反爬抓取，5000 次/月）
minis-mcp-cli call brightdata scrape_as_markdown --input '{"url":"..."}'

# GitHub
gh search repos "query" --sort stars --limit 10

# B站（不要用 yt-dlp，会被 412 拦）
bili search "query" --type video -n 5

# 小红书（先 search/hot 拿 xsec_token，再 read）
xhs search "关键词" --yaml
xhs read "https://www.xiaohongshu.com/explore/<id>" --xsec-token "<token>"
```

## 小红书注意事项

`xhs read` 必须带配对的 `xsec_token`（search/hot/feed 返回的 `AB` 前缀 token）。裸笔记 ID 会报 300031"笔记暂时无法浏览"。短链接 `xhslink.com` 需要先在浏览器解析出真实 URL。详见 `extensions/d-reach-xhs/SKILL.md`。

## 工作区

临时输出用 `/tmp/`，持久数据用 `~/.d-reach/`。不要在 agent workspace 创建文件。

## 详细文档

按需读取，不要一次全部加载：

| 文档 | 什么时候读 |
|------|-----------|
| [references/search.md](references/search.md) | 需要搜索通道的完整参数和配额细节 |
| [references/scrape.md](references/scrape.md) | 需要爬虫通道的完整参数、Firecrawl/Jina 用法 |
| [references/social.md](references/social.md) | 需要小红书/抖音/微博/Twitter/V2EX/Reddit 的调用细节 |
| [references/dev.md](references/dev.md) | 需要 gh CLI / DeepWiki 的完整用法 |
| [references/web.md](references/web.md) | 需要网页阅读 / 公众号 / RSS 的调用细节 |
| [references/video.md](references/video.md) | 需要 YouTube / B站 / 播客字幕的调用细节 |
| [references/finance.md](references/finance.md) | 需要雪球股票行情的调用细节 |
| [extensions/d-reach-xhs/SKILL.md](extensions/d-reach-xhs/SKILL.md) | 处理小红书笔记链接时 |
| [extensions/d-reach-twitter/SKILL.md](extensions/d-reach-twitter/SKILL.md) | 处理 Twitter/X 内容时 |
