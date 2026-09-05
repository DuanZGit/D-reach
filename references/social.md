# 社交媒体 & 社区

微博、V2EX、Reddit。其余平台各有归属：

| 平台 | 去哪 |
|------|------|
| 小红书 | `../extensions/d-reach-xhs/SKILL.md`（cookie 会周期性过期，恢复流程见顶层 `SKILL.md`） |
| Twitter/X | `../extensions/d-reach-twitter/SKILL.md`（**本机 `twitter` 是 npm 同名假货，静默 exit 0** → 先用 `browser_use`） |
| B站 | `SKILL.md` 的「B站 / 小红书 铁律」+ `video.md` |
| 抖音 | 无可用通道（原 mcporter douyin 未配置）→ `browser_use` |

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
