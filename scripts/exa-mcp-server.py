#!/usr/bin/env python3
"""Minimal MCP server for Exa web search.

[备用] 仅当运行环境没有 Minis MCP（minis-mcp-cli）时使用。
正常情况下 agent-reach / D-Reach 通过 `minis-mcp-cli call exa ...` 调用 Exa，
无需启动本脚本。需要 EXA_API_KEY 环境变量。
"""
import json
import os
import sys
import urllib.request
import urllib.error

EXA_API_KEY = os.environ.get("EXA_API_KEY")
if not EXA_API_KEY:
    print(json.dumps({"error": "EXA_API_KEY not set"}))
    sys.exit(1)

TOOL_DEF = {
    "name": "web_search_exa",
    "description": "Search the web using Exa AI.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "numResults": {"type": "integer", "default": 5}
        },
        "required": ["query"]
    }
}

def handle_request(payload):
    method = payload.get("method")
    if method == "tools/list":
        return {"tools": [TOOL_DEF]}
    if method == "tools/call":
        params = payload.get("params", {})
        arguments = params.get("arguments", {})
        query = arguments.get("query", "")
        num_results = arguments.get("numResults", 5)
        return exa_search(query, num_results)
    return {"error": f"unknown method: {method}"}

def exa_search(query, num_results):
    url = "https://api.exa.ai/search"
    data = json.dumps({"query": query, "numResults": num_results}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "x-api-key": EXA_API_KEY,
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}

    items = []
    for r in result.get("results", [])[:num_results]:
        items.append({
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("snippet") or r.get("text", "")[:300]
        })
    return {
        "content": [
            {"type": "text", "text": json.dumps(items, ensure_ascii=False, indent=2)}
        ]
    }

if __name__ == "__main__":
    # Simple stdio JSON-RPC loop
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle_request(payload)
        print(json.dumps({"jsonrpc": "2.0", "id": payload.get("id"), "result": response}))
        sys.stdout.flush()
