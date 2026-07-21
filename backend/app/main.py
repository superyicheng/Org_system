import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.auth import issue_session, new_machine_token, require_admin, require_identity, verify_google
from app.config import get_settings
from app.distiller import distill
from app.experience_store import ExperienceStore, actor_key
from app.llm_client import LLMClient
from app.mcp_service import app as mcp_app, configure_mcp, lifespan as mcp_lifespan
from app.models import AssistRequest, CaptureRequest, DistillRequest, GatewayEvent, GoogleCredentialRequest, MCPTokenRequest, MemberInviteRequest, RecallRequest, VerifyRequest
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
    configure_mcp(store)
    app.state.store = store
    app.state.settings = settings
    app.state.llm = LLMClient(settings)
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
app.mount("/mcp", mcp_app)


def store_for(request: Request) -> ExperienceStore:
    return request.app.state.store


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
    active_tokens = [token for token in store.list_mcp_tokens() if not token.get("revoked_at")]
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
            "active_personal_tokens": len(active_tokens),
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
    if not settings.is_public_trial and not store.member_is_allowed(email=identity.email, configured_emails=settings.admin_emails | settings.allowed_emails):
        raise HTTPException(status_code=403, detail="Your Google account has not been added to this org.system team.")
    store.upsert_user(email=identity.email, display_name=identity.display_name, role=identity.role)
    return {"access_token": issue_session(identity, settings), "token_type": "bearer", "user": identity.__dict__}


@app.get("/api/auth/me", tags=["auth"])
def current_identity(request: Request) -> dict[str, Any]:
    return {"user": require_identity(request).__dict__}


@app.post("/api/auth/mcp-token", tags=["auth"])
def create_mcp_token(payload: MCPTokenRequest, request: Request) -> dict[str, str]:
    identity = require_identity(request)
    settings = request.app.state.settings
    if settings.is_demo:
        return {"token_id": "demo", "token": "demo", "warning": "Local demo token only; do not use it in cloud mode.", "codex_url": f"{settings.public_url}/mcp/"}
    store = store_for(request)
    store.upsert_user(email=identity.email, display_name=identity.display_name, role=identity.role)
    raw_token = new_machine_token()
    token_id = store.create_mcp_token(owner_email=identity.email, label=payload.label, raw_token=raw_token)
    return {"token_id": token_id, "token": raw_token, "warning": "Copy this token now. It is shown only once.", "codex_url": f"{settings.public_url}/mcp/"}


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
    identity = require_identity(request)
    items = store_for(request).list_experiences(include_nonserveable=include_nonserveable, consumer=None if identity.role == "admin" else identity.email)
    if request.app.state.settings.is_public_trial:
        items = [item for item in items if actor_key(item) == identity.email]
    elif identity.role != "admin":
        items = [item for item in items if item["status"] == "verified" or actor_key(item) == identity.email]
    return {"experiences": items}


@app.post("/api/capture", status_code=201, tags=["capture"])
def capture(payload: CaptureRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    if not payload.consent:
        raise HTTPException(status_code=422, detail="Capture requires explicit consent.")
    capture_data = payload.model_dump()
    capture_data["actor"] = actor_for(identity, payload.actor, request)
    capture_data["visibility"] = visibility_for(request, payload.visibility)
    experience = store_for(request).create_candidate(capture_data)
    return {"experience": experience, "next_action": (
        "Verify the candidate before it can be served to your future AI requests."
        if request.app.state.settings.is_public_trial else
        "Verify the candidate before it can be served to a teammate."
    )}


@app.post("/api/distill", status_code=201, tags=["capture"])
def distill_trace(payload: DistillRequest, request: Request) -> dict[str, Any]:
    identity = require_identity(request)
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
    identity = require_identity(request)
    recall_data = payload.model_dump()
    recall_data["consumer"] = identity.email
    receipts = store_for(request).recall(**recall_data, personal_only=request.app.state.settings.is_public_trial)
    return {
        "query": payload.query,
        "consumer": identity.display_name,
        "receipts": receipts,
        "served_only_verified_visible_experiences": True,
    }


@app.post("/api/assist", tags=["serve"])
def assist(payload: AssistRequest, request: Request) -> dict[str, Any]:
    """Conversational demo boundary used by Sarah, Tom, and Mei."""
    identity = require_identity(request)
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
    receipts = store.recall(query=payload.message, consumer=consumer, limit=3, record_usage=payload.record_usage, personal_only=request.app.state.settings.is_public_trial)
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
    identity = require_identity(request)
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
    identity = require_identity(request)
    if not request.app.state.settings.is_demo and identity.role != "admin" and actor.lower() != identity.display_name.lower():
        raise HTTPException(status_code=403, detail="Employees can view only their own dashboard.")
    return store_for(request).user_dashboard(actor)


@app.get("/api/dashboard/team", tags=["dashboard"])
def team_dashboard(request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    return store_for(request).team_dashboard(consumer=None if identity.role == "admin" else identity.email, personal_only=request.app.state.settings.is_public_trial)


@app.get("/api/dashboard/admin", tags=["dashboard"])
def admin_dashboard(request: Request) -> dict[str, Any]:
    require_admin(request)
    return store_for(request).admin_dashboard()


@app.get("/api/dashboard/impact", tags=["dashboard"])
def impact_dashboard(request: Request) -> dict[str, Any]:
    identity = require_identity(request)
    return store_for(request).impact_dashboard(consumer=identity.email if request.app.state.settings.is_public_trial else None)


@app.post("/api/demo/reset", tags=["system"])
def reset_demo(request: Request) -> dict[str, str]:
    require_admin(request)
    if not request.app.state.settings.is_demo:
        raise HTTPException(status_code=404, detail="Demo reset is unavailable in the shared service.")
    store_for(request).reset_demo()
    return {"status": "reset", "message": "The transparent local fixtures were restored."}
