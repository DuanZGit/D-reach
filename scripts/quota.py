#!/usr/bin/env python3
"""D-Reach 免费额度计数器 + 裕度线（默认保留 30%）。

只管两件事：记数、判断有没有越过"裕度线/免费线"。选路与执行由 agent 按 SKILL.md 直接调。

  quota.py status            看所有通道原始计数
  quota.py budget            规划本轮调研：到裕度线还剩多少、今日建议额度
  quota.py use <svc> [n]     占用 n 次。exit 0=正常 / 2=已过裕度线(仍记账) / 1=越免费线(不记账)
  quota.py check <svc> [n]   只看不占，退出码同 use
  quota.py reset [svc]       清零

环境变量：
  D_REACH_RESERVE      裕度比例，默认 0.30（即用到 70% 就提示转免费通道）
  D_REACH_QUOTA_FILE   计数文件路径（默认 ~/.agent-reach/quota.json；仅测试时覆盖）

百度千帆不在此记账 —— 由 baiduaisearchwithquota 自己的计数器负责。
免 Key 不限量通道（cn.bing / StackExchange / HN / OpenAlex / Crossref / 掘金 / gh …）不记账。
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

FILE = Path(os.environ.get("D_REACH_QUOTA_FILE")
            or Path.home() / ".agent-reach/quota.json")
try:
    RESERVE = float(os.environ.get("D_REACH_RESERVE", "0.30"))
except ValueError:
    RESERVE = 0.30
RESERVE = min(max(RESERVE, 0.0), 0.9)

# 服务: (月上限, 日上限)；None = 该项不限
LIMITS = {
    "brightdata":  (5000, None),   # 免费 5000/月
    "exa":         (1000, 50),     # 新账号约 1000/月，日线防单日打爆
    "firecrawl":   (1000, 200),    # Free plan 1000 credits/月
    "jina_reader": (None, 300),    # 免费但限流
    "browser_use": (None, 100),    # Minis 内置
    "xhs":         (None, 200),    # 登录态免费，防风控
    "bili":        (None, 200),
    "twitter":     (None, 100),
}
# 不限量、不记账的免 Key 通道（写在这里只为 budget 里提醒，别去 use 它们）
FREE_CHANNELS = ("cn.bing", "StackExchange", "HN Algolia", "OpenAlex", "Crossref",
                 "掘金", "博客园/SegmentFault", "36氪/InfoQ/澎湃/界面", "豆瓣",
                 "gh CLI", "DeepWiki", "V2EX")


def _soft(limit):
    """裕度线：留 RESERVE 比例。"""
    if limit is None:
        return None
    return int(limit * (1 - RESERVE))


def _load():
    try:
        d = json.loads(FILE.read_text())
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    d.pop("buckets", None)   # 旧版 quota_manager 的 schema，一次性丢弃
    return d


def _save(d):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(d, indent=2))


def _bucket(d, svc):
    """跨月/跨日自动归零。"""
    now = datetime.now(timezone.utc)
    b = d.get(svc)
    if not isinstance(b, dict):
        b = {"month": now.strftime("%Y-%m"), "day": now.strftime("%Y-%m-%d"),
             "monthly": 0, "daily": 0}
        d[svc] = b
    if b["month"] != now.strftime("%Y-%m"):
        b["monthly"], b["month"] = 0, now.strftime("%Y-%m")
    if b["day"] != now.strftime("%Y-%m-%d"):
        b["daily"], b["day"] = 0, now.strftime("%Y-%m-%d")
    return b


def _try(d, svc, n, consume):
    """返回 (code, 说明)。code: 0 正常 / 2 已过裕度线 / 1 越免费线。"""
    if svc not in LIMITS:
        return 0, f"{svc}: 无限额（免 Key/本地 CLI），不记账"
    mo, day = LIMITS[svc]
    b = _bucket(d, svc)
    over = []
    if mo and b["monthly"] + n > mo:
        over.append(f"月 {b['monthly']}+{n}/{mo}")
    if day and b["daily"] + n > day:
        over.append(f"日 {b['daily']}+{n}/{day}")
    if over:
        return 1, (f"{svc} 越免费线（{'；'.join(over)}）→ 不记账，立刻换备选/免费通道")

    near = []
    if mo and b["monthly"] + n > _soft(mo):
        near.append(f"月 {b['monthly']}+{n}>{_soft(mo)}/{mo}")
    if day and b["daily"] + n > _soft(day):
        near.append(f"日 {b['daily']}+{n}>{_soft(day)}/{day}")
    code = 2 if near else 0
    if consume:
        b["monthly"] += n
        b["daily"] += n
        _save(d)
    state = "已过裕度线" if code == 2 else "ok"
    hint = "（仍记账；此后只用在免费通道拿不到的内容上）" if code == 2 else ""
    detail = f"{svc} {state}{hint} [月 {b['monthly']}/{mo or '不限'}"
    if mo:
        detail += f"（裕度线 {_soft(mo)}）"
    detail += f", 日 {b['daily']}/{day or '不限'}"
    if day:
        detail += f"（裕度线 {_soft(day)}）"
    detail += "]"
    if near:
        detail += " 触发：" + "；".join(near)
    return code, detail


def _status(d):
    out = {}
    for svc, (mo, day) in LIMITS.items():
        b = _bucket(d, svc)
        out[svc] = {"monthly": f"{b['monthly']}/{mo if mo else '不限'}",
                    "daily": f"{b['daily']}/{day if day else '不限'}"}
    return out


def _budget(d):
    """给 agent 看的规划视图：到裕度线还剩多少，以及今日可用建议。"""
    now = datetime.now(timezone.utc)
    days_in_month = 28 if now.month == 2 else 30 if now.month in (4, 6, 9, 11) else 31
    days_left = max(days_in_month - now.day + 1, 1)
    lines, advice = [], []
    lines.append(f"裕度：保留 {RESERVE:.0%}（裕度线 = 上限的 {1 - RESERVE:.0%}）；"
                 f"本月剩 {days_left} 天")
    lines.append(f"{'通道':13s}{'月 已用/裕度线/上限':>26s}{'日 已用/裕度线':>18s}  状态")
    for svc, (mo, day) in LIMITS.items():
        b = _bucket(d, svc)
        sm, sd = _soft(mo), _soft(day)
        sta = "充裕"
        if (mo and b["monthly"] >= _soft(mo)) or (day and b["daily"] >= _soft(day)):
            sta = "已过裕度线"
        if (mo and b["monthly"] >= mo) or (day and b["daily"] >= day):
            sta = "越免费线"
        m_col = f"{b['monthly']}/{sm if sm else '-'}/{mo if mo else '-'}" if mo else "—"
        d_col = (f"{b['daily']}/{sd if sd else '-'}" if day
                 else (f"{b['daily']}/—" if b["daily"] else "—"))
        lines.append(f"{svc:13s}{m_col:>26s}{d_col:>18s}  {sta}")
        if mo:
            room_m = max(sm - b["monthly"], 0)
            advice.append(f"{svc} 月余量到裕度线 {room_m} 次（≈{room_m // days_left}/日）")
        elif day:
            advice.append(f"{svc} 日余量到裕度线 {max(sd - b['daily'], 0)} 次")
    out = "\n".join(lines)
    out += "\n\n今日可用（到裕度线）：" + "；".join(advice)
    out += ("\n免 Key 不限量通道（不记账，深挖优先铺满）：" + " / ".join(FREE_CHANNELS))
    return out


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    d = _load()
    if cmd == "status":
        print(json.dumps(_status(d), indent=2, ensure_ascii=False))
        return 0
    if cmd == "budget":
        print(_budget(d))
        return 0
    if cmd in ("use", "check"):
        svc = argv[2] if len(argv) > 2 else ""
        if not svc:
            print("usage: quota.py use|check <service> [count]")
            return 2
        try:
            n = int(argv[3]) if len(argv) > 3 else 1
        except ValueError:
            print(f"count 必须是整数：{argv[3]!r}")
            return 2
        code, msg = _try(d, svc, n, cmd == "use")
        print(msg)
        return code
    if cmd == "reset":
        svc = argv[2] if len(argv) > 2 else None
        if svc:
            d.pop(svc, None)
        else:
            for k in LIMITS:
                d.pop(k, None)
        _save(d)
        print(f"reset {svc if svc else 'all'}")
        return 0
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
