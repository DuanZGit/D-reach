---
name: d-reach
description: >
  统一搜索与爬取路由器，覆盖中英文网页搜索、社交媒体（小红书/B站/微博/Twitter/Reddit）、
  GitHub 仓库、视频字幕、股票行情和任意网页抓取。整合百度千帆、Exa、BrightData、Firecrawl、
  Jina Reader、gh CLI、DeepWiki、yt-dlp、bili、xhs 等全部通道，共享一套免费额度计数器。
  只要用户想搜（搜/查/找/search/搜索/查一下/帮我搜）、想爬或抓网页内容（爬/抓/scrape/提取数据）、
  想读一篇文章或链接（读一下/打开这个/看看链接）、想查社交平台内容（小红书/B站/微博/推特/Reddit）、
  想找 GitHub 仓库或代码、想要视频字幕、想查股票行情，或者需要任何需要当前网络信息的调研——
  即使用户没有点名具体平台，也使用本技能。
  不要用于有独立触发词的领域技能：食谱/健康（DK）、个股分析流程（gushen）、深度研究报告（research）。
license: MIT
metadata:
  openclaw:
    homepage: https://github.com/DuanZGit/D-reach
---

# D-Reach — 搜索与爬取统一路由

把"用户想找信息"翻译成"用哪个通道、怎么调用"。**路由表由你（agent）直接执行**，
没有中间脚本；唯一的代码是 `scripts/quota.py`，它只负责记额度。

## 决策流程

1. 判断意图 → 查下方路由表，取首选通道
2. 有免费上限的通道（表中标 ⏱）调用前记账：`python3 scripts/quota.py use <svc>`
   返回 exit 1 表示已越线 → **立刻换同一行的备选，不要停下来问用户**
3. 首选失败（超时/风控/未安装）→ 同样换备选
4. 全部越线 → 明确告知用户哪些额度用完，**不静默失败，不偷偷调付费 API**

## 路由表

| 意图 | 首选 | 备选 | 兜底 |
|------|------|------|------|
| 中文搜索 | 百度千帆（自带计数器） | BrightData ⏱ | Jina ⏱ |
| 英文/技术搜索 | Exa ⏱ | 百度千帆 | BrightData ⏱ |
| 编程文档/issue | Firecrawl Developer Index（免 key） | Exa ⏱ | gh CLI |
| 学术论文 | Firecrawl Research Index（需 key，免费） | Exa ⏱ | — |
| 网页抓取（反爬） | BrightData ⏱ | Jina ⏱ | browser_use ⏱ |
| 批量网页抓取 | BrightData（循环单抓，≤10）⏱ | Jina ⏱ | — |
| GitHub 仓库/代码 | gh CLI（免费无限） | DeepWiki MCP | Exa |
| 仓库语义问答 | DeepWiki MCP `ask_question` | gh CLI 读源码 | — |
| B站 | bili CLI ⏱ | browser_use ⏱（**不要 yt-dlp，会被 412 拦**） | — |
| YouTube 字幕 | yt-dlp（免费无限） | — | — |
| 小红书 | xhs CLI ⏱（**当前 cookie 过期，需 `xhs login`**） | browser_use ⏱ | — |
| Twitter/X | browser_use ⏱（本机 `twitter` 是 npm 同名假货，见下） | 装 Python 版 twitter-cli | — |
| 股票行情 | gushen 技能（雪球） | 百度千帆 | — |
| 需要登录的站点 | browser_use ⏱ | — | — |

### 通道现状（2026-09-05 实测）

> **网络全线 000 时先查 DNS，别怀疑出口**：`/etc/resolv.conf` 里 `172.19.0.2` 是透明代理的
> fake-ip 解析器，代理一死就返回 `198.18.x` 让所有 HTTPS 变 000（域名看着解析成功，实则废）。
> 改成 `nameserver 8.8.8.8` / `1.1.1.1` 立刻全通，不需要任何隧道或中继。

- ✅ 实测返回真实数据：百度千帆、Exa、BrightData（抓取 + Google）、Jina、Firecrawl（developer + research）、gh（search/api）、DeepWiki `ask_question`、bili CLI、V2EX。
- ⚠️ `xhs`：cookie 过期，报 `not_authenticated` → 要用户 `xhs login` 扫码后才能用。
- ❌ `twitter`：PATH 上的是 npm `twitter-cli@0.0.2`（filter stream 玩具），**不是**文档里的 Python v0.8.5。任何子命令都只打印一行 usage 并 **exit 0** —— 静默假成功，别当成"没结果"。要真用得 `pipx install twitter-cli` 并确认 `which twitter` 不再指向 `/usr/local/bin`。
- ⚠️ Reddit 公开 JSON：数据中心 IP 被拉黑，返回 **200 + "Blocked" HTML**（不是 403），别误读成空结果 → 换 browser_use / BrightData。

