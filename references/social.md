# 社交媒体 & 社区

微博、V2EX、Reddit。其余平台各有归属：

| 平台 | 去哪 |
|------|------|
| 小红书 | `../extensions/d-reach-xhs/SKILL.md`（cookie 会周期性过期，恢复流程见顶层 `SKILL.md`） |
| Twitter/X | `../extensions/d-reach-twitter/SKILL.md`（**本机 `twitter` 是 npm 同名假货，静默 exit 0** → 先用 `browser_use`） |
| B站 | `SKILL.md` 的「B站 / 小红书 铁律」+ `video.md` |
| 微信公众号 | 本文件下方「微信公众号」小节 |
| 豆瓣 | 本文件下方「豆瓣」小节 |
| 抖音 | 无可用通道（原 mcporter douyin 未配置）→ `browser_use` |

## 微信公众号（✅ 免登录入口）

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"

# 搜狗微信 —— 免登录搜公众号文章（本环境 200 可达）
curl -s -A "$UA" "https://weixin.sogou.com/weixin?type=2&query=关键词"
#   type=1 搜公众号，type=2 搜文章
#   ⚠️ 列表页是 JS 拼装，HTML 里拿不到完整标题/链接 → 用 browser_use 打开该 URL 再 get_readable
```

- 拿到真实 `mp.weixin.qq.com/s/xxx` 链接后，**正文用 BrightData 抓**（Jina 读不了公众号，会被 CAPTCHA 拦，见 `scrape.md`）。
- 另一条路：Exa 限定 `includeDomains: ["mp.weixin.qq.com"]` 搜（见 `scrape.md`），但覆盖不如搜狗微信全。

## 豆瓣（✅ 免 Key，书影音评分）

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
curl -s -A "$UA" "https://search.douban.com/book/subject_search?search_text=关键词"
#   结果在页面里的 window.__DATA__ = {"items":[...]}  → 正则截出 JSON 再解析
#   movie 换 /movie/subject_search，music 换 /music/subject_search
```

用途：书/影/音评分与短评（选书选片）。**注意豆瓣评分是社区主观值，不是事实源。**

## 知乎 / 贴吧（⚠️ 反爬，需交互）

`www.zhihu.com` 与 `www.zhihu.com/api/v4/search_v3` 均 **403**，`tieba.baidu.com` 亦 403。
本环境无免 Key 通道 → 走 `browser_use`（navigate → wait_for_dom_stable → get_readable），
或先用百度千帆搜"知乎 关键词"拿快照摘要。

## 微博

```bash
curl -s "https://r.jina.ai/https://weibo.com/USER_ID/POST_ID"
```

## V2EX（公开 API，无需认证）

```bash
UA="Mozilla/5.0 (X11; Linux x86_64)"
curl -s -A "$UA" "https://www.v2ex.com/api/topics/hot.json"                        # 热门
curl -s -A "$UA" "https://www.v2ex.com/api/topics/show.json?node_name=python&page=1" # 节点
curl -s -A "$UA" "https://www.v2ex.com/api/topics/show.json?id=TOPIC_ID"            # 主题
curl -s -A "$UA" "https://www.v2ex.com/api/replies/show.json?topic_id=TOPIC_ID"     # 回复
curl -s -A "$UA" "https://www.v2ex.com/api/members/show.json?username=USERNAME"     # 用户
```

节点列表：https://www.v2ex.com/planes

## Reddit（公开 JSON，无需登录）

```bash
UA="Mozilla/5.0 (X11; Linux x86_64)"
curl -s -A "$UA" "https://www.reddit.com/search.json?q=QUERY&limit=10"          # 搜索
curl -s -A "$UA" "https://www.reddit.com/r/SUB/hot.json?limit=20"               # 版块热门
curl -s -A "$UA" "https://www.reddit.com/r/SUB/comments/ID.json"                # 帖子+评论
```

> 本机没有 `rdt` CLI。**2026-09-05 实测：数据中心 IP 被拉黑，返回 200 + 一个 "Blocked" HTML 页**
> （不是 403，别当成"搜索无结果"）→ 换 `browser_use` 或 BrightData 抓。
> 能通时用 jq 取字段：`| jq '.data.children[].data | {title,url,num_comments,selftext:(.selftext[:200])}'`
