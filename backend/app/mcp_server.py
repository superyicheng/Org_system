"""Minimal JSON-RPC MCP surface for local demo and integration testing.

It implements the product tools from the design: recall, duplicate-work
preflight, and candidate capture. The same handlers are used by the stdio MCP
entrypoint and the HTTP integration surface.
"""

from __future__ import annotations

import json
from typing import Any, Literal, get_args

from app.experience_store import AVOIDED_COST_EVIDENCE, ExperienceStore
from app.verifiers import verify


SERVER_INSTRUCTIONS = (
    "Before resource-heavy, novel, debugging, migration, or incident work, call avoid_duplicate_work with the user's natural-language proposal. "
    "Use only verified receipts and preserve attribution. After a completed task with objective evidence and user consent, call record_completed_work; "
    "pass outcome='failure' for a confirmed negative result so the team inherits the dead end instead of repeating it. "
    "Never store secrets, credentials, raw private files, or unredacted logs."
)

# A confirmed failure is a first-class record, not a degraded success. The Literal is
# the single source of truth: it reaches MCP clients as a schema enum, so a connected
# AI can see that "failure" is an available outcome instead of defaulting to success.
RecordableOutcome = Literal["success", "failure", "partial"]
RECORDABLE_OUTCOMES = frozenset(get_args(RecordableOutcome))


def clean_resource_evidence(raw: Any) -> dict[str, float]:
    """Coerce a capture-time evidence dict to {name: number}, rejecting bad input loudly.

    Shared by both MCP surfaces so a recorded cost means the same thing regardless of
    which transport captured it. Empty/None yields {}, which stores no evidence and
    credits nothing — the honest default when a caller omits it.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("resource_evidence must be an object of {name: number}.")
    cleaned: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"resource_evidence['{key}'] must be a number.")
        if value < 0:
            raise ValueError(f"resource_evidence['{key}'] must not be negative.")
        cleaned[str(key)] = float(value)
    return cleaned


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
                "outcome": {
                    "type": "string", "enum": ["success", "failure", "partial"], "default": "success",
                    "description": "Record 'failure' for a confirmed negative result; what_worked then carries the safer next experiment.",
                },
                "resource_evidence": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "description": (
                        "Measured cost this work consumed, e.g. {\"gpu_hours\": 148} or {\"wet_lab_days\": 6}. "
                        f"When a failure is later reused, recognized keys ({', '.join(sorted(AVOIDED_COST_EVIDENCE))}) "
                        "are credited as avoided cost on the impact dashboard; other keys are stored but not scored."
                    ),
                },
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
            outcome = arguments.get("outcome", "success")
            if outcome not in RECORDABLE_OUTCOMES:
                return error(request_id, -32602, f"outcome must be one of {', '.join(sorted(RECORDABLE_OUTCOMES))}")
            try:
                evidence = clean_resource_evidence(arguments.get("resource_evidence"))
            except ValueError as bad_evidence:
                return error(request_id, -32602, str(bad_evidence))
            domain_extension = {"reuse_recipe": arguments["what_worked"]}
            if evidence:
                domain_extension["resource_evidence"] = evidence
            candidate = store.create_candidate({
                "actor": arguments["actor"], "task": arguments["task"], "trace_summary": arguments["trace_summary"],
                "tool_name": "Codex via org.system MCP", "tags": arguments.get("tags", []),
                "rationale": arguments["what_worked"], "visibility": arguments.get("visibility", "team"),
                "consent": True, "outcome": outcome,
                "domain_extension": domain_extension,
            })
            updated = store.verify(candidate["id"], verify(candidate, {
                "method": "outcome_signal", "evidence_confirmed": bool(arguments["evidence_confirmed"]),
            }))
            return response(request_id, {"content": [{"type": "text", "text": json.dumps({
                "experience_id": updated["id"], "status": updated["status"], "asset_hash": store.hash_for(updated["id"]),
            })}]})
        return error(request_id, -32602, f"Unknown tool: {name}")
    return error(request_id, -32601, f"Unknown method: {method}")
