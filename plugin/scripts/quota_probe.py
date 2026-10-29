#!/usr/bin/env python3
"""D-Reach 额度官方校准（quota probe）。

本地 quota.json 记的是「我们发过几次请求」，不是「厂商还剩多少」。
本脚本去各家官方接口取真实额度，写进 quota.json 的 `_official` 段，
不覆盖本地计数 —— 两者互为校验：本地计数漏记时，官方数字能纠回来。

  quota_probe.py                 校准并打印人类可读结果
  quota_probe.py --json          机器可读
  quota_probe.py --quiet         fanout 结束时静默调用（只在异常时出声）

已确认可查（2026-10-28 实测）：
  firecrawl   GET /v2/team/credit-usage      → remainingCredits / planCredits / 账期
  tinyfish    MCP get_wallet                 → 钱包余额（search/fetch 本身 $0）
未开放 / 权限不足（如实记录，不猜）：
  brightdata  token 无 account 读权限（/customer/balance 403）
  exa         官方团队接口需申请 access
  jina        只有 dashboard，无公开额度 API
  langsearch  官方只给 token 日额度，无查询端点
"""
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

FILE = Path(os.environ.get("D_REACH_QUOTA_FILE") or Path.home() / ".agent-reach/quota.json")
KEY_SH = Path(__file__).with_name("load_key.sh")
TIMEOUT = 12


def key(name):
    """走 load_key.sh，与全技能同一条查找链（env → ~/.config/agents/env → .env）。"""
    import subprocess
    try:
        out = subprocess.run(
            ["sh", str(KEY_SH), name, ""],
            capture_output=True, text=True, timeout=8,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def probe_firecrawl():
    k = key("FIRECRAWL_API_KEY")
    if not k:
        return {"state": "no_key"}
    d = _get("https://api.firecrawl.dev/v2/team/credit-usage",
             {"Authorization": f"Bearer {k}"})
    box = d.get("data") or {}
    return {
        "state": "ok",
        "remaining": box.get("remainingCredits"),
        "total": box.get("planCredits"),
        "period_start": box.get("billingPeriodStart"),
        "period_end": box.get("billingPeriodEnd"),
        "source": "api:/v2/team/credit-usage",
    }


def probe_tinyfish():
    """TinyFish 走 hosted MCP：initialize 拿 session，再调 get_wallet。"""
    k = key("TINYFISH_API_KEY")
    if not k:
        return {"state": "no_key"}
    url = "https://agent.tinyfish.ai/mcp"

    def rpc(payload, sid=None):
        hdr = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "X-API-Key": k}
        if sid:
            hdr["Mcp-Session-Id"] = sid
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=hdr)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
            return dict(r.headers), raw

    hdrs, _ = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                              "clientInfo": {"name": "d-reach-probe", "version": "1"}}})
    sid = hdrs.get("Mcp-Session-Id") or hdrs.get("mcp-session-id")
    _, raw = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "get_wallet", "arguments": {}}}, sid)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"state": "error", "error": "响应里没有 JSON"}
    body = json.loads(m.group(0))
    text = ""
    for c in (body.get("result") or {}).get("content") or []:
        if c.get("type") == "text":
            text = c.get("text") or ""
            break
    try:
        wallet = json.loads(text)
    except Exception:
        return {"state": "error", "error": "wallet 解析失败"}
    return {
        "state": "ok",
        "balance": wallet.get("available_balance"),
        "currency": wallet.get("currency"),
        "as_of": wallet.get("as_of"),
        "source": "mcp:get_wallet",
    }


