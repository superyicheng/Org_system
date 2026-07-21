"""API contracts for org.system's experience lifecycle."""

from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


VisibilityScope = Literal["private", "team", "org"]
VerifierMethod = Literal["outcome_signal", "llm_judge", "rerun_and_compare", "tests_ci"]


class CaptureRequest(BaseModel):
    actor: str = Field(default="server-derived", min_length=1, max_length=120)
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
    evidence_confirmed: bool | None = None
    test_exit_code: int | None = None
    judge_score: float | None = Field(default=None, ge=0, le=1)


class RecallRequest(BaseModel):
    query: str = Field(min_length=3, max_length=4000)
    consumer: str = Field(default="server-derived", min_length=1, max_length=120)
    limit: int = Field(default=3, ge=1, le=10)
    record_usage: bool = True


class GatewayEvent(BaseModel):
    session_id: str = Field(default_factory=lambda: f"session-{uuid.uuid4().hex[:10]}", min_length=3, max_length=120)
    event_type: Literal["tool_result", "task_completed"] = "task_completed"
    actor: str = Field(default="server-derived", min_length=1, max_length=120)
    tool_name: str = Field(min_length=1, max_length=120)
    tool_call: str = Field(min_length=1, max_length=4000)
    result: str = Field(min_length=1, max_length=12000)
    succeeded: bool = True
    tags: list[str] = Field(default_factory=list, max_length=20)
    visibility: VisibilityScope = "team"
    consent: bool = True


class MCPRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class DistillRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=120)
    transcript: str = Field(min_length=20, max_length=20000)
    tool_name: str = Field(default="Codex work session", min_length=1, max_length=120)
    visibility: VisibilityScope = "team"
    consent: bool = True


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistRequest(BaseModel):
    role: Literal["auto", "veteran", "newcomer"] = "auto"
    message: str = Field(min_length=10, max_length=12000)
    title: str = Field(default="Team Member", min_length=1, max_length=120)
    record_usage: bool = True
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


class GoogleCredentialRequest(BaseModel):
    credential: str = Field(min_length=20, max_length=12000)


class MemberInviteRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class JoinOrganizationRequest(BaseModel):
    code: str = Field(min_length=8, max_length=120)


class CreateInviteRequest(BaseModel):
    ttl_hours: int = Field(default=168, ge=1, le=24 * 90)
    max_uses: int = Field(default=25, ge=1, le=500)


class RegisterClientRequest(BaseModel):
    """RFC 7591 dynamic client registration; unknown metadata fields are ignored."""

    model_config = ConfigDict(extra="ignore")

    client_name: str = Field(default="MCP client", max_length=120)
    redirect_uris: list[str] = Field(min_length=1, max_length=10)


class OAuthConsentRequest(BaseModel):
    """Consent submitted from the authorization page after Google sign-in."""

    credential: str = Field(default="", max_length=12000)
    client_id: str = Field(min_length=3, max_length=120)
    redirect_uri: str = Field(min_length=3, max_length=2000)
    code_challenge: str = Field(min_length=20, max_length=200)
    code_challenge_method: Literal["S256"] = "S256"
    state: str = Field(default="", max_length=2000)
    scope: str = Field(default="org.read org.write", max_length=200)
    org_id: str = Field(default="", max_length=120)
    label: str = Field(default="", max_length=120)
