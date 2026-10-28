---
name: d-reach
description: >
  统一搜索与爬取路由器，覆盖中英文网页搜索、社交媒体（小红书/B站/微博/Twitter/Reddit）、
  GitHub 仓库、视频字幕、股票行情和任意网页抓取。整合百度千帆、Exa、LangSearch、BrightData、Firecrawl、
  Jina Reader、gh CLI、DeepWiki、yt-dlp、bili、xhs 等全部通道，共享一套免费额度计数器。
  **执行纪律（L2 起）**：一律先跑 `scripts/fanout.sh "<query>"` 一条命令并发铺满默认档 9 路（~5s）；
  L3 或命中「对比/选型/调研/为什么/最新/vs/替代」再追加 `--deep`（+4 路限额通道，脚本自动记账）。
  禁止一条一条串行 curl（实测串行 3 路 2.95s vs 并行 1.30s），禁止没铺开就下结论。
  只要用户想搜（搜/查/找/search/搜索/查一下/帮我搜）、想爬或抓网页内容（爬/抓/scrape/提取数据）、
  想读一篇文章或链接（读一下/打开这个/看看链接）、想查社交平台内容（小红书/B站/微博/推特/Reddit）、
  想找 GitHub 仓库或代码、想要视频字幕、想查股票行情，或者需要任何需要当前网络信息的调研——
  即使用户没有点名具体平台，也使用本技能。
  口语变体同样算触发：全网看一下 / 去网上看看 / 看看有没有 / 有没有类似（项目·插件·工具）/ 现成的吗 /
  帮我找个 / 找一下有没有 / 查一下是不是真的 / 对比一下几个方案 / 求推荐。判据是「结论是否依赖当前网络上的信息」，
  不是词面本身——只要依赖外部信息就走本技能，先 read 本 SKILL.md 再用路由表选通道，
  不要直接调内置 web_search / fetch_content（那会绕开额度记账与免费通道优先原则）。
  不要用于有独立触发词的领域技能：食谱/健康（DK）、个股分析流程（gushen）、深度研究报告（research）。
license: MIT
metadata:
  openclaw:
    homepage: https://github.com/DuanZGit/D-reach
upstream:
  repo: https://github.com/DuanZGit/D-reach
  path: .
  pin: e1f58fc

---

> **路径约定**：本文件里 `$SKILLS` = 技能根目录。执行前先解析：
> `SKILLS="$HOME/.agents/skills"; [ -d "$SKILLS" ] || SKILLS=/var/minis/skills`
> （UG/本机命中 `~/.agents/skills`，Minis 命中 `/var/minis/skills`。）

# D-Reach — 搜索与爬取统一路由

> 🔴 **RED LINE —— 每次搜索前先过这一条**
>
> **L2 起必用 `bash $SKILLS/d-reach/scripts/fanout.sh "<query>" [--deep]` 把通道铺开，再进追深 / 反证轮。**
> 只打一路（哪怕第一路出了结果）就下结论 = 违规。
> 理由很直白：13 条路里 9 路走默认档（7 路完全免 key、千帆需配套技能、TinyFish 需 key 但 $0/次）、4 路限额通道月余量 >96%
> —— **不铺开不是省钱，是把信息漏掉**。
> 例外只有 L1 点查（2 路互证，`--on hn,<最相关一路>`）。

把"用户想找信息"翻译成"用哪个通道、怎么调用"。**路由表由你（agent）直接执行**，
没有中间脚本；唯一的代码是 `scripts/quota.py`，它只负责记额度。

## 决策流程（默认 L2，见下节）

1. **定档**：按「调研强度」判断本次是 L1 / L2 / L3，记住该档的**最小来源数与轮次**
2. **铺开通道 = 一条命令**：`bash $SKILLS/d-reach/scripts/fanout.sh "<query>" [--deep]`
   L2 起一律走它：**默认档 9 路并发**（实测约 5s），`--deep` 追加 LangSearch / Exa /
   Firecrawl-Research / BrightData-Google（约 10-15s）。**别一条一条串行试** ——
   实测同一 query 3 路串行 2.95s vs 并行 1.30s：铺开耗时 ≈ 最慢那一路，与路数基本无关。
   L1 点查可只跑两路互证：`fanout.sh "<query>" --on hn,<最相关一路>`
   想知道单路返回什么/排查某通道时，用 `--on <通道名>` 隔离测试（通道名见 fanout.sh 头注释）
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

