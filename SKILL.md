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

> **路径约定**：本文件里 `$SKILLS` = 技能根目录。执行前先解析：
> `SKILLS="$HOME/.agents/skills"; [ -d "$SKILLS" ] || SKILLS=/var/minis/skills`
> （UG/本机命中 `~/.agents/skills`，Minis 命中 `/var/minis/skills`。）

# D-Reach — 搜索与爬取统一路由

把"用户想找信息"翻译成"用哪个通道、怎么调用"。**路由表由你（agent）直接执行**，
没有中间脚本；唯一的代码是 `scripts/quota.py`，它只负责记额度。

## 决策流程（默认 L2，见下节）

1. **定档**：按「调研强度」判断本次是 L1 / L2 / L3，记住该档的**最小来源数与轮次**
2. **铺开通道**：查下方路由表，把该档要求的通道**一次全起**，不是只取一行首选。
   免费免 Key 通道（✅免）优先铺满 —— 它们不限量，闲着才是浪费
3. **记账**：限额通道（⏱）调用前 `python3 scripts/quota.py use <svc>`
   - exit 0 → 正常用
   - **exit 2 → 已过 30% 裕度线（仍记账）**：这一路后续只用在免费通道拿不到的内容上
   - **exit 1 → 越免费线（不记账）**：立刻换同一行备选 / 免费通道，不要停下来问用户
4. **先重试再换**：本机出口对境外域**有间歇抖动**（同一请求时而 0.8s 200、时而 5s 被切）——
   遇到超时 / 000 **先重试 1 次**，仍失败才换备选；同一通道最多重试 3 次再降级。
   （踩过：把一次抖动判成「通道坏了」，连换 4 个通道还错杀了 Jina）
5. **追深一轮**（L2 起）：把首轮捞到的新名词、版本号、人名、机构名回灌成第二轮查询
6. **收尾自查**：过一遍「收尾自查」，不达标就补一轮，别急着交付
7. 全部越线且免费通道也无结果 → 明确告知哪些额度用完、试过哪些通道，**不静默失败，不偷偷调付费 API**

## 调研强度（默认 L2）

> 定档依据来自实测：d-reach 是低频技能（近 30 天仅 20 个会话用到），而限额通道余量 >95%
> （BrightData 月用 152/5000、Exa 3/1000、Firecrawl 1/1000）。**单次做深**比「每次都浅」划算得多。

| 档 | 什么时候用 | 最小独立来源 | 轮次 | 硬要求 |
|---|---|---|---|---|
| **L1 点查** | 单一事实：版本号 / 价格 / 日期 / 某人某物是否存在 | 2 | 1 | 两个独立来源互证；打架就升 L2 |
| **L2 对比·选型**（默认） | 「哪个好 / 怎么选 / 求推荐 / 怎么样 / 值不值」 | 4 | 2（发现轮 → 追证轮） | ≥2 类通道且免费优先；≥1 条一手源（官方文档 / 论文原文 / 原帖 / 公告） |
| **L3 深调研** | 用户明说「调研 / 报告 / 全面 / 系统性对比 / 出一份」 | 6 | 3（广撒 → 追深 → 反证） | ≥1 条**反方来源**（缺点 / 失败案例 / 相反结论）；交付可引用清单 |

**独立来源** = 不同域名或不同主体；同一篇文章被转载 5 次仍算 1 个。
不确定档位时取高一档（多查一条比漏查一条便宜）。

**广度**：同一问题至少 3 种改写（原词 → 同义/上下位 → 英文 → 限定域 `site:` → 时效问题加时间），
反证独立走一轮（`<主题> 缺点 / 失败 / 不推荐 / 争议`）。模板与分档调用序列见
[references/search.md](references/search.md)。

**免费优先**：cn.bing / StackExchange / HN Algolia / OpenAlex / Crossref / 掘金 / 博客园 /
36氪 / 豆瓣 / gh CLI / DeepWiki / V2EX 不限量且不记账 —— L2 至少试其中 3 条，L3 至少 5 条；
限额通道只用在它们拿不到的内容上。

## 收尾自查（交付前逐条过）

