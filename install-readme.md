# 安装 D-Reach

D-Reach 是一个纯文本 + 两个小脚本的 Agent Skill：**没有密钥也能用**，装上就有一批免费免 Key 通道；
想要更强的中文/学术/商业搜索，再按需填 key，功能逐级解锁。

---

## 1. 装到哪里

Agent 读取技能的标准位置（二选一，装到 `~/.agents/skills` 最稳）：

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/DuanZGit/D-reach.git ~/.agents/skills/d-reach
```

Minis / 其它把技能放在 `/var/minis/skills` 的环境：

```bash
git clone https://github.com/DuanZGit/D-reach.git /var/minis/skills/d-reach
```

`scripts/fanout.sh` 会自动探测这两个路径，装哪边都能跑。

## 2. 系统依赖

| 依赖 | 必需 | 用途 | 安装 |
| --- | --- | --- | --- |
| `bash` | 是 | 跑 `fanout.sh` | 系统自带 |
| `curl` | 是 | 所有通道的 HTTP 请求 | 系统自带 |
| `python3` ≥ 3.8 | 是 | `quota.py` 记账、解析 JSON | 系统自带 |
| `gh` CLI | 否 | GitHub 仓库/代码搜索（`gh search`） | `brew install gh` / `apt install gh` |
| `yt-dlp` | 否 | 视频字幕（B站/YouTube） | `pipx install yt-dlp` |
| `bili` / `xhs` / `twitter-cli` | 否 | 社交平台登录态抓取 | 见 `references/social.md` |
| `opencli` | 否 | 电商/雪球等适配器（需 Chrome 桥） | `npm i -g @jackwener/opencli`（本机 2.0.2；2.x 默认输出 JSON，`-f yaml` 仍可用） |

不需要 Node、不需要 npm 安装、不需要任何 Python 第三方包。

## 3. 验证安装

```bash
cd ~/.agents/skills/d-reach
bash scripts/fanout.sh --list          # 应列出所有通道名
bash scripts/fanout.sh "测试查询"       # 默认档 9 路，约 5 秒
python3 scripts/quota.py budget        # 看限额通道还剩多少
python3 scripts/test_quota.py          # 记账逻辑自检（应打印「自检通过」）
```

默认档 9 路里有 7 路**完全不需要 key**（Crossref 遇中文自动跳过），所以第一次跑就该有结果。
显示 `🔇 未配置 key` 属于正常 —— 千帆要装另一个技能、TinyFish 要 key，缺了自动跳过。

## 4. 密钥清单（按需填，全部可选）

所有 key 走同一条查找链，**填一处即可**：

```
$环境变量  →  ~/.config/agents/env  →  <技能目录>/.env
```

推荐做法：

```bash
mkdir -p ~/.config
touch ~/.config/agents/env && chmod 600 ~/.config/agents/env
echo 'EXA_API_KEY=你的key' >> ~/.config/agents/env
```

缺失时脚本会在 stderr 打印「变量名 / 申请地址 / 写入方法 / 降级方案」四要素，Agent 会转述给你。

### 4.1 限额通道（填了才解锁）

> 数字口径：**2026-10-26 对官方定价页核实**。厂商改政策频繁，长期用之前自己再核一次。

| 变量名 | 服务 | 免费额度 | 不填的后果 | 申请 |
| --- | --- | --- | --- | --- |
| `LANGSEARCH_API_KEY` | LangSearch | 每日 token 额度（官方不给固定请求数；00:00 UTC 重置，起始 5 RPS） | 少一路中文长尾/限域搜索 | langsearch.com/dashboard |
| `EXA_API_KEY` | Exa | $10 余额/月 ≈ 2,500 次 Lite search（每月 1 日重置） | 缺语义搜索，官方文档/wiki 命中变差 | dashboard.exa.ai |
| `FIRECRAWL_API_KEY` | Firecrawl | 1,000 credits/月（约 500 次 search 或 1,000 页；不结转）<br>**论文端点免费，不耗 credits** | Research Index 不可用，只剩免 Key 的 Developer Index | firecrawl.dev |
| `BRIGHTDATA_APITOKEN` | BrightData | 5,000 requests/月 | 反爬站点打不开，只能退回 Jina | brightdata.com |
| `TINYFISH_API_KEY` | TinyFish | **search / fetch $0/次**（30 搜/分、150 抓/分；automation $0.016/步） | 少一路免计费搜索与网页抓取 | agent.tinyfish.ai/api-keys |
| `BAIDU_API_KEY` | 百度千帆 | 搜索类 400 次/日（总量，5 个搜索 API 共享） | 中文 AI 摘要线索缺失（由另一个技能 `baiduaisearchwithquota` 使用，缺了自动跳过） | qianfan.console.baidu.com |
| `JINA_API_KEY` | Jina Reader（**仅手打时用**，fanout 不读） | 免 key 约 20 RPM；有 key 约 200 RPM（按 token 计） | 手打 `curl r.jina.ai` 时更易被限流 | jina.ai |

> `SERPER_API_KEY` / `SCRAPECREATORS_API_KEY` 已从本表移除：当前 `fanout.sh` 与 `quota.py` 里**没有任何代码读它们**（早前版本留的残影）。
> 需要这两家的能力时按 `references/` 里的 REST 示例手打，并自己把 key 写进 env。

**额度会自动校准**：`fanout.sh` 每次跑完调用 `scripts/quota_probe.py`，去官方接口查真实剩余
（Firecrawl `/v2/team/credit-usage`、TinyFish MCP `get_wallet`）。其余几家没有公开额度接口，
继续用本地记账兜底。想看校准结果：`python3 scripts/quota.py budget`。

### 4.2 登录态（社交通道，不是普通 key）

| 变量 / 文件 | 用途 | 拿法 |
| --- | --- | --- |
| `TWITTER_AUTH_TOKEN` + `TWITTER_CT0` | twitter-cli 读推文/搜索 | 浏览器登录后从 Cookie 取 `auth_token`、`ct0` |
| `~/.bilibili-cli/credential.json` | B站登录态 | `bili login`，或按 `references/social.md` 手工写 |
| `~/.xiaohongshu-cli/cookies.json` | 小红书登录态 | `xhs login`，cookie 约 30 天失效需重取 |

### 4.3 官方 MCP 接入（Agent 支持 MCP 时首选）

上面这些服务里，有一批**官方提供了 MCP server**。如果你的 Agent（pi / Claude Code / Codex / Cursor 等）支持 MCP，
直接挂官方端点即可，不用自己写 HTTP 调用 —— 和本技能的 REST 通道**共用同一把 key**，两条路可以并存。

| 服务 | 官方托管端点 | 认证 | 本地 stdio 方式 | 关键工具 | 本机状态 |
| --- | --- | --- | --- | --- | --- |
| Exa | `https://mcp.exa.ai/mcp` | 免 key（限速）/ OAuth 用 `?login` / header `x-api-key` | `npx -y exa-mcp-server` + `EXA_API_KEY` | `web_search_exa`、`web_fetch_exa`、`agent_run`（实测 3 个，带 key 会多出 agent_run） | **已挂** |
| Firecrawl | `https://mcp.firecrawl.dev/v2/mcp`（Bearer key）<br>`https://mcp.firecrawl.dev/v2/mcp-oauth`（OAuth，无需 key） | `Authorization: Bearer $FIRECRAWL_API_KEY` 或浏览器 OAuth | 见官方 `mcp-server/local` 文档 | 31 个（`firecrawl_search`/`scrape`/`map`…） | 未挂 |
| TinyFish | `https://agent.tinyfish.ai/mcp` | OAuth（`pi mcp auth tinyfish`）或 `X-API-Key` header | — | search、fetch_content、monitor、run_web_automation | **已挂** |
| BrightData | `https://mcp.brightdata.com/mcp?token=<token>`（SSE 版：`/sse?token=`） | token 直接放 query | `npx @brightdata/mcp` + `API_TOKEN` | 31 个（`search_engine`/`scrape_as_markdown`…） | 未挂 |
| Jina | `https://mcp.jina.ai/v1` | header `Authorization: Bearer $JINA_API_KEY`（可省略，限额更紧） | `npx -y mcp-remote https://mcp.jina.ai/v1` | 12 个（`read_url`/`search_web`/`search_arxiv`/`extract_pdf`） | 未挂 |
| LangSearch | `https://mcp.langsearch.com/mcp`（Streamable HTTP，**路径必须带 `/mcp`**） | `Authorization: Bearer <LangSearch API key>` | — | 1 个（`web_search`） | **已挂** |
| DeepWiki | `https://mcp.deepwiki.com/mcp` | **免 key** | — | `ask_wiki_question`、`read_wiki_contents`、`read_wiki_structure` | **已挂** |

