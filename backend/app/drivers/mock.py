import hashlib

from app.worker_protocol import (
    AgentRun,
    SuggestedIntent,
    WorkerContext,
    WorkerFinding,
    WorkerOutput,
    WorkerRelation,
)


class MockDriver:
    """Deterministic driver used to exercise the orchestration path without an LLM."""

    async def run_agent(self, context: WorkerContext) -> AgentRun:
        fingerprint = hashlib.sha1(context.intent.encode()).hexdigest()[:8]
        observation_key = f"observation:mock:{fingerprint}"
        evidence_key = f"evidence:mock:{fingerprint}"
        return AgentRun(
            output=WorkerOutput(
                observations=[
                    WorkerFinding(
                        kind="Observation",
                        label="Worker inspected the selected program neighborhood",
                        entity_key=observation_key,
                        properties={"intent": context.intent, "driver": "mock"},
                        confidence=1.0,
                    )
                ],
                evidence=[
                    WorkerFinding(
                        kind="Evidence",
                        label="Deterministic worker result",
                        entity_key=evidence_key,
                        confidence=0.82,
                        properties={"provenance": {"tool": "mock", "operation": "run_agent"}},
                    )
                ],
                hypotheses=[
                    WorkerFinding(
                        kind="Hypothesis",
                        label="Validation logic is reachable from the input path",
                        entity_key="hypothesis:validation-path",
                        confidence=0.64,
                        properties={"state": "unverified"},
                    )
                ],
                facts=[],
                relations=[
                    WorkerRelation(
                        source_entity_key=evidence_key,
                        target_entity_key="hypothesis:validation-path",
                        kind="supports",
                        properties={},
                    )
                ],
                artifacts=[],
                suggested_intents=[
                    SuggestedIntent(
                        description=(
                            "Inspect callers and data references for the candidate "
                            "validation function."
                        ),
                        source_entity_keys=[evidence_key],
                        goal_relevance="high",
                        information_gain="high",
                        confidence="medium",
                        expected_cost="medium",
                    )
                ],
                status="completed",
                summary="Mock driver produced evidence and a follow-up exploration intent.",
            ),
            duration_seconds=0.0,
            schema_valid=True,
        )
