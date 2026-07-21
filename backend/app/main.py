import asyncio
from contextlib import asynccontextmanager, suppress
import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.auth import Identity, issue_session, require_admin, require_identity, require_org, verify_google
from app.config import get_settings
from app.distiller import distill
from app.experience_store import ExperienceStore, actor_key
from app.llm_client import LLMClient
from app.mcp_service import app as mcp_app, configure_mcp, lifespan as mcp_lifespan
from app.models import AssistRequest, CaptureRequest, CreateInviteRequest, CreateOrganizationRequest, DistillRequest, GatewayEvent, GoogleCredentialRequest, JoinOrganizationRequest, MemberInviteRequest, OAuthConsentRequest, RecallRequest, RegisterClientRequest, VerifyRequest
from app.oauth import OAuthError, OAuthStore, SUPPORTED_SCOPES, authorization_server_metadata, protected_resource_metadata, redirect_with
from app.runners import replay_experience
from app.verifiers import verify


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    store = ExperienceStore(settings)
    # The public trial is a blank personal workspace, never an exposed copy of
    # the award fixtures or the organization database.
    if not settings.is_public_trial:
        store.seed()
    # Existing deployments predate organizations: give their records and members a home
    # before any request can be served, so nothing is stranded without an owner.
    default_org = store.adopt_orphans()
    if settings.is_demo:
        # Keep the local demo internally consistent: the demo identity is a real
        # member of the organization whose records it is looking at.
        store.upsert_user(email="demo@org.system", display_name="Demo User", role="admin")
        store.add_member(org_id=default_org, email="demo@org.system", role="admin")
    oauth = OAuthStore(store.engine)
    llm = LLMClient(settings)
    configure_mcp(store, oauth, llm)
    app.state.store = store
    app.state.settings = settings
    app.state.oauth = oauth
    app.state.llm = llm
    async def scheduled_reverification() -> None:
        # REAL LOGIC: due evidence is periodically rerun or marked stale, fail closed.
        while True:
            await asyncio.sleep(settings.reverify_interval_seconds)
            for due in store.reverify_due():
                experience = store.get(due["id"])
                if not experience:
                    continue
                if experience.get("domain_extension", {}).get("runner_payload"):
                    replay = replay_experience(experience)
                    store.verify(experience["id"], verify(experience, {
                        "method": "rerun_and_compare", "environment_matches": replay["succeeded"],
                        "observed_metrics": replay["observed_metrics"],
                    }))
                else:
                    store.verify(experience["id"], {
                        "status": "stale",
                        "verification": {
                            "method": experience["verification"]["method"], "verdict": "STALE",
                            "reverify_after_days": experience["verification"].get("reverify_after_days", 30),
                            "detail": "Scheduled freshness window expired; objective re-verification is required.",
                        },
                    })
    scheduler = asyncio.create_task(scheduled_reverification())
    try:
        async with mcp_lifespan():
            yield
    finally:
        scheduler.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler
        store.close()