- [ ] 独立来源数达标？（L1: 2 / L2: 4 / L3: 6）
- [ ] 每条关键结论都有来源，且至少 1 条**一手源**？（官方文档 / 论文原文 / 原帖 / 公告，非二手转述）
- [ ] 有没有哪条结论**只有一个来源**？→ 补一条独立佐证，或降级为「未证实」
- [ ] L3：反方来源找到了吗？找不到也要如实说「未发现反例」，不能假装没有
- [ ] 免费通道铺开了吗？（别一上来就把限额通道打光）
- [ ] 有没有把「搜不到」当成「不存在」？要说明试过哪些通道

## 凭据接口（key 从哪来，技能不管）

本技能**不携带任何密钥**。需要 key 的通道统一经 `scripts/load_key.sh` 取用，查找链：

```
$环境变量 → ~/.config/agents/env（用户级集中 env）→ <技能目录>/.env → 缺失报错+引导
```

- 用法：`KEY=$(sh scripts/load_key.sh EXA_API_KEY https://dashboard.exa.ai) || 降级`
- 缺失时 stderr 输出四要素（变量名/申请 URL/写入方法/降级说明），agent 转述给用户即可
- 首次使用无 key 的用户（BYOK）：按报错申请填入 `~/.config/agents/env`（chmod 600）即可解锁付费通道；不填则全技能走免费通道，功能自动降级
- 纪律：key 值永不进 SKILL.md/代码/commit/日志/记忆；引用一律 `$VAR`；禁止 `cat .env*`

| 通道 | 变量名 | 申请入口（免费额度） |
|---|---|---|
| Exa | `EXA_API_KEY` | dashboard.exa.ai |
| BrightData | `BRIGHTDATA_APITOKEN` | brightdata.com |
| Firecrawl | `FIRECRAWL_API_KEY` | firecrawl.dev |
| Serper | `SERPER_API_KEY` | serper.dev |
| 百度千帆 | `BAIDU_API_KEY` | qianfan.console.baidu.com |
| ScrapeCreators | `SCRAPECREATORS_API_KEY` | scrapecreators.com |

## 路由表

> **✅免 = 免 Key 且不限量，不记账；⏱ = 调用前先 `quota.py use <svc>`**
> 表内每行的 首选/备选/兜底 是**降级链**（首选挂了才走下一列），不是三选一；L2 起要多行同时开。
> 完整国内通道实测清单（含不可达站点与替代链）见 **[references/cn-reach.md](references/cn-reach.md)**。

| 意图 | 首选 | 备选 | 兜底 |
|------|------|------|------|
| 中文搜索 | 百度千帆（自带计数器） | cn.bing 站内 ⏱ | BrightData ⏱ |
| 英文/技术搜索 | **cn.bing** ✅免 | Exa ⏱ | BrightData ⏱ |
| 代码报错/排障 | **StackExchange API** ✅免 | Firecrawl Developer Index ✅免 | cn.bing 站内 |
| 中文技术长尾 | **掘金 API / 博客园 / SegmentFault** ✅免 | 百度千帆 | cn.bing |
| 编程文档/issue | Firecrawl Developer Index ✅免 | Exa ⏱ | gh CLI ✅免 |
| 学术论文 | **OpenAlex / Crossref** ✅免 | Firecrawl Research Index ✅免 | Semantic Scholar ✅免 |
| 公司/专有名词背景 | 百度百科（千帆） | **cn.bing 站内** ✅免 | BrightData ⏱ |
| 深度技术讨论 | **HN Algolia** ✅免 | V2EX ✅免 | cn.bing |
| A股公告/披露 | **巨潮资讯 cninfo** ✅免 | gushen（雪球） | 东方财富 |
| 股票行情 | gushen 技能（雪球） | 百度千帆 | — |
| 行业资讯 | 36氪 / InfoQ / 澎湃 / 界面 ✅免 | 百度千帆 | — |
| 书影音评分 | 豆瓣 `window.__DATA__` ✅免 | 百度千帆 | — |
| 网页抓取（反爬） | BrightData ⏱ | Jina ⏱ | browser_use ⏱ |
| 批量网页抓取 | BrightData（循环单抓，≤10）⏱ | Jina ⏱ | — |
| GitHub 仓库/代码 | gh CLI（免费无限） | DeepWiki MCP | Gitee ✅免 |
| 仓库语义问答 | DeepWiki MCP `ask_question` | gh CLI 读源码 | —（连不上先重试：**pi 的 MCP 有 ~15s 失败退避**，`fetch failed` 常是上轮失败缓存，不是服务死；见 dev.md）|
| B站 | bili CLI ⏱ | browser_use ⏱（**不要 yt-dlp，会被 412 拦**） | — |
| YouTube 字幕 | browser_use（yt-dlp 本机未跑通，见 video.md） | 隧道+cookies 的 yt-dlp | — |
| 小红书 | xhs CLI ⏱ | browser_use ⏱ | — |
| 微信公众号 | **weixin.sogou.com** ✅免 | Exa 限域 + BrightData ⏱ | — |
| 微博 / 知乎 | browser_use ⏱（web 与 api 均 403 拦爬） | 千帆搜快照 | — |
| Twitter/X | browser_use ⏱（本机 `twitter` 是 npm 同名假货，见下） | 装 Python 版 twitter-cli | — |
| 需要登录的站点 | browser_use ⏱ | — | — |

