> **路径约定**：本文件里 `$SKILLS` = 技能根目录。执行前先解析：
> `SKILLS="$HOME/.agents/skills"; [ -d "$SKILLS" ] || SKILLS=/var/minis/skills`
> （UG/本机命中 `~/.agents/skills`，Minis 命中 `/var/minis/skills`。）

# 搜索工具

> **主路由表在 `SKILL.md`，国内环境通道实测清单在 [`cn-reach.md`](cn-reach.md)。本文只补参数细节，不重复路由。**

## 调研强度与调用序列

定档表在 `SKILL.md`。这里只给「一次到底发几条」的样板。

> **2026-09-25 起一律走 `fanout.sh`**：一条命令并发铺开，别照下面的老样例一条一条 curl。
> 本节保留是因为它解释**每一轮在干嘛**——fanout 只把「铺开」这一个动作自动化了。

```bash
bash $SKILLS/d-reach/scripts/fanout.sh "<query>"          # L2 默认档：9 路免费并发（~5s）
bash $SKILLS/d-reach/scripts/fanout.sh "<query>" --deep    # L3：+LangSearch/Exa/FC-Research/BrightData
bash $SKILLS/d-reach/scripts/fanout.sh "<query>" --on bing   # L1：单路点查，再配一手源
```

**L1 点查**（2 来源 / 1 轮）—— 例：查某库版本发布日期

```bash
bash $SKILLS/d-reach/scripts/fanout.sh "Rust 1.90 release date" --on bing
# 一手源优先：直接读官方公告原文（Jina，记账）
curl -s --max-time 30 "https://r.jina.ai/https://blog.rust-lang.org/"
```

**L2 对比·选型**（6 来源 / 2 轮 / 免费优先）—— 默认档

| 轮 | 做什么 | 用什么 |
|---|---|---|
| 轮 1 发现 | 中英文 + 真实使用体验 + 中文长尾 + 学术一次全铺 | `fanout.sh "<query>"`（默认档 9 路） |
| 轮 2 追证 | 对轮 1 冒出的每个候选抓一手源；补反向体验 | Jina 读官方文档原文；`<候选> vs`、`<候选> 问题`、`<候选> 替代` |

只有 Exa / BrightData / Jina / LangSearch / Firecrawl-SDK 才 `quota.py use`；fanout 默认档
那 9 路全免费，`--deep` 的 4 路由脚本自动记账（越免费线自动跳过该路，不拖死其他路）。

**L3 深调研**（10 来源 / 3 轮 / 必含反证）

| 轮 | 做什么 | 用什么 |
|---|---|---|
| 1 广撒 | 中英文 + 学术 + 编程一手源 + 全网覆盖一次全铺 | `fanout.sh "<query>" --deep`（13 路） |
| 2 追深 | 把首轮捞到的人名/机构/版本/术语回灌成新查询 | `fanout.sh "<回灌词> 原理/对比/评测" --deep` |
| 3 反证 | `<主题> 缺点/失败/不推荐/争议/vs 替代` | `fanout.sh "<主题> 缺点 不推荐" --deep`；反证轮**不并入**前两轮计数 |

交不了差就老实写「未发现反例 + 试过哪些通道」，**不编造**。

**缺口触发（a2 —— 默认档铺完先看结果，再决定要不要转 deep）**：

| 观察到的 | 动作 |
|---|---|
| 有结果的路 **<3 路** | 默认档没喂饱 → 自动补 `--deep` + 换改写词再跑一轮 |
| 两路来源关键结论**互相矛盾** | 按 L3 处理：补 `--deep` + 反证轮，不许挑顺手的用 |
| 只要一个事实、两路互证一致 | 直接收，别再铺（铺满 ≠ 每问都铺满） |

## 广度：查询改写矩阵（至少 5 种）

