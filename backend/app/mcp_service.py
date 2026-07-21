"""Authenticated Streamable HTTP MCP server for employee Codex clients."""

from contextlib import asynccontextmanager
import json
from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.auth import token_digest
from app.config import get_settings
from app.experience_store import ExperienceStore
from app.verifiers import verify


_store: ExperienceStore | None = None
_settings = get_settings()
_public_host = urlparse(_settings.public_url).netloc


def configure_mcp(store: ExperienceStore) -> None:
    global _store
    _store = store


class OrgSystemTokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        if _settings.is_demo and token == "demo":
            return AccessToken(token=token, client_id="demo@org.system", scopes=["admin"])
        if _store is None or not token.startswith("orgmcp_"):
            return None
        identity = _store.identity_for_mcp_token(token_digest(token))
        return AccessToken(token=token, client_id=identity["email"], scopes=[identity["role"]]) if identity else None


def _employee() -> dict[str, str]:
    access_token = get_access_token()
    if access_token is None:
        raise RuntimeError("org.system MCP authentication context is missing.")
    if _settings.is_demo and access_token.client_id == "demo@org.system":
        return {"email": "demo@org.system", "display_name": "Demo User", "role": "admin"}
    if _store is None:
        raise RuntimeError("org.system storage is unavailable.")
    identity = _store.identity_for_email(access_token.client_id)
    if not identity:
        raise RuntimeError("The authenticated org.system user no longer exists.")
    return identity


server = FastMCP(
    "org.system",
    instructions=(
        "Before resource-heavy, novel, debugging, migration, deployment, or incident work, call avoid_duplicate_work. "
        "Use only verified receipts and preserve attribution. After objective work completes, call record_completed_work; never store secrets or raw private files."
    ),
    stateless_http=True,
    streamable_http_path="/",
    auth=AuthSettings(issuer_url=_settings.public_url, resource_server_url=f"{_settings.public_url}/mcp"),
    token_verifier=OrgSystemTokenVerifier(),
    transport_security=TransportSecuritySettings(
        allowed_hosts=[_public_host, "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "testserver"],
        allowed_origins=list(_settings.allowed_origins),
    ),
)


@server.tool()
def recall_experience(query: str, limit: int = 3) -> dict[str, Any]:
    """Retrieve verified and visible organizational experience for this employee."""
    employee = _employee()
    if _store is None:
        raise RuntimeError("org.system storage is unavailable.")
    return {"receipts": _store.recall(query=query, consumer=employee["email"], limit=max(1, min(limit, 10)), record_usage=True, personal_only=_settings.is_public_trial)}


@server.tool()
def avoid_duplicate_work(proposal: str, limit: int = 3) -> dict[str, Any]:
    """Check a proposed task against verified team experience before costly work begins."""
    employee = _employee()
    if _store is None:
        raise RuntimeError("org.system storage is unavailable.")
    receipts = _store.recall(query=proposal, consumer=employee["email"], limit=max(1, min(limit, 5)), record_usage=True, personal_only=_settings.is_public_trial)
    return {"matched": bool(receipts), "verified_receipts": receipts}


@server.tool()
def store_experience(task: str, trace_summary: str, tags: list[str] | None = None, visibility: str = "team") -> dict[str, str]:
    """Capture a completed task as a candidate; it remains unavailable until verified."""
    employee = _employee()
    if _store is None:
        raise RuntimeError("org.system storage is unavailable.")
    if visibility not in {"private", "team", "org"}:
        raise ValueError("visibility must be private, team, or org")
    visibility = "private" if _settings.is_public_trial else visibility
    candidate = _store.create_candidate({"actor": {"id": employee["email"], "display_name": employee["display_name"]}, "task": task, "trace_summary": trace_summary, "tool_name": "Codex via Streamable HTTP MCP", "tags": tags or [], "visibility": visibility, "consent": True})
    return {"experience_id": candidate["id"], "status": "candidate"}


@server.tool()
def record_completed_work(task: str, trace_summary: str, what_worked: str, evidence_confirmed: bool, tags: list[str] | None = None, visibility: str = "team") -> dict[str, str]:
    """Capture a completed lesson; cloud deployments hold it for admin verification before teammate reuse."""
    employee = _employee()
    if _store is None:
        raise RuntimeError("org.system storage is unavailable.")
    visibility = "private" if _settings.is_public_trial else visibility
    candidate = _store.create_candidate({"actor": {"id": employee["email"], "display_name": employee["display_name"]}, "task": task, "trace_summary": trace_summary, "tool_name": "Codex via Streamable HTTP MCP", "tags": tags or [], "rationale": what_worked, "visibility": visibility, "consent": True, "outcome": "success", "domain_extension": {"reuse_recipe": what_worked}})
    saved = _store.verify(candidate["id"], verify(candidate, {"method": "outcome_signal", "evidence_confirmed": evidence_confirmed})) if _settings.auto_verifies_personal_memory else candidate
    return {"experience_id": saved["id"], "status": saved["status"], "asset_hash": _store.hash_for(saved["id"]) or ""}


app = server.streamable_http_app()


@asynccontextmanager
async def lifespan():
    async with server.session_manager.run():
        yield