> 定档依据来自低频使用实况（2026-09-25 首次勘测，2026-10-26 复核）：d-reach 是低频技能，而限额通道余量极度富余 ——
> 实际用量随时变，开工前跑一条 `python3 scripts/quota.py budget` 看当下裕度，别信文档里的快照数字。
> **浅搜才是真正的浪费**：单次做深、一次搜透，比来回补搜省总 token。

| 档 | 什么时候用 | 最小独立来源 | 轮次 | 硬要求 |
|---|---|---|---|---|
| **L1 点查** | 单一事实：版本号 / 价格 / 日期 / 某人某物是否存在 | 2 | 1 | 两个独立来源互证；打架就升 L2 |
| **L2 对比·选型**（默认） | 「哪个好 / 怎么选 / 求推荐 / 怎么样 / 值不值 / 靠不靠谱」 | 6 | 2（发现轮 → 追证轮） | ≥2 类通道且免费优先；≥1 条一手源（官方文档 / 论文原文 / 原帖 / 公告） |
| **L3 深调研** | 用户明说「调研 / 报告 / 全面 / 系统性 / 出一份」；**或**命中自动升档触发器 | 10 | 3（广撒 → 追深 → 反证） | ≥1 条**反方来源**（缺点 / 失败案例 / 相反结论）；交付可引用清单 |

**独立来源** = 不同域名或不同主体；同一篇文章被转载 5 次仍算 1 个。

**自动升档（b1）**：问题文本命中下列任一类词 → 直接按 **L3** 跑，不必等用户说「调研」：
`对比` `选型` `哪家` `哪个好` `怎么样` `靠不靠谱` `值不值` `为什么` `原理` `最新` `动态`
`演进` `替代` `方案` `盘点` `排行榜` `测评` `benchmark` `vs`。
只有用户明说「快速 / 简单 / 大概知道一下」才压回 L2 / L1。**拿不准就取高一档**（多查一条比漏查一条便宜得多）。

**缺口自动升级（a2，首轮铺开后必查）**：档位不是只靠词判，跑完 fanout 默认档还要看结果 ——

1. **有结果的路 <3 路** → 说明默认档没喂饱，自动补 `--deep` 并换改写词再跑一轮；
2. **两路来源对同一问题的关键结论互相矛盾** → 按 L3 处理（补 `--deep` + 反证轮），
   不许挑一个看着顺手的就用；
3. 反向：用户只要一个事实且两路互证一致 → 直接收，别再铺（铺满 ≠ 每问都 AI 生成一遍）。

这三条是「先量后调」：**先看铺开结果再决定要不要加深**，比一开始就固定 deep 省时间，也比词一命中就 deep 更少漏判。

**广度**：同一问题至少 **5 种**改写 —— 原词 → 同义/上下位 → 英文 → 限定域（`site:` /
LangSearch `includeDomains`）→ 时效加日期 → 再加一条**反方问法**（`缺点 / 不推荐 / 坑 / 争议`）。
嫌手写慢就让千帆「智能Query改写」(10/日) 批量生成变体。
**语义通道的 query 控制在 4–6 个词**（c2 实测：9 个词把 LangSearch 稀释成维基泛条目，换 4 词后
Exa 立刻命中官方 wiki 和真实 issue）——长尾限定词交给 LangSearch `includeDomains` 和 Firecrawl Developer 过滤。
反证独立走一轮（`<主题> 缺点 / 失败 / 不推荐 / 争议`）。模板与分档调用序列见
[references/search.md](references/search.md)。

**追深（b3）**：首轮 fanout 输出末尾要人肉/自动把冒出来的**人名、机构名、版本号、
术语、竞品名**回灌成第二轮 query（`fanout.sh "<回灌词> 原理/对比/评测" --deep`），
再单独跑一轮反证。首轮与追深轮的来源**不合并计数**（要的是互相印证，不是凑数）。

**免费优先**：`fanout.sh` 默认档一次并发 **9 路**（Firecrawl Developer /
StackExchange / HN / 掘金 / SegmentFault / OpenAlex / Crossref / 千帆）—— 它们不限量、不记账，
**闲着才是浪费**；`--deep` 的 LangSearch / Exa / Firecrawl-Research / BrightData 是限额/计 token 通道，
**L3 无条件铺**（实测月余量 >96%，不用省着），L2 视首轮缺口补铺。

## 收尾自查（交付前逐条过）

