from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.experience_store import ExperienceStore
from app.mcp_server import handle
from app.models import CaptureRequest, GatewayEvent, MCPRequest, RecallRequest, VerifyRequest
from app.verifiers import verify


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    store = ExperienceStore(settings.database_path)
    store.seed()
    app.state.store = store
    app.state.settings = settings
    yield


app = FastAPI(
    title="Org_system API",
    description="Verified organizational experience for AI tools",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def store_for(request: Request) -> ExperienceStore:
    return request.app.state.store


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parents[2] / "frontend" / "index.html")


@app.get("/health", tags=["system"])
def health(request: Request) -> dict[str, str]:
    return {"status": "ok", "service": "Org_system", "memory_engine": request.app.state.settings.memory_engine}


@app.get("/api/experiences", tags=["experience"])
def experiences(request: Request, include_nonserveable: bool = True) -> dict[str, Any]:
    return {"experiences": store_for(request).list_experiences(include_nonserveable=include_nonserveable)}


@app.post("/api/capture", status_code=201, tags=["capture"])
def capture(payload: CaptureRequest, request: Request) -> dict[str, Any]:
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Capture requires explicit consent.")
    experience = store_for(request).create_candidate(payload.model_dump())
    return {"experience": experience, "next_action": "Verify the candidate before it can be served to a teammate."}


@app.post("/api/experiences/{experience_id}/verify", tags=["verify"])
def verify_experience(experience_id: str, payload: VerifyRequest, request: Request) -> dict[str, Any]:
    store = store_for(request)
    experience = store.get(experience_id)
    if experience is None:
        raise HTTPException(status_code=404, detail="Experience not found.")
    updated = store.verify(experience_id, verify(experience, payload.model_dump()))
    return {"experience": updated, "serveable": updated["status"] == "verified"}


@app.post("/api/recall", tags=["serve"])
def recall(payload: RecallRequest, request: Request) -> dict[str, Any]:
    receipts = store_for(request).recall(**payload.model_dump())
    return {
        "query": payload.query,
        "consumer": payload.consumer,
        "receipts": receipts,
        "served_only_verified_visible_experiences": True,
    }


@app.post("/api/gateway/events", status_code=201, tags=["connection"])
def gateway_event(payload: GatewayEvent, request: Request) -> dict[str, Any]:
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Gateway event was not captured because consent is disabled.")
    experience = store_for(request).create_candidate({
        "actor": payload.actor,
        "task": payload.tool_call,
        "trace_summary": payload.result,
        "tool_name": payload.tool_name,
        "tags": payload.tags,
        "visibility": payload.visibility,
        "consent": payload.consent,
        "outcome": "success" if payload.succeeded else "failed",
    })
    return {"captured": True, "experience": experience, "note": "The gateway records a candidate; it never serves it before verification."}


@app.post("/mcp", tags=["connection"])
def mcp(payload: MCPRequest, request: Request) -> dict[str, Any]:
    return handle(payload.id, payload.method, payload.params, store_for(request))


@app.get("/api/dashboard/user/{actor}", tags=["dashboard"])
def user_dashboard(actor: str, request: Request) -> dict[str, Any]:
    return store_for(request).user_dashboard(actor)


@app.get("/api/dashboard/team", tags=["dashboard"])
def team_dashboard(request: Request) -> dict[str, Any]:
    return store_for(request).team_dashboard()


@app.get("/api/dashboard/admin", tags=["dashboard"])
def admin_dashboard(request: Request) -> dict[str, Any]:
    return store_for(request).admin_dashboard()


@app.post("/api/demo/reset", tags=["system"])
def reset_demo(request: Request) -> dict[str, str]:
    store_for(request).reset_demo()
    return {"status": "reset", "message": "The transparent local fixtures were restored."}