def probe_brightdata():
    k = key("BRIGHTDATA_APITOKEN")
    if not k:
        return {"state": "no_key"}
    try:
        _get("https://api.brightdata.com/customer/balance", {"Authorization": f"Bearer {k}"})
        return {"state": "ok", "source": "api:/customer/balance"}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"state": "no_permission",
                    "error": "token 没有 account 读取权限（在控制台 Settings→Users 勾选后再试）"}
        return {"state": "error", "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"state": "error", "error": str(e)[:80]}


def unimplemented(reason):
    return {"state": "unavailable", "error": reason}


PROBES = {
    "firecrawl": probe_firecrawl,
    "tinyfish": probe_tinyfish,
    "brightdata": probe_brightdata,
    "exa": lambda: unimplemented("官方 usage 接口需向 support 申请 access，默认不可用"),
    "jina_reader": lambda: unimplemented("只有 dashboard 看余额，没有公开额度 API"),
    "langsearch": lambda: unimplemented("官方只给 token 日额度，没有查询端点"),
}


def load():
    try:
        return json.loads(FILE.read_text())
    except Exception:
        return {}


def save(d):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=2))
    tmp.replace(FILE)


def run(max_age=0):
    """max_age>0 时：如果上次校准已在 N 秒内，直接复用，不重复请求厂商接口。"""
    if max_age:
        old = (load().get("_official") or {})
        stamps = [v.get("probed_at") for v in old.values() if v.get("state") == "ok"]
        if stamps:
            try:
                last = max(datetime.fromisoformat(t) for t in stamps)
                if (datetime.now(timezone.utc) - last).total_seconds() < max_age:
                    return old
            except Exception:
                pass
    with ThreadPoolExecutor(max_workers=len(PROBES)) as ex:
        futs = {name: ex.submit(fn) for name, fn in PROBES.items()}
        out = {}
        for name, fut in futs.items():
            try:
                out[name] = fut.result()
            except Exception as e:
                out[name] = {"state": "error", "error": str(e)[:100]}
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for v in out.values():
        v["probed_at"] = stamp
    d = load()
    d["_official"] = out
    save(d)
    return out


def render(out, as_json=False):
    if as_json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    lines = []
    for name, v in out.items():
        st = v.get("state")
        if st == "ok":
            if name == "firecrawl":
                rem, tot = v.get("remaining"), v.get("total")
                pct = f"（{rem / tot * 100:.0f}% 剩余）" if rem is not None and tot else ""
                lines.append(f"  {name:12s} ✅ 剩余 {rem}/{tot} credits{pct} 账期至 {str(v.get('period_end'))[:10]}")
            elif name == "tinyfish":
                lines.append(f"  {name:12s} ✅ 钱包 {v.get('balance')} {v.get('currency')}（search/fetch 本身 $0）")
            else:
                lines.append(f"  {name:12s} ✅ {v.get('source')}")
        elif st == "no_key":
            lines.append(f"  {name:12s} 🔇 未配置 key")
        elif st == "unavailable":
            lines.append(f"  {name:12s} ⚪ 无公开接口：{v.get('error')}")
        elif st == "no_permission":
            lines.append(f"  {name:12s} ⚠️ {v.get('error')}")
        else:
            lines.append(f"  {name:12s} ❌ {v.get('error')}")
    print("官方额度校准（写入 quota.json 的 _official 段）")
    print("\n".join(lines))


def main(argv):
    as_json = "--json" in argv
    quiet = "--quiet" in argv
    max_age = 600 if quiet else 0      # fanout 高频调用时 10 分钟内复用上次结果
    for i, a in enumerate(argv):
        if a == "--max-age" and i + 1 < len(argv):
            max_age = int(argv[i + 1])
    try:
        out = run(max_age)
    except Exception as e:
        if not quiet:
            print(f"[quota_probe] 校准失败：{e}", file=sys.stderr)
        return 1
    if not quiet:
        render(out, as_json)
    else:
        ok = [k for k, v in out.items() if v.get("state") == "ok"]
        bad = [k for k, v in out.items() if v.get("state") in ("error", "no_permission")]
        if bad:
            print(f"[quota_probe] 校准异常：{', '.join(bad)}（其余 {len(ok)} 家正常）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
