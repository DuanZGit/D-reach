# 搜索工具

## 搜索路由

遇到搜索/查询类请求时，按以下优先级自动选择工具，不再反问用户：

| 场景 | 首选 | 备选 | 兜底 |
|------|------|------|------|
| 中文搜索 | 百度 AI 搜索（quota_manager dispatch search）| BrightData MCP (`search_engine`) | Exa MCP |
| 英文/技术搜索 | Exa MCP (`exa.web_search_exa`) | BrightData MCP (`search_engine`) | 百度 AI 搜索 |
| 代码/仓库搜索 | GitHub (`gh search repos/code`) | Firecrawl Developer Index (`unified_entry developer`) | DeepWiki |
| 编程问题/README/Issue/PR | Firecrawl Developer Index | Exa | GitHub |
| 学术论文/科研 | Firecrawl Research Index (`unified_entry research`) | DeepWiki | - |
| 特定网页阅读 | Jina Reader (`curl r.jina.ai/URL`) | BrightData MCP (`scrape_as_markdown`) | Firecrawl |
| 批量网页抓取 | BrightData MCP (`scrape_batch`) | Firecrawl | - |
| AI 相关性排序研究 | BrightData MCP (`discover`) | Exa | - |
| 视频/字幕 | yt-dlp | - | - |
| 需要登录/交互的站点 | browser_use | BrightData MCP (`scraping_browser_*`) | - |
| 千帆内容生成/文库/电商 | quota_manager dispatch | - | - |
| 千帆热榜 | ⚠️ 千帆 API 已废弃，请用 quota_manager list | - | - |

### 搜索执行器（unified_entry）

```bash
# 统一搜索（自动配额+路由+fallback）
python3 scripts/unified_entry.py search "关键词" zh   # 中文
python3 scripts/unified_entry.py search "query" en  # 英文

# Firecrawl Developer Index（编程专用，免 API key）
python3 scripts/unified_entry.py developer "how to configure retries in tokio"

# Firecrawl Research Index 论文（免费，需 FIRECRAWL_API_KEY）
python3 scripts/unified_entry.py research "LLM agent memory"
```

---

## BrightData MCP 搜索（已配置）

BrightData MCP 提供 3 个搜索工具，均已默认启用：

| 工具 | 说明 | 调用示例 |
|------|------|---------|
| `search_engine` | Google/Bing/Yandex 搜索 | `minis-mcp-cli call brightdata search_engine --input '{"query":"xxx","engine":"google"}'` |
| `search_engine_batch` | 批量搜索（最多 10 个查询） | `minis-mcp-cli call brightdata search_engine_batch --input '{"queries":[{"query":"q1"},{"query":"q2"}]}'` |
| `discover` | AI 相关性排序搜索，支持 intent、geo、日期过滤 | `minis-mcp-cli call brightdata discover --input '{"query":"xxx","num_results":5}'` |

### 参数说明

**search_engine**
- `query` (必填): 搜索关键词
- `engine` (可选): `google` / `bing` / `yandex`，默认 `google`
- `cursor` (可选): 分页游标
- `geo_location` (可选): 2 字母国家代码，如 `us`、`uk`

**search_engine_batch**
- `queries` (必填): 查询数组，最多 10 个，结构与 `search_engine` 相同

**discover**
- `query` (必填): 搜索关键词
- `intent` (可选): 搜索意图描述，用于 AI 相关性排序
- `country` / `city` (可选): 地理位置
- `language` (可选): 语言代码
- `num_results` (可选): 结果数量
- `filter_keywords` (可选): 必须包含的关键词
- `start_date` / `end_date` (可选): 日期范围过滤

---

## Firecrawl Developer Index（编程专用，⭐ 免 API key）

Firecrawl 的编程 Agent 专用检索索引，覆盖 **70M+ 一手来源**（README、docs、issue、PR、agent-skills），每日刷新，带 rerank + passages。

| 特性 | 值 |
|------|-----|
| 端点 | `GET /v2/search/developer` |
| **API key** | **不需要**（无 key 即用，加 key 提高限流） |
| 类型 | `doc` / `issue` / `pull_request` / `readme` |
| 过滤 | `repos`、`sources`、`language`、`topic`、`license`、`min_stars`、`max_stars`、`archived`、`fork`、`skills=only` |
| k 范围 | 1-100（默认 10） |

**原始 curl：**
```bash
curl -s "https://api.firecrawl.dev/v2/search/developer?query=how%20do%20I%20configure%20retries&k=10&language=Rust&license=MIT"
```

**经统一入口（推荐）：**
```bash
python3 scripts/unified_entry.py developer "你想要的问题"
```

**适用场景：** 写代码、查 GitHub issue/PR、读 README、理解开源项目、找最佳实践。

---

## Firecrawl Research Index（学术论文，⭐ 免费但需 key）

论文检索索引，覆盖 **41M+ 生命科学 + AI/ML 论文**。FAQ 明确 **paper endpoints 免费，不耗 credits**。

