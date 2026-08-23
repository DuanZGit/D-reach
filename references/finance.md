# 金融行情

雪球股票行情、搜索与热门内容。行情可能延迟，不构成投资建议。

## 先检查状态

```bash
agent-reach doctor --json
```

`xueqiu.active_backend` 有值时按该后端使用；值为 `null` 只表示 Doctor 没有完成
实时内容验证。雪球需要已登录会话或最小 Cookie，不能把 HTTP 400 当成股票不存在。

> **PRoot / Minis 环境下注意：** `opencli`（OpenCLI 后端）是桌面工具，本环境未安装。
> 无需 `opencli` 的替代路径：
> - 雪球公开数据可用 `curl` 抓 `xueqiu.com` 页面，或用 `jina_reader`（`curl https://r.jina.ai/<xueqiu_url>`）
> - 行情查询优先走 `gushen` 技能（A股/美股）：`python3 /var/minis/skills/gushen/tools/cn_market.py a <code>`
> - URL 已知时直接 `scrape`（走 agent-reach 统一爬取入口）

## OpenCLI（桌面已有 Chrome 登录态时优先）

```bash
# 验证当前登录态
opencli xueqiu whoami -f yaml

# 股票搜索与实时行情
opencli xueqiu search "英伟达" -f yaml
opencli xueqiu stock NVDA -f yaml

# 热门内容与热门股票
opencli xueqiu hot -f yaml
opencli xueqiu hot-stock -f yaml
```

OpenCLI 只复用用户已经存在且明确控制的浏览器会话。不要自动执行
`opencli xueqiu login`；没有现成登录态时，让用户先在 Chrome 登录，或显式导入
雪球所需的最小 Cookie：

```bash
agent-reach configure --from-browser chrome --platform xueqiu
```

该配置只读取并保存 `xq_a_token`，不会顺带采集其他平台 Cookie。

## 验收与失败处理

- 以返回股票名称、代码、价格或非空内容列表为成功；退出码 0 但字段为空不算成功。
- HTTP 400 通常是会话/Cookie 问题，不表示股票代码不存在。
- `whoami` 成功而 `stock`/`hot` 失败时，按适配器解析或平台接口问题报告，不要误诊成未登录。

## 本环境推荐路径

```bash
# 1) A股/美股实时行情（gushen）
python3 /var/minis/skills/gushen/tools/cn_market.py a 600519          # A股
python3 /var/minis/skills/gushen/tools/cn_market.py quote usNVDA usQQQ # 美股

# 2) 雪球页面/社区内容（jina_reader 或统一爬取）
python3 /var/minis/skills/d-reach/scripts/unified_entry.py scrape "https://xueqiu.com/S/SH600519"

# 3) 雪球热帖（公开 JSON API）
curl -s "https://xueqiu.com/query/v1/statuses/hot/listV3.json" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" \
  -H "Referer: https://xueqiu.com/" 2>/dev/null | head -c 2000
```
