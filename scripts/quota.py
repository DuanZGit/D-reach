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
Firecrawl Research Index（论文端点）官方明确免费，本技能也不记账。
免 Key 不限量通道（Firecrawl Dev Index / TinyFish / StackExchange / HN / OpenAlex / Crossref / 掘金 / gh …）不记账。
"""
import contextlib
import fcntl
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
# 数字口径：2026-10-26 重新对官方定价页核实，改数字先回头对一次账。
LIMITS = {
    "brightdata":  (5000, None),    # MCP/Unlocker Free Tier: 5,000 requests/月（官方 pricing/mcp-server）
    "exa":         (2500, 50),      # 免费余额 $10/月，约合 2,500 次 Lite search（官方 pricing，每月 1 号重置）
    "firecrawl":   (1000, 200),      # Free plan: 1,000 credits/月，每月重置、不结转（官方 pricing）；论文端点免费不计这里
    "langsearch":  (None, 50),      # 官方只给“daily token 额度”（00:00 UTC 重置、起始 5 RPS），无明确请求数；50=本技能自设保守线
    "jina_reader": (None, 300),      # 免 key 约 20 RPM（按 IP 限速），有 key 提到约 200 RPM；300/日 = 自设保守线
    # browser_use 已移除：本机没有这个工具（pi 未注册、CLI 不存在），记了也是假账
    "xhs":         (None, 200),    # 登录态免费，防风控
    "bili":        (None, 200),
    "twitter":     (None, 100),
}
# 不限量、不记账的免 Key 通道（写在这里只为 budget 里提醒，别去 use 它们）
# 2026-10-26 校正：剔除已投毒的 cn.bing、搜索已退役的 V2EX、已退役的博客园，
# 补上一直在用却没列进来的 Firecrawl Developer Index 与 TinyFish（$0/次）。
FREE_CHANNELS = ("Firecrawl Developer Index", "TinyFish search/fetch", "StackExchange",
                 "HN Algolia", "OpenAlex", "Crossref", "掘金", "SegmentFault",
                 "36氪/InfoQ/澎湃/界面", "豆瓣", "gh CLI", "DeepWiki")


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


@contextlib.contextmanager
def _locked():
    """跨进程互斥：fanout.sh 会并行调多路 use，无锁会丢失更新。"""
    FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = FILE.with_suffix(FILE.suffix + ".lock")
    with open(lock_path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


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
    off = d.get("_official") or {}
    if off:
        out += "\n官方额度校准（最近一次 quota_probe）："
        for name, v in off.items():
            st = v.get("state")
            if st == "ok" and name == "firecrawl":
                out += (f"\n  {name}: 剩余 {v.get('remaining')}/{v.get('total')} credits"
                        f"，账期至 {str(v.get('period_end'))[:10]}")
            elif st == "ok" and name == "tinyfish":
                out += f"\n  {name}: 钱包 {v.get('balance')} {v.get('currency')}"
            elif st == "ok":
                out += f"\n  {name}: ok"
            elif st == "no_permission":
                out += f"\n  {name}: 权限不足"
            elif st == "unavailable":
                out += f"\n  {name}: 无公开接口"
            elif st == "no_key":
                continue
            else:
                out += f"\n  {name}: {v.get('error')}"
        out += "\n  （本地计数 = 我们发过几次；官方数字 = 厂商真实剩余，差异大说明漏记）"
    else:
        out += "\n官方额度：尚未校准，跑 `python3 scripts/quota_probe.py`（fanout 结束会自动跑一次）"
    return out


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    with _locked():
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
        if cmd == "refund":
            # 两段式记账的另一半：请求失败时把先占的额度退回来
            svc = argv[2] if len(argv) > 2 else ""
            if not svc:
                print("usage: quota.py refund <service> [count]")
                return 2
            try:
                n = int(argv[3]) if len(argv) > 3 else 1
            except ValueError:
                print(f"count 必须是整数：{argv[3]!r}")
                return 2
            if svc not in LIMITS:
                print(f"{svc}: 无限额，无需退款")
                return 0
            b = _bucket(d, svc)
            b["monthly"] = max(b["monthly"] - n, 0)
            b["daily"] = max(b["daily"] - n, 0)
            _save(d)
            print(f"refund {svc} {n} → 月 {b['monthly']} / 日 {b['daily']}")
            return 0
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
