#!/usr/bin/env python3
"""D-Reach 免费额度计数器。只做一件事：记数 + 判断有没有越过免费线。

选路/执行由 agent 按 SKILL.md 的路由表直接调通道，本脚本不参与。
百度千帆不在此记账 —— 由 baiduaisearchwithquota 自己的计数器负责。

  quota.py status            看所有通道余量
  quota.py use <svc> [n]     占用 n 次额度；超限 exit 1（于是可以 `use x || 换备选`）
  quota.py check <svc> [n]   只看不占
  quota.py reset [svc]       清零
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FILE = Path.home() / ".agent-reach/quota.json"

# 服务: (月上限, 日上限)；None = 该项不限
LIMITS = {
    "brightdata":  (5000, None),   # 免费 5000/月
    "exa":         (1000, 50),     # 新账号约 1000/月，保守按 50/日
    "firecrawl":   (1000, 200),    # Free plan 1000 credits/月
    "jina_reader": (None, 300),    # 免费但限流
    "browser_use": (None, 100),    # Minis 内置
    "xhs":         (None, 200),    # 登录态免费，防风控
    "bili":        (None, 200),
    "twitter":     (None, 100),
}


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
    """返回 (ok, 说明)。未知服务不限额，放行。"""
    if svc not in LIMITS:
        return True, f"{svc}: 无限额（免费/本地 CLI），不记账"
    mo, day = LIMITS[svc]
    b = _bucket(d, svc)
    if mo and b["monthly"] + n > mo:
        return False, f"{svc} 月度将超限 {b['monthly']}+{n}/{mo} → 换备选"
    if day and b["daily"] + n > day:
        return False, f"{svc} 日度将超限 {b['daily']}+{n}/{day} → 换备选"
    if consume:
        b["monthly"] += n
        b["daily"] += n
        _save(d)
    return True, f"{svc} ok ({b['monthly']}/{mo or '-'} 月, {b['daily']}/{day or '-'} 日)"


def _status(d):
    out = {}
    for svc, (mo, day) in LIMITS.items():
        b = _bucket(d, svc)
        out[svc] = {"monthly": f"{b['monthly']}/{mo if mo else '不限'}",
                    "daily": f"{b['daily']}/{day if day else '不限'}"}
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    d = _load()
    if cmd == "status":
        print(json.dumps(_status(d), indent=2, ensure_ascii=False))
    elif cmd in ("use", "check"):
        svc = sys.argv[2] if len(sys.argv) > 2 else ""
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        if not svc:
            print("usage: quota.py use|check <service> [count]"); sys.exit(2)
        ok, msg = _try(d, svc, n, cmd == "use")
        print(msg)
        sys.exit(0 if ok else 1)
    elif cmd == "reset":
        svc = sys.argv[2] if len(sys.argv) > 2 else None
        if svc:
            d.pop(svc, None)
        else:
            for k in LIMITS:
                d.pop(k, None)
        _save(d)
        print(f"reset {'all' if not svc else svc}")
    else:
        print(f"unknown command: {cmd}"); sys.exit(2)