> 上表的端点、工具数都是 2026-10-26 用本机 key 实测 `tools/list` 拿到的，不是抄文档。
> 本机 `mcp.json` 已挂：deepwiki / tinyfish / exa / langsearch / rea（`pi mcp list` 全部 connected）。
> 需要带 session 的（BrightData / TinyFish）先 `initialize` 拿 `Mcp-Session-Id`，后续请求要带上，否则 400。

客户端配置样例（支持标准 `mcpServers` 的客户端通用）：

```json
{
  "mcpServers": {
    "exa": { "url": "https://mcp.exa.ai/mcp" },
    "deepwiki": { "url": "https://mcp.deepwiki.com/mcp" },
    "jina": {
      "url": "https://mcp.jina.ai/v1",
      "headers": { "Authorization": "Bearer ${JINA_API_KEY}" }
    },
    "brightdata": {
      "command": "npx",
      "args": ["-y", "@brightdata/mcp"],
      "env": { "API_TOKEN": "${BRIGHTDATA_APITOKEN}" }
    }
  }
}
```

几点说明：

- **免 key 也能连**的只有 Exa（限速档）和 DeepWiki，其余官方 MCP 都要 key（同一把，不用申请两次）。
- **Serper 没有官方 MCP**（GitHub 上只有社区包 `mcp-server-serper` / `serper-mcp-server`），要接就自己评估第三方实现。
- MCP 走的是各服务自己的配额，本技能 `quota.py` 只管 REST 调用；走 MCP 时不记账，别以为「没记账 = 随便用」。
- 不适合挂 MCP 的客户端（纯 HTTP 环境）照旧用 REST + `scripts/load_key.sh`，能力一样。

