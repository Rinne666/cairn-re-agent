from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)


class WorkerContext(BaseModel):
    goal: str
    intent: str
    facts: list[dict[str, Any]] = Field(default_factory=list)
    program_nodes: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    other_nodes: list[dict[str, Any]] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    failed_directions: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)


class WorkerFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: StrictStr = Field(min_length=1)
    label: StrictStr = Field(min_length=1)
    entity_key: StrictStr = Field(min_length=1)
    properties: dict[str, Any]
    confidence: StrictFloat = Field(ge=0.0, le=1.0)


class WorkerRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_entity_key: StrictStr = Field(min_length=1)
    target_entity_key: StrictStr = Field(min_length=1)
    kind: Literal[
        "derived_from",
        "supports",
        "contradicts",
        "verified_by",
        "references",
        "calls",
        "flows_to",
    ]
    properties: dict[str, Any]


class WorkerArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: StrictStr = Field(min_length=1)
    path: StrictStr = Field(min_length=1)
    sha256: StrictStr = Field(min_length=1)
    summary: StrictStr = Field(min_length=1)
    size: StrictInt = Field(ge=0)
    provenance: dict[str, Any]


class SuggestedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    description: StrictStr = Field(min_length=1)
    source_entity_keys: list[StrictStr]
    goal_relevance: Literal["low", "medium", "high"]
    information_gain: Literal["low", "medium", "high"]
    confidence: Literal["low", "medium", "high"]
    expected_cost: Literal["low", "medium", "high"]


class WorkerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    observations: list[WorkerFinding]
    evidence: list[WorkerFinding]
    hypotheses: list[WorkerFinding]
    facts: list[WorkerFinding]
    relations: list[WorkerRelation]
    artifacts: list[WorkerArtifact]
    suggested_intents: list[SuggestedIntent] = Field(max_length=3)
    status: Literal["completed", "failed"]
    summary: StrictStr

    @model_validator(mode="after")
    def validate_findings(self) -> WorkerOutput:
        categories = {
            "Observation": self.observations,
            "Evidence": self.evidence,
            "Hypothesis": self.hypotheses,
            "Fact": self.facts,
        }
        seen: set[str] = set()
        for expected_kind, findings in categories.items():
            for finding in findings:
                if finding.kind != expected_kind:
                    raise ValueError(f"{expected_kind} entries must have kind={expected_kind!r}")
                if finding.entity_key in seen:
                    raise ValueError(f"duplicate finding entity_key: {finding.entity_key}")
                seen.add(finding.entity_key)
        return self


@dataclass
class AgentRun:
    """Driver-neutral result and telemetry; raw process streams are diagnostics only."""

    output: WorkerOutput | None
    duration_seconds: float
    token_input: int = 0
    token_output: int = 0
    retry_count: int = 0
    schema_valid: bool = False
    schema_invalid_attempts: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class AgentDriver(Protocol):
    async def run_agent(self, context: WorkerContext) -> AgentRun: ...
