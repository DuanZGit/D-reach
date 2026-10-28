# 开发工具

> GitHub 不稳 / 需要中文排障时的替代通道见下方「国内开发通道」；完整实测清单在 [`cn-reach.md`](cn-reach.md)。

## 国内开发通道（✅免 Key，不记账）

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

# StackExchange 官方 API —— 报错/排障第一源（比搜索引擎更快命中已采纳答案）
#   坑：q 只在 /search/advanced 生效；/search 只吃 intitle，用 q 会 400
curl -s --compressed "https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q=alpine+proot&site=stackoverflow&pagesize=5"
# 取答案：/2.3/questions/<ids>/answers?filter=withbody&site=stackoverflow

# 掘金（中文技术，POST）
curl -s -H "Content-Type: application/json" -X POST "https://api.juejin.cn/search_api/v1/search" \
  -d '{"key_word":"关键字","id_type":0,"cursor":"0","limit":5,"search_type":0}'

# 博客园 / SegmentFault / OSCHINA —— 中文踩坑长尾（站内搜索页 + 浏览器 UA）
curl -s -A "$UA" "https://zzk.cnblogs.com/s?w=关键字"
curl -s -A "$UA" "https://segmentfault.com/search?q=关键字"
curl -s -A "$UA" "https://www.oschina.net/search?q=关键字"

# Hacker News —— 深度讨论
curl -s "https://hn.algolia.com/api/v1/search?query=关键字&hitsPerPage=5"
```

- **Gitee**（国内代码托管，✅可达）：GitHub push 失败/不可达时的镜像与备选。
- ⚠️ `search.douban.com`、`zhihu.com`（403）、`tieba.baidu.com`（403）需 browser_use 交互。

## GitHub (gh CLI)

本机 `/usr/bin/gh`，免费无限，不记账。常用不啰嗦，只记容易踩的：

```bash
gh search repos "query" --sort stars --limit 10     # 仓库搜索
gh search code "query" --language python            # 代码搜索（要 -L 指定 owner/repo 更快）
gh api repos/owner/repo/contents/README.md --jq '.content' | base64 -d   # 读单文件
gh issue list -R owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'
gh run view <run-id> --repo owner/repo --log-failed  # 只看失败日志
```

- 读单个文件用 `gh api .../contents/...`（返回 base64，要 `base64 -d`）；
  问架构/实现原理走 DeepWiki，别 clone。
- 认证状态：`gh auth status`。私有仓库 push 注意全局 `insteadOf` 会把 github.com
  重写到只读镜像，需临时 unset。

## DeepWiki（MCP，已注册）

问 GitHub 仓库的架构 / 用法 / 实现原理。**工具清单和参数以自描述为准**，不要照抄本文档：

```bash
minis-mcp-cli tools deepwiki                       # 看有哪些工具 + 入参 schema
minis-mcp-cli call deepwiki ask_question --input '{"repoName":"owner/repo","question":"这个仓库的并发模型是怎么实现的？"}'
```

- 参数名是 **`repoName`**（不是 `repo`），实测 2026-09-05；接受 `owner/repo` 字符串或最多 10 个的数组。
- 另有 `read_wiki_structure`（目录树）、`read_wiki_contents`（全文）两个工具。
- 未索引的仓库直接回 `Repository not found`（私有仓库默认没索引）→ 立刻降级 `gh`，不要重试。
  但 **`fetch failed` / `not available (last failed Ns ago)` 是另一回事**：pi 的 MCP 客户端有 ~15s 失败退避缓存，
  `connect` 报这类错常常是上一轮的瞬时抖动被缓存住了（2026-09-22 实测：DeepWiki 被判死 → 等待后重连即通，
  端点 `mcp.deepwiki.com/mcp` 全程 200），**隔一会儿重试即可，别当场判通道死了**。
- **不要传 `https://github.com/...` 全 URL**（会被拒）。
- 返回的是已索引的文档摘要（顶部有 `Last indexed:` 日期），不是实时文件列表；
  要精确文件内容 / 最新 commit → `gh api`。
