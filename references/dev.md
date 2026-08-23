# 开发工具

GitHub CLI 

## BrightData MCP 代码工具（需启用 `code` 组）

| 工具 | 说明 | 调用示例 |
|------|------|---------|
| `web_data_npm_package` | npm 包信息（版本、README、依赖） | `minis-mcp-cli call brightdata web_data_npm_package --input '{"url":"https://www.npmjs.com/package/express"}'` |
| `web_data_pypi_package` | PyPI 包信息 | `minis-mcp-cli call brightdata web_data_pypi_package --input '{"url":"https://pypi.org/project/requests/"}'` |
| `web_data_github_repository_file` | GitHub 文件内容 | `minis-mcp-cli call brightdata web_data_github_repository_file --input '{"url":"https://github.com/owner/repo/blob/main/README.md"}'` |

## GitHub (gh CLI)

GitHub 官方命令行工具，用于仓库、Issue、PR、Actions、Release 以及 API 访问。

```bash
# 认证
gh auth login
gh auth status

# 搜索
gh search repos "query" --sort stars --limit 10
gh search code "query" --language python

# 仓库
gh repo view owner/repo
gh repo clone owner/repo
gh repo create my-repo --private
gh repo fork owner/repo
gh repo fork owner/repo --clone
gh repo sync owner/repo

# Issues
gh issue list -R owner/repo --state open
gh issue view 123 -R owner/repo
gh issue create -R owner/repo --title "Title" --body "Body"

# Pull Requests
gh pr list -R owner/repo --state open
gh pr view 123 -R owner/repo
gh pr create -R owner/repo --title "Title" --body "Body"
gh pr checks 123 --repo owner/repo

# Actions / CI
gh run list --repo owner/repo --limit 10
gh run view <run-id> --repo owner/repo
gh run view <run-id> --repo owner/repo --log-failed
gh workflow list --repo owner/repo

# Releases
gh release list -R owner/repo
gh release create v1.0.0

# API
gh api /user
gh api repos/owner/repo

# JSON 输出
gh issue list --repo owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'
```


## DeepWiki (MCP)

DeepWiki 是一个用于获取 GitHub 仓库文档化摘要的 MCP 服务器，基于 deepwiki.com。它能把仓库源码转换成结构化 Markdown 文档。

```bash
# 查看可用工具
minis-mcp-cli tools mcp-deepwiki

# 基本调用语法
minis-mcp-cli call mcp-deepwiki deepwiki_fetch --input '{"url":"...","maxDepth":0,"mode":"pages","verbose":true}'
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | 必填 | 仓库标识，支持三种格式：① 单个关键词（如 `"proot"`）；② `owner/repo` 格式（如 `"vercel/ai"`、`"proot-me/proot"`）；**不支持**普通 URL（`https://github.com/...` 会返回 `DOMAIN_NOT_ALLOWED`）。 |
| `maxDepth` | int | 1 | `0`=单个仓库；`1`=多仓库/全局索引。 |
| `mode` | string | `"aggregate"` | `"aggregate"`=聚合模式；`"pages"`=页面模式（返回更完整的分页结构）。 |
| `verbose` | bool | `false` | `true` 返回更详细的源码引用和来源链接。 |

### 返回值结构

成功时返回 Markdown 文本，包含：
- 仓库 Overview（架构、核心子系统、设计模式）
- 分页导航目录
- Relevant source files（带 GitHub 行号链接）
- 源码片段和架构图

失败时返回 JSON error：
```json
{"error":"unexpected argument: ...","code":"PARSE_ERROR"}
{"error":"Only deepwiki.com domains are allowed","code":"DOMAIN_NOT_ALLOWED"}
```

### 使用示例

```bash
# 按关键词查询（会匹配最相关的仓库）
minis-mcp-cli call mcp-deepwiki deepwiki_fetch --input '{"url":"proot","maxDepth":0,"mode":"pages","verbose":true}'

# 按 owner/repo 精确查询
minis-mcp-cli call mcp-deepwiki deepwiki_fetch --input '{"url":"vercel/ai","maxDepth":0,"mode":"pages","verbose":true}'

# 简洁模式（默认 aggregate）
minis-mcp-cli call mcp-deepwiki deepwiki_fetch --input '{"url":"mvanhorn/last30days-skill"}'
```

### 注意事项

1. **不要用普通 URL**：`https://github.com/...` 格式会被拒绝，只接受关键词或 `owner/repo` 格式。
2. **不是实时仓库克隆**：DeepWiki 返回的是已索引的文档化摘要，不是原始文件列表。最新索引日期在返回内容顶部可见（如 `Last indexed: 9 June 2025`）。
3. **适合快速理解代码库**：比直接 clone 仓库更快，尤其适合：架构 overview、源码结构、关键类/函数映射、设计模式分析。
4. **不适合场景**：需要精确文件内容、最新 commit 细节、非 GitHub 仓库。

## 环境变量配置参考

以下环境变量用于解锁 agent-reach 的各平台能力。优先使用免费 tier，不要轻易升级付费计划。

| 变量名 | 用途 | 免费额度 | 获取方式 |
|--------|------|----------|----------|
| `AUTH_TOKEN` | Twitter/X 搜索 | 无（浏览器 cookie） | 浏览器登录 x.com → F12 → Application → Cookies → `auth_token` |
| `CT0` | Twitter/X 搜索 | 无（浏览器 cookie） | 同上，复制 `ct0` 值 |
| `XIAOHONGSHU_API_BASE` | 小红书 API | 未知 | 自建 API 服务或第三方接口 |
| `EXA_API_KEY` | Exa AI 搜索 | 有免费额度 | https://exa.ai 注册 |
| `BRAVE_API_KEY` | Brave 网页搜索 | 2000 次/月 | https://brave.com/search/api |
| `SERPER_API_KEY` | Google 搜索 API | 2500 次免费 | https://serper.dev |
| `SCRAPECREATORS_API_KEY` | YouTube/TikTok/Instagram 抓取 | 有免费额度 | https://scrapecreators.com |
| `BRIGHTDATA_APITOKEN` | BrightData MCP | 5000 次/月免费 | https://brightdata.com/cp/setting/users |
| `FIRECRAWL_API_KEY` | Firecrawl | 有免费额度 | https://www.firecrawl.dev/ |

### 配置方式

通过 Minis Settings → Environment Variables 创建，或在 shell 中：
```bash
minis-config set envvars.append '{"key":"AUTH_TOKEN","value":"xxx"}'
```

### 注意事项

1. **不要超过免费额度**：每月检查用量，避免意外扣费
2. **Twitter/X cookie 会过期**：如果搜索失效，重新登录浏览器获取新 cookie
3. **代理环境**：当前 PRoot 环境通过 `HTTPS_PROXY` 联网，某些 API 可能受限
4. **key 安全**：不要直接发到聊天窗口，使用 [Set ENV_NAME](minis://settings/environments?create_key=ENV_NAME) 链接私密配置

## 选择指南

| 工具 | 来源 | 用途 |
|-----|------|------|
| gh CLI | agent-reach | Git 操作 |
| DeepWiki | MCP (deepwiki) | 代码库架构理解与文档化摘要 |
| zread | my-mcp-tools | 读仓库内容 |
| context7 | my-mcp-tools | 查技术文档 |
