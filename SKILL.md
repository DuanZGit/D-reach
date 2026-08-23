---
name: d-reach
description: >
  统一搜索、爬虫、网页读取、社交媒体、代码仓库、视频字幕的顶层路由器。
  整合百度千帆、Exa、BrightData、Firecrawl、Jina Reader、gh CLI、DeepWiki、
  yt-dlp、xhs、bili、twitter、rdt、browser_use 等全部通道。

  触发词：搜/查/找/search/搜索/查一下/帮我搜/读一下/打开这个/看看链接/爬/抓/scrape。
  用户只须说"搜/查/读/爬"，agent 自动选最优通道。
triggers:
  - search: 搜/查/找/search/搜索/查一下/帮我搜
  - scrape: 爬/抓/抓取/scrape/提取/提取数据
  - social:
    - 小红书: xiaohongshu/xhs/小红书/红书
    - 抖音: douyin/抖音
    - Twitter: twitter/推特/x.com/推文
    - 微博: weibo/微博
    - B站: bilibili/b站/哔哩哔哩
    - V2EX: v2ex
    - Reddit: reddit
  - career: 招聘/职位/求职/linkedin/领英/找工作
  - dev: github/代码/仓库/gh/issue/pr/分支/commit
  - web: 网页/链接/文章/公众号/微信文章/rss/读一下/打开这个
  - video: youtube/视频/播客/字幕/小宇宙/转录/yt
  - finance: 雪球/股票/stock/xueqiu/行情/基金
metadata:
  openclaw:
    homepage: https://github.com/DuanZGit/D-reach
---

# Agent Reach — 路由器

17 平台工具集合。根据用户意图选择对应分类。

## 路由表

| 用户意图 | 分类 | 详细文档 |
|---------|------|---------|
| 网页搜索/代码搜索 | search | [references/search.md](references/search.md) |
| 爬虫/抓取/数据提取 | scrape | [references/scrape.md](references/scrape.md) |
| 小红书/抖音/微博/推特/B站/V2EX/Reddit | social | [references/social.md](references/social.md) |
| 招聘/职位/LinkedIn | career | [references/career.md](references/career.md) |
| GitHub/代码 | dev | [references/dev.md](references/dev.md) |
| 网页/文章/公众号/RSS | web | [references/web.md](references/web.md) |
| YouTube/B站/播客字幕 | video | [references/video.md](references/video.md) |
| 雪球/股票行情 | finance | [references/finance.md](references/finance.md) |

## 搜索路由（执行优先级）

遇到搜索/查询类请求时，按以下优先级自动选择工具，**不再反问用户**：

| 场景 | 首选 | 备选 | 兜底 |
|------|------|------|------|
| 中文搜索 | 百度 AI 搜索 (`smart_search_pro`) | Exa MCP (`exa.web_search_exa`) | BrightData MCP (`search_engine`) |
| 英文/技术搜索 | Exa MCP (`exa.web_search_exa`) | 百度 AI 搜索 | BrightData MCP (`search_engine`) |
| 代码/仓库搜索 | GitHub (`gh search repos/code`) | DeepWiki (`ask_question`) | Exa |
| GitHub 项目详情/README | gh CLI (`gh api repos/.../readme`) | DeepWiki (`ask_question`) | - |
| 特定网页阅读 | Jina Reader (`curl r.jina.ai/URL`) | BrightData MCP (`scrape_as_markdown`) | Firecrawl |
| 批量网页抓取 | BrightData MCP (`scrape_batch`) | Firecrawl (`firecrawl/scrape`) | - |
| AI 相关性排序研究 | BrightData MCP (`discover`) | Exa | - |
| 结构化数据提取 | BrightData MCP (`web_data_*`) | Firecrawl (`firecrawl/extract`) | - |
| 视频/字幕 | yt-dlp（仅 YouTube） | bili-cli（B站） | - |
| 需要登录/交互的站点 | browser_use | BrightData MCP (`scraping_browser_*`) | - |

### GitHub 项目调研流程

1. `gh search repos "query" --limit 10` 找到候选仓库
2. 用 `gh api repos/<owner>/<repo> --jq '{name, description, stars, ...}'` 快速比较
3. 读 README：`gh api repos/<owner>/<repo>/readme --jq .content | base64 -d`
4. 若 DeepWiki 已索引该仓库，可用 `minis-mcp-cli call deepwiki ask_question --input '{"repoName":"owner/repo","question":"..."}'` 做语义问答
5. **注意**：DeepWiki 可能未索引小众/新仓库，此时 fallback 到 gh CLI 读源码/README

**规则**
1. 按场景查表，直接执行，不确认。
2. 如果首选返回空结果或报错，自动尝试同一行的备选。
3. 不自动调用未配置的平台：Twitter/X、小红书等需要 cookies 的渠道，**只在使用时才提示配置**。
4. **所有带免费上限的服务，必须先经过配额门控检查。**
5. 超限后自动切换 fallback，绝不进入付费模式。

## 配额门控系统

所有搜索/爬虫调用前，必须先检查配额。调用链：

```bash
# 1. 检查额度状态
python3 scripts/quota_manager.py status

# 2. 统一入口（自动配额检查 + 路由 + fallback）
python3 scripts/unified_entry.py search "查询内容"
python3 scripts/unified_entry.py scrape "https://example.com"

# 3. 手动重置（测试用）
python3 scripts/quota_manager.py reset
```

### 免费额度限制

| 服务 | 免费额度 | Fallback 链 |
|------|---------|-----------|
| BrightData MCP | 5,000 次/月 | Jina Reader → Firecrawl |
| 百度千帆搜索 | 400 次/日 | BrightData → Exa |
| 百度千帆文库 | 47 次/日 | Jina Reader |
| 百度千帆电商 | 20 次/日 | Jina Reader |
| 百度千帆内容 | 230 次/日 | - |
| Brave Search | 2,000 次/月 | BrightData |
| Serper | 2,500 次/月 | BrightData |

