import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Intent
from app.verify_pi_worker import _configured_provider_model, run_experiment, summarize_metrics
from app.worker_protocol import AgentRun, WorkerOutput


def test_metric_denominators_reconcile_retries_and_actual_runs():
    report = summarize_metrics(
        [
            {
                "status": "completed",
                "schema_valid": True,
                "retry_count": 1,
                "schema_invalid_attempts": 1,
                "output_suggested_intents_count": 2,
                "duplicate_intent_count": 1,
                "output_facts_count": 2,
                "unsupported_fact_count": 1,
                "unresolved_relation_count": 0,
                "token_input": 60,
                "token_output": 10,
                "duration_seconds": 4.0,
            },
            {
                "status": "failed",
                "schema_valid": False,
                "retry_count": 0,
                "schema_invalid_attempts": 0,
                "output_suggested_intents_count": 2,
                "duplicate_intent_count": 0,
                "output_facts_count": 0,
                "unsupported_fact_count": 0,
                "unresolved_relation_count": 0,
                "token_input": 0,
                "token_output": 0,
                "duration_seconds": 2.0,
            },
        ],
        requested_runs=20,
    )
    assert report["persisted_runs"] == 2
    assert report["completed_valid_runs"] == 1
    assert report["success_rate"] == 1 / 20
    assert report["pi_invocations"] == 3
    assert report["invalid_schema_rate"] == 1 / 3
    assert report["duplicate_intent_rate"] == 1 / 4
    assert report["unsupported_fact_rate"] == 1 / 2
    assert report["unresolved_relations"] == 0
    assert report["token_input_total"] == 60
    assert report["token_input_mean_per_run"] == 30
    assert report["token_output_total"] == 10
    assert report["token_output_mean_per_run"] == 5
    assert report["duration_total_seconds"] == 6
    assert report["duration_mean_seconds"] == 3


def test_provider_and_model_are_explicit_for_reproducibility():
    assert _configured_provider_model('pi --provider openai --model "gpt-4.1-mini"') == (
        "openai",
        "gpt-4.1-mini",
    )
    assert _configured_provider_model("pi --model anthropic/claude-haiku-4-5") == (
        "anthropic",
        "claude-haiku-4-5",
    )
    with pytest.raises(RuntimeError, match="explicit --provider and --model"):
        _configured_provider_model("pi")


@pytest.mark.asyncio
async def test_verifier_runs_exact_sequential_count_and_creates_only_needed_continuations(
    monkeypatch,
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def create_test_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.verify_pi_worker.SessionLocal", factory)
    monkeypatch.setattr("app.verify_pi_worker.create_schema", create_test_schema)
    monkeypatch.setattr(
        "app.verify_pi_worker.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "pi_command": "pi --provider openai --model gpt-4.1-mini",
                "database_url": "sqlite+aiosqlite:///:memory:",
            },
        )(),
    )
    monkeypatch.setattr("app.verify_pi_worker._pi_version", lambda _: "test-pi")
    concurrency = {"active": 0, "max_active": 0}
    contexts = []

    async def deterministic_real_boundary(context):
        concurrency["active"] += 1
        concurrency["max_active"] = max(concurrency["max_active"], concurrency["active"])
        contexts.append(context)
        assert context.available_tools == []
        assert context.goal.startswith("Find how the program validates")
        await asyncio.sleep(0)
        concurrency["active"] -= 1
        return AgentRun(
            output=WorkerOutput(
                observations=[],
                evidence=[],
                hypotheses=[],
                facts=[],
                relations=[],
                artifacts=[],
                suggested_intents=[],
                status="completed",
                summary="No additional claims are justified.",
            ),
            duration_seconds=0.01,
            schema_valid=True,
        )

    monkeypatch.setattr(
        "app.services.runner.get_driver",
        lambda _: type("Driver", (), {"run_agent": staticmethod(deterministic_real_boundary)})(),
    )
    try:
        report = await run_experiment(runs=3)
        assert report["passed"] is True
        assert len(report["worker_run_ids"]) == 3
        assert report["metrics"]["persisted_runs"] == 3
        assert report["metrics"]["success_rate"] == 1.0
        assert concurrency["max_active"] == 1
        assert len(contexts) == 3
        async with factory() as session:
            continuations = list(
                (
                    await session.scalars(
                        select(Intent).where(
                            Intent.creator == "pi-experiment",
                            Intent.description.like("Continue Pi closed-loop verification%"),
                        )
                    )
                ).all()
            )
            assert len(continuations) == 2
            assert len({item.dedupe_key for item in continuations}) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_verifier_stops_and_reports_first_unavailable_provider_failure(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def create_test_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.verify_pi_worker.SessionLocal", factory)
    monkeypatch.setattr("app.verify_pi_worker.create_schema", create_test_schema)
    monkeypatch.setattr(
        "app.verify_pi_worker.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "pi_command": "pi --provider openai --model gpt-4.1-mini",
                "database_url": "sqlite+aiosqlite:///:memory:",
            },
        )(),
    )
    monkeypatch.setattr("app.verify_pi_worker._pi_version", lambda _: "test-pi")
    calls = []

    async def unavailable(context):
        calls.append(context)
        return AgentRun(
            output=None,
            duration_seconds=0.2,
            schema_valid=False,
            error="Pi provider request failed: unavailable",
        )

    monkeypatch.setattr(
        "app.services.runner.get_driver",
        lambda _: type("Driver", (), {"run_agent": staticmethod(unavailable)})(),
    )
    try:
        report = await run_experiment(runs=20)
        assert report["passed"] is False
        assert report["fatal_error"] == "Pi provider request failed: unavailable"
        assert report["worker_run_ids"] and len(report["worker_run_ids"]) == 1
        assert len(calls) == 1
        assert report["metrics"]["success_rate"] == 0.0
    finally:
        await engine.dispose()
