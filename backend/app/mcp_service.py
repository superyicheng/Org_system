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

from app.config import get_settings
from app.distiller import distill
from app.experience_store import ExperienceStore
from app.llm_client import LLMClient
from app.oauth import OAuthStore
from app.mcp_server import RECORDABLE_OUTCOMES, RecordableOutcome, clean_resource_evidence
from app.verifiers import verify


_store: ExperienceStore | None = None
_oauth: OAuthStore | None = None
_llm: LLMClient | None = None
_settings = get_settings()
_public_host = urlparse(_settings.public_url).netloc


def configure_mcp(store: ExperienceStore, oauth: OAuthStore | None = None, llm: LLMClient | None = None) -> None:
    global _store, _oauth, _llm
    _store = store
    _oauth = oauth
    _llm = llm


class OrgSystemTokenVerifier:
    """Accepts OAuth access tokens issued by this service's authorization server."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if _settings.is_demo and token == "demo":
            org_id = _store.default_organization()["id"] if _store else ""
            return AccessToken(token=token, client_id="demo@org.system", scopes=["admin", f"org:{org_id}"])
        if _store is None or _oauth is None:
            return None
        granted = _oauth.identity_for_access_token(token)
        if granted is None:
            return None
        identity = _store.identity_for_email(granted.email)
        if identity is None:
            return None
        # The organization travels with the credential, so a tool call can never be
        # served from an organization the connected client does not belong to.
        return AccessToken(token=token, client_id=granted.email, scopes=[identity["role"], f"org:{granted.org_id}"])


def _employee() -> dict[str, str]:
    access_token = get_access_token()
    if access_token is None:
        raise RuntimeError("org.system MCP authentication context is missing.")
    org_id = next((scope.removeprefix("org:") for scope in access_token.scopes if scope.startswith("org:")), "")
    if not org_id:
        raise RuntimeError("This org.system connection is not bound to an organization. Reconnect from the website.")
    if _settings.is_demo and access_token.client_id == "demo@org.system":
        return {"email": "demo@org.system", "display_name": "Demo User", "role": "admin", "org_id": org_id}
    if _store is None:
        raise RuntimeError("org.system storage is unavailable.")
    identity = _store.identity_for_email(access_token.client_id)
    if not identity:
        raise RuntimeError("The authenticated org.system user no longer exists.")
    if not _store.is_member(org_id=org_id, email=identity["email"]):
        raise RuntimeError("You are no longer a member of this organization.")
    return {**identity, "org_id": org_id}


server = FastMCP(
    "org.system",
    instructions=(
        "Before resource-heavy, novel, debugging, migration, deployment, or incident work, call avoid_duplicate_work. "
        "Use only verified receipts and preserve attribution. After objective work completes, call record_completed_work, "
        "passing outcome='failure' for a confirmed negative result; never store secrets or raw private files."
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
    return {"receipts": _store.recall(query=query, consumer=employee["email"], limit=max(1, min(limit, 10)), record_usage=True, personal_only=_settings.is_public_trial, org_id=employee["org_id"])}


@server.tool()
def avoid_duplicate_work(proposal: str, limit: int = 3) -> dict[str, Any]:
    """Check a proposed task against verified team experience before costly work begins."""
    employee = _employee()
    if _store is None:
        raise RuntimeError("org.system storage is unavailable.")
    receipts = _store.recall(query=proposal, consumer=employee["email"], limit=max(1, min(limit, 5)), record_usage=True, personal_only=_settings.is_public_trial, org_id=employee["org_id"])
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
    candidate = _store.create_candidate({"actor": {"id": employee["email"], "display_name": employee["display_name"]}, "task": task, "trace_summary": trace_summary, "tool_name": "Codex via Streamable HTTP MCP", "tags": tags or [], "visibility": visibility, "consent": True, "org_id": employee["org_id"]})
    return {"experience_id": candidate["id"], "status": "candidate"}


@server.tool()
def record_completed_work(task: str, trace_summary: str, what_worked: str, evidence_confirmed: bool, outcome: RecordableOutcome = "success", tags: list[str] | None = None, resource_evidence: dict[str, float] | None = None, visibility: str = "team") -> dict[str, str]:
    """Capture a completed lesson; cloud deployments hold it for admin verification before teammate reuse.

    Pass outcome='failure' for a confirmed negative result. A measured dead end is
    the most valuable thing the team can inherit, so it is stored as a failure and
    what_worked carries the safer next experiment rather than a claimed win.

    resource_evidence records the measured cost this work consumed, e.g.
    {"gpu_hours": 148} or {"wet_lab_days": 6}. When a failure is later reused, recognized
    keys are credited as avoided cost on the impact dashboard; other keys are stored as-is.
    """
    employee = _employee()
    if _store is None:
        raise RuntimeError("org.system storage is unavailable.")
    if outcome not in RECORDABLE_OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(sorted(RECORDABLE_OUTCOMES))}")
    evidence = clean_resource_evidence(resource_evidence)
    domain_extension = {"reuse_recipe": what_worked}
    if evidence:
        domain_extension["resource_evidence"] = evidence
    visibility = "private" if _settings.is_public_trial else visibility
    candidate = _store.create_candidate({"actor": {"id": employee["email"], "display_name": employee["display_name"]}, "task": task, "trace_summary": trace_summary, "tool_name": "Codex via Streamable HTTP MCP", "tags": tags or [], "rationale": what_worked, "visibility": visibility, "consent": True, "outcome": outcome, "domain_extension": domain_extension, "org_id": employee["org_id"]})
    saved = _store.verify(candidate["id"], verify(candidate, {"method": "outcome_signal", "evidence_confirmed": evidence_confirmed})) if _settings.auto_verifies_personal_memory else candidate
    return {"experience_id": saved["id"], "status": saved["status"], "asset_hash": _store.hash_for(saved["id"]) or ""}


@server.tool()
def capture_session_context(transcript: str, tags: list[str] | None = None, visibility: str = "team") -> dict[str, Any]:
    """Distil a raw work session into a reusable experience and file it for this organization.

    Give it the session context you would otherwise throw away: what was attempted, the
    commands and measurements, and how it ended. The service extracts the task, the
    reusable lesson, the outcome, and any resource evidence, then stores the result in
    the caller's organization. Nothing is stored verbatim, so redact secrets first.
    """
    employee = _employee()
    if _store is None or _llm is None:
        raise RuntimeError("org.system storage is unavailable.")
    if len(transcript.strip()) < 40:
        raise ValueError("Provide enough session context to distil a reusable lesson.")
    if visibility not in {"private", "team", "org"}:
        raise ValueError("visibility must be private, team, or org")
    visibility = "private" if _settings.is_public_trial else visibility
    distilled = distill(transcript, employee["display_name"], "AI session via MCP", _llm)
    candidate = _store.create_candidate({
        "actor": {"id": employee["email"], "display_name": employee["display_name"]},
        "task": distilled["task"], "trace_summary": distilled["trace_summary"],
        "tool_name": "AI session via MCP", "tags": sorted(set((tags or []) + distilled["tags"])),
        "rationale": distilled["rationale"], "visibility": visibility, "consent": True,
        "outcome": distilled["outcome"],
        "domain_extension": {
            "domain": distilled["domain"], "resource_evidence": distilled.get("resource_evidence", {}),
            "reuse_recipe": distilled["what_worked"],
        },
        "org_id": employee["org_id"],
    })
    # A measured dead end is evidence, not a missing result. Gating verification on
    # success would quietly discard exactly the negative results this product exists
    # to preserve, so a definite outcome either way counts as a confirmed signal.
    saved = _store.verify(candidate["id"], verify(candidate, {
        "method": "outcome_signal", "evidence_confirmed": distilled["outcome"] in {"success", "failure"},
    })) if _settings.auto_verifies_personal_memory else candidate
    return {
        "experience_id": saved["id"], "status": saved["status"], "outcome": distilled["outcome"],
        "lesson": distilled["what_worked"], "tags": distilled["tags"],
        "distilled_by": "openai" if _llm.live else "deterministic fallback",
        "note": (
            "Stored and verified in your memory."
            if saved["status"] == "verified" else
            "Held as a candidate until an administrator verifies the evidence in Trust center."
        ),
    }


app = server.streamable_http_app()


@asynccontextmanager
async def lifespan():
    async with server.session_manager.run():
        yield
