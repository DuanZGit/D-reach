#!/usr/bin/env python3
"""
Agent-Reach 统一配额管理器。
覆盖：BrightData / 百度千帆 / Exa / Firecrawl / Brave / Serper / ScrapeCreators。
策略：超限自动切免费替代，绝不进入付费。
"""
from __future__ import annotations

import json
import time
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone

# ── 数据模型 ────────────────────────────────────────────────────────────────

@dataclass
class QuotaBucket:
    """单个服务的额度桶。"""
    name: str
    monthly_limit: Optional[int] = None   # 每月上限，None=不限
    daily_limit: Optional[int] = None     # 每日上限，None=不限
    monthly_used: int = 0
    daily_used: int = 0
    last_reset_month: str = ""            # "YYYY-MM"
    last_reset_day: str = ""              # "YYYY-MM-DD"
    fallback: str = ""                    # 超限后切到哪个服务
    enabled: bool = True                  # 是否启用此服务

    def check_and_consume(self, count: int = 1) -> tuple[bool, str]:
        """检查并扣除额度。返回 (是否可用, 原因)。"""
        if not self.enabled:
            return False, f"{self.name} disabled"

        now = datetime.now(timezone.utc)
        month_str = now.strftime("%Y-%m")
        day_str = now.strftime("%Y-%m-%d")

        # 按月重置
        if self.last_reset_month != month_str:
            self.monthly_used = 0
            self.last_reset_month = month_str
        # 按日重置
        if self.last_reset_day != day_str:
            self.daily_used = 0
            self.last_reset_day = day_str

        # 检查月额度
        if self.monthly_limit is not None:
            if self.monthly_used + count > self.monthly_limit:
                return False, f"{self.name} monthly limit reached ({self.monthly_used}/{self.monthly_limit})"

        # 检查日额度
        if self.daily_limit is not None:
            if self.daily_used + count > self.daily_limit:
                return False, f"{self.name} daily limit reached ({self.daily_used}/{self.daily_limit})"

        # 通过，扣额度
        self.monthly_used += count
        self.daily_used += count
        return True, "ok"

    def to_dict(self) -> dict:
        return asdict(self)


# ── 全局配额注册表 ───────────────────────────────────────────────────────────

