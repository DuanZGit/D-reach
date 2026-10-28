# D-Reach

搜索 / 爬取 / 网页读取 / 社交媒体 / 代码仓库 / 视频字幕的统一路由（Agent Skill）。

**通道**：百度千帆、Exa、LangSearch、BrightData、Firecrawl（Developer / Research Index）、Jina Reader、
gh CLI、DeepWiki、yt-dlp、bili-cli、xhs-cli、twitter-cli、opencli、browser_use。

**设计**：路由表写在 `SKILL.md`，由 agent 直接读表执行 —— 没有中间执行器。
代码只有两个小件：`scripts/quota.py`（约 200 行）记免费额度防越线，
`scripts/fanout.sh`（一条命令并发铺开默认档 10 路 + `--deep` 4 路限额通道）。

## 安装

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/DuanZGit/D-reach.git ~/.agents/skills/d-reach
bash ~/.agents/skills/d-reach/scripts/fanout.sh --list
```

系统依赖（bash / curl / python3）、按需填的密钥清单、哪些通道完全免 key、
哪些服务提供**官方 MCP 接入** —— 全部见 [install-readme.md](install-readme.md)。

## 用法

```bash
# 开工前规划：到裕度线还剩多少（推荐第一步）
python3 scripts/quota.py budget

# 看原始计数
python3 scripts/quota.py status

# 官方额度校准（查厂商真实剩余，写进 quota.json 的 _official 段）
python3 scripts/quota_probe.py

# 占用一次：exit 0=正常 / 2=已过裕度线（仍记账）/ 1=越免费线（不记账）
python3 scripts/quota.py use brightdata

# 清零
python3 scripts/quota.py reset brightdata
```

调用方式全部在 [`SKILL.md`](./SKILL.md) 的路由表与命令块里；细节按场景查 [`references/`](references/)。

```bash
# L2 起别逐条手打 —— 一条命令并发铺开（默认档 10 路，仅千帆/TinyFish 要 key，~5s）
bash scripts/fanout.sh "ollama vs vllm"
# L3 深调研：追加 LangSearch / Exa / Firecrawl-Research / BrightData（~12s，自动记账）
bash scripts/fanout.sh "ollama vs vllm" --deep
```

**调研强度默认 L2**（≥6 个独立来源 + 2 轮），命中「对比/选型/调研/为什么/最新/vs」等词自动升 L3
（≥10 来源 + 3 轮）。定档依据、查询改写 ≥5 种、收尾自查见 SKILL.md。
免费免 Key 通道不记账，**fanout 默认档已一次并发铺满；deep 四路月余量 >96%，L3 无条件铺**。

`fanout.sh` 跑完会自动做一次**官方额度校准**（`quota_probe.py --quiet`，10 分钟内复用上次结果，
不拖慢本轮）。可查的只有 Firecrawl（`/v2/team/credit-usage`）和 TinyFish（MCP `get_wallet`）；
BrightData 需要 token 有 account 读权限，Exa / Jina / LangSearch 没有公开额度接口 —— 这些继续用本地计数兜底。

## 免费额度一览

> 数字口径：**2026-10-26 对官方定价页核实**。厂商改政策频繁，长期使用前建议自己再核一次。

| 通道 | 免费额度 | 重置规则 | 超限降级 |
| --- | --- | --- | --- |
| BrightData（MCP/Unlocker） | 5,000 requests / 月 | 月 | Jina → browser_use |
| Exa | $10 余额 / 月 ≈ 2,500 次 Lite search | 每月 1 日重置 | 百度千帆 → BrightData |
| LangSearch | 每日 token 额度（官方不给固定请求数，起始 5 RPS） | 00:00 UTC | cn.bing 已弃用 → BrightData |
| Firecrawl Free | 1,000 credits / 月（约 500 次 search 或 1,000 页抓取） | 月，不结转 | BrightData → Jina |
| Firecrawl Research Index | **论文端点完全免费，不耗 credits**（官方 Billing FAQ 明确） | — | — |
| Firecrawl Developer Index | 免 API key | — | — |
| 百度千帆搜索 | 400 / 日（**由 baiduaisearchwithquota 自己记账**，非本技能扣） | 日 | BrightData → Exa |
| Jina Reader | 免 key 约 20 RPM；有 key 约 200 RPM（按 token 计） | 分钟级 | BrightData |
| TinyFish search / fetch | **$0/次**（30 搜/分、150 抓/分） | 分钟级 | — |
| Serper | 2,500 次（**一次性，不重置**） | 不重置 | 换 Exa / LangSearch |
| gh / yt-dlp / DeepWiki / StackExchange / HN / OpenAlex / Crossref / 掘金 / SegmentFault | 免费无限 | — | — |

**30% 裕度**：日线与月线都按上限的 70% 设线（`D_REACH_RESERVE` 可调），过线只提示不阻断；
剩下 30% 留给突发任务。免 Key 不限量通道不记账 —— 它们才是深挖的主力。

## 环境变量

全部 optional，路径与申请入口见 [install-readme.md](install-readme.md#4-密钥清单按需填全部可选)。核心四个：

| 变量 | 用途 |
| --- | --- |
| `BRIGHTDATA_APITOKEN` | BrightData REST（5,000 次/月） |
| `EXA_API_KEY` | Exa 搜索 |
| `FIRECRAWL_API_KEY` | Firecrawl Research Index / 提高 Developer Index 限流 |
| `LANGSEARCH_API_KEY` | LangSearch Web Search（langsearch.com/dashboard） |

社交通道另外需要 `TWITTER_AUTH_TOKEN` / `TWITTER_CT0`，以及 bili / xhs 的登录态文件。

## 安全

- 密钥一律走环境变量或 `~/.config/agents/env`，不硬编码、不写进 markdown。
- **本仓库不携带任何凭据**。key 只存在用户本机（`~/.config/agents/env` 或技能目录 `.env`，后者已在 `.gitignore` 内）。
- `scripts/load_key.sh` 是取 key 的统一入口：查找链 `$环境变量 → ~/.config/agents/env → <技能目录>/.env`，
  找不到时在 stderr 打印「变量名 / 申请地址 / 写入方法 / 降级方案」，从不 echo 值。
- 社交通道用登录态文件（`~/.bilibili-cli/credential.json`、`~/.xiaohongshu-cli/cookies.json`），同样不入库。

## 说明

基于开源 [Agent-Reach](https://github.com/Panniantong/Agent-Reach) 的本地定制超集，
按本机实况裁剪：删除了未注册的 MCP 通道与统一执行器，保留经本机验证的
小红书 / B站 / Twitter 登录态流程与踩坑记录。
