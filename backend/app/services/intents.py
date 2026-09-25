import hashlib
import re
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import GraphNode, Intent, IntentSource, Worker, utcnow
from app.schemas import EdgeCreate, IntentCreate, NodeCreate
from app.services.events import emit_event
from app.services.graph import upsert_edge, upsert_node

SIGNAL_VALUES = {"low": 0.35, "medium": 0.65, "high": 1.0}


def normalize_intent(description: str) -> str:
    return re.sub(r"\s+", " ", description.strip().lower())


def intent_key(description: str, source_node_ids: list[str]) -> str:
    material = f"{normalize_intent(description)}|{'|'.join(sorted(set(source_node_ids)))}"
    return hashlib.sha256(material.encode()).hexdigest()


def score_intent(data: IntentCreate) -> float:
    signals = data.signals
    numerator = (
        SIGNAL_VALUES[signals.goal_relevance]
        * SIGNAL_VALUES[signals.information_gain]
        * SIGNAL_VALUES[signals.novelty]
        * SIGNAL_VALUES[signals.confidence]
    )
    cost = SIGNAL_VALUES[signals.expected_cost]
    return round(min(1.0, numerator / max(cost, 0.1)), 4)


async def create_intent(
    session: AsyncSession,
    project_id: str,
    data: IntentCreate,
    *,
    create_source_edges: bool = True,
) -> Intent:
    dedupe = intent_key(data.description, data.source_node_ids)
    existing = await session.scalar(
        select(Intent).where(Intent.project_id == project_id, Intent.dedupe_key == dedupe)
    )
    if existing:
        return existing
    intent = Intent(
        project_id=project_id,
        description=data.description,
        priority=score_intent(data),
        creator=data.creator,
        dedupe_key=dedupe,
        metadata_json={"signals": data.signals.model_dump(), **data.metadata},
    )
    session.add(intent)
    await session.flush()
    intent_node = await upsert_node(
        session,
        project_id,
        NodeCreate(
            graph_type="exploration",
            kind="Intent",
            label=data.description[:255],
            entity_key=f"intent:{intent.id}",
            properties={"intent_id": intent.id, "priority": intent.priority, "status": "open"},
            confidence=SIGNAL_VALUES[data.signals.confidence],
            status="open",
            created_by=data.creator,
        ),
    )
    intent.metadata_json = {**intent.metadata_json, "exploration_node_id": intent_node.id}
    for node_id in dict.fromkeys(data.source_node_ids):
        session.add(IntentSource(intent_id=intent.id, node_id=node_id))
        if create_source_edges:
            await upsert_edge(
                session,
                project_id,
                EdgeCreate(
                    source_node_id=node_id,
                    target_node_id=intent_node.id,
                    kind="motivates",
                    created_by=data.creator,
                ),
            )
    await emit_event(
        session,
        project_id,
        "intent.created",
        {"intent_id": intent.id, "priority": intent.priority},
    )
    return intent


async def claim_next_intent(
    session: AsyncSession, project_id: str, worker_id: str
) -> Intent | None:
    now = utcnow()
    query = (
        select(Intent)
        .where(
            Intent.project_id == project_id,
            or_(
                Intent.status == "open",
                (Intent.status.in_(["claimed", "running"])) & (Intent.lease_until < now),
            ),
        )
        .order_by(Intent.priority.desc(), Intent.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    intent = await session.scalar(query)
    if intent is None:
        return None
    worker = await session.get(Worker, worker_id)
    if worker is None or worker.project_id != project_id:
        raise ValueError("worker does not belong to project")
    intent.status = "claimed"
    intent.worker_id = worker_id
    intent.heartbeat_at = now
    intent.lease_until = now + timedelta(seconds=get_settings().intent_lease_seconds)
    worker.status = "busy"
    worker.last_seen_at = now
    intent_node = await session.get(GraphNode, intent.metadata_json.get("exploration_node_id"))
    if intent_node:
        intent_node.status = "claimed"
        intent_node.properties = {
            **intent_node.properties,
            "status": "claimed",
            "worker_id": worker_id,
        }
    await emit_event(
        session,
        project_id,
        "intent.claimed",
        {
            "intent_id": intent.id,
            "worker_id": worker_id,
            "lease_until": intent.lease_until.isoformat(),
        },
    )
    return intent


async def heartbeat(session: AsyncSession, intent: Intent, worker_id: str) -> Intent:
    if intent.worker_id != worker_id or intent.status not in {"claimed", "running"}:
        raise ValueError("intent is not leased by this worker")
    now = utcnow()
    intent.heartbeat_at = now
    intent.lease_until = now + timedelta(seconds=get_settings().intent_lease_seconds)
    return intent