class QuotaManager:
    def __init__(self, storage_path: str = "/root/.agent-reach/quota.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.buckets: dict[str, QuotaBucket] = {}
        self._load()
        self._register_defaults()

    def _register_defaults(self):
        """注册所有已知服务的默认额度。"""
        defaults = {
            # 服务名: (月额度, 日额度, fallback服务, enabled)
            "brightdata":      (5000, None,    "jina_reader", True),
            "baidu_search":    (None, 400,     "exa",         True),
            "baidu_wenku":     (None, 47,      "jina_reader", True),
            "baidu_ecommerce": (None, 20,      "jina_reader", True),
            "baidu_content":   (None, 230,     None,          True),
            "baidu_knowledge": (None, 200,     None,          True),
            "baidu_trending":  (None, 10,      None,          True),
            "baidu_media":     (None, 10800,   None,          True),  # 秒
            "exa":             (1000, 50,     "baidu_search",True),  # 新账号约1000次/月,保守设50/日
            "firecrawl":       (1000, 200,    "brightdata",  True),  # Free plan 1000 credits/月; research index 免费不限耗时, 保守200/日
            "brave":           (2000, None,   "brightdata",  True),
            "serper":          (2500, None,   "brightdata",  True),
            "scrapecreators":  (1000, 50,     "brightdata",  True),  # 假设免费额,保守设50/日
            "github":          (None, None,   "deepwiki",     True),  # GitHub 免费无限(personal)
            "deepwiki":        (None, None,   "exa",          True),  # 免费,无限(fair-use)
            "yt-dlp":          (None, None,   "jina_reader",  True),  # 免费,无限
            "v2ex":            (None, None,   "jina_reader",  True),  # 公开API免费
            "jina_reader":     (None, 300,    "brightdata",   True),  # 免费但有限流,保守300/日
            "browser_use":     (None, 100,    "brightdata",   True),  # Minis内置,保守100/日
            "xhs":             (None, 200,    "browser_use",  True),  # 登录后免费,防触及限流
            "bili":            (None, 200,    "browser_use",  True),
            "twitter":         (None, 100,    "browser_use",  True),
            "rdt":             (None, 200,    "browser_use",  True),
        }

        for name, (monthly, daily, fallback, enabled) in defaults.items():
            if name not in self.buckets:
                self.buckets[name] = QuotaBucket(
                    name=name,
                    monthly_limit=monthly,
                    daily_limit=daily,
                    fallback=fallback,
                    enabled=enabled,
                )

    # ── 持久化 ──────────────────────────────────────────────────────────────

    def _load(self):
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text())
                for name, b in data.get("buckets", {}).items():
                    self.buckets[name] = QuotaBucket(**b)
            except Exception:
                pass

    def save(self):
        data = {
            "buckets": {k: v.to_dict() for k, v in self.buckets.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.storage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # ── 核心 API ────────────────────────────────────────────────────────────

    def consume(self, service: str, count: int = 1) -> tuple[bool, str]:
        """消耗额度（只针对该服务本身，不做自动 fallback）。

        Fallback 由 quota_gate.gate() 按场景链统一编排，避免重复扣额度。
        返回 (是否可用, 原因)。未知服务默认放行。
        """
        bucket = self.buckets.get(service)
        if not bucket:
            return True, "ok"  # 无配额限制的服务，默认放行

        ok, reason = bucket.check_and_consume(count)
        self.save()
        return ok, reason

    def status(self, service: Optional[str] = None) -> dict:
        """查询额度状态。"""
        if service:
            bucket = self.buckets.get(service)
            if not bucket:
                return {"error": f"unknown service: {service}"}
            return bucket.to_dict()
        return {k: v.to_dict() for k, v in self.buckets.items()}

    def reset(self, service: Optional[str] = None):
        """手动重置额度。"""
        if service:
            bucket = self.buckets.get(service)
            if bucket:
                bucket.monthly_used = 0
                bucket.daily_used = 0
                bucket.last_reset_month = ""
                bucket.last_reset_day = ""
        else:
            for b in self.buckets.values():
                b.monthly_used = 0
                b.daily_used = 0
                b.last_reset_month = ""
                b.last_reset_day = ""
        self.save()

    def disable(self, service: str):
        """禁用某个服务（强制走 fallback）。"""
        if service in self.buckets:
            self.buckets[service].enabled = False
            self.save()

    def enable(self, service: str):
        """启用某个服务。"""
        if service in self.buckets:
            self.buckets[service].enabled = True
            self.save()


# ── 全局单例 ────────────────────────────────────────────────────────────────

_quota_manager: Optional[QuotaManager] = None

def get_quota_manager() -> QuotaManager:
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = QuotaManager()
    return _quota_manager

def quota_check(service: str, count: int = 1) -> tuple[bool, str]:
    """快速检查：是否可用，或应切到哪个 fallback。"""
    return get_quota_manager().consume(service, count)

def quota_status(service: Optional[str] = None) -> dict:
    return get_quota_manager().status(service)

def quota_reset(service: Optional[str] = None):
    get_quota_manager().reset(service)


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    mgr = get_quota_manager()

    if len(sys.argv) < 2:
        print("Usage: quota_manager.py <status|reset|consume|disable|enable> [service] [count]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        service = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(mgr.status(service), indent=2, ensure_ascii=False))

    elif cmd == "reset":
        service = sys.argv[2] if len(sys.argv) > 2 else None
        mgr.reset(service)
        print(f"Reset {'all' if service is None else service}")

    elif cmd == "consume":
        service = sys.argv[2] if len(sys.argv) > 2 else "brightdata"
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        ok, reason = mgr.consume(service, count)
        print(json.dumps({"ok": ok, "reason": reason}, ensure_ascii=False))

    elif cmd == "disable":
        service = sys.argv[2]
        mgr.disable(service)
        print(f"Disabled {service}")

    elif cmd == "enable":
        service = sys.argv[2]
        mgr.enable(service)
        print(f"Enabled {service}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