| 特性 | 值 |
|------|-----|
| 端点 | `GET /v2/search/research/papers` |
| API key | 需要 `FIRECRAWL_API_KEY` |
| 计费 | **免费**（不扣 1000 credits 额度） |
| k 范围 | 1-500（默认 40） |
| 过滤 | `authors`、`categories`、`from`、`to` |

**经统一入口：**
```bash
python3 scripts/unified_entry.py research "multi-agent systems"
```

---

## Exa AI 搜索（通过 MCP）

Exa 是 AI 搜索引擎，擅长英文内容、技术文档和代码语义搜索。当前通过 Minis MCP (`exa`) 调用。

```bash
# 通过 minis-mcp-cli 调用
minis-mcp-cli call exa web_search_exa --input '{"query":"AI agent","numResults":5}'
```

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | 必填 | 搜索关键词 |
| `numResults` | int | 5 | 返回结果数量 |

### 特点

- 语义理解强，适合技术/英文查询
- 返回结果包含 title、url、snippet
- 免费额度可用，注意控制调用量

---

## 百度千帆 AI（v3.0，27 个工具统一管理）

> **依赖说明**：脚本来自独立 skill `baiduaisearchwithquota`，非本仓库自带。
> 安装后通过环境变量 `BAIDU_QF_SCRIPT` 指向其 `scripts/quota_manager.py`，
> 或放在 `/var/minis/skills/baiduaisearchwithquota/` 位置自动探测。

百度千帆提供中文智能搜索、百科、热搜、内容生成、文库、多媒体、知识图谱、电商等 **27 个官方工具**，统一通过 `quota_manager.py` 调度。

```bash
# 推荐：按场景智能调度（自动跳过用完/≤20%/未开通的 API）
python3 /var/minis/skills/baiduaisearchwithquota/scripts/quota_manager.py dispatch search '搜索内容'
python3 /var/minis/skills/baiduaisearchwithquota/scripts/quota_manager.py dispatch doc '主题'
python3 /var/minis/skills/baiduaisearchwithquota/scripts/quota_manager.py dispatch ecommerce

# 兼容旧版（仅搜索类）
python3 /var/minis/skills/baiduaisearchwithquota/scripts/smart_search.py search '搜索内容'
python3 /var/minis/skills/baiduaisearchwithquota/scripts/smart_search.py search '搜索内容' --force smart_search_pro

# 配额管理
python3 /var/minis/skills/baiduaisearchwithquota/scripts/quota_manager.py status              # 全部 27 个工具
python3 /var/minis/skills/baiduaisearchwithquota/scripts/quota_manager.py status search      # 仅搜索类
python3 /var/minis/skills/baiduaisearchwithquota/scripts/quota_manager.py reset             # 重置所有
```

### 7 个场景 + 27 个工具

| 场景 | 工具数 | 每日免费 | 典型 API |
|------|--------|---------|---------|
| **search**（搜索）| 5 | 400 次 | smart_search_pro / smart_search / baike |
| **trending**（热搜）| 1 | 10 次 | baidu_hot |
| **content**（内容生成）| 5 | 230 次 | miaodong_baike / image_understand |
| **doc**（文库）| 5 | 47 次 | wenku_ppt / wenku_paper_outline |
| **knowledge**（知识图谱）| 2 | 200 次 | baike_map_list |
| **ecommerce**（电商）| 2 | 20 次 | product_marketing |
| **media**（多媒体）| 1 | 10800 秒 | video_note |

### 配额规则

- 每日赠送额度内**完全免费**
- 自动跨天重置（无需手动）
- 剩余 ≤20% 自动跳过切下一个免费 API（避免计费）
- 全部用完才报错，不会误调用任何收费 API

### 热榜说明

⚠️ **百度千帆原热榜 API 已废弃**（404）。通用热榜查询请用 agent-reach 的其他渠道（如微博热搜等），百度热搜（10 次/天）仍可通过 quota_manager dispatch trending。

## 选择指南

| 工具 | 来源 | 适用场景 |
|-----|------|------|
| BrightData MCP | MCP (brightdata) | 综合搜索/爬虫/结构化提取/浏览器自动化 |
| Firecrawl Developer Index | REST (unified_entry developer) | 编程问题/README/Issue/PR（免 key） |
| Firecrawl Research Index | REST (unified_entry research) | 学术论文/科研（免费） |
| Firecrawl | Python SDK (firecrawl-py) | 网页抓取/搜索（耗 1000 credits/月） |
| Exa | MCP (exa) | 英文/技术/代码语义搜索 |
| 百度千帆 (quota_manager) | baiduaisearchwithquota | 中文搜索/百科/内容生成/文库/电商 |
| GitHub | agent-reach | 仓库/代码/Issue/PR 搜索 |
| DeepWiki | MCP (deepwiki) | 代码库架构理解与文档化摘要 |
| Jina Reader | curl | 网页正文提取（零配置） |
| browser_use | Minis built-in | 需要登录/交互的网页 |
| yt-dlp | 系统 | 视频/字幕下载 |
