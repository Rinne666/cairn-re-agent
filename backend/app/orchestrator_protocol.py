from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictStr

Rating = Literal["low", "medium", "high"]
BoundedText = Annotated[StrictStr, Field(max_length=500)]
IntentId = Annotated[StrictStr, Field(min_length=1, max_length=36)]


class OrchestratorContext(BaseModel):
    goal: StrictStr
    confirmed_findings: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    active_hypotheses: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    contradictions: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    critical_unknowns: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    active_branches: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    failed_branches: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    recent_evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=16)
    recently_completed_intents: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    recently_failed_intents: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    open_intents: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    pending_worker_proposals: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    budget: dict[str, Any] = Field(default_factory=dict)


class IntentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    description: StrictStr = Field(min_length=12, max_length=1000)
    source_entity_keys: list[Annotated[StrictStr, Field(min_length=1, max_length=320)]] = Field(
        min_length=1, max_length=8
    )
    goal_relevance: Rating
    information_gain: Rating
    novelty: Rating
    confidence: Rating
    expected_cost: Rating
    reason: StrictStr = Field(min_length=8, max_length=1000)


class OrchestratorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    state_summary: StrictStr = Field(max_length=2000)
    focus: StrictStr = Field(min_length=1, max_length=1000)
    intents_to_create: list[IntentProposal] = Field(max_length=3)
    intents_to_close: list[IntentId] = Field(max_length=20)
    intents_to_deprioritize: list[IntentId] = Field(max_length=20)
    critical_unknowns: list[BoundedText] = Field(max_length=20)
    convergence_status: Literal["continue", "completed", "stalled"]
    convergence_reason: StrictStr = Field(max_length=2000)


@dataclass
class OrchestratorRun:
    output: OrchestratorOutput | None
    duration_seconds: float
    token_input: int = 0
    token_output: int = 0
    retry_count: int = 0
    schema_valid: bool = False
    schema_invalid_attempts: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class OrchestratorDriver(Protocol):
    async def run_orchestrator(self, context: OrchestratorContext) -> OrchestratorRun: ...
