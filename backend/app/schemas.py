from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1, max_length=4000)
    config: dict[str, Any] = Field(default_factory=dict)


class ProjectRead(ORMModel):
    id: str
    name: str
    goal: str
    status: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class BinaryRead(ORMModel):
    id: str
    project_id: str
    filename: str
    path: str
    sha256: str
    format: str | None
    architecture: str | None
    bits: int | None
    endian: str | None
    image_base: str | None
    entry_point: str | None
    metadata_json: dict[str, Any]


GraphType = Literal["exploration", "program", "evidence"]


class NodeCreate(BaseModel):
    graph_type: GraphType
    kind: str = Field(min_length=1, max_length=48)
    label: str = Field(min_length=1, max_length=255)
    entity_key: str = Field(min_length=1, max_length=320)
    binary_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: str = "active"
    created_by: str = "api"


class NodeRead(ORMModel):
    id: str
    project_id: str
    binary_id: str | None
    graph_type: str
    kind: str
    label: str
    entity_key: str
    properties: dict[str, Any]
    confidence: float
    status: str
    created_by: str
    created_at: datetime


class EdgeCreate(BaseModel):
    source_node_id: str
    target_node_id: str
    kind: str = Field(min_length=1, max_length=48)
    properties: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "api"


class EdgeRead(ORMModel):
    id: str
    project_id: str
    source_node_id: str
    target_node_id: str
    kind: str
    properties: dict[str, Any]
    created_by: str
    created_at: datetime


class GraphSnapshot(BaseModel):
    nodes: list[NodeRead]
    edges: list[EdgeRead]


class PrioritySignals(BaseModel):
    goal_relevance: Literal["low", "medium", "high"] = "medium"
    information_gain: Literal["low", "medium", "high"] = "medium"
    novelty: Literal["low", "medium", "high"] = "high"
    confidence: Literal["low", "medium", "high"] = "medium"
    expected_cost: Literal["low", "medium", "high"] = "medium"


class IntentCreate(BaseModel):
    description: str = Field(min_length=3, max_length=4000)
    source_node_ids: list[str] = Field(default_factory=list)
    signals: PrioritySignals = Field(default_factory=PrioritySignals)
    creator: str = "api"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentRead(ORMModel):
    id: str
    project_id: str
    description: str
    status: str
    priority: float
    creator: str
    worker_id: str | None
    lease_until: datetime | None
    heartbeat_at: datetime | None
    result_node_id: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None


class WorkerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    driver: str = "mock"
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerRead(ORMModel):
    id: str
    project_id: str
    name: str
    driver: str
    model: str | None
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime
    last_seen_at: datetime


class ClaimRequest(BaseModel):
    worker_id: str


class CompleteRequest(BaseModel):
    worker_id: str
    status: Literal["completed", "failed"] = "completed"
    result_node_id: str | None = None
    error: str | None = None


class EventRead(ORMModel):
    id: str
    project_id: str
    kind: str
    payload: dict[str, Any]
    created_at: datetime


class ArtifactRead(ORMModel):
    id: str
    project_id: str
    kind: str
    path: str
    sha256: str
    size: int
    summary: str
    provenance: dict[str, Any]
    created_at: datetime


class RunResult(BaseModel):
    worker_id: str
    intent_id: str
    worker_run_id: str
    status: str
    created_nodes: int
    created_intents: int


class OrchestrationRead(BaseModel):
    status: str
    created_intents: int
    closed_intents: int
    deprioritized_intents: int
    token_input: int
    token_output: int
    retry_count: int
    error: str | None = None
