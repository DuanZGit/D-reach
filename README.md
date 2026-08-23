# D-Reach

统一搜索、爬虫、网页读取、社交媒体、代码仓库、视频字幕的顶层路由器（Agent Skill）。

**整合通道**：百度千帆、Exa、BrightData MCP、Firecrawl（Developer Index / Research Index / scrape）、Jina Reader、gh CLI、DeepWiki、yt-dlp、xhs、bili、twitter、rdt、browser_use 等。

**核心特性**：
- 🔀 统一路由：用户只说「搜 / 查 / 读 / 爬」，自动选最优通道
- 🛡️ 免费额度防护：所有带免费上限的服务调用前自动检查配额，超限自动降级到免费替代，**绝不进入付费模式**
- 🧩 顶层 Skill：`SKILL.md` + `references/`（按场景阅读）+ `scripts/`（配额门控 + 统一执行器）

## 内容结构

| 路径 | 作用 |
| --- | --- |
| [`SKILL.md`](SKILL.md) | 顶层路由器（触发词、路由表、配额门控说明、零配置命令） |
| [`references/`](references/) | 场景文档：`search` / `scrape` / `web` / `social` / `career` / `dev` / `video` / `finance` |
| [`scripts/`](scripts/) | 统一执行器 + 配额门控 + 配额管理器 |
| [`extensions/d-reach-xhs`](extensions/d-reach-xhs) | 小红书实战增强 |
| [`extensions/d-reach-twitter`](extensions/d-reach-twitter) | Twitter/X 实战增强 |

## 快速使用

```bash
# 统一搜索（自动配额+路由+fallback）
python3 scripts/unified_entry.py search "关键词" zh   # 中文
python3 scripts/unified_entry.py search "query" en    # 英文

# Firecrawl Developer Index（编程专用，免 API key）
python3 scripts/unified_entry.py developer "how to configure retries in tokio"

# Firecrawl Research Index（学术论文，免费）
python3 scripts/unified_entry.py research "LLM agent memory"

# 统一爬取
python3 scripts/unified_entry.py scrape "https://example.com"

# 查所有通道额度
python3 scripts/quota_manager.py status
```

### 免费额度一览

| 通道 | 免费额度 | 超限 fallback |
| --- | --- | --- |
| BrightData MCP | 5,000 / 月 | Jina Reader → Firecrawl |
| Firecrawl Free | 1,000 credits / 月 | BrightData → Jina |
| Firecrawl Research Index | 免费（不耗 credits） | - |
| Firecrawl Developer Index | 免 API key | - |
| 百度千帆搜索 | 400 / 日 | BrightData → Exa |
| Exa | 1,000 / 月 | BrightData → 百度 |
| Jina Reader | 300 / 日 | BrightData |
| Brave | 2,000 / 月 | BrightData |
| Serper | 2,500 / 月 | BrightData |

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `BRIGHTDATA_APITOKEN` | BrightData MCP（5,000 次/月免费） |
| `FIRECRAWL_API_KEY` | Firecrawl（1,000 credits/月；Research Index 免费需 key） |
| `EXA_API_KEY` | Exa 搜索 |
| `TWITTER_AUTH_TOKEN` / `TWITTER_CT0` | Twitter/X（浏览器 Cookie） |

## 安全规则

- `.env` 与真实凭据目录已由 [`.gitignore`](.gitignore) 排除；
- 本仓库不包含任何真实 Cookie、Token、账号或浏览器会话数据；
- 示例中的 `...`、`<auth_token>`、`<ct0>` 均为占位符，不可替换为真实凭据后提交；
- 密钥一律通过环境变量引用（`$$VARNAME`），不硬编码。

## 说明

D-Reach 基于开源 [Agent-Reach](https://github.com/Panniantong/Agent-Reach) 的本地定制超集，额外整合 BrightData MCP、Firecrawl 全能力、统一配额防护系统，以及经本机验证的小红书 / B站 / Twitter 登录态流程。
