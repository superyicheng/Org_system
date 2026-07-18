from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.llm_client import LLMClient
from app.models import (
    ComparisonItem,
    DistillRequest,
    DistillResponse,
    HiveStats,
    PreflightRequest,
    PreflightResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from app.seed_data import SEED_SKILLS
from app.vector_store import SkillStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    store = SkillStore(get_settings())
    store.seed()
    app.state.skill_store = store
    yield


app = FastAPI(
    title="Hive.skill API",
    description="AI debugging and execution memory for platform engineering teams",
    version="0.1.0",
    lifespan=lifespan,
)

# The later Next.js frontend will run on local port 3000.
app.add_middleware(
    CORSMiddleware,
    # "null" lets a directly opened local HTML demo call this API.
    allow_origins=["null", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/hive/stats", response_model=HiveStats, tags=["hive"])
def hive_stats(request: Request) -> HiveStats:
    store: SkillStore = request.app.state.skill_store
    return store.stats()


@app.post("/retrieve", response_model=RetrieveResponse, tags=["hive"])
def retrieve(payload: RetrieveRequest, request: Request) -> RetrieveResponse:
    """Real error fingerprinting, Chroma retrieval, and LLM fix adaptation."""

    store: SkillStore = request.app.state.skill_store
    match = store.search_solution(payload.error)
    settings = get_settings()
    if match is None or float(match["similarity"]) < settings.retrieve_similarity_threshold:
        return RetrieveResponse(hit=False)

    generated = LLMClient(settings).generate_fix(payload.error, match)
    return RetrieveResponse(
        hit=True,
        skill_name=str(match["name"]),
        similarity=float(match["similarity"]),
        author=str(match["author"]),
        created_days_ago=int(match["created_days_ago"]),
        fix_script=generated.text,
        model_mode=generated.mode,
    )


@app.post("/distill", response_model=DistillResponse, tags=["hive"])
def distill(payload: DistillRequest, request: Request) -> DistillResponse:
    """Hackathon-safe distillation with deterministic extraction and persistence."""

    transcript_lower = payload.transcript.lower()
    if "postgres" in transcript_lower or "pg_hba" in transcript_lower:
        source = next(skill for skill in SEED_SKILLS if skill.name == "Connect_Internal_Postgres.skill")
        name = source.name
        bug_signature = source.bug_signature
        working_code = source.working_code
        tags = list(source.tags)
        assumptions = list(source.env_assumptions)
    else:
        name = "Team_Debug_Resolution.skill"
        bug_signature = "A solved internal platform incident with a verified executable fix"
        working_code = "#!/usr/bin/env bash\nset -euo pipefail\n# Replace with the verified commands from the incident.\n"
        tags = ["platform", "debug", "team-memory"]
        assumptions = ["The veteran confirmed the fix in the target environment"]

    store: SkillStore = request.app.state.skill_store
    store.save_distilled(
        name=name,
        bug_signature=bug_signature,
        working_code=working_code,
        tags=tags,
        env_assumptions=assumptions,
    )
    return DistillResponse(
        saved=True,
        skill_name=name,
        bug_signature=bug_signature,
        working_code=working_code,
        tags=tags,
        env_assumptions=assumptions,
        model_mode="mock",
    )


@app.post("/preflight", response_model=PreflightResponse, tags=["hive"])
def preflight(payload: PreflightRequest, request: Request) -> PreflightResponse:
    """Prevent an expensive repeat failure before any resource is allocated."""

    store: SkillStore = request.app.state.skill_store
    match = store.search_failed_experiment(payload.plan)
    if match is None or float(match["similarity"]) < get_settings().preflight_similarity_threshold:
        return PreflightResponse(hit=False)

    llm = LLMClient(get_settings())
    generated = llm.explain_preflight(payload.plan, match)
    return PreflightResponse(
        hit=True,
        skill_name=str(match["name"]),
        similarity=float(match["similarity"]),
        author=str(match["author"]),
        created_days_ago=int(match["created_days_ago"]),
        resource_cost=str(match["resource_cost"]),
        ai_message=generated.text,
        safer_script=str(match["working_code"]),
        model_mode=generated.mode,
        resource_created=False,
        proposed_gpu_hours=152,
        historical_gpu_hours=148,
        safer_gpu_hours=6,
        accuracy_gain_percent=3,
        comparison=[
            ComparisonItem(dimension="Data type", current_plan="Production Kubernetes logs", prior_experiment="Production Kubernetes logs"),
            ComparisonItem(dimension="Data volume", current_plan="~8 TB / 30 days", prior_experiment="7.6 TB / 30 days"),
            ComparisonItem(dimension="Processing", current_plan="Full embedding run", prior_experiment="Full embedding run"),
            ComparisonItem(dimension="Resources", current_plan="8 GPU × 19h", prior_experiment="8 GPU × 18.5h"),
        ],
    )