### 4.4 完全不需要 key 的通道（装机即用，深挖主力）

`cn.bing`、Firecrawl Developer Index、StackExchange、HN Algolia、掘金、SegmentFault、
OpenAlex、Crossref、GitHub（`gh` 登录即可）、DeepWiki、yt-dlp。

这些通道**不限量、不记账**，L2 起步就该一次铺满 —— 闲置才是浪费。

## 5. 30 秒上手

```bash
cd ~/.agents/skills/d-reach

# 默认档：9 路并发（7 路完全免 key，约 5s）
bash scripts/fanout.sh "ollama vs vllm"

# 深调研：追加 4 路限额通道（约 12s，自动记账）
bash scripts/fanout.sh "ollama vs vllm" --deep

# 只看某几路
bash scripts/fanout.sh "关键词" --on bing,hn,oalex
```

调用细节、定档规则（L1/L2/L3）、各平台命令都在 [`SKILL.md`](SKILL.md)，
按场景的示例见 [`references/`](references/)。

## 6. 安全约定

- 仓库**不含任何密钥**；key 只存在你自己的 `~/.config/agents/env` 或技能目录 `.env`（已被 `.gitignore` 排除）。
- 不要把 `env` / `cookies.json` / `credential.json` 提交到任何仓库。
- `scripts/load_key.sh` 只输出 key 值给调用方，永不打印到终端。