### 🔴 本环境不可达（DNS 通 ≠ 能连，别硬试）

`arxiv.org` / `zh.wikipedia.org` / `html.duckduckgo.com` / `scholar.google.com` / `chinaxiv.org` — 全部 000。
替代链见 [cn-reach.md](references/cn-reach.md)。

> ⚠️ **000 ≠ 通道挂了**（2026-09-22 复检教训）：上表之外，`github.com` / `api.stackexchange.com` /
> `r.jina.ai` / DeepWiki MCP 都曾被误判 000 而其实正常——**探活只认 GET + 重试 1 次**，
> **绝不用 `curl -I`**（HEAD 不被支持时会挂死或回 405/406，假报“挂了”）。

### 通道现状（2026-09-05 实测）

> **网络全线 000 时先查 DNS，别怀疑出口**：`/etc/resolv.conf` 里 `172.19.0.2` 是透明代理的
> fake-ip 解析器，代理一死就返回 `198.18.x` 让所有 HTTPS 变 000（域名看着解析成功，实则废）。
> 改成 `nameserver 223.5.5.5` / `8.8.8.8` 立刻全通，不需要任何隧道、中继或 hosts 钉 IP
> （duanz.xin 是 DDNS，IP 每天变，钉了隔天就砖）。

- ✅ 实测返回真实数据：百度千帆、Exa、BrightData（抓取 + Google）、Jina、Firecrawl（developer + research）、gh（search/api）、DeepWiki `ask_question`、bili CLI、V2EX。
- ✅ `xhs`：2026-09-05 已重新登录（search / comments 实测通）。**cookie 会周期性过期**，
  报 `not_authenticated / Session expired` 时按下面恢复 —— 注意 `xhs login --qrcode` **走不通**：
  扫码和确认都能过，但最后一步 `_complete_confirmed_session` 会被风控要验证码
  （`NeedVerifyError: Captcha required type=124`），纯 HTTP 流程解不了，cookie 不落盘。
  可用的是**借内置浏览器登录，再把 cookie 灌回 CLI**：

  ```bash
  # 1) browser_use: set_user_agent desktop_chrome → navigate https://www.xiaohongshu.com/explore
  #    （移动端 UA 不发二维码，必须桌面版；模态框没自动弹就点侧栏「登录」）
  # 2) 把 img.qrcode-img 的截图区域裁出来给用户扫（dpr=4，坐标×4；必须补 ≥4 模块白边，
  #    否则扫码器因缺 quiet zone 拒识）。别手抄 base64 —— 会抄成垃圾。
  # 3) 用户确认后：browser_use get_cookies keywords="web_session a1 webId gid"
  # 4) 写 ~/.xiaohongshu-cli/cookies.json（扁平结构，不是嵌套）：
  #    {"a1":…,"webId":…,"gid":…,"web_session":…,"saved_at":<unix秒>}  权限 600
  # 5) xhs status 验证 authenticated: true
  ```

