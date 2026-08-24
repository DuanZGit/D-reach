#!/usr/bin/env python3
"""
Agent-Reach 配额门控【决策层】。
只负责：一次 gate() 扣额度 + 返回该用哪个服务。不执行任何实际调用。
执行层在 unified_entry.py。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from quota_manager import get_quota_manager

# ── 服务映射 ────────────────────────────────────────────────────────────────

# 用户请求场景 -> (主服务, fallback 链)
# 主服务超限 → 依次尝试 fallback，全部超限则报错
ROUTING = {
    # 搜索
    "search_zh":          ("baidu_search",  ["brightdata", "exa", "jina_reader"]),
    "search_en":          ("exa",           ["brightdata", "baidu_search", "jina_reader"]),
    "search_code":        ("github",        ["deepwiki", "exa"]),  # gh CLI 免费无限
    # 爬虫
    "scrape_single":      ("brightdata",    ["jina_reader"]),
    "scrape_batch":       ("brightdata",    []),
    "scrape_structured":  ("brightdata",    ["jina_reader"]),
    "scrape_browser":     ("brightdata",    ["browser_use"]),
    # 社交（CLI 免费但需登录态）
    "social_xhs":         ("xhs",           ["browser_use"]),
    "social_bili":        ("bili",          ["browser_use"]),
    "social_twitter":     ("twitter",       ["browser_use"]),
    "social_reddit":      ("rdt",           ["browser_use"]),
    "social_v2ex":        ("v2ex",          ["jina_reader"]),
    # 电商/商业
    "ecommerce":          ("brightdata",    ["jina_reader"]),
    "business_intel":     ("brightdata",    ["jina_reader"]),
    # 代码
    "npm_package":        ("brightdata",    ["jina_reader"]),
    "pypi_package":       ("brightdata",    ["jina_reader"]),
    "github_file":        ("github",        ["deepwiki", "jina_reader"]),
    # 视频
    "youtube_sub":        ("yt-dlp",        ["jina_reader"]),
    "bilibili_sub":       ("yt-dlp",        ["jina_reader"]),
    # 网页阅读
    "web_general":        ("brightdata",   ["browser_use"]),
    "web_wechat":         ("brightdata",    ["browser_use"]),
}

# 由独立技能维护真实额度的服务，不在 D-Reach 再扣一次。
# 这样避免 D-Reach 的 quota.json 与百度技能自己的官方计数器双扣。
DELEGATED_QUOTA_SERVICES = {"baidu_search"}

# ── 决策函数 ────────────────────────────────────────────────────────────────

def gate(scenario: str, count: int = 1) -> dict:
    """检查配额并返回该用哪个服务。只扣额度，不执行。

    Returns:
        {"ok": bool, "service": str, "reason": str,
         "fallback_chain": list, "quota_snapshot": dict}
    """
    mgr = get_quota_manager()

    if scenario not in ROUTING:
        # 无额度限制的服务（如 gh / yt-dlp / v2ex 公开 API）直接放行
        return {"ok": True, "service": scenario, "reason": "free, no quota limit",
                "fallback_chain": [], "quota_snapshot": {}}

    primary, fallbacks = ROUTING[scenario]

    # 百度配额由 baiduaisearchwithquota 自己持久化和门控；D-Reach 只负责选路，避免双扣。
    if primary in DELEGATED_QUOTA_SERVICES:
        return {"ok": True, "service": primary, "reason": "delegated quota: baiduaisearchwithquota", "fallback_chain": fallbacks, "quota_snapshot": {}}

    # 尝试主服务
    ok, reason = mgr.consume(primary, count)
    if ok and not reason.startswith("fallback:"):
        return {"ok": True, "service": primary, "reason": "ok",
                "fallback_chain": fallbacks, "quota_snapshot": mgr.status(primary)}

    # 主服务超限，依次尝试 fallback
    for fb in fallbacks:
        ok, reason = mgr.consume(fb, count)
        if ok:
            return {"ok": True, "service": fb,
                    "reason": f"primary {primary} exhausted, fell back to {fb}",
                    "fallback_chain": fallbacks, "quota_snapshot": mgr.status(fb)}

    # 全部超限
    return {"ok": False, "service": primary,
            "reason": f"All services exhausted: {primary} -> {' -> '.join(fallbacks)}",
            "fallback_chain": fallbacks,
            "quota_snapshot": {s: mgr.status(s) for s in [primary] + fallbacks}}

def get_service_for_scenario(scenario: str) -> str:
    """快速获取当前应该使用的服务名。"""
    return gate(scenario).get("service", scenario)

def list_scenarios() -> list[str]:
    """列出所有已注册场景。"""
    return list(ROUTING.keys())

# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: quota_gate.py <gate|route|list|status> [scenario] [count]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "gate":
        sc = sys.argv[2] if len(sys.argv) > 2 else "search_zh"
        c = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        print(json.dumps(gate(sc, c), indent=2, ensure_ascii=False))
    elif cmd == "route":
        sc = sys.argv[2] if len(sys.argv) > 2 else "search_zh"
        print(get_service_for_scenario(sc))
    elif cmd == "list":
        print(json.dumps(list_scenarios(), indent=2, ensure_ascii=False))
    elif cmd == "status":
        print(json.dumps(get_quota_manager().status(), indent=2, ensure_ascii=False))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
