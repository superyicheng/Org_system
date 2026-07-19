from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.auth import issue_session, new_machine_token, require_admin, require_identity, verify_google
from app.config import get_settings
from app.experience_store import ExperienceStore, actor_key
from app.mcp_service import app as mcp_app, configure_mcp, lifespan as mcp_lifespan
from app.models import CaptureRequest, GatewayEvent, GoogleCredentialRequest, MCPTokenRequest, RecallRequest, VerifyRequest
from app.verifiers import verify


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    store = ExperienceStore(settings)
    store.seed()
    configure_mcp(store)
    app.state.store = store
    app.state.settings = settings
    async with mcp_lifespan():
        yield


app = FastAPI(
    title="Org_system API",
    description="Verified organizational experience for AI tools",
    version="0.2.0",
    lifespan=lifespan,
)
settings_for_cors = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings_for_cors.allowed_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/mcp", mcp_app)


def store_for(request: Request) -> ExperienceStore:
    return request.app.state.store


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    module_path = Path(__file__).resolve()
    for parent in (module_path.parents[2], module_path.parents[1]):
        candidate = parent / "frontend" / "index.html"
        if candidate.exists():
            return FileResponse(candidate)
    raise HTTPException(status_code=500, detail="Frontend bundle is missing.")


@app.get("/health", tags=["system"])
def health(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    return {"status": "ok", "service": "Org_system", "memory_engine": settings.memory_engine, "auth_mode": settings.auth_mode}


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
    store_for(request).upsert_user(email=identity.email, display_name=identity.display_name, role=identity.role)
    return {"access_token": issue_session(identity, settings), "token_type": "bearer", "user": identity.__dict__}


@app.get("/api/auth/me", tags=["auth"])
def current_identity(request: Request) -> dict[str, Any]:
    return {"user": require_identity(request).__dict__}


@app.post("/api/auth/mcp-token", tags=["auth"])
def create_mcp_token(payload: MCPTokenRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    settings = request.app.state.settings
    if settings.is_demo:
        return {
            "token_id": "demo",
            "token": "demo",
            "warning": "Local demo token only. Do not use this value in a hosted deployment.",
            "codex_url": f"{settings.public_url}/mcp/",
        }
    store = store_for(request)
    store.upsert_user(email=identity.email, display_name=identity.display_name, role=identity.role)
    raw_token, _ = new_machine_token()
    token_id = store.create_mcp_token(owner_email=identity.email, label=payload.label, raw_token=raw_token)
    return {
        "token_id": token_id,
        "token": raw_token,
        "warning": "Copy this token now. It is shown once and should be stored in your OS credential manager, not committed to a repository.",
        "codex_url": f"{settings.public_url}/mcp/",
    }


@app.get("/api/auth/mcp-tokens", tags=["auth"])
def list_mcp_tokens(request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    return {"tokens": store_for(request).list_mcp_tokens(owner_email=None if identity.role == "admin" else identity.email)}


@app.delete("/api/auth/mcp-tokens/{token_id}", tags=["auth"])
def revoke_mcp_token(token_id: str, request: Request) -> dict[str, bool]:
    identity = require_identity(request)
    revoked = store_for(request).revoke_mcp_token(token_id=token_id, owner_email=None if identity.role == "admin" else identity.email)
    if not revoked:
        raise HTTPException(status_code=404, detail="Active Codex connection not found.")
    return {"revoked": True}


@app.get("/api/experiences", tags=["experience"])
def experiences(request: Request, include_nonserveable: bool = True) -> dict[str, Any]:
    identity = require_identity(request)
    consumer = None if identity.role == "admin" else identity.email
    return {"experiences": store_for(request).list_experiences(include_nonserveable=include_nonserveable, consumer=consumer)}


@app.post("/api/capture", status_code=201, tags=["capture"])
def capture(payload: CaptureRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Capture requires explicit consent.")
    capture_data = payload.model_dump()
    capture_data["actor"] = {"id": identity.email, "display_name": identity.display_name}
    experience = store_for(request).create_candidate(capture_data)
    return {"experience": experience, "next_action": "Verify the candidate before it can be served to a teammate."}


@app.post("/api/experiences/{experience_id}/verify", tags=["verify"])
def verify_experience(experience_id: str, payload: VerifyRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    store = store_for(request)
    experience = store.get(experience_id)
    if experience is None:
        raise HTTPException(status_code=404, detail="Experience not found.")
    if identity.role != "admin" and actor_key(experience) != identity.email.lower():
        raise HTTPException(status_code=403, detail="Only the contributor or an admin can verify this experience.")
    updated = store.verify(experience_id, verify(experience, payload.model_dump()))
    return {"experience": updated, "serveable": updated["status"] == "verified"}


@app.post("/api/recall", tags=["serve"])
def recall(payload: RecallRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    recall_data = payload.model_dump()
    recall_data["consumer"] = identity.email
    receipts = store_for(request).recall(**recall_data)
    return {
        "query": payload.query,
        "consumer": identity.display_name,
        "receipts": receipts,
        "served_only_verified_visible_experiences": True,
    }


@app.post("/api/gateway/events", status_code=201, tags=["connection"])
def gateway_event(payload: GatewayEvent, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Gateway event was not captured because consent is disabled.")
    experience = store_for(request).create_candidate({
        "actor": {"id": identity.email, "display_name": identity.display_name},
        "task": payload.tool_call,
        "trace_summary": payload.result,
        "tool_name": payload.tool_name,
        "tags": payload.tags,
        "visibility": payload.visibility,
        "consent": payload.consent,
        "outcome": "success" if payload.succeeded else "failed",
    })
    return {"captured": True, "experience": experience, "note": "The gateway records a candidate; it never serves it before verification."}


@app.get("/api/dashboard/user/{actor}", tags=["dashboard"])
def user_dashboard(actor: str, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    if identity.role != "admin" and actor.lower() != identity.display_name.lower():
        raise HTTPException(status_code=403, detail="Employees can view only their own dashboard.")
    return store_for(request).user_dashboard(actor)


@app.get("/api/dashboard/team", tags=["dashboard"])
def team_dashboard(request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    return store_for(request).team_dashboard(consumer=None if identity.role == "admin" else identity.email)


@app.get("/api/dashboard/admin", tags=["dashboard"])
def admin_dashboard(request: Request) -> dict[str, Any]:
    require_admin(request)
    return store_for(request).admin_dashboard()


@app.post("/api/demo/reset", tags=["system"])
def reset_demo(request: Request) -> dict[str, str]:
    require_admin(request)
    store_for(request).reset_demo()
    return {"status": "reset", "message": "The transparent local fixtures were restored."}