**硬规则：**
- 当主服务超限时，自动切换到 fallback，用户无感知
- 当所有服务都超限时，返回明确错误，并告知用户
- 绝不静默失败，也不偷偷调用付费 API

## 零配置快速命令

```bash
# 百度 AI 搜索（智能调度，27 个工具统一管理）
python3 /var/minis/skills/baiduaisearchwithquota/scripts/quota_manager.py dispatch search '搜索内容'
# 或兼容老用法：
python3 /var/minis/skills/baiduaisearchwithquota/scripts/smart_search.py search '搜索内容'

# 统一搜索入口（自动配额检查 + 路由 + fallback）
python3 scripts/unified_entry.py search '搜索内容'
python3 scripts/unified_entry.py search 'query' --lang en

# 统一爬取入口（自动配额检查 + 路由 + fallback）
python3 scripts/unified_entry.py scrape 'https://example.com'

# 检查所有服务额度
python3 scripts/quota_manager.py status

# Exa 网页搜索（通过 MCP）
minis-mcp-cli call exa web_search_exa --input '{"query":"query","numResults":5}'

# BrightData 搜索/爬虫（通过 MCP，建议通过 unified_entry 调用）
minis-mcp-cli call brightdata search_engine --input '{"query":"query","engine":"google"}'
minis-mcp-cli call brightdata scrape_as_markdown --input '{"url":"https://example.com"}'
minis-mcp-cli call brightdata search_engine_batch --input '{"queries":[{"query":"q1"},{"query":"q2"}]}'
minis-mcp-cli call brightdata scrape_batch --input '{"urls":["https://a.com","https://b.com"]}'
minis-mcp-cli call brightdata discover --input '{"query":"query","num_results":5}'

# Firecrawl 搜索/抓取
python3 -c "from firecrawl import Firecrawl; app = Firecrawl(); app.scrape('https://example.com')"

# 通用网页阅读
curl -s "https://r.jina.ai/URL"

# GitHub 搜索
gh search repos "query" --sort stars --limit 10

# YouTube/B站字幕（⚠️ B站不要用 yt-dlp，被 412 拦截；B站用 bili-cli）
yt-dlp --write-sub --skip-download -o "/tmp/%(id)s" "URL"   # 仅 YouTube
bili video BVxxx                                             # B站视频详情
bili search "query" --type video -n 5                        # B站搜索

# V2EX 热门
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: d-reach/1.0"
```

## 环境检查

```bash
# 检查 MCP 服务状态
minis-mcp-cli list

# Ping 具体服务
minis-mcp-cli ping brightdata
minis-mcp-cli ping exa
minis-mcp-cli ping deepwiki
```

## 工作区规则

**不要在 agent workspace 创建文件。** 使用 `/tmp/` 存放临时输出，`~/.d-reach/` 存放持久数据。

## 详细文档

根据用户需求，阅读对应的详细文档：

- [搜索工具](references/search.md) — 百度千帆、Exa、BrightData MCP 搜索
- [爬虫工具](references/scrape.md) — BrightData MCP 爬虫、Firecrawl、Jina Reader
- [社交媒体](references/social.md) — 小红书, 抖音, Twitter, B站, V2EX, Reddit, BrightData social
- [职场招聘](references/career.md) — LinkedIn
- [开发工具](references/dev.md) — GitHub CLI, DeepWiki, BrightData code
- [网页阅读](references/web.md) — Jina Reader, 微信公众号, RSS, BrightData scrape, Firecrawl
- [视频播客](references/video.md) — YouTube, B站, 小宇宙
- [金融行情](references/finance.md) — 雪球股票行情、搜索、热门内容（PRoot 下走 gushen/jina_reader）

## 本地实战增强

本仓库还保留了从实际使用中沉淀出的独立 skill；遇到对应场景时优先阅读：

- [小红书（XHS）增强](extensions/d-reach-xhs/SKILL.md) — `xsec_token`、短链接重定向、浏览器 Cookie 登录、错误码与限速
- [Twitter/X 增强](extensions/d-reach-twitter/SKILL.md) — Cookie 环境变量认证、X Article、结构化归档
- [Twitter/X Cookie 参考](extensions/d-reach-twitter/references/twitter-cli-cookie-workflow.md) — `auth_token` / `ct0` 的安全传入方式
- [知乎与通用网页](references/web.md) — 当前保留的知乎读取路径是 Jina Reader；未找到独立的已验证知乎扩展

## 触发边界（必读）

**只有用户明确提到搜索/查询/爬取动词时，才激活 d-reach。**
- 触发词：`搜 / 查 / 找 / search / 搜索 / 查一下 / 帮我搜`
- 也包含：`读一下 / 打开这个 / 看看链接`
- 也包含：`爬 / 抓 / 抓取 / scrape / 提取 / 提取数据`

**其他专业技能的触发规则（硬边界）：**
- **DK**：只有用户明确提到 `DK`、`食谱`、`饮食`、`健康`、`营养`、`生活技巧`、`科学常识` 等 DK 专属领域词，才走 DK。**普通搜索不走 DK。**
- **gushen**：只有用户明确提到 `gushen`、`股票`、`行情`、`基金`、`投资`、`A股`、`美股`，才走 gushen。**普通搜索不走 gushen。**
- **research**：只有用户明确说 `research XXX`，才走 research。**普通搜索不走 research。**

**简单说：没提到 DK/gushen/research，就不触发它们。d-reach 只管通用搜索。**
