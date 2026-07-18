from pydantic import BaseModel, Field


class HiveStats(BaseModel):
    skill_count: int = Field(description="Number of reusable skills in the Hive")
    total_minutes_saved: int = Field(description="Total minutes saved by all reuse events")
    reuse_count: int = Field(description="Total successful skill reuse events")


class PreflightRequest(BaseModel):
    plan: str = Field(min_length=10, max_length=6000, description="A technical plan the user is about to execute")


class ComparisonItem(BaseModel):
    dimension: str
    current_plan: str
    prior_experiment: str
    matched: bool = True


class PreflightResponse(BaseModel):
    hit: bool
    skill_name: str | None = None
    similarity: float | None = None
    author: str | None = None
    created_days_ago: int | None = None
    resource_cost: str | None = None
    ai_message: str | None = None
    safer_script: str | None = None
    model_mode: str = "mock"
    resource_created: bool = False
    proposed_gpu_hours: int | None = None
    historical_gpu_hours: int | None = None
    safer_gpu_hours: int | None = None
    accuracy_gain_percent: int | None = None
    comparison: list[ComparisonItem] = Field(default_factory=list)


class RetrieveRequest(BaseModel):
    error: str = Field(min_length=5, max_length=12000, description="Raw error or stack trace")


class RetrieveResponse(BaseModel):
    hit: bool
    skill_name: str | None = None
    similarity: float | None = None
    author: str | None = None
    created_days_ago: int | None = None
    fix_script: str | None = None
    model_mode: str = "mock"


class DistillRequest(BaseModel):
    transcript: str = Field(min_length=10, max_length=12000, description="Solved incident and working fix")


class DistillResponse(BaseModel):
    saved: bool
    skill_name: str
    bug_signature: str
    working_code: str
    tags: list[str]
    env_assumptions: list[str]
    model_mode: str = "mock"