| 改写方向 | 例（问：「DeepSeek Harness 靠谱吗」） |
|---|---|
| 原词 | `DeepSeek Harness` |
| 同义 / 上下位 | `DeepSeek 自动化测试工具` / `LLM 测试框架 对比` |
| 英文（英文源信息密度高） | `DeepSeek Harness review` / `agent harness benchmark` |
| 限定域（找一手源） | `site:github.com` / `site:docs.xxx.com` / LangSearch `includeDomains:[...]` |
| 时效（时效类问题必加） | `after:2026-06-01` / 中文加「2026」 / LangSearch `freshness:oneMonth` / BrightData `&tbs=qdr:m` |
| **反方问法**（新） | `DeepSeek Harness 缺点 / 不推荐 / 坑 / 争议 / 替代品` |

懒得多想就让**千帆「智能Query改写」(10/日)** 把一个问题批量翻成多种问法，再挑几条去打。

**反证独立走一轮**（L3 必做）：`<主题> 缺点` / `失败` / `不推荐` / `争议` / `vs 替代品`，
且**不并入**前两轮的来源计数。

## 免费通道铺开清单（不限量，深挖主力）

> **别逐条手打** —— 这些里能一起铺的已经被 `fanout.sh` 默认档一次并发打完了
> （cn.bing / FirecrawlDev / StackExchange / HN / 掘金 / SegmentFault / OpenAlex / Crossref /
> 千帆共 9 路）。下表留作「fanout 没覆盖到的场景」查漏。

| 场景 | 通道 | 命中数（L2 建议） | fanout 覆盖？ |
|---|---|---|---|
| 英文/技术 | cn.bing | 2-4 | ✅ 默认档 |
| 报错/排障 | StackExchange `search/advanced?q=` | 1-2 | ✅ 默认档 |
| 深度讨论 | HN Algolia | 1-2 | ✅ 默认档 |
| 学术 | OpenAlex → Crossref | 1-2 各 | ✅ 默认档 |
| 编程一手源 | Firecrawl Developer Index（免 key） | 2-5 | ✅ 默认档 |
| 中文技术长尾 | 掘金 API / SegmentFault（~~博客园~~已退役） | 1-2 | ✅ 默认档 |
| 中文综合回答 | 百度千帆（生成式，非来源） | 1 | ✅ 默认档（标 💬） |
| 行业资讯 | 36氪 / InfoQ / 澎湃 / 界面 | 1-2 | ❌ 需手打 |
| 书影音评分 | 豆瓣 `window.__DATA__` | 1 | ❌ 需手打 |
| 代码/仓库 | gh CLI search / DeepWiki `ask_question` | 1-3 | ❌ 需手打 |
| A 股公告 | 巨潮 cninfo | 1-2 | ❌ 需手打 |
| 微信公众号 | weixin.sogou.com | 1 | ❌ 需手打 |

> `--deep` 追加的 LangSearch / Exa / Firecrawl-Research / BrightData-Google 是限额/计 token 通道，
> 脚本会自动 `quota.py use`；这些通道 **不要 `quota.py use` 之外再手动 use**（会双扣）。
> deep 四路的月余量实测 >96%（LangSearch 本月 0 次、Exa 3/1000、Firecrawl 1/1000、BrightData 163/5000）——
> **L3 无条件铺，不必省**。

## 搜索路由（速查，完整见 SKILL.md）

