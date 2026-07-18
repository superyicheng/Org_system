"""Minimal JSON-RPC MCP surface for local demo and integration testing.

It implements the two product tools from the design: `recall_experience` and
`store_experience`. A production deployment can mount this same service through
the official MCP Python SDK streamable HTTP transport.
"""

from __future__ import annotations

import json
from typing import Any

from app.experience_store import ExperienceStore


TOOLS = [
    {
        "name": "recall_experience",
        "description": "Retrieve verified, visible team experience with verification receipts.",
        "inputSchema": {
            "type": "object",
            "required": ["query", "consumer"],
            "properties": {"query": {"type": "string"}, "consumer": {"type": "string"}, "limit": {"type": "integer"}},
        },
    },
    {
        "name": "store_experience",
        "description": "Capture a trace as an unverified experience candidate for later verification.",
        "inputSchema": {
            "type": "object",
            "required": ["actor", "task", "trace_summary"],
            "properties": {"actor": {"type": "string"}, "task": {"type": "string"}, "trace_summary": {"type": "string"}},
        },
    },
]


def response(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(request_id: str | int | None, method: str, params: dict[str, Any], store: ExperienceStore) -> dict[str, Any]:
    if method == "initialize":
        return response(request_id, {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "org-system", "version": "0.1.0"}})
    if method == "tools/list":
        return response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if name == "recall_experience":
            records = store.recall(query=arguments["query"], consumer=arguments["consumer"], limit=int(arguments.get("limit", 3)), record_usage=True)
            return response(request_id, {"content": [{"type": "text", "text": json.dumps({"receipts": records})}]})
        if name == "store_experience":
            candidate = store.create_candidate({
                "actor": arguments["actor"], "task": arguments["task"], "trace_summary": arguments["trace_summary"],
                "tool_name": "MCP client", "tags": arguments.get("tags", []), "visibility": arguments.get("visibility", "team"), "consent": True,
            })
            return response(request_id, {"content": [{"type": "text", "text": json.dumps({"experience_id": candidate["id"], "status": "candidate"})}]})
        return error(request_id, -32602, f"Unknown tool: {name}")
    return error(request_id, -32601, f"Unknown method: {method}")
