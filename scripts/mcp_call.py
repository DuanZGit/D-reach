#!/usr/bin/env python3
"""极简 MCP streamable-HTTP 客户端：一次调用完成 initialize → tools/call。

只做 d-reach 需要的那一种用法：无认证、单次请求-响应、结果要 JSON。
不实现 SSE 长连接、不实现 notifications 队列、不实现 resumability ——
Parallel 的免费档三个工具都是「问一次答一次」，用不上那些。

用法:
  mcp_call.py <endpoint> <tool> '<json-args>'
  mcp_call.py https://mcp.parallel.ai/mcp web_search '{"objective":"...","search_queries":["..."]}'

成功: 把 tool 返回的第一个 content[].text 原样打到 stdout（通常是 JSON 字符串）
失败: 打一行 `MCP_ERROR: ...` 到 stdout 并退出码 1（调用方按文本判失败，不必解析 stderr）
"""
import json
import sys
import urllib.error
import urllib.request

PROTO = "2024-11-05"
TIMEOUT = 40


def _post(endpoint: str, body: dict, session: str | None) -> tuple[str, str | None]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(endpoint, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    # 不声明 text/event-stream 时部分服务端只回 JSON，声明后回 SSE —— 两种都吃
    req.add_header("Accept", "application/json, text/event-stream")
    # 有些 MCP 网关（You.com）会 403 掉 Python-urllib 的默认 UA
    req.add_header("User-Agent", "d-reach/1.0")
    req.add_header("MCP-Protocol-Version", PROTO)
    if session:
        req.add_header("Mcp-Session-Id", session)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", "replace")
        sid = resp.headers.get("Mcp-Session-Id") or session
    return raw, sid


def _parse(raw: str) -> dict | None:
    """SSE 里取最后一条 data: 的 JSON；纯 JSON 响应直接解析。"""
    text = raw.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    payloads = []
    for line in text.splitlines():
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk:
                payloads.append(chunk)
    for chunk in reversed(payloads):
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    return None


def main() -> int:
    if len(sys.argv) < 4:
        print("MCP_ERROR: 用法 mcp_call.py <endpoint> <tool> '<json-args>'")
        return 1
    endpoint, tool, args_raw = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        args = json.loads(args_raw)
    except json.JSONDecodeError as e:
        print(f"MCP_ERROR: 参数不是合法 JSON（{e}）")
        return 1

    try:
        raw, sid = _post(
            endpoint,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTO,
                    "capabilities": {},
                    "clientInfo": {"name": "d-reach", "version": "1.0"},
                },
            },
            None,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"MCP_ERROR: initialize 失败（{e}）")
        return 1
    if not (_parse(raw) or {}).get("result"):
        print(f"MCP_ERROR: initialize 无 result（{raw[:160]}）")
        return 1

    # notifications/initialized 是单向通知，服务端可能回 202 空体，失败也无所谓
    try:
        _post(endpoint, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    except (urllib.error.URLError, TimeoutError, OSError):
        pass

    try:
        raw, _ = _post(
            endpoint,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            },
            sid,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"MCP_ERROR: tools/call 失败（{e}）")
        return 1

    msg = _parse(raw) or {}
    if "error" in msg:
        err = msg["error"]
        print(f"MCP_ERROR: {err.get('message', err) if isinstance(err, dict) else err}")
        return 1
    content = (msg.get("result") or {}).get("content") or []
    for block in content:
        if block.get("type") == "text" and block.get("text"):
            print(block["text"])
            return 0
    print(f"MCP_ERROR: 返回里没有 text 块（{raw[:160]}）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