## 通道命令

```bash
# 百度千帆（400 次/日免费，配额由该技能自己记账，不要重复扣）
python3 /var/minis/skills/baiduaisearchwithquota/scripts/smart_search.py search '查询'

# Exa（英文/技术）
curl -s --max-time 30 -X POST https://api.exa.ai/search \
  -H "x-api-key: $EXA_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"查询","numResults":5}'

# BrightData Web Unlocker（5000 次/月）——抓取
curl -s --max-time 120 -X POST https://api.brightdata.com/request \
  -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" -H "Content-Type: application/json" \
  -d '{"zone":"mcp_unlocker","format":"raw","data_format":"markdown","url":"https://example.com"}'

# BrightData 搜 Google（parsed_light 才返回 JSON）
curl -s --max-time 120 -X POST https://api.brightdata.com/request \
  -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" -H "Content-Type: application/json" \
  -d '{"zone":"mcp_unlocker","format":"raw","data_format":"parsed_light","url":"https://www.google.com/search?q=%E6%9F%A5%E8%AF%A2&num=10"}'

# Jina Reader（零配置，只吃 URL，不吃关键词）
curl -s --max-time 30 "https://r.jina.ai/https://example.com/article"

# GitHub（免费无限，不记账）
gh search repos "query" --sort stars --limit 10
```

编程文档 / 论文 / DeepWiki / gh 读文件的写法在 `references/scrape.md`、`references/dev.md`。

## B站 / 小红书 铁律（踩过的坑，别再来一遍）

```bash
bili search "query" --type video -n 5
bili video <bvid> -s --yaml        # 字幕
bili video <bvid> --ai             # AI 总结
bili video <bvid> -c --yaml        # 评论（字段是 message）

xhs search "关键词" --json         # note_id / xsec_token 在 item 顶层！
xhs comments <note_id> --xsec-token <token> --all --yaml
```

- **B站取证必须字幕 + 评论区都看**：字幕 = 作者说的（可能恰饭），评论区 = 真实用户验证
  （"买一次就没了"这类坑只出现在评论区）。单人操作帖尤其看评论；高赞薅羊毛教学默认可能有坑。
- **B站不要用 yt-dlp**，会被 412 拦。
- **小红书必须 xhs-cli ≥ 0.6.4**（`pip install --user --no-deps xiaohongshu-cli==0.6.4 xhshow`），
  旧版 0.4.0 读评论被 406 风控拦。读评论一律走 `comments`，`xhs read` 会触发 captcha。
- 裸笔记 ID 报 300031 = token 缺失/过期；短链 `xhslink.com` 需先在浏览器解析出真实 URL。
  细节见 `extensions/d-reach-xhs/SKILL.md`。

## 额度

```bash
python3 /var/minis/skills/d-reach/scripts/quota.py status
python3 /var/minis/skills/d-reach/scripts/quota.py use brightdata    # 占用，超限 exit 1
python3 /var/minis/skills/d-reach/scripts/quota.py reset brightdata
```

计数文件 `~/.agent-reach/quota.json`，跨日/跨月自动归零。
⏱ = 调用前 `quota.py use <svc>`。例外：**百度千帆由它自己的计数器记账**（别双扣）；
Firecrawl 的两个 Index REST 端点免费不记账，只有走 SDK 抓取才 `use firecrawl`；
gh / yt-dlp / DeepWiki / V2EX 免费无限，不记账。
BrightData 真实用量可对账：`curl -s -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" https://api.brightdata.com/account/usage`。

## 工作区

临时输出 `/tmp/`，持久数据 `~/.agent-reach/`。不要在 agent workspace 建文件。

## 详细文档

按需读取，不要一次全部加载：

| 文档 | 什么时候读 |
|------|-----------|
| [references/search.md](references/search.md) | 搜索通道完整参数与配额细节 |
| [references/scrape.md](references/scrape.md) | 抓取 / 网页阅读 / 公众号 / RSS |
| [references/social.md](references/social.md) | 小红书/抖音/微博/Twitter/V2EX/Reddit 细节 |
| [references/dev.md](references/dev.md) | gh CLI / DeepWiki 完整用法 |
| [references/video.md](references/video.md) | YouTube / B站 / 播客字幕 |
| [references/finance.md](references/finance.md) | 雪球股票行情 |
| [extensions/d-reach-xhs/SKILL.md](extensions/d-reach-xhs/SKILL.md) | 处理小红书笔记链接时 |
| [extensions/d-reach-twitter/SKILL.md](extensions/d-reach-twitter/SKILL.md) | 处理 Twitter/X 内容时 |
