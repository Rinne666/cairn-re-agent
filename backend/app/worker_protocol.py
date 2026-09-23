from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class WorkerContext(BaseModel):
    goal: str
    intent: str
    facts: list[dict[str, Any]] = Field(default_factory=list)
    program_nodes: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    failed_directions: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)


class WorkerFinding(BaseModel):
    kind: str
    label: str
    entity_key: str
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0


class SuggestedIntent(BaseModel):
    description: str
    source_entity_keys: list[str] = Field(default_factory=list)
    goal_relevance: Literal["low", "medium", "high"] = "medium"
    information_gain: Literal["low", "medium", "high"] = "medium"
    confidence: Literal["low", "medium", "high"] = "medium"
    expected_cost: Literal["low", "medium", "high"] = "medium"


class WorkerOutput(BaseModel):
    observations: list[WorkerFinding] = Field(default_factory=list)
    evidence: list[WorkerFinding] = Field(default_factory=list)
    hypotheses: list[WorkerFinding] = Field(default_factory=list)
    facts: list[WorkerFinding] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    suggested_intents: list[SuggestedIntent] = Field(default_factory=list)
    status: Literal["completed", "failed"] = "completed"
    summary: str = ""


class AgentDriver(Protocol):
    async def run_agent(self, context: WorkerContext) -> WorkerOutput: ...
