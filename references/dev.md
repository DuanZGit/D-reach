# 开发工具

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
minis-mcp-cli call deepwiki ask_question --input '{"repo":"owner/repo","question":"这个仓库的并发模型是怎么实现的？"}'
```

- `repo` 用 `owner/repo` 或关键词，**不要传 `https://github.com/...` 全 URL**（会被拒）。
- 返回的是已索引的文档摘要（顶部有 `Last indexed:` 日期），不是实时文件列表；
  要精确文件内容 / 最新 commit → `gh api`。
- 未索引的仓库直接降级到 `gh`，不要反复重试。