| 场景 | 首选 | 备选 | 兜底 |
|------|------|------|------|
| 中文搜索 | 百度千帆（`smart_search.py search`，生成式答案） | cn.bing 站内 | BrightData REST |
| 英文/技术搜索 | **cn.bing ✅免 + LangSearch ⏱ 双发**（`count=20`） | Exa REST ⏱ | BrightData REST（Google） |
| 时效/限域检索 | LangSearch REST ⏱（freshness + include/excludeDomains） | cn.bing 站内 ✅免 | BrightData `&tbs` ⏱ |
| 代码报错/排障 | **StackExchange API** ✅免 | Firecrawl Developer Index ✅免 | cn.bing 站内 |
| 中文技术长尾 | **掘金 API / 博客园 / SegmentFault** ✅免 | 百度千帆 | cn.bing |
| 编程问题/README/Issue/PR | Firecrawl Developer Index ✅免 | Exa | GitHub |
| 学术论文 | **OpenAlex / Crossref** ✅免 | Firecrawl Research Index ✅免 | Semantic Scholar ✅免 |
| 公司/专有名词背景 | 百度百科（千帆） | cn.bing 站内 ✅免 | BrightData ⏱ |
| 深度技术讨论 | **HN Algolia** ✅免 | V2EX | cn.bing |
| 特定网页阅读 | Jina Reader (`curl r.jina.ai/URL`) | BrightData REST | browser_use |
| 批量网页抓取 | BrightData REST 循环 | Jina 循环 | - |
| 需要登录/交互的站点 | browser_use | BrightData REST | - |
| 千帆内容生成/文库/电商 | `quota_manager.py dispatch` | - | - |
| 千帆热榜 | ⚠️ 原热榜 API 已废弃，用 `dispatch trending` | - | - |

> 🔴 **arxiv.org / wikipedia / duckduckgo / google scholar 在本环境全部 000 不可达**，
> 学术一律走 OpenAlex → Crossref → Firecrawl Research。详见 [`cn-reach.md`](cn-reach.md)。

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

## ✅ 免 Key 免费通道（本环境实测可用，不记账）

> 这几个是 **不限量、免申请** 的官方 API，优先用它们，把百度/BrightData/Exa 的额度省给真正需要的地方。
> 逐条实测记录（含不可达站点）见 [`cn-reach.md`](cn-reach.md)。

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

# 必应中国 —— 英文/技术搜索首选（中文几乎不出结果，别用）
curl -s -A "$UA" "https://cn.bing.com/search?q=alpine+proot+x86+emulation"

# StackExchange / StackOverflow —— 报错排障第一源，带 score/is_answered
#   坑：q 只在 /search/advanced 生效，/search 只吃 intitle（写错 → 400）
curl -s --compressed "https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q=proot+alpine&site=stackoverflow&pagesize=5"

# Hacker News（Algolia）—— 深度技术讨论
curl -s "https://hn.algolia.com/api/v1/search?query=proot&hitsPerPage=5"

# 掘金 —— 中文技术长尾（POST）
curl -s -H "Content-Type: application/json" -X POST "https://api.juejin.cn/search_api/v1/search" \
  -d '{"key_word":"deepseek","id_type":0,"cursor":"0","limit":5,"search_type":0}'

# OpenAlex —— 2.5 亿篇全领域学术，含引用数/开放获取链接（arXiv 的替代首选）
curl -s "https://api.openalex.org/works?search=deepseek&per-page=5"

