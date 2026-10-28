#!/usr/bin/env python3
"""quota.py 的最小自检 —— 逻辑坏了会红，不测实现细节。

跑：python3 scripts/test_quota.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

QUOTA = Path(__file__).with_name("quota.py")


def run(env, *args):
    r = subprocess.run([sys.executable, str(QUOTA), *args],
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout


def main():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "quota.json"
        env = {**os.environ, "D_REACH_QUOTA_FILE": str(f)}
        monthly = lambda: json.loads(f.read_text())["firecrawl"]["monthly"]

        # 1) check 只看不记 —— 两段式记账的前提
        rc, _ = run(env, "check", "firecrawl")
        assert rc == 0, f"check 应返回 0，实际 {rc}"
        assert not f.exists() or monthly() == 0, "check 不该记账"

        # 2) use 才记账
        assert run(env, "use", "firecrawl")[0] == 0
        assert monthly() == 1, f"use 后应记 1，实际 {monthly()}"

        # 3) 过裕度线（70%）返回 2，但仍然记账
        f.write_text(json.dumps({"firecrawl": {"month": "2026-10", "day": "2026-10-28",
                                               "monthly": 750, "daily": 0}}))
        rc, _ = run(env, "use", "firecrawl")
        assert rc == 2, f"750/1000 应返回 2（过裕度线），实际 {rc}"
        assert monthly() == 751, "过裕度线仍要记账"

        # 4) 越免费线返回 1，且不记账
        f.write_text(json.dumps({"firecrawl": {"month": "2026-10", "day": "2026-10-28",
                                               "monthly": 1000, "daily": 0}}))
        rc, _ = run(env, "use", "firecrawl")
        assert rc == 1, f"1000/1000 应返回 1（越线），实际 {rc}"
        assert monthly() == 1000, "越线不该记账"

        # 5) 跨日归零但保留月计数
        f.write_text(json.dumps({"firecrawl": {"month": "2026-10", "day": "2026-10-01",
                                               "monthly": 50, "daily": 40}}))
        run(env, "use", "firecrawl")
        b = json.loads(f.read_text())["firecrawl"]
        assert b["daily"] == 1 and b["monthly"] == 51, f"跨日归零错了：{b}"

    print("quota.py 自检通过（check 不记 / use 记 / 裕度 2 / 越线 1 / 跨日归零）")


if __name__ == "__main__":
    main()
