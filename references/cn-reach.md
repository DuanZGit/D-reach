# 国内网络环境通道（免 Key / 免登录优先）

> **适用前提**：本机走国内 DNS（`/etc/resolv.conf` = 43.239.172.x），出口与国内家宽/IDC 一致。
> 下表全部为 **2026-09-11 实测**，🔴 = 本环境不可达（GFW/超时），🟢 = 可达且有数据。
> 判定标准不是"域名解析成功"，而是 **HTTP 200 且能解析出正文**——DNS 通了不代表能连。

## 🔴 本环境不可达（别浪费配额去试，直接走备选）

| 站点 | 现象 | 替代方案 |
|------|------|----------|
| `export.arxiv.org` / `arxiv.org` | 000 连接超时（-4 强制 IPv4 同样 000） | Firecrawl Research Index / OpenAlex / Crossref |
| `zh.wikipedia.org` | 000（只解析出 IPv6 `2001::1`） | 百度百科（千帆）/ 中文维基镜像 |
| `html.duckduckgo.com` | 000 | **cn.bing.com**（英文）/ 百度千帆（中文） |
| `scholar.google.com` | 000 | 百度学术 / OpenAlex / Crossref / ncpssd |
| `www.researchgate.net` | 403 | OpenAlex（元数据全覆盖，无反爬） |
| `tieba.baidu.com` | 403（WebView UA 被拦） | browser_use 走交互 |
| `www.chinaxiv.org` / `cn.arxiv.org` | 000 | ncpssd / Firecrawl Research |

## 🟢 通用搜索（免 Key）

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

# 必应中国 —— ✅ 英文/技术查询实测返回 4 条干净结果（<h2><a href> 直出，无需解跳转）
curl -s -A "$UA" "https://cn.bing.com/search?q=alpine+proot+x86+emulation"
# 抽结果（URL 可直接取，不像 360 那样套 link 跳转）
#   grep -oE '<h2[^>]*><a[^>]*href="[^"]+"[^>]*>.*?</a>'
# ⚠️ 中文查询实测几乎不出结果（h2 计数 =1）→ 中文一律回百度千帆，别在这硬耗

# 360 搜索 —— ✅ 可达，但结果是 /link?m=... 跳转串，要先解跳转才能拿真 URL
curl -s -A "$UA" "https://www.so.com/s?q=关键词"
#   grep -oE '<h3[^>]*class="res-title[^>]*>.{0,120}'
```

**结论**：搜英文技术用 **cn.bing.com**；搜中文用 **百度千帆**（400/日）；两者都不够再上 BrightData 打 Google。

## 🟢 编程 / 排障（全部免 Key，不记账）

```bash
# StackExchange 官方 API —— ✅ 查报错/排障第一源，带 score + is_answered 排序
#   注意：q 参数只在 /search/advanced 生效，/search 只吃 intitle（写错会 400）
curl -s --compressed --max-time 20 \
  "https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q=proot+alpine&site=stackoverflow&pagesize=5"
# 返回 items[]：title / link / score / is_answered / answer_count / accepted_answer_id

# Hacker News（Algolia）—— ✅ 深技术讨论与一手吐槽
curl -s "https://hn.algolia.com/api/v1/search?query=proot&hitsPerPage=5"

# 掘金（中文技术，需 POST）
curl -s -A "$UA" -H "Content-Type: application/json" -X POST \
  "https://api.juejin.cn/search_api/v1/search" \
  -d '{"key_word":"deepseek","id_type":0,"cursor":"0","limit":5,"search_type":0}'
# 返回 data[].result_model.article_info.{article_id,title,brief_content}

# 博客园 / SegmentFault / OSCHINA / CSDN —— 可达，走站内搜索页 + 浏览器 UA 抓 HTML
#   简中技术长尾内容（踩坑记录）比英文源更贴国内环境问题
curl -s -A "$UA" "https://zzk.cnblogs.com/s?w=proot"
curl -s -A "$UA" "https://segmentfault.com/search?q=proot"
```

## 🟢 学术（免 Key）

```bash
# Crossref —— ✅ DOI 权威元数据（出版社直供），查"这篇论文是否存在/正确 DOI"最准
curl -s "https://api.crossref.org/works?query=deepseek&rows=5&select=title,DOI,URL,published"

