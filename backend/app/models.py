"""API contracts for Org_system's experience lifecycle."""

from typing import Any, Literal

from pydantic import BaseModel, Field


VisibilityScope = Literal["private", "team", "org"]
VerifierMethod = Literal["outcome_signal", "llm_judge", "rerun_and_compare", "tests_ci"]


class CaptureRequest(BaseModel):
    actor: str = Field(default="server-derived", min_length=1, max_length=120, description="Ignored in cloud mode; identity comes from the credential.")
    task: str = Field(min_length=3, max_length=4000)
    trace_summary: str = Field(min_length=3, max_length=12000)
    tool_name: str = Field(default="MCP gateway", min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    rationale: str = Field(default="", max_length=5000)
    visibility: VisibilityScope = "team"
    consent: bool = True
    outcome: str = Field(default="success", max_length=40)
    domain_extension: dict[str, Any] = Field(default_factory=dict)


class VerifyRequest(BaseModel):
    method: VerifierMethod = "outcome_signal"
    outcome_succeeded: bool = True
    observed_metrics: dict[str, Any] = Field(default_factory=dict)
    environment_matches: bool = True


class RecallRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    consumer: str = Field(default="server-derived", min_length=1, max_length=120, description="Ignored in cloud mode; identity comes from the credential.")
    limit: int = Field(default=3, ge=1, le=10)
    record_usage: bool = True


class GatewayEvent(BaseModel):
    actor: str = Field(default="server-derived", min_length=1, max_length=120, description="Ignored in cloud mode; identity comes from the credential.")
    tool_name: str = Field(min_length=1, max_length=120)
    tool_call: str = Field(min_length=1, max_length=4000)
    result: str = Field(min_length=1, max_length=12000)
    succeeded: bool = True
    tags: list[str] = Field(default_factory=list, max_length=20)
    visibility: VisibilityScope = "team"
    consent: bool = True


class GoogleCredentialRequest(BaseModel):
    credential: str = Field(min_length=20, max_length=12000)


class MCPTokenRequest(BaseModel):
    label: str = Field(default="Codex laptop", min_length=1, max_length=120)
