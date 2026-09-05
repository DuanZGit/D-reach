# D-Reach

搜索 / 爬取 / 网页读取 / 社交媒体 / 代码仓库 / 视频字幕的统一路由（Agent Skill）。

**通道**：百度千帆、Exa、BrightData、Firecrawl（Developer / Research Index）、Jina Reader、
gh CLI、DeepWiki、yt-dlp、bili-cli、xhs-cli、twitter-cli、opencli、browser_use。

**设计**：路由表写在 `SKILL.md`，由 agent 直接读表执行 —— 没有中间执行器。
唯一的代码是 `scripts/quota.py`（约 100 行），只做一件事：记免费额度，防止越过免费线产生费用。

## 用法

```bash
# 看额度
python3 scripts/quota.py status

# 占用一次（超限 exit 1，于是可以 `use x || 换备选`）
python3 scripts/quota.py use brightdata

# 清零
python3 scripts/quota.py reset brightdata
```

调用方式全部在 [`SKILL.md`](SKILL.md) 的路由表与命令块里；细节按场景查 [`references/`](references/)。

## 免费额度一览

| 通道 | 免费额度 | 超限降级 |
| --- | --- | --- |
| BrightData Unlocker | 5,000 / 月 | Jina → browser_use |
| Exa | ~1,000 / 月 | 百度千帆 → BrightData |
| Firecrawl Free | 1,000 credits / 月 | BrightData → Jina |
| Firecrawl Research Index | 免费（不耗 credits，需 key） | — |
| Firecrawl Developer Index | 免 API key | — |
| 百度千帆搜索 | 400 / 日（**由 baiduaisearchwithquota 自己记账**） | BrightData → Exa |
| Jina Reader | 300 / 日（限流） | BrightData |
| gh / yt-dlp / DeepWiki / v2ex | 免费无限 | — |

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `BRIGHTDATA_APITOKEN` | BrightData REST（5,000 次/月） |
| `EXA_API_KEY` | Exa 搜索 |
| `FIRECRAWL_API_KEY` | Firecrawl Research Index / 提高 Developer Index 限流 |
| `TWITTER_AUTH_TOKEN` / `TWITTER_CT0` | twitter-cli 登录态 |

## 安全

- 密钥一律走环境变量（`$$VARNAME`），不硬编码、不写进 markdown。
- `secrets.enc` 是**已加密**的凭据包（AES-256-CBC + PBKDF2 600k），含 API key 与
  bilibili / xhs cookie；密码不入库，丢失不可恢复。加解密方式见 [`SECRETS.md`](SECRETS.md)。
- `secrets.json`（明文）已被 `.gitignore` 排除。若仓库转公开，**必须先删 `secrets.enc` 并清历史**。

## 说明

基于开源 [Agent-Reach](https://github.com/Panniantong/Agent-Reach) 的本地定制超集，
按本机实况裁剪：删除了未注册的 MCP 通道与统一执行器，保留经本机验证的
小红书 / B站 / Twitter 登录态流程与踩坑记录。
