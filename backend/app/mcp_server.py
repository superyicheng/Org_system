"""Minimal JSON-RPC MCP surface for local demo and integration testing.

It implements the product tools from the design: recall, duplicate-work
preflight, and candidate capture. The same handlers are used by the stdio MCP
entrypoint and the HTTP integration surface.
"""

from __future__ import annotations

import json
from typing import Any

from app.experience_store import ExperienceStore
from app.verifiers import verify


SERVER_INSTRUCTIONS = (
    "Before resource-heavy, novel, debugging, migration, or incident work, call avoid_duplicate_work with the user's natural-language proposal. "
    "Use only verified receipts and preserve attribution. After a completed task with objective evidence and user consent, call record_completed_work. "
    "Never store secrets, credentials, raw private files, or unredacted logs."
)


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
        "name": "avoid_duplicate_work",
        "description": "Check a proposed task against verified team experience before spending time or compute.",
        "inputSchema": {
            "type": "object",
            "required": ["proposal", "consumer"],
            "properties": {
                "proposal": {"type": "string"},
                "consumer": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
            },
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
    {
        "name": "record_completed_work",
        "description": "Capture and verify a completed, consented work lesson with objective evidence so teammates can reuse it.",
        "inputSchema": {
            "type": "object",
            "required": ["actor", "task", "trace_summary", "what_worked", "evidence_confirmed"],
            "properties": {
                "actor": {"type": "string"}, "task": {"type": "string"},
                "trace_summary": {"type": "string"}, "what_worked": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "evidence_confirmed": {"type": "boolean"},
                "visibility": {"type": "string", "enum": ["private", "team", "org"], "default": "team"},
            },
        },
    },
]


def response(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(request_id: str | int | None, method: str, params: dict[str, Any], store: ExperienceStore) -> dict[str, Any]:
    if method == "initialize":
        return response(request_id, {
            "protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
            "serverInfo": {"name": "org.system", "version": "1.1.0"},
            "instructions": SERVER_INSTRUCTIONS,
        })
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
        if name == "avoid_duplicate_work":
            records = store.recall(query=arguments["proposal"], consumer=arguments["consumer"], limit=int(arguments.get("limit", 3)), record_usage=True)
            return response(request_id, {"content": [{"type": "text", "text": json.dumps({"matched": bool(records), "verified_receipts": records})}]})
        if name == "record_completed_work":
            candidate = store.create_candidate({
                "actor": arguments["actor"], "task": arguments["task"], "trace_summary": arguments["trace_summary"],
                "tool_name": "Codex via org.system MCP", "tags": arguments.get("tags", []),
                "rationale": arguments["what_worked"], "visibility": arguments.get("visibility", "team"),
                "consent": True, "outcome": "success",
                "domain_extension": {"reuse_recipe": arguments["what_worked"]},
            })
            updated = store.verify(candidate["id"], verify(candidate, {
                "method": "outcome_signal", "evidence_confirmed": bool(arguments["evidence_confirmed"]),
            }))
            return response(request_id, {"content": [{"type": "text", "text": json.dumps({
                "experience_id": updated["id"], "status": updated["status"], "asset_hash": store.hash_for(updated["id"]),
            })}]})
        return error(request_id, -32602, f"Unknown tool: {name}")
    return error(request_id, -32601, f"Unknown method: {method}")
