from sqlalchemy import select

from app.models import GraphEdge, Intent
from app.services.context import assemble_context
from app.services.runner import seed_demo


async def test_context_contains_goal_intent_local_nodes_and_relation_endpoints(session):
    project = await seed_demo(session)
    intent = await session.scalar(select(Intent).where(Intent.project_id == project.id))
    context = await assemble_context(session, intent)

    assert context.goal == project.goal
    assert context.intent == intent.description
    assert context.program_nodes
    assert context.facts
    assert context.available_tools == []
    assert context.budget == project.config["budget"]
    assert context.relations
    assert all(
        set(relation) >= {"source_entity_key", "target_entity_key", "kind", "properties"}
        for relation in context.relations
    )

    context_pairs = {
        (relation["source_entity_key"], relation["target_entity_key"], relation["kind"])
        for relation in context.relations
    }
    categories = (
        context.facts,
        context.program_nodes,
        context.evidence,
        context.hypotheses,
        context.other_nodes,
    )
    packed_nodes = [node for nodes in categories for node in nodes]
    entity_keys = {node["entity_key"] for node in packed_nodes}
    assert context_pairs
    assert entity_keys

    node_ids = {node["id"] for node in packed_nodes}
    node_keys = {node["id"]: node["entity_key"] for node in packed_nodes}
    expected_edges = list(
        (
            await session.scalars(
                select(GraphEdge).where(
                    GraphEdge.project_id == project.id,
                    GraphEdge.source_node_id.in_(node_ids),
                    GraphEdge.target_node_id.in_(node_ids),
                )
            )
        ).all()
    )
    expected_pairs = {
        (node_keys[edge.source_node_id], node_keys[edge.target_node_id], edge.kind)
        for edge in expected_edges
    }
    assert context_pairs == expected_pairs
    assert all(
        key in entity_keys
        for relation in context.relations
        for key in (relation["source_entity_key"], relation["target_entity_key"])
    )