- [ ] 独立来源数达标？（**L1: 2 / L2: 6 / L3: 10**）
- [ ] 每条关键结论都有来源，且至少 1 条**一手源**？（官方文档 / 论文原文 / 原帖 / 公告，非二手转述）
- [ ] 有没有哪条结论**只有一个来源**？→ 补一条独立佐证，或降级为「未证实」
- [ ] 查询改写做了 **≥5 种**吗？（原词/同义/英文/限域/时效，外加一条反方问法）
- [ ] 追深轮做了吗？首轮冒出的人名/机构/版本/术语**回灌**了吗？
- [ ] L3：反方来源找到了吗？找不到也要如实说「未发现反例」，不能假装没有
- [ ] L3：`fanout.sh --deep` 铺了吗？（LangSearch / Exa / FC-Research / BrightData 月余量 >96%，不必省）
- [ ] ❌/⚠️ 的路注明原因了吗？（别把「请求失败」写成「搜不到」——那会把工程问题伪装成事实结论）
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
| TinyFish | `TINYFISH_API_KEY` | agent.tinyfish.ai/api-keys（search/fetch **$0/次**，30 搜/150 抓每分钟） |
| Serper（**仅手打，fanout 不读**） | `SERPER_API_KEY` | serper.dev |
| 百度千帆 | `BAIDU_API_KEY` | qianfan.console.baidu.com |
| ScrapeCreators（**仅手打，fanout 不读**） | `SCRAPECREATORS_API_KEY` | scrapecreators.com |
| LangSearch | `LANGSEARCH_API_KEY` | langsearch.com |

## 可视化网关（可选，人看状态用）

```bash
python3 scripts/gateway.py                 # 只绑 127.0.0.1，无 key
python3 scripts/gateway.py --lan           # 绑 0.0.0.0，局域网可访问，要 ?k=<key>
                                           # key 首次自动生成在 ~/.agent-reach/gateway.key
```

浏览器开 `http://127.0.0.1:3426/`：左边通道健康（连败几次、最后成功时间），右边本地额度 vs 官方剩余，
底部能直接跑一轮搜索。pi 可以不用 CLI 直接调 API：

```
GET  /api/state     → 通道 + 额度状态（JSON）
POST /api/search    → {"q":"...","deep":true,"on":"hn,exa"} → {ok, markdown, secs}
```

`--lan` 模式下三重限制：源 IP 必须在 `127.0.0.0/8`、`192.168.5.0/24`、`10.7.0.0/24` 内；
URL 或 `X-Gateway-Key` 头必须带对 key；防火墙只放行这两个网段（ufw 3426）。
**不要往公网映射** —— 链接即权限，拿到就能跑搜索。要公网走 Caddy + 鉴权（同 sev 那套）。

## 铺开器 fanout.sh（L2 起必用）

```bash
bash $SKILLS/d-reach/scripts/fanout.sh "<query>"              # 默认档：9 路并发（~5s，7 路免 key）
bash $SKILLS/d-reach/scripts/fanout.sh "<query>" --deep        # +LangSearch/Exa/FC-Research/BrightData（~12s）
bash $SKILLS/d-reach/scripts/fanout.sh "<query>" --on hn,oalex  # 只跑指定路（点名 deep 通道会自动开 deep）
bash $SKILLS/d-reach/scripts/fanout.sh "<query>" --n 8         # 每路多列几条（显示条数）
bash $SKILLS/d-reach/scripts/fanout.sh "<query>" --force       # 忽略健康状态强跑（复检用）
```

**通道健康状态**：每轮结果写进 `~/.agent-reach/channels.json`（ok / fail / streak_fail / last_fail_at）。
连续失败 ≥3 次的路，下一轮**默认不发请求**，直接标 `🔇 连续失败 N 次`；要复检加 `--force`，
或用 `--on <key>` 显式点名。跳过不等于失败 —— 本轮没请求的通道不计入连败。

**输出怎么读**（每种标记对应不同动作，别混）：

| 标记 | 含义 | 该做什么 |
|---|---|---|
| ✅ | 该路有 N 条来源 | 直接读，进入追深轮 |
| ⚪ 通道正常，0 命中 | 请求成功但这批源没有相关内容 | 换改写词重试，不是通道坏 |
| ❌ 通道无响应/超时 | 超时或结构突变 | 按「先重试再换」纪律重试 1 次；连续失败记进 `cn-reach.md` |
| ⚠️ HTTP 4xx/5xx | 参数/凭据/限流问题 | 看状态码修请求（例：BrightData 漏 `format` 会 400），**不是「没搜到」** |
| 🔇 未配置 key / 已越免费线 | 自动跳过 | 补 key 或换路，不阻塞其他路 |
| 💬 百度千帆段 | **AI 生成的浓缩回答，不是来源链接** | 只能当线索/关键词提取器；关键结论必须另找一手源 |

