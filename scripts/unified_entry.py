#!/usr/bin/env python3
"""
Agent-Reach 统一调用入口【执行层】。
调用链：先 gate() 一次扣额度并选服务，再按服务执行底层工具。
绝不重复 gate（避免双重扣额度），超限自动安全 fallback，绝不进付费。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from quota_gate import gate
from quota_manager import get_quota_manager


# ── 底层执行器（按服务名逐个实现） ─────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 120) -> dict:
    """执行命令并返回 JSON 结果。"""
    try:
        out = subprocess.check_output(cmd, text=True, timeout=timeout)
        return {"ok": True, "data": json.loads(out)}
    except subprocess.CalledProcessError as e:
        return {"error": "cmd_failed", "message": str(e)}
    except Exception as e:
        return {"error": str(e)}


def _exec_bili_search(query: str, count: int = 5, page: int = 1) -> dict:
    """Search Bilibili through the installed bili-cli.

    Use an absolute fallback path because non-login shells (including DSH tool
    calls) may not source ~/.bashrc and therefore omit ~/.local/bin.
    """
    binary = shutil.which("bili") or "/root/.local/bin/bili"
    if not Path(binary).exists():
        return {"ok": False, "service": "bili-cli", "error": "bili_not_installed"}
    result = _run([binary, "search", query, "--type", "video",
                   "--page", str(max(1, page)), "--max", str(max(1, count)), "--json"], timeout=60)
    result["service"] = "bili-cli"
    return result


def _exec_xhs_search(query: str, count: int = 10, page: int = 1,
                     sort: str = "general") -> dict:
    """Search Xiaohongshu through xhs-cli and preserve xsec_token results."""
    binary = shutil.which("xhs") or "/root/.local/bin/xhs"
    if not Path(binary).exists():
        return {"ok": False, "service": "xhs-cli", "error": "xhs_not_installed"}
    result = _run([binary, "search", query, "--sort", sort,
                   "--page", str(max(1, page)), "--json"], timeout=60)
    result["service"] = "xhs-cli"
    if result.get("ok") and isinstance(result.get("data"), dict):
        items = result["data"].get("items", [])
        if isinstance(items, list):
            result["data"]["items"] = items[:max(1, count)]
    return result


def _exec_xhs_read(note: str, xsec_token: str | None = None) -> dict:
    """Read one Xiaohongshu note; token must come from search/feed output."""
    binary = shutil.which("xhs") or "/root/.local/bin/xhs"
    if not Path(binary).exists():
        return {"ok": False, "service": "xhs-cli", "error": "xhs_not_installed"}
    cmd = [binary, "read", note, "--json"]
    if xsec_token:
        cmd.extend(["--xsec-token", xsec_token])
    result = _run(cmd, timeout=60)
    result["service"] = "xhs-cli"
    return result


def social_search(platform: str, query: str, count: int = 5,
                  page: int = 1) -> dict:
    """Search Bilibili/Xiaohongshu without consuming web-search quota."""
    platform = platform.lower().replace("哔哩哔哩", "bilibili").replace("小红书", "xiaohongshu")
    if platform in {"bili", "bilibili", "b站"}:
        return _exec_bili_search(query, count, page)
    if platform in {"xhs", "xiaohongshu", "xhs-cli"}:
        return _exec_xhs_search(query, count, page)
    return {"ok": False, "error": "unsupported_social_platform",
            "message": "supported platforms: bilibili, xiaohongshu"}


def social_read(platform: str, note: str, xsec_token: str | None = None) -> dict:
    """Read a Xiaohongshu note using the token paired with search results."""
    platform = platform.lower().replace("小红书", "xiaohongshu")
    if platform in {"xhs", "xiaohongshu", "xhs-cli"}:
        return _exec_xhs_read(note, xsec_token)
    return {"ok": False, "error": "unsupported_social_read",
            "message": "read currently supports xiaohongshu"}


def _exec_baidu_search(query: str) -> dict:
    """百度千帆搜索。脚本来自独立 skill baiduaisearchwithquota，
    路径通过 BAIDU_QF_SCRIPT 环境变量指定，或按常见位置自动探测。"""
    import os as _os
    candidates = [
        _os.environ.get("BAIDU_QF_SCRIPT", ""),
        "/var/minis/skills/baiduaisearchwithquota/scripts/smart_search.py",
        str(Path.home() / ".d-reach" / "vendor" / "baiduaisearchwithquota" / "scripts" / "smart_search.py"),
    ]
    script = next((c for c in candidates if c and Path(c).exists()), None)
    if not script:
        return {"error": "baidu_script_not_found",
                "message": "Set BAIDU_QF_SCRIPT to baiduaisearchwithquota/scripts/quota_manager.py, "
                           "or install the baiduaisearchwithquota skill."}
    try:
        out = subprocess.check_output([sys.executable, script, "search", query],
                                      text=True, timeout=120)
        return {"ok": True, "service": "baidu_search", "data": out.strip()}
    except Exception as e:
        return {"error": str(e), "service": "baidu_search"}


def _exec_brightdata_tool(tool: str, input_json: str) -> dict:
    cmd = ["minis-mcp-cli", "call", "brightdata", tool, "--input", input_json]
    r = _run(cmd)
    if "ok" in r:
        r["service"] = "brightdata"
    return r


def _exec_exa_search(query: str, count: int) -> dict:
    cmd = ["minis-mcp-cli", "call", "exa", "web_search_exa",
           "--input", json.dumps({"query": query, "numResults": count})]
    r = _run(cmd)
    if "ok" in r:
        r["service"] = "exa"
    return r


def _exec_jina_fetch(target: str, is_query: bool = False) -> dict:
    """Jina Reader：is_query=True 时把关键词当 URL 查询，否则当 URL 抓取。"""
    # Jina 用 URL 前缀：r.jina.ai/<url>；关键词搜索用 r.jina.ai/http://... 不适用，需框定
    if is_query:
        # Jina 不直接支持裸关键词搜索，这里作为 lightweight fallback 返回提示
        return {"error": "jina_search_unsupported", "message":
                "Jina Reader 只支持 URL 抓取，搜索请用 Exa/BrightData/百度"}
    quoted = urllib.parse.quote(target, safe="")
    url = f"https://r.jina.ai/{quoted}"
    try:
        out = subprocess.check_output(["curl", "-s", "--max-time", "30", url],
                                      text=True, timeout=35)
        return {"ok": True, "service": "jina_reader", "data": out[:10000]}
    except Exception as e:
        return {"error": str(e), "service": "jina_reader"}


def _paid_firecrawl_allowed() -> bool:
    """Firecrawl 免费计划有 1000 credits/月；显式 opt-in 才允许消耗 credits。"""
    return os.environ.get("DREACH_ALLOW_PAID", "").lower() in {"1", "true", "yes"}


def _exec_firecrawl_scrape(url: str) -> dict:
    """Firecrawl 单页抓取（显式允许后可能消耗 credits）。"""
    if not _paid_firecrawl_allowed():
        return {"ok": False, "service": "firecrawl", "error": "paid_service_disabled",
                "message": "Firecrawl 默认关闭以保护免费额度；明确允许后设置 DREACH_ALLOW_PAID=1。"}

    try:
        from firecrawl import Firecrawl
        app = Firecrawl()
        doc = app.scrape(url)
        md = getattr(doc, "markdown", "") or getattr(doc, "content", "")
        return {"ok": True, "service": "firecrawl", "data": {"markdown": md[:15000]}}
    except Exception as e:
        return {"error": str(e), "service": "firecrawl"}


def _exec_firecrawl_search(query: str, limit: int = 5) -> dict:
    """Firecrawl /search（耗 2 credits/10 结果）。"""
    try:
        from firecrawl import Firecrawl
        app = Firecrawl()
        s = app.search(query, limit=limit)
        results = []
        for r in s.data or []:
            results.append({"title": getattr(r, "title", ""), "url": getattr(r, "url", ""),
                            "desc": (getattr(r, "description", "") or "")[:500]})
        return {"ok": True, "service": "firecrawl", "data": {"results": results}}
    except Exception as e:
        return {"error": str(e), "service": "firecrawl"}


def _exec_firecrawl_developer(query: str, limit: int = 5) -> dict:
    """Firecrawl Developer Index（编程专用，免 API key，加 key 提高限流）。
    覆盖 doc/issue/pull_request/readme，带 rerank + passages。直接 REST。"""
    try:
        import urllib.request as ur
        url = ("https://api.firecrawl.dev/v2/search/developer?"
               f"query={urllib.parse.quote(query)}&k={min(limit,100)}")
        req = ur.Request(url)
        key = os.environ.get("FIRECRAWL_API_KEY")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with ur.urlopen(req, timeout=40) as resp:
            d = json.loads(resp.read().decode())
        if not d.get("success"):
            return {"ok": False, "service": "firecrawl_developer", "data": d}
        results = [{k: r.get(k) for k in ("id", "type", "url", "title", "license")}
                   for r in d.get("results", [])[:limit]]
        return {"ok": True, "service": "firecrawl_developer",
                "data": {"results": results, "reranked": d.get("reranked")}}
    except Exception as e:
        return {"error": str(e), "service": "firecrawl_developer"}


def _exec_firecrawl_research(query: str, limit: int = 5) -> dict:
    """Firecrawl Research Index 论文搜索（免费，不耗 credits）。需 API key。""" 
    import urllib.request as ur
    try:
        key = os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            return {"ok": False, "service": "firecrawl_research",
                    "error": "FIRECRAWL_API_KEY not set (research index requires key)"}
        url = ("https://api.firecrawl.dev/v2/search/research/papers?"
               f"query={urllib.parse.quote(query)}&k={min(limit,500)}")
        req = ur.Request(url)
        req.add_header("Authorization", f"Bearer {key}")
        with ur.urlopen(req, timeout=40) as resp:
            d = json.loads(resp.read().decode())
        if not d.get("success"):
            return {"ok": False, "service": "firecrawl_research", "data": d}
        papers = [{"paperId": p.get("paperId"), "title": p.get("title"),
                   "arxiv": p.get("primaryId"), "abstract": (p.get("abstract") or "")[:300]}
                  for p in d.get("results", [])[:limit]]
        return {"ok": True, "service": "firecrawl_research", "data": {"papers": papers}}
    except Exception as e:
        return {"error": str(e), "service": "firecrawl_research"}


def _exec_developer_delegate(query: str, limit: int = 5) -> dict:
    """Developer Index 统一入口（quota 判 firecrawl 有余额则走 SDK，否则仍 keyless 可用）。"""
    # Developer Index 免 key 也能用，但触发配额防滥用；超限仍允许（因不耗 credits）
    return _exec_firecrawl_developer(query, limit)


# ── 场景接口 ────────────────────────────────────────────────────────────────

def search(query: str, lang: str = "zh", count: int = 5) -> dict:
    """统一搜索。一次 gate()，按结果分发。"""
    scenario = "search_zh" if lang == "zh" else "search_en"
    result = gate(scenario, count=1)
    if not result["ok"]:
        return {"error": "quota_exhausted", "message": result["reason"],
                "quota": result["quota_snapshot"]}

    service = result["service"]
    if service == "baidu_search":
        return _exec_baidu_search(query)
    elif service == "brightdata":
        return _exec_brightdata_tool("search_engine",
                                     json.dumps({"query": query, "engine": "google"}))
    elif service == "exa":
        return _exec_exa_search(query, count)
    elif service == "jina_reader":
        return _exec_jina_fetch(query, is_query=True)
    else:
        return {"error": f"unknown_service: {service}"}


def scrape(url: str, mode: str = "markdown") -> dict:
    """统一单页爬取。"""
    result = gate("scrape_single", count=1)
    if not result["ok"]:
        return {"error": "quota_exhausted", "message": result["reason"],
                "quota": result["quota_snapshot"]}

    service = result["service"]
    if service == "brightdata":
        tool = "scrape_as_markdown" if mode == "markdown" else "scrape_as_html"
        return _exec_brightdata_tool(tool, json.dumps({"url": url}))
    elif service == "jina_reader":
        return _exec_jina_fetch(url, is_query=False)
    elif service == "firecrawl":
        try:
            from firecrawl import Firecrawl
            app = Firecrawl()
            data = app.scrape(url)
            return {"ok": True, "service": "firecrawl", "data": data}
        except Exception as e:
            return {"error": str(e), "service": "firecrawl"}
    else:
        return {"error": f"unknown_service: {service}"}


def scrape_batch(urls: list[str]) -> dict:
    """统一批量爬取。"""
    # BrightData batch 一次最多 10 个 URL；超过则分片
    result = gate("scrape_batch", count=max(1, len(urls) // 10 + (1 if len(urls) % 10 else 0)))
    if not result["ok"]:
        return {"error": "quota_exhausted", "message": result["reason"],
                "quota": result["quota_snapshot"]}

    service = result["service"]
    if service == "brightdata":
        return _exec_brightdata_tool("scrape_batch", json.dumps({"urls": urls[:10]}))
    elif service == "firecrawl":
        results = []
        for u in urls[:10]:
            results.append(scrape(u))
        return {"ok": True, "service": "firecrawl", "data": results}
    elif service == "jina_reader":
        results = []
        for u in urls[:10]:
            results.append(_exec_jina_fetch(u, is_query=False))
        return {"ok": True, "service": "jina_reader", "data": results}
    else:
        return {"error": f"batch_not_supported: {service}"}


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: unified_entry.py <search|scrape|scrape_batch|status> [args...]")
        sys.exit(1)
    cmd = sys.argv[1]

    if cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        lang = sys.argv[3] if len(sys.argv) > 3 else "zh"
        print(json.dumps(search(q, lang), indent=2, ensure_ascii=False) if q
              else json.dumps({"error": "query required"}))
    elif cmd == "developer":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(_exec_developer_delegate(q), indent=2, ensure_ascii=False) if q
              else json.dumps({"error": "query required"}))
    elif cmd == "research":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(_exec_firecrawl_research(q), indent=2, ensure_ascii=False) if q
              else json.dumps({"error": "query required"}))
    elif cmd == "firecrawl_search":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(_exec_firecrawl_search(q), indent=2, ensure_ascii=False) if q
              else json.dumps({"error": "query required"}))
    elif cmd == "social_search":
        platform = sys.argv[2] if len(sys.argv) > 2 else ""
        q = sys.argv[3] if len(sys.argv) > 3 else ""
        count = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        page = int(sys.argv[5]) if len(sys.argv) > 5 else 1
        print(json.dumps(social_search(platform, q, count, page),
                         indent=2, ensure_ascii=False) if q
              else json.dumps({"error": "query required"}))
    elif cmd == "social_read":
        platform = sys.argv[2] if len(sys.argv) > 2 else ""
        note = sys.argv[3] if len(sys.argv) > 3 else ""
        token = sys.argv[4] if len(sys.argv) > 4 else None
        print(json.dumps(social_read(platform, note, token),
                         indent=2, ensure_ascii=False) if note
              else json.dumps({"error": "note required"}))
    elif cmd == "search_bili":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        print(json.dumps(social_search("bilibili", q, count),
                         indent=2, ensure_ascii=False) if q
              else json.dumps({"error": "query required"}))
    elif cmd == "search_xhs":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        print(json.dumps(social_search("xiaohongshu", q, count),
                         indent=2, ensure_ascii=False) if q
              else json.dumps({"error": "query required"}))
    elif cmd == "scrape":
        url = sys.argv[2] if len(sys.argv) > 2 else ""
        mode = sys.argv[3] if len(sys.argv) > 3 else "markdown"
        print(json.dumps(scrape(url, mode), indent=2, ensure_ascii=False) if url
              else json.dumps({"error": "url required"}))
    elif cmd == "scrape_batch":
        import shlex
        urls = shlex.split(sys.argv[2]) if len(sys.argv) > 2 else []
        print(json.dumps(scrape_batch(urls), indent=2, ensure_ascii=False) if urls
              else json.dumps({"error": "urls required"}))
    elif cmd == "status":
        print(json.dumps(get_quota_manager().status(), indent=2, ensure_ascii=False))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