# OpenAlex —— ✅ 2.5 亿篇全领域，含引用数/机构/开放获取链接
curl -s "https://api.openalex.org/works?search=deepseek&per-page=5"

# Semantic Scholar —— ✅ 可达但 429 限流频繁，需退避重试
curl -s "https://api.semanticscholar.org/graph/v1/paper/search?query=agent+memory&limit=5"

# 国家哲学社会科学文献中心（人文社科免费全文）—— ✅ 可达
# 百度学术 xueshu.baidu.com —— 403，需 browser_use 交互
```

**arXiv 替代链**：`OpenAlex`（元数据+引用）→ `Crossref`（DOI 校验）→ `Firecrawl Research Index`（全文/摘要，免费但要 key）。

## 🟢 财经 / 上市公司（免费）

```bash
# 巨潮资讯 —— ✅ A 股权威公告源（法定披露），POST 检索
curl -s -X POST "http://www.cninfo.com.cn/new/hisAnnouncement/query" \
  -H "User-Agent: $UA" -H "Content-Type: application/x-www-form-urlencoded" \
  -d "pageNum=1&pageSize=20&column=szse&tabName=fulltext&searchkey=回购&seDate="
# 返回 announcements[]：secCode / secName / announcementTitle / announcementTime / adjunctUrl
#   adjunctUrl 前拼 http://static.cninfo.com.cn/ 即 PDF 原文

# 雪球（行情/讨论，已有 gushen 技能覆盖）· 东方财富 · 同花顺 —— 可达
# 财联社电报 —— 页面可达；⚠️ 旧 nodeapi 已失效（返回 HTML），要接需现场探测新接口
```

## 🟢 社区 / 消费决策

| 通道 | 状态 | 用法 |
|------|------|------|
| 小红书 `xhs` CLI | ✅ 已登录 | `xhs search` / `xhs comments`（消费决策主力，见 SKILL 铁律） |
| B站 `bili` CLI | ✅ | 字幕 + AI 总结 + 评论（见 SKILL 铁律） |
| V2EX | ⚠️ 接口时通时断 | 通了就用，断了换 cn.bing 站内 |
| 豆瓣 | ✅ `search.douban.com/book/subject_search?search_text=X`，结果在 `window.__DATA__` JSON | 书/影/音评分与短评 |
| 微博 | 302（需登录） | browser_use |
| 知乎 | 403（web + api 均被拦） | browser_use 交互，或千帆搜知乎快照 |

## 🟢 资讯 / 行业

`36kr.com` · `infoq.cn` · `thepaper.cn`（澎湃）· `jiemian.com`（界面）—— 全部 ✅ 可达，
走站内搜索页 + 浏览器 UA 抓 HTML。深度行业稿优先 36氪/InfoQ，时政社会走澎湃。

## 🟢 代码托管

```bash
# Gitee —— ✅ 国内可达（GitHub 不稳定时的镜像/替代）
# 搜索走 Gitee 站内 API/页面；GitHub API (api.github.com) 本环境 ✅ 200，但大文件 push 常失败
```

## 路由优先级（国内环境）

```
中文搜索      → 百度千帆(400/日)          → cn.bing（弱） → BrightData Google
英文技术      → cn.bing                   → Exa           → BrightData Google
代码报错      → StackExchange API         → Firecrawl Dev Index → cn.bing 站内
中文技术长尾  → 掘金 API / 博客园 / SegmentFault / OSCHINA
深度讨论      → HN Algolia                → V2EX
学术          → OpenAlex → Crossref       → Firecrawl Research（arXiv 不可达）
公司/专有名词 → 百度百科(千帆)             → cn.bing 站内
A股公告       → 巨潮资讯 cninfo           → 东方财富
消费决策      → 小红书 → B站              → 豆瓣
行业资讯      → 36氪 / InfoQ / 澎湃 / 界面
强反爬        → BrightData → Jina         → browser_use
```

> **记账规则**：本文件所有通道 **免 Key 且不限量 → 不执行 `quota.py use`**。
> 只有 BrightData / Exa / Firecrawl SDK / Jina 才记账。