逐路格式与字段坑（OpenAlex 用 `display_name`+`id`、Crossref 用大写 `URL`、掘金标题埋在
`article_info` 里、LangSearch 在 `data.webPages.value[]`、Firecrawl Research 顶层是 `results`
且 `primaryId` 是 `arxiv:xxx`）已全部处理在脚本里，**新增通道时照这个模式加专用解析函数，
不要指望一个通用 harvest 覆盖所有 schema**。

**已退役通道**（2026-09-25 实测，别往回加）：
博客园 `zzk.cnblogs.com`（302→zzkx 返回 5.7KB 壳页、0 结果）、
V2EX `/search?q=`（302→`/go/search`，返回与 query 无关的节点帖子 —— **假结果比无响应更毒**）。

**cn.bing 已从代码与路由表移除（2026-10-05 判定投毒）**：
HTTP 200、结果页结构完好、能抓到 10 条，但**内容与 query 完全无关**（查咖啡豆返回法语食谱、
查英文技术词返回百度百科、中文 query 返回乌尔都语诗歌站）。同 query 稳定复现，
加随机参数 / no-cache / 换 UA / 换 mkt 全部无效 → 服务端投毒，不是解析器 bug。
**假结果比无响应更毒**，所以这一路直接删掉，不给「再试一次」留口子。
中文/时效搜索改用 LangSearch + 千帆 + BrightData。

## TinyFish 双接入（2026-10-08 落地）

TinyFish（tinyfish.ai）在本机有**两层入口，按场景选，不要混用**：

| 层 | 入口 | 适用 | 费用 |
|---|---|---|---|
| d-reach 铺开 | `fanout.sh` 默认档 `tf` 通道（hosted MCP JSON-RPC + `X-API-Key`） | 多通道并行搜一遍，只要标题/URL/snippet | search $0/次 |
| pi 原生 MCP | `mcp.json` 已注册 `tinyfish`（`https://agent.tinyfish.ai/mcp`，OAuth：`pi mcp auth tinyfish`），28 个工具 `mcp__tinyfish__*`（`search`/`fetch_content` 已提为 direct，其余 deferred 按需 `tool_search`） | 单点深取、页面监控（`create_monitor`/`run_monitor`）、web 自动化（`run_web_automation`）、browser 会话 | search/fetch $0；automation $0.016/step；monitor $0.005/run；browser $0.002/min |

- 官方 5 个技能（`npm:@tiny-fish/pi` 包内）：`tinyfish-web`（选型路由）、`tinyfish-research`、`tinyfish-automation`、`tinyfish-authenticated`、`tinyfish-browser` —— pi 重启后进技能索引。
- 两层共用同一把钥匙 `TINYFISH_API_KEY`（`~/.config/agents/env`，chmod 600）；MCP 走 OAuth 时不需要它，但 fanout 的 tf 通道必须要。
- **fetch 选型铁律**：只读内容优先 `fetch_content`（免费、10 URL/次）；必须点击/填表/登录后才拿得到的数据才上 `run_web_automation`（按 step 计费）。

## 路由表

> **✅免 = 免 Key 且不限量，不记账；⏱ = 限额通道，`fanout` 自动两段式记账（先 `check`、请求成功才 `use` 真扣，失败不扣）；⏱$0 = 需 Key 但 $0/次（TinyFish search/fetch）**
> 表内每行的 首选/备选/兜底 是**降级链**（首选挂了才走下一列），不是三选一；L2 起要多行同时开。
> 完整国内通道实测清单（含不可达站点与替代链）见 **[references/cn-reach.md](references/cn-reach.md)**。

