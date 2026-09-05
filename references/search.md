# 搜索工具

## 搜索路由

遇到搜索/查询类请求时，按以下优先级自动选择工具，不再反问用户：

| 场景 | 首选 | 备选 | 兜底 |
|------|------|------|------|
| 中文搜索 | 百度 AI 搜索（`smart_search.py dispatch search`）| BrightData REST | Exa REST |
| 英文/技术搜索 | Exa REST | BrightData REST（Google） | 百度 AI 搜索 |
| 代码/仓库搜索 | GitHub (`gh search repos/code`) | Firecrawl Developer Index | DeepWiki |
| 编程问题/README/Issue/PR | Firecrawl Developer Index | Exa | GitHub |
| 学术论文/科研 | Firecrawl Research Index | DeepWiki | - |
| 特定网页阅读 | Jina Reader (`curl r.jina.ai/URL`) | BrightData REST | browser_use |
| 批量网页抓取 | BrightData REST 循环 | Jina 循环 | - |
| AI 相关性排序研究 | Exa（语义排序） | BrightData REST | - |
| 视频/字幕 | yt-dlp | - | - |
| 需要登录/交互的站点 | browser_use | BrightData REST | - |
| 千帆内容生成/文库/电商 | `quota_manager.py dispatch` | - | - |
| 千帆热榜 | ⚠️ 原热榜 API 已废弃，用 `dispatch trending` | - | - |

### BrightData 搜索参数（REST）

本机没有 brightdata MCP server，搜索 = 用 Unlocker 抓搜索引擎结果页：

- `zone`: `mcp_unlocker`（`WEB_UNLOCKER_ZONE` 可覆盖）
- `data_format`: Google 用 `parsed_light`（返回 JSON），Bing/Yandex 用 `markdown`
- 查询词自己 URL 编码进 `url`：`google.com/search?q=<q>&num=10`，翻页 `&start=<n>`，地区 `&gl=<cc>`

完整 curl 见 `scrape.md`。

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

**curl：**
```bash
curl -s "https://api.firecrawl.dev/v2/search/developer?query=%E4%BD%A0%E7%9A%84%E9%97%AE%E9%A2%98&k=5"
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

**curl：**
```bash
curl -s -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  "https://api.firecrawl.dev/v2/search/research/papers?query=multi-agent+systems&k=5"
```

---

## Exa AI 搜索（REST）

Exa 是 AI 搜索引擎，擅长英文内容、技术文档和代码语义搜索。直接打 REST，无需 MCP。

```bash
curl -s -X POST https://api.exa.ai/search -H "x-api-key: $EXA_API_KEY" \
  -H "Content-Type: application/json" -d '{"query":"AI agent","numResults":5}'
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

## 百度千帆（27 个工具）

**不在本技能记账，也不在此复制文档** —— 配额、场景、工具清单全部由独立技能
`baiduaisearchwithquota` 自己维护（计数器在 `~/.baidu_search_quota.json`）。

```bash
S=/var/minis/skills/baiduaisearchwithquota/scripts
python3 $S/smart_search.py search '搜索内容'          # 搜索（最常用）
python3 $S/quota_manager.py dispatch search '内容'    # 按场景调度（自动跳过用完/≤20% 的 API）
python3 $S/quota_manager.py status                    # 27 个工具剩余额度
python3 $S/quota_manager.py list                      # 工具清单
```

`dispatch` 的 7 个场景：`search`(400/日) / `trending`(10) / `content`(230) /
`doc`(47) / `knowledge`(200) / `ecommerce`(20) / `media`(10800 秒)。
原热榜 API 已废弃(404)，热榜走 `dispatch trending`。