app = FastAPI(
    title="org.system API",
    description="Verified organizational experience for AI tools",
    version="1.0.0",
    lifespan=lifespan,
)
settings_for_cors = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings_for_cors.allowed_origins) + ["null"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
def protected_resource_document(request: Request) -> dict[str, Any]:
    """RFC 9728 metadata that turns the 401 on /mcp/ into a usable OAuth flow."""
    return protected_resource_metadata(request.app.state.settings.public_url)


# Registered before the mount on purpose: Starlette matches routes in registration
# order, so anything added after app.mount("/mcp", ...) can never win for a /mcp path.
# Clients and SDK versions disagree about where this document lives, so serve every
# spelling rather than leave discovery to luck.
for _metadata_path in (
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
    "/mcp/.well-known/oauth-protected-resource",
    "/mcp/.well-known/oauth-protected-resource/mcp",
):
    app.add_api_route(_metadata_path, protected_resource_document, methods=["GET"], include_in_schema=False, tags=["oauth"])

app.mount("/mcp", mcp_app)


def store_for(request: Request) -> ExperienceStore:
    return request.app.state.store


def oauth_store_for(request: Request) -> OAuthStore:
    return request.app.state.oauth


def actor_for(identity: Any, supplied_name: str, request: Request) -> dict[str, str]:
    """Use Google identity in cloud mode while retaining named award fixtures locally."""
    if request.app.state.settings.is_demo:
        name = supplied_name.strip() or "Demo User"
        return {"id": name.lower().replace(" ", "-"), "display_name": name}
    return {"id": identity.email, "display_name": identity.display_name}


def visibility_for(request: Request, requested: str) -> str:
    """Public trial records are private to their visitor; team scope is never public."""
    return "private" if request.app.state.settings.is_public_trial else requested


def may_manage_experience(identity: Any, experience: dict[str, Any], request: Request) -> bool:
    """Public-trial visitors can manage only their own private records."""
    settings = request.app.state.settings
    return identity.role == "admin" or (
        (settings.is_demo or settings.is_public_trial) and actor_key(experience) == identity.email
    )


def domain_extension_for(distilled: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """Attach a replayable evidence envelope only for the bounded demo workflow."""
    evidence = distilled.get("resource_evidence", {})
    extension: dict[str, Any] = {
        "domain": distilled["domain"], "resource_evidence": evidence,
        "reuse_recipe": distilled.get("what_worked", ""), **extra,
    }
    if {"logs", "embeddings"}.issubset(set(distilled.get("tags", []))) and all(
        key in evidence for key in ("dataset_tb", "gpu_hours", "accuracy_gain_pct")
    ):
        extension["expected_metrics"] = {
            key: {"value": float(evidence[key]), "tolerance": "exact"}
            for key in ("dataset_tb", "gpu_hours", "accuracy_gain_pct")
        }
        extension["runner_payload"] = {
            "workflow": "log-embedding-experiment", "dataset_tb": float(evidence["dataset_tb"]),
            "sampling_ratio": 1.0,
        }
    return extension


def infer_work_intent(message: str) -> str:
    """Infer capture, pre-flight, or general chat from content, never from a person's name."""
    lowered = message.lower()
    completed_signals = (
        "completed", "finished", "we ran", "we embedded", "we tested", "we tried",
        "consumed", "used ", "improved", "failed", "fixed", "solved", "tests passed",
        "the better path", "what worked", "result was",
    )
    proposal_signals = (
        "i want", "i plan", "planning", "should i", "can i launch", "before i", "considering",
        "propose", "proposal", "going to", "want to build",
    )
    completed_score = sum(signal in lowered for signal in completed_signals)
    proposal_score = sum(signal in lowered for signal in proposal_signals)
    if completed_score >= 2 and completed_score > proposal_score:
        return "capture"
    if proposal_score:
        return "recall"
    return "general"


def grounded_reuse_answer(receipt: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    evidence = receipt.get("resource_evidence", {})
    recipe = receipt.get("reuse_recipe") or receipt["claim"]
    if evidence.get("gpu_hours") is not None:
        gpu_hours = float(evidence["gpu_hours"])
        gain = float(evidence.get("accuracy_gain_pct", 0))
        return (
            f"Stop before launching the full job. I found a verified team experiment from {receipt['actor']}: the same approach consumed "
            f"{gpu_hours:g} GPU-hours for only a {gain:g}% accuracy gain. Reuse the proven alternative: {recipe} "
            "This avoids repeating the expensive failure while preserving the innovation as a measurable pilot.",
            {"value": gpu_hours, "unit": "GPUh", "display_value": f"{gpu_hours:g} GPUh", "gpu_hours": gpu_hours,
             "reason": "Matched verified prior experiment before execution"},
        )
    if evidence.get("time_saved_minutes") is not None:
        baseline = float(evidence.get("baseline_minutes", 0))
        result = float(evidence.get("result_minutes", 0))
        saved = float(evidence["time_saved_minutes"])
        return (
            f"Pause before rebuilding this from scratch. I found a verified experiment from {receipt['actor']}: content-addressed dependency "
            f"caching reduced CI build time from {baseline:g} to {result:g} minutes with tests passing. Reuse the proven implementation: {recipe}",
            {"value": saved, "unit": "min", "display_value": f"{saved:g} min", "minutes": saved,
             "reason": "Matched a verified CI optimization before duplicate implementation"},
        )
    return (
        f"I found verified team experience from {receipt['actor']}. Reuse this evidence-backed next step: {recipe}",
        {"value": 1, "unit": "reuse", "display_value": "1 reuse", "reason": "Matched verified team experience"},
    )


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    module_path = Path(__file__).resolve()
    for parent in (module_path.parents[2], module_path.parents[1]):
        candidate = parent / "frontend" / "index.html"
        if candidate.exists():
            return FileResponse(candidate)
    raise HTTPException(status_code=500, detail="Frontend bundle is missing.")


@app.get("/health", tags=["system"])
def health(request: Request) -> dict[str, Any]:
    llm: LLMClient = request.app.state.llm
    return {
        "status": "ok",
        "service": "org.system",
        "memory_engine": request.app.state.settings.memory_engine,
        "llm_mode": request.app.state.settings.llm_mode,
        "llm_live": llm.live,
        "llm_model": llm.model,
        "auth_mode": request.app.state.settings.auth_mode,
    }


@app.get("/api/ai/status", tags=["system"])
def ai_status(request: Request) -> dict[str, Any]:
    """Expose AI readiness without ever returning the API key."""
    require_identity(request)
    llm: LLMClient = request.app.state.llm
    return {
        "configured": llm.live,
        "mode": llm.mode,
        "model": llm.model,
        "last_provider": llm.last_provider,
        "general_questions": "live" if llm.live else "needs OPENAI_API_KEY",
        "memory_core": "online",
    }


@app.get("/api/judge/proof", tags=["system"])
def judge_proof(request: Request) -> dict[str, Any]:
    """Return sanitized, live infrastructure evidence for the hackathon demo.

    This endpoint intentionally exposes capabilities and aggregate counters only.
    It never returns credentials, private experience content, or token hashes.
    """
    identity = require_identity(request)
    settings = request.app.state.settings
    store = store_for(request)
    admin = store.admin_dashboard()
    impact = store.impact_dashboard()
    active_connections = oauth_store_for(request).connections(email=identity.email)
    storage_backend = "PostgreSQL" if settings.database_url.startswith("postgresql") else "SQLite"
    identity_boundary = (
        "Demo identities (Sarah, Tom, Mei)"
        if settings.is_demo
        else "Google Workspace identity + signed sessions"
    )
    return {
        "runtime": {
            "status": "online",
            "service": "org.system",
            "deployment": "local judge demo" if settings.is_demo else "shared cloud service",
            "llm_mode": settings.llm_mode,
            "language_model": settings.openai_model if settings.llm_mode == "openai" else "deterministic stage-safe fallback",
        },
        "memory": {
            "storage_backend": storage_backend,
            "cloud_ready": True,
            "semantic_activation": "hybrid lexical + semantic vectors",
            "verified_assets": admin["status_counts"].get("verified", 0),
            "content_receipts": "SHA-256 + contributor attribution",
        },
        "identity": {
            "mode": settings.auth_mode,
            "boundary": identity_boundary,
            "current_role": identity.role,
            "demo_identities": ["Sarah", "Tom", "Mei"] if settings.is_demo else [],
            "visibility_scopes": ["private", "team", "org"],
        },
        "mcp": {
            "status": "ready",
            "endpoint": f"{settings.public_url}/mcp/",
            "transports": ["Streamable HTTP", "stdio"],
            "active_oauth_connections": len(active_connections),
            "tools": [
                "avoid_duplicate_work",
                "recall_experience",
                "record_completed_work",
                "store_experience",
            ],
        },
        "serve_policy": {
            "gate": ["explicit consent", "visibility permission", "verified status"],
            "freshness": "scheduled re-verification; stale evidence fails closed",
            "claim": "Only verified, visible, consented experience can reach another AI.",
        },
        "ai_roles": {
            "codex": "Build workflow plus project-scoped MCP pre-flight and completed-work capture.",
            "gpt_5_6": "Optional live provider for trace distillation and evidence-grounded answer wording.",
            "executable_core": "Retrieval, persistence, permissions, verification, replay, receipts, and impact accounting do not depend on model output.",
        },
        "differentiator": {
            "ordinary_rag": "Retrieves text that may be stale, private, or unverified.",
            "org_system": "Candidate → evidence gate → permissioned verified recall → attributed reuse receipt.",
        },
        "impact": impact,
        "truth_note": (
            "Demo mode changes identity and wording providers only. Storage, semantic retrieval, "
            "permissions, verification, replay, MCP contracts, receipts, and impact accounting execute normally."
        ),
    }


@app.get("/.well-known/oauth-authorization-server", include_in_schema=False, tags=["oauth"])
@app.get("/.well-known/oauth-authorization-server/mcp", include_in_schema=False, tags=["oauth"])
def oauth_metadata(request: Request) -> dict[str, Any]:
    return authorization_server_metadata(request.app.state.settings.public_url)


@app.post("/oauth/register", status_code=201, tags=["oauth"])
def register_oauth_client(payload: RegisterClientRequest, request: Request) -> dict[str, Any]:
    """RFC 7591 dynamic registration so a client can connect without pre-shared setup."""
    try:
        client = oauth_store_for(request).register_client(client_name=payload.client_name, redirect_uris=payload.redirect_uris)
    except OAuthError as error:
        return JSONResponse(status_code=error.status_code, content={"error": error.code, "error_description": error.description})
    return {**client, "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}


@app.get("/oauth/authorize", include_in_schema=False, tags=["oauth"])
def authorize_page(request: Request) -> HTMLResponse:
    """Consent screen: the one place a human must appear in the connect flow."""
    params = request.query_params
    settings = request.app.state.settings
    client = oauth_store_for(request).client(params.get("client_id", ""))
    redirect_uri = params.get("redirect_uri", "")
    problem = None
    if client is None:
        problem = "This application is not registered with org.system."
    elif redirect_uri not in client["redirect_uris"]:
        # Never redirect to an unregistered URI, not even to report the error.
        problem = "This application asked to be sent to an address it did not register."
    elif params.get("response_type") != "code":
        problem = "org.system only supports the authorization code flow."
    elif params.get("code_challenge_method", "S256") != "S256" or not params.get("code_challenge"):
        problem = "This application must use PKCE with S256."
    context = json.dumps({
        "client_name": (client or {}).get("client_name", "Unknown client"),
        "client_id": params.get("client_id", ""),
        "redirect_uri": redirect_uri,
        "state": params.get("state", ""),
        "scope": params.get("scope") or " ".join(SUPPORTED_SCOPES),
        "code_challenge": params.get("code_challenge", ""),
        "google_client_id": settings.google_client_id,
        "demo": settings.is_demo,
        "problem": problem,
    })
    page = (Path(__file__).resolve().parents[2] / "frontend" / "authorize.html").read_text(encoding="utf-8")
    return HTMLResponse(page.replace("__ORG_SYSTEM_AUTHORIZE_CONTEXT__", context))


@app.post("/oauth/authorize/consent", include_in_schema=False, tags=["oauth"])
def authorize_consent(payload: OAuthConsentRequest, request: Request) -> dict[str, Any]:
    """Verify the person, then mint a code bound to their chosen organization."""
    settings = request.app.state.settings
    store = store_for(request)
    oauth = oauth_store_for(request)
    client = oauth.client(payload.client_id)
    if client is None or payload.redirect_uri not in client["redirect_uris"]:
        raise HTTPException(status_code=400, detail="This application is not registered for that redirect address.")
    if settings.is_demo:
        identity = Identity("demo@org.system", "Demo User", "admin", "demo")
        # The demo user must exist and be a member like anyone else, otherwise the
        # token it is about to receive would not resolve to a person.
        store.upsert_user(email=identity.email, display_name=identity.display_name, role="admin")
        store.add_member(org_id=store.default_organization()["id"], email=identity.email, role="admin")
    else:
        identity = verify_google(payload.credential, settings)
        allowlisted = store.member_is_allowed(email=identity.email, configured_emails=settings.admin_emails | settings.allowed_emails)
        if not settings.is_public_trial and not allowlisted and not store.organizations_for(identity.email) and not settings.org_self_serve:
            raise HTTPException(status_code=403, detail="Your Google account has not been added to this org.system team.")
        store.upsert_user(email=identity.email, display_name=identity.display_name, role=identity.role)
        if (allowlisted or settings.is_public_trial) and not store.organizations_for(identity.email):
            store.add_member(org_id=store.default_organization()["id"], email=identity.email, role=identity.role)
    memberships = store.organizations_for(identity.email) if not settings.is_demo else [{**store.default_organization(), "role": "admin", "status": "active"}]
    if not payload.org_id:
        # First round trip: tell the page who signed in and which memories they may connect.
        return {"stage": "choose_organization", "user": {"email": identity.email, "display_name": identity.display_name}, "organizations": memberships}
    if not any(org["id"] == payload.org_id for org in memberships):
        raise HTTPException(status_code=403, detail="You are not a member of that organization.")
    code = oauth.issue_code(
        client_id=payload.client_id, redirect_uri=payload.redirect_uri, code_challenge=payload.code_challenge,
        email=identity.email, org_id=payload.org_id, scope=payload.scope,
    )
    location = redirect_with(payload.redirect_uri, {"code": code, "state": payload.state} if payload.state else {"code": code})
    return {"stage": "granted", "redirect_to": location}


@app.post("/oauth/token", include_in_schema=False, tags=["oauth"])
async def oauth_token(request: Request) -> JSONResponse:
    """Token endpoint. Accepts form encoding per the spec, and JSON for convenience."""
    body: dict[str, Any] = {}
    if "application/json" in request.headers.get("content-type", ""):
        body = await request.json()
    else:
        body = dict(await request.form())
    oauth = oauth_store_for(request)
    try:
        grant_type = str(body.get("grant_type", ""))
        client_id = str(body.get("client_id", ""))
        if oauth.client(client_id) is None:
            raise OAuthError("invalid_client", "That client is not registered.", 401)
        if grant_type == "authorization_code":
            granted = oauth.consume_code(
                code=str(body.get("code", "")), client_id=client_id,
                redirect_uri=str(body.get("redirect_uri", "")), verifier=str(body.get("code_verifier", "")),
            )
            tokens = oauth.issue_tokens(client_id=client_id, email=granted["email"], org_id=granted["org_id"], scope=granted["scope"])
        elif grant_type == "refresh_token":
            tokens = oauth.rotate_refresh_token(refresh_token=str(body.get("refresh_token", "")), client_id=client_id)
        else:
            raise OAuthError("unsupported_grant_type", "Use authorization_code or refresh_token.")
    except OAuthError as error:
        return JSONResponse(status_code=error.status_code, content={"error": error.code, "error_description": error.description})
    return JSONResponse(content=tokens, headers={"Cache-Control": "no-store"})


@app.post("/oauth/revoke", include_in_schema=False, tags=["oauth"])
async def oauth_revoke(request: Request) -> JSONResponse:
    body = dict(await request.form()) if "application/json" not in request.headers.get("content-type", "") else await request.json()
    identity = oauth_store_for(request).identity_for_access_token(str(body.get("token", "")))
    if identity:
        oauth_store_for(request).revoke_everything_for(identity.email)
    # RFC 7009: revocation always answers 200 so a token cannot be probed for existence.
    return JSONResponse(content={})


@app.get("/api/auth/connections", tags=["auth"])
def list_connections(request: Request) -> dict[str, Any]:
    identity, org_id = require_org(request)
    return {"connections": oauth_store_for(request).connections(email=identity.email, org_id=org_id)}


@app.delete("/api/auth/connections/{connection_id}", tags=["auth"])
def revoke_connection(connection_id: str, request: Request) -> dict[str, bool]:
    identity, _ = require_org(request)
    if not oauth_store_for(request).revoke_connection(connection_id=connection_id, email=identity.email):
        raise HTTPException(status_code=404, detail="Active connection not found.")
    return {"revoked": True}


@app.get("/api/auth/config", tags=["auth"])
def auth_config(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {"auth_mode": settings.auth_mode, "google_client_id": settings.google_client_id, "public_url": settings.public_url}


@app.post("/api/auth/google", tags=["auth"])
def google_sign_in(payload: GoogleCredentialRequest, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    if settings.is_demo:
        raise HTTPException(status_code=400, detail="Google sign-in is disabled in local demo mode.")
    identity = verify_google(payload.credential, settings)
    store = store_for(request)
    allowlisted = store.member_is_allowed(email=identity.email, configured_emails=settings.admin_emails | settings.allowed_emails)
    memberships = store.organizations_for(identity.email)
    if not settings.is_public_trial and not allowlisted and not memberships and not settings.org_self_serve:
        raise HTTPException(status_code=403, detail="Your Google account has not been added to this org.system team.")
    store.upsert_user(email=identity.email, display_name=identity.display_name, role=identity.role)
    if memberships:
        org_id: str | None = memberships[0]["id"]
        identity = Identity(email=identity.email, display_name=identity.display_name, role=memberships[0]["role"], auth_kind=identity.auth_kind, org_id=org_id)
    elif allowlisted or settings.is_public_trial:
        # Existing allowlisted employees and public-trial users land in the organization
        # their records already belong to, so nothing they captured disappears.
        org_id = store.default_organization()["id"]
        store.add_member(org_id=org_id, email=identity.email, role=identity.role)
        identity = Identity(email=identity.email, display_name=identity.display_name, role=identity.role, auth_kind=identity.auth_kind, org_id=org_id)
    else:
        # Signed in, but with no organization yet: the client must create or join one.
        org_id = None
    return {
        "access_token": issue_session(identity, settings), "token_type": "bearer", "user": identity.__dict__,
        "organizations": store.organizations_for(identity.email),
        "needs_organization": org_id is None,
    }


@app.get("/api/auth/me", tags=["auth"])
def current_identity(request: Request) -> dict[str, Any]:
    return {"user": require_identity(request).__dict__}


def _session_for_org(identity: Identity, org_id: str, request: Request) -> dict[str, Any]:
    """Re-issue the browser session bound to an organization and its membership role."""
    store = store_for(request)
    membership = store.membership_for(org_id=org_id, email=identity.email)
    if membership is None or membership["status"] != "active":
        raise HTTPException(status_code=403, detail="You are not an active member of that organization.")
    scoped = Identity(email=identity.email, display_name=identity.display_name, role=membership["role"], auth_kind=identity.auth_kind, org_id=org_id)
    organization = store.get_organization(org_id)
    return {"access_token": issue_session(scoped, request.app.state.settings), "token_type": "bearer", "user": scoped.__dict__, "organization": organization}


@app.get("/api/orgs", tags=["organization"])
def my_organizations(request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    return {"organizations": store_for(request).organizations_for(identity.email), "active_org_id": identity.org_id}


@app.post("/api/orgs", status_code=201, tags=["organization"])
def create_organization(payload: CreateOrganizationRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    store = store_for(request)
    store.upsert_user(email=identity.email, display_name=identity.display_name, role=identity.role)
    try:
        organization = store.create_organization(name=payload.name, created_by=identity.email)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session = _session_for_org(identity, organization["id"], request)
    return {"organization": organization, **session, "message": "You are the first administrator of this organization."}


@app.post("/api/orgs/join", tags=["organization"])
def join_organization(payload: JoinOrganizationRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    store = store_for(request)
    store.upsert_user(email=identity.email, display_name=identity.display_name, role=identity.role)
    try:
        organization = store.redeem_invite(code=payload.code.strip(), email=identity.email)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session = _session_for_org(identity, organization["id"], request)
    return {"organization": organization, **session, "message": f"You joined {organization['name']}."}


@app.post("/api/orgs/{org_id}/activate", tags=["organization"])
def activate_organization(org_id: str, request: Request) -> dict[str, Any]:
    """Switch the signed-in browser session to another organization the user belongs to."""
    identity = require_identity(request)
    if store_for(request).get_organization(org_id) is None:
        raise HTTPException(status_code=404, detail="That organization does not exist.")
    return _session_for_org(identity, org_id, request)


@app.get("/api/orgs/{org_id}/members", tags=["organization"])
def organization_members(org_id: str, request: Request) -> dict[str, Any]:
    """Who is in this organization, how much each has contributed, and how often it was reused."""
    identity, active_org = require_org(request)
    if org_id != active_org:
        raise HTTPException(status_code=403, detail="Switch to that organization before reading its members.")
    members = store_for(request).org_members(org_id)
    return {
        "organization": store_for(request).get_organization(org_id),
        "members": members,
        "totals": {
            "members": len(members),
            "experiences_contributed": sum(member["experiences_contributed"] for member in members),
            "verified_contributions": sum(member["verified_contributions"] for member in members),
            "times_reused": sum(member["times_reused_by_others"] for member in members),
        },
    }


@app.get("/api/orgs/{org_id}/invites", tags=["organization"])
def list_organization_invites(org_id: str, request: Request) -> dict[str, Any]:
    identity, active_org = require_org(request)
    if org_id != active_org or identity.role != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator of this organization may read its invites.")
    return {"invites": store_for(request).list_invites(org_id)}


@app.post("/api/orgs/{org_id}/invites", status_code=201, tags=["organization"])
def create_organization_invite(org_id: str, payload: CreateInviteRequest, request: Request) -> dict[str, Any]:
    identity, active_org = require_org(request)
    if org_id != active_org or identity.role != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator of this organization may create invites.")
    try:
        invite = store_for(request).create_invite(org_id=org_id, created_by=identity.email, ttl_hours=payload.ttl_hours, max_uses=payload.max_uses)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    settings = request.app.state.settings
    return {"invite": invite, "join_url": f"{settings.public_url}/?invite={invite['code']}", "warning": "Anyone with this code can join and read verified team memory."}


@app.delete("/api/orgs/{org_id}/invites/{code}", tags=["organization"])
def revoke_organization_invite(org_id: str, code: str, request: Request) -> dict[str, bool]:
    identity, active_org = require_org(request)
    if org_id != active_org or identity.role != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator of this organization may revoke invites.")
    if not store_for(request).revoke_invite(code=code, org_id=org_id):
        raise HTTPException(status_code=404, detail="That invite is not active.")
    return {"revoked": True}


@app.delete("/api/orgs/{org_id}/members/{email}", tags=["organization"])
def remove_organization_member(org_id: str, email: str, request: Request) -> dict[str, bool]:
    identity, active_org = require_org(request)
    if org_id != active_org or identity.role != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator of this organization may remove members.")
    if email.strip().lower() == identity.email:
        raise HTTPException(status_code=422, detail="You cannot remove your own membership.")
    if not store_for(request).remove_member(org_id=org_id, email=email):
        raise HTTPException(status_code=404, detail="That person is not a member of this organization.")
    # Leaving an organization must also end any AI client still acting inside it.
    oauth_store_for(request).revoke_everything_for(email.strip().lower())
    return {"removed": True}


@app.get("/api/admin/members", tags=["admin"])
def list_members(request: Request) -> dict[str, Any]:
    require_admin(request)
    members = store_for(request).list_users()
    configured_admins = request.app.state.settings.admin_emails
    known = {member["email"] for member in members}
    members.extend({"email": email, "display_name": email.split("@", 1)[0], "role": "admin", "updated_at": "configured"} for email in configured_admins if email not in known)
    return {"members": sorted(members, key=lambda member: (member["role"] != "admin", member["email"]))}


@app.post("/api/admin/members", status_code=201, tags=["admin"])
def provision_member(payload: MemberInviteRequest, request: Request) -> dict[str, Any]:
    require_admin(request)
    try:
        member = store_for(request).provision_employee(payload.email)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"member": member, "message": "Employee may now sign in with this Google account and create a personal Codex connection."}


@app.delete("/api/admin/members/{email}", tags=["admin"])
def deprovision_member(email: str, request: Request) -> dict[str, bool]:
    require_admin(request)
    if email.lower() in request.app.state.settings.admin_emails:
        raise HTTPException(status_code=422, detail="Configured admins cannot be removed from the web allowlist.")
    if not store_for(request).deprovision_employee(email):
        raise HTTPException(status_code=404, detail="Employee is not on the team allowlist.")
    return {"removed": True}


@app.get("/api/experiences", tags=["experience"])
def experiences(request: Request, include_nonserveable: bool = True) -> dict[str, Any]:
    identity, org_id = require_org(request)
    items = store_for(request).list_experiences(include_nonserveable=include_nonserveable, consumer=None if identity.role == "admin" else identity.email, org_id=org_id)
    if request.app.state.settings.is_public_trial:
        items = [item for item in items if actor_key(item) == identity.email]
    elif identity.role != "admin":
        items = [item for item in items if item["status"] == "verified" or actor_key(item) == identity.email]
    return {"experiences": items}


@app.post("/api/capture", status_code=201, tags=["capture"])
def capture(payload: CaptureRequest, request: Request) -> dict[str, Any]:
    identity, org_id = require_org(request)
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Capture requires explicit consent.")
    capture_data = payload.model_dump()
    capture_data["actor"] = actor_for(identity, payload.actor, request)
    capture_data["visibility"] = visibility_for(request, payload.visibility)
    capture_data["org_id"] = org_id
    experience = store_for(request).create_candidate(capture_data)
    return {"experience": experience, "next_action": (
        "Verify the candidate before it can be served to your future AI requests."
        if request.app.state.settings.is_public_trial else
        "Verify the candidate before it can be served to a teammate."
    )}


@app.post("/api/distill", status_code=201, tags=["capture"])
def distill_trace(payload: DistillRequest, request: Request) -> dict[str, Any]:
    identity, org_id = require_org(request)
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Distillation requires explicit capture consent.")
    actor = actor_for(identity, payload.actor, request)
    distilled = distill(payload.transcript, actor["display_name"], payload.tool_name, request.app.state.llm)
    candidate = store_for(request).create_candidate({
        "actor": actor,
        "task": distilled["task"],
        "trace_summary": distilled["trace_summary"],
        "tool_name": payload.tool_name,
        "tags": distilled["tags"],
        "rationale": distilled["rationale"],
        "visibility": visibility_for(request, payload.visibility),
        "consent": payload.consent,
        "outcome": distilled["outcome"],
        "domain_extension": domain_extension_for(distilled),
        "org_id": org_id,
    })
    return {"experience": candidate, "distilled": distilled, "llm_mode": request.app.state.settings.llm_mode}


@app.post("/api/experiences/{experience_id}/verify", tags=["verify"])
def verify_experience(experience_id: str, payload: VerifyRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    store = store_for(request)
    experience = store.get(experience_id)
    if experience is None:
        raise HTTPException(status_code=404, detail="Experience not found.")
    if not may_manage_experience(identity, experience, request):
        raise HTTPException(status_code=403, detail="Only an admin can verify shared production experience.")
    updated = store.verify(experience_id, verify(experience, payload.model_dump()))
    return {"experience": updated, "serveable": updated["status"] == "verified"}


@app.post("/api/experiences/{experience_id}/replay", tags=["verify"])
def replay_and_verify(experience_id: str, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    store = store_for(request)
    experience = store.get(experience_id)
    if experience is None:
        raise HTTPException(status_code=404, detail="Experience not found.")
    if not may_manage_experience(identity, experience, request):
        raise HTTPException(status_code=403, detail="Only an admin can replay shared production experience.")
    try:
        replay = replay_experience(experience)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    result = verify(experience, {
        "method": "rerun_and_compare",
        "environment_matches": replay["succeeded"],
        "observed_metrics": replay["observed_metrics"],
    })
    updated = store.verify(experience_id, result)
    return {"experience": updated, "replay": replay, "serveable": updated["status"] == "verified"}


@app.post("/api/experiences/{experience_id}/verify/ai", tags=["verify"])
def ai_judge_experience(experience_id: str, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    store = store_for(request)
    experience = store.get(experience_id)
    if experience is None:
        raise HTTPException(status_code=404, detail="Experience not found.")
    if not may_manage_experience(identity, experience, request):
        raise HTTPException(status_code=403, detail="Only an admin can judge shared production experience.")
    judge = request.app.state.llm.judge_experience(experience)
    updated = store.verify(experience_id, verify(experience, {
        "method": "llm_judge", "judge_score": judge["score"],
    }))
    return {"experience": updated, "judge_receipt": judge, "serveable": updated["status"] == "verified"}


@app.post("/api/recall", tags=["serve"])
def recall(payload: RecallRequest, request: Request) -> dict[str, Any]:
    identity, org_id = require_org(request)
    recall_data = payload.model_dump()
    recall_data["consumer"] = identity.email
    receipts = store_for(request).recall(**recall_data, personal_only=request.app.state.settings.is_public_trial, org_id=org_id)
    return {
        "query": payload.query,
        "consumer": identity.display_name,
        "receipts": receipts,
        "served_only_verified_visible_experiences": True,
    }


@app.post("/api/assist", tags=["serve"])
def assist(payload: AssistRequest, request: Request) -> dict[str, Any]:
    """Conversational demo boundary used by Sarah, Tom, and Mei."""
    identity, org_id = require_org(request)
    store = store_for(request)
    llm: LLMClient = request.app.state.llm
    intent = (
        "capture" if payload.role == "veteran" else
        "recall" if payload.role == "newcomer" else
        infer_work_intent(payload.message)
    )
    if intent == "capture":
        actor = actor_for(identity, payload.title, request)
        distilled = distill(payload.message, actor["display_name"], "Codex work session", llm)
        candidate = store.create_candidate({
            "actor": actor,
            "task": distilled["task"],
            "trace_summary": distilled["trace_summary"],
            "tool_name": "Codex work session",
            "tags": distilled["tags"],
            "rationale": distilled["rationale"],
            "visibility": visibility_for(request, "team"),
            "consent": True,
            "outcome": distilled["outcome"],
            "domain_extension": domain_extension_for(distilled),
            "org_id": org_id,
        })
        verified = store.verify(candidate["id"], verify(candidate, {
            "method": "outcome_signal", "evidence_confirmed": True,
        })) if request.app.state.settings.auto_verifies_personal_memory else candidate
        fallback = (
            "I captured the completed experiment as a verified negative result. The reusable lesson is: "
            f"{distilled['what_worked']} The evidence and provenance are now available to the next AI request - no documentation form required."
            if request.app.state.settings.auto_verifies_personal_memory else
            "I captured the completed experiment as a candidate for administrator verification. The reusable lesson is: "
            f"{distilled['what_worked']} It will become available to teammates only after the evidence gate passes."
        )
        answer = llm.generate(
            instructions="Respond as an organizational AI memory. Explain what was captured, why the failed result is valuable, and how a teammate will reuse it. Be concise.",
            prompt=str(distilled),
            fallback=fallback,
        )
        return {"answer": answer, "intent": "capture", "experience": verified, "distilled": distilled, "llm_mode": llm.mode}

    consumer = actor_for(identity, payload.title, request)["id"]
    receipts = store.recall(query=payload.message, consumer=consumer, limit=3, record_usage=payload.record_usage, personal_only=request.app.state.settings.is_public_trial, org_id=org_id)
    if not receipts:
        if intent == "general":
            recent = "\n".join(
                f"{turn.role}: {turn.content}" for turn in payload.history[-8:]
            )
            conversation = f"Recent conversation:\n{recent}\n\nCurrent user question:\n{payload.message}" if recent else payload.message
            fallback = (
                "General AI answers are not enabled in this runtime yet. Configure OPENAI_API_KEY and set "
                "ORG_SYSTEM_LLM_MODE=openai; organizational memory, permissions, and MCP remain online."
            )
            answer = llm.generate(
                instructions=(
                    "You are org.system's general AI assistant. Answer the user's question directly and helpfully in the user's language. "
                    "Use recent conversation only when relevant. Do not invent organizational memory or claim that a team record matched. "
                    "Be concise by default, but include concrete steps or examples when useful."
                ),
                prompt=conversation,
                fallback=fallback,
            )
            provider_live = llm.last_provider.startswith("openai:")
            return {
                "answer": answer,
                "intent": "general",
                "hit": False,
                "receipts": [],
                "llm_mode": llm.mode,
                "provider": llm.last_provider,
                "model": llm.model,
                "general_questions_live": provider_live,
            }
        fallback = (
            "I found no verified prior team experience close enough to this proposal. You can proceed with a bounded experiment: "
            "record the current baseline, define a measurable success threshold, limit the first run's cost, and keep tests as a safety gate. "
            "When the experiment finishes, report the before/after result here so I can verify and preserve it for the team."
        )
        return {"answer": llm.generate(instructions="Give a safe next step when organizational memory has no match.", prompt=payload.message, fallback=fallback), "intent": "recall", "hit": False, "receipts": [], "llm_mode": llm.mode}
    top = receipts[0]
    fallback, avoided = grounded_reuse_answer(top)
    answer = llm.generate(
        instructions=(
            "You are the team's AI experience layer. Use only the supplied verified receipt. Explain the concrete prior difficulty, "
            "how it prevents duplicate resource spend, and give an executable next step. Preserve the source name exactly as supplied."
        ),
        prompt=f"New proposal: {payload.message}\nVerified receipt: {top}",
        fallback=fallback,
    )
    return {
        "answer": answer,
        "intent": "recall",
        "hit": True,
        "receipt": top,
        "receipts": receipts,
        "llm_mode": llm.mode,
        "avoided": avoided,
    }


@app.post("/api/gateway/events", status_code=201, tags=["connection"])
def gateway_event(payload: GatewayEvent, request: Request) -> dict[str, Any]:
    identity, org_id = require_org(request)
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Gateway event was not captured because consent is disabled.")
    store = store_for(request)
    event_data = payload.model_dump()
    actor = actor_for(identity, payload.actor, request)
    event_data["actor"] = actor
    event = store.record_gateway_event(event_data)
    if payload.event_type == "tool_result":
        return {"captured": True, "event": event, "experience": None, "note": "Trace buffered until the task-completed boundary."}
    # REAL LOGIC: task boundary triggers distillation automatically; there is no save form.
    distilled = distill(payload.result, actor["display_name"], payload.tool_name, request.app.state.llm)
    candidate = store.create_candidate({
        "actor": actor, "task": distilled["task"], "trace_summary": distilled["trace_summary"],
        "tool_name": payload.tool_name, "tags": sorted(set(payload.tags + distilled["tags"])),
        "rationale": distilled["rationale"], "visibility": visibility_for(request, payload.visibility), "consent": payload.consent,
        "outcome": "success" if payload.succeeded else distilled["outcome"],
        "domain_extension": domain_extension_for(distilled, gateway_session_id=payload.session_id),
        "org_id": org_id,
    })
    experience = store.verify(candidate["id"], verify(candidate, {
        "method": "outcome_signal", "evidence_confirmed": payload.succeeded,
    })) if request.app.state.settings.auto_verifies_personal_memory else candidate
    return {
        "captured": True, "event": event, "experience": experience,
        "note": (
            "Task boundary automatically distilled and verified the consented trace."
            if request.app.state.settings.auto_verifies_personal_memory and payload.succeeded else
            "Task boundary automatically distilled the consented trace; it awaits administrator verification before teammate reuse."
        ),
    }


@app.get("/api/dashboard/user/{actor}", tags=["dashboard"])
def user_dashboard(actor: str, request: Request) -> dict[str, Any]:
    identity, org_id = require_org(request)
    if not request.app.state.settings.is_demo and identity.role != "admin" and actor.lower() != identity.display_name.lower():
        raise HTTPException(status_code=403, detail="Employees can view only their own dashboard.")
    return store_for(request).user_dashboard(actor, org_id=org_id)


@app.get("/api/dashboard/team", tags=["dashboard"])
def team_dashboard(request: Request) -> dict[str, Any]:
    identity, org_id = require_org(request)
    return store_for(request).team_dashboard(consumer=None if identity.role == "admin" else identity.email, personal_only=request.app.state.settings.is_public_trial, org_id=org_id)


@app.get("/api/dashboard/admin", tags=["dashboard"])
def admin_dashboard(request: Request) -> dict[str, Any]:
    _, org_id = require_org(request)
    require_admin(request)
    return store_for(request).admin_dashboard(org_id=org_id)


@app.get("/api/dashboard/impact", tags=["dashboard"])
def impact_dashboard(request: Request) -> dict[str, Any]:
    identity, org_id = require_org(request)
    return store_for(request).impact_dashboard(consumer=identity.email if request.app.state.settings.is_public_trial else None, org_id=org_id)


@app.post("/api/demo/reset", tags=["system"])
def reset_demo(request: Request) -> dict[str, str]:
    require_admin(request)
    if not request.app.state.settings.is_demo:
        raise HTTPException(status_code=404, detail="Demo reset is unavailable in the shared service.")
    store_for(request).reset_demo()
    return {"status": "reset", "message": "The transparent local fixtures were restored."}