# Crossref —— DOI 权威元数据（校验"这篇论文/DOI 是否真实存在"最准）
curl -s "https://api.crossref.org/works?query=deepseek&rows=5&select=title,DOI,URL,published"
```

| 通道 | 覆盖 | 不适合 |
|------|------|--------|
| cn.bing | 英文技术、长尾网页 | 中文查询（h2≈1，几乎无结果） |
| StackExchange | 编程报错、工具用法 | 中文问题、时效资讯 |
| HN Algolia | 技术趋势、一手吐槽 | 中文内容 |
| 掘金 | 中文技术实践、踩坑 | 学术、英文一手源 |
| OpenAlex | 学术元数据+引用+OA 链接 | 全文 PDF 内容 |
| Crossref | DOI/出版社元数据 | 全文、引用网络 |

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

## LangSearch（Web Search，⭐ 全功能免费）

**限制按 token 计、不按次**（官方无 RPM/RPD——配额里的 50 次/日是本技能自设保守线）。三线实际值**只在 Dashboard 显示**：

| 线 | 含义 | 官方公布值 |
|---|---|---|
| RPS | 每秒请求数 | 新号 **5** |
| TPM | 滚动 60s 窗口内 input+output tokens | Dashboard |
| TPD | 当前 UTC 日 input+output tokens | Dashboard（含日用量百分比） |

单价 **$0/百万 token**；计法：input=查询词、output=正文/snippet，**标题/URL 等元数据不计**；响应 `usage.input/output_tokens`
相加=本次消耗。**00:00 UTC 固定重置**（非本地午夜、非首请求后 24h），所有 key 共享、多 key 不恢复。
429 跟 `Retry-After`；⚠️ **客户端超时 ≠ 服务端没跑成**（可能已结算 token）——抖动重试前先权衡双花。

| 参数 | 类型 | 说明 |
|---|---|---|
| `query` | string | 必填非空 |
| `count` | int 1-50（默认 10） | >50 返 400 |
| `freshness` | `noLimit/oneDay/oneWeek/oneMonth/oneYear` 或 `YYYY-MM-DD[..YYYY-MM-DD]` | 时效检索 |
| `includeDomains` / `excludeDomains` | string[] | 限域 / 排除 |
| `contents.text` | bool 或 `{maxCharacters: 正整数}`（默认 5000；旧名 `max_characters` 也兼容，同时给时 maxCharacters 优先） | 返回全文而非 snippet，**照常计入日额度** |

**响应**：先看 HTTP 状态 → 成功取 `data.webPages.value[]`（`name/url/snippet` 或 `text`，`datePublished` 可能缺；body `code=200`）。
**错误**：400=参数错不原样重试；401/403=凭据；429=先分清瞬时限流 vs 日额度用尽（看 `msg` + dashboard）；5xx=退避重试。
**深挖默认别开 `contents.text`**：实测 snippet 5 结果 ≈ 1.2k（英）/ 2.3k（中）tok，而全文 10 结果 ×5000 字 ≈ 上万 tok/次——几次就可能烧穿 TPD；要全文时 `maxCharacters` 压到 1000-3000。

```bash
KEY=$(sh $SKILLS/d-reach/scripts/load_key.sh LANGSEARCH_API_KEY https://langsearch.com/dashboard || 降级)
curl -s --max-time 30 -X POST https://api.langsearch.com/v1/web-search \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"query":"uv pip benchmark","count":10,"freshness":"oneWeek","includeDomains":["astral.sh"]}'
```

> 也有 MCP 端点 `https://mcp.langsearch.com/mcp`（Bearer）——**MCP 连接不额外给额度**，与 API key 同池共享。
> 本机实测 2026-09-22：EN/CN 均 200（1.5s/1.9s），
> **CN 相关性一般**（中文查询返了英文结果）→ 中文仍优先千帆，LangSearch 定位英文+时效/限域。
> ⚠️ **TPM/TPD 绝对数值与今日消耗官方从不公布**：官方 12 页文档（`llms.txt` 全清单）已逐页查过，
> 唯一出处是登录后 Dashboard —— **别再花轮次检索数值**，要看就打开 Dashboard 三个数：RPS 上限 / TPM 上限 / 今日已耗+百分比。


---

## 百度千帆（27 个工具）

**不在本技能记账，也不在此复制文档** —— 配额、场景、工具清单全部由独立技能
`baiduaisearchwithquota` 自己维护（计数器在 `~/.baidu_search_quota.json`）。

```bash
S=$SKILLS/baiduaisearchwithquota/scripts
python3 $S/smart_search.py search '搜索内容'          # 搜索（最常用）
python3 $S/quota_manager.py dispatch search '内容'    # 按场景调度（自动跳过用完/≤20% 的 API）
python3 $S/quota_manager.py status                    # 27 个工具剩余额度
python3 $S/quota_manager.py list                      # 工具清单
```

`dispatch` 的 7 个场景：`search`(400/日) / `trending`(10) / `content`(230) /
`doc`(47) / `knowledge`(200) / `ecommerce`(20) / `media`(10800 秒)。
原热榜 API 已废弃(404)，热榜走 `dispatch trending`。