- ❌ `twitter`：PATH 上的是 npm `twitter-cli@0.0.2`（filter stream 玩具），**不是**文档里的 Python v0.8.5。任何子命令都只打印一行 usage 并 **exit 0** —— 静默假成功，别当成"没结果"。要真用得 `pipx install twitter-cli` 并确认 `which twitter` 不再指向 `/usr/local/bin`。
- ⚠️ Reddit 公开 JSON：数据中心 IP 被拉黑，返回 **200 + "Blocked" HTML**（不是 403），别误读成空结果 → 换 browser_use / BrightData。

## 通道命令

```bash
# 百度千帆（400 次/日免费，配额由该技能自己记账，不要重复扣）
python3 $SKILLS/baiduaisearchwithquota/scripts/smart_search.py search '查询'

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

## 额度（保留 30% 裕度）

```bash
python3 $SKILLS/d-reach/scripts/quota.py budget     # 开工前先看：到裕度线还能用多少
python3 $SKILLS/d-reach/scripts/quota.py status     # 原始计数
python3 $SKILLS/d-reach/scripts/quota.py use brightdata    # 占用；退出码见下表
python3 $SKILLS/d-reach/scripts/quota.py reset brightdata
```

**退出码三态**（裕度比例用 `D_REACH_RESERVE` 覆盖，默认 `0.30`）：

| 码 | 含义 | 动作 |
|---|---|---|
| 0 | 正常 | 继续 |
| 2 | 已过裕度线（= 上限的 70%，**仍记账**） | 本轮后续只在免费通道拿不到时用 |
| 1 | 越免费线（**不记账**） | 立刻换备选 / 免费通道 |

**留 30% 裕度**：日线和月线都按 70% 设线，剩下 30% 留给当天突发任务。
免费免 Key 通道（cn.bing / StackExchange / HN / OpenAlex / Crossref / 掘金 / 博客园 /
36氪 / 豆瓣 / gh CLI / DeepWiki / V2EX）**不限量、不记账 → 深挖时优先铺满它们**，
这才是「用足日额度」的正确姿势。

计数文件 `~/.agent-reach/quota.json`，跨日/跨月自动归零。
⏱ = 调用前 `quota.py use <svc>`。例外：**百度千帆由它自己的计数器记账**（别双扣）；
Firecrawl 的两个 Index REST 端点免费不记账，只有走 SDK 抓取才 `use firecrawl`；
gh / yt-dlp / DeepWiki / V2EX 免费无限，不记账。
**Jina 与 Exa 同样是 ⏱ 通道，别因为「感觉免费」就跳过记账** —— 实测近 30 天有 25 次 Jina、
4 次 Exa 调用未记账，额度计数因此长期失真。
BrightData 真实用量可对账：`curl -s -H "Authorization: Bearer $BRIGHTDATA_APITOKEN" https://api.brightdata.com/account/usage`。

## 工作区

临时输出 `/tmp/`，持久数据 `~/.agent-reach/`。不要在 agent workspace 建文件。

## 详细文档

按需读取，不要一次全部加载：

| 文档 | 什么时候读 |
|------|-----------|
| [references/cn-reach.md](references/cn-reach.md) | **国内网络环境实测通道总表**（可达/不可达 + 替代链 + 细分路由）——选路前先看它 |
| [references/search.md](references/search.md) | 搜索通道完整参数、**查询改写矩阵与分档调用序列** |
| [references/scrape.md](references/scrape.md) | 抓取 / 网页阅读 / 公众号 / RSS |
| [references/social.md](references/social.md) | 微博 / V2EX / Reddit / 公众号 / 豆瓣 / 知乎 |
| [references/dev.md](references/dev.md) | gh CLI / DeepWiki / StackExchange / 掘金 完整用法 |
| [references/video.md](references/video.md) | YouTube / B站 / 播客字幕 |
| [references/finance.md](references/finance.md) | 雪球 / 巨潮资讯 / A股公告 |
| [extensions/d-reach-xhs/SKILL.md](extensions/d-reach-xhs/SKILL.md) | 处理小红书笔记链接时 |
| [extensions/d-reach-twitter/SKILL.md](extensions/d-reach-twitter/SKILL.md) | 处理 Twitter/X 内容时 |