| 意图 | 首选 | 次选 | 兜底 |
|------|------|------|------|
| 中文综合/线索 | 百度千帆（AI 摘要，**不是来源**） | TinyFish search | LangSearch |
| 英文/技术搜索 | **LangSearch**（`count=20`，限域/时效最强） | **TinyFish search**（$0/次） | Exa |
| 代码报错/排障 | **StackExchange** ✅免 | Firecrawl Developer Index ✅免 | 掘金 / SegmentFault ✅免 |
| 中文技术长尾 | **掘金 + SegmentFault** ✅免 | 百度千帆 | — |
| 学术论文 | **OpenAlex + Crossref** ✅免 | Firecrawl Research ✅免（论文端点不耗 credits） | — |
| 编程文档/issue | Firecrawl Developer Index ✅免 | Exa | gh CLI ✅免 |
| 公司/人名背景 | 千帆百科星图（200/日，需手打 `dispatch`） | 百度百科词条 | Exa |
| 深度技术讨论 | **HN Algolia** ✅免 | 掘金 / SegmentFault | — |
| 读一个 URL（不反爬） | `curl` 直取 ✅免 | TinyFish `fetch_content`（$0，真渲染） | Jina |
| 读一个 URL（反爬/需 JS） | TinyFish `fetch_content`（$0） | BrightData ⏱ | Jina ⏱ |
| 批量抓取 | BrightData 循环（≤10）⏱ | TinyFish `fetch_content`（10 URL/次，$0） | Jina ⏱ |
| GitHub 仓库/代码 | gh CLI ✅免 | DeepWiki MCP ✅免 | Gitee |
| 仓库语义问答 | DeepWiki `ask_wiki_question` ✅免 | gh CLI 读源码 | —（连不上先重试：pi 的 MCP 有 ~15s 失败退避） |
| B站 | bili CLI（需登录态） | TinyFish `run_web_automation` | — |
| 小红书 | xhs CLI（需登录态） | TinyFish `run_web_automation` | — |
| Twitter/X | twitter-cli（需登录态，本机 `twitter` 是 npm 同名假货） | TinyFish `run_web_automation` | — |
| 微信公众号 | weixin.sogou.com ✅免（列表页 JS 拼装，拿不到标题就换 TinyFish fetch） | Exa 限域 + BrightData ⏱ | — |
| A股公告 | 巨潮 cninfo ✅免 | gushen（雪球） | 东方财富（需手打站内搜索） |
| 股票行情 | gushen 技能（雪球） | 百度千帆 | — |

**已删除的通道（别再试）**
- `cn.bing` —— 疑投毒，结果与 query 无关；已从 `fanout.sh` 移除
- `V2EX` 搜索 —— 2026-09-25 起 `/search?q=` 302 到节点列表，返回假结果
- 博客园 —— 302 后返回壳页
- `browser_use` —— 本机没有这个工具（pi 未注册、CLI 不存在），原来的 7 处引用全部改成 TinyFish / BrightData

**声明了但没有实现的能力（别按表找）**
- 图片/截图找来源：千帆图片 API 只有清单没有执行器
- YouTube 字幕：yt-dlp 本机未跑通，替代见 `references/video.md`

### 🔴 本环境不可达（DNS 通 ≠ 能连，别硬试）

`arxiv.org` / `zh.wikipedia.org` / `html.duckduckgo.com` / `scholar.google.com` / `chinaxiv.org` — 全部 000。
替代链见 [cn-reach.md](references/cn-reach.md)。

### 🔴 抓取侧已确认被反爬拦（2026-10-05 实测，别浪费轮次）

| 目标 | 现象 | 出路 |
|---|---|---|
| 京东搜索 `search.jd.com/Search?keyword=` | 302 → 风控页 `JDR_shields`（`-L --compressed` 也一样，返回 957B 验证脚本） | 住宅代理（BrightData 需 KYC）；或走榜单/快照 |
| 知乎 `zhuanlan.zhihu.com` | 裸 curl 返回空壳（仅「让每一次点击都充满意义」）；**Jina Reader 也拿到「安全验证」页** | 千帆搜快照 / TinyFish fetch |
| BrightData 抓知乎 | `bad_endpoint: Requested site is not available ... robots.txt`（无 KYC 的住宅模式被拒） | 做 KYC 后可用 |
| B站字幕 `bili video -s` | 大量视频 `subtitle.available: false` —— **是视频本身没字幕，不是 CLI 坏**（bili 0.6.2 已是 PyPI 最新） | 改用 `--ai` 摘要 + `-c` 评论区 |

> 另：新浪财经/腾讯新闻类页面常需 JS 渲染，裸 curl 只得骨架，直接换 TinyFish `fetch_content`。

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
  # 1) TinyFish run_web_automation：打开 https://www.xiaohongshu.com/explore
  #    （移动端 UA 不发二维码，必须桌面版；模态框没自动弹就点侧栏「登录」）
  # 2) 把 img.qrcode-img 的截图区域裁出来给用户扫（dpr=4，坐标×4；必须补 ≥4 模块白边，
  #    否则扫码器因缺 quiet zone 拒识）。别手抄 base64 —— 会抄成垃圾。
  # 3) 用户在自己浏览器 DevTools 里取 cookie（web_session / a1 / webId / gid）
  # 4) 写 ~/.xiaohongshu-cli/cookies.json（扁平结构，不是嵌套）：
  #    {"a1":…,"webId":…,"gid":…,"web_session":…,"saved_at":<unix秒>}  权限 600
  # 5) xhs status 验证 authenticated: true
  ```

- ❌ `twitter`：PATH 上的是 npm `twitter-cli@0.0.2`（filter stream 玩具），**不是**文档里的 Python v0.8.5。任何子命令都只打印一行 usage 并 **exit 0** —— 静默假成功，别当成"没结果"。要真用得 `pipx install twitter-cli` 并确认 `which twitter` 不再指向 `/usr/local/bin`。
- ⚠️ Reddit 公开 JSON：数据中心 IP 被拉黑，返回 **200 + "Blocked" HTML**（不是 403），别误读成空结果 → 换 TinyFish fetch / BrightData。

## 通道命令

```bash
# 百度千帆（400 次/日免费，配额由该技能自己记账，不要重复扣）
# 普通搜索（生成式答案，fanout 里那一路走的就是它）
python3 $SKILLS/baiduaisearchwithquota/scripts/smart_search.py search '查询'

# ---- 2026-09-25 起接通的「0/310 闲置工具」（KB-a3），全部走 dispatch 按场景调度 ----
# knowledge 场景（200/日）：百科星图列表/详情 —— 公司/人物/产品的关联实体图谱，比百科词条更能"一圈圈挖"
python3 $SKILLS/baiduaisearchwithquota/scripts/quota_manager.py dispatch knowledge '比亚迪 产业链'
# 智能 Query 改写（10/日）：把手上的一个问题批量翻成多种问法 —— 查询改写矩阵 ≥5 种的自动生成器
python3 $SKILLS/baiduaisearchwithquota/scripts/quota_manager.py dispatch search 'ollama vs vllm'   # 见 quota_manager.py list 取准确子命令名
# 智能识图 / 相似图搜索（100/日 each）、秒懂百科（100/日）同理走 dispatch content|knowledge
# ⚠️ 千帆工具清单与子命令名以 quota_manager.py list 为准，别照记忆写

# Exa（英文/技术）
curl -s --max-time 30 -X POST https://api.exa.ai/search \
  -H "x-api-key: $EXA_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"查询","numResults":5}'

# LangSearch（Web Search，全功能免费；唯 daily token 额度 00:00 UTC 重置、多 key 共享；count 1-50）
KEY=$(sh $SKILLS/d-reach/scripts/load_key.sh LANGSEARCH_API_KEY https://langsearch.com/dashboard || 降级)
curl -s --max-time 30 -X POST https://api.langsearch.com/v1/web-search \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"query":"查询","count":10,"freshness":"oneWeek"}'
# 结果 data.webPages.value[]（name/url/snippet/summary/datePublished 可能缺；contents.text 开启换全文）
# 每次看响应 usage.input/output_tokens——全文模式最烧日额度，深挖默认用 snippet

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
免费通道（Firecrawl Developer / TinyFish / StackExchange / HN / OpenAlex / Crossref / 掘金 /
SegmentFault / 36氪 / 豆瓣 / gh CLI / DeepWiki）**不限量、不记账 → 深挖时优先铺满它们**；
已除名：cn.bing（投毒，已从 fanout 移除）、V2EX 搜索（退役）、博客园（退役）、browser_use（本机不存在）。
这才是「用足日额度」的正确姿势。

计数文件 `~/.agent-reach/quota.json`，跨日/跨月自动归零。
`fanout.sh` 结束会自动跑 `quota_probe.py --quiet` 做**官方额度校准**（写 `_official` 段，
10 分钟内复用）。能查的只有 Firecrawl 与 TinyFish；其余靠本地计数，别把本地数字当厂商余额。
⏱ = 两段式记账：`fanout` 先 `quota.py check`，**请求成功（HTTP 200）才 `use` 真扣，失败不扣**。
手动调用时同样如此。例外：**百度千帆由它自己的计数器记账**（别双扣）；
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
