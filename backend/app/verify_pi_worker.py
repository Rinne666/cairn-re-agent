from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shlex
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db import SessionLocal, create_schema
from app.drivers.pi import SYSTEM_PROMPT, PiDriver
from app.models import GraphEdge, GraphNode, Intent, Worker, WorkerRun
from app.schemas import IntentCreate
from app.services.intents import create_intent
from app.services.runner import run_once, seed_demo
from app.worker_protocol import WorkerOutput


def summarize_metrics(rows: list[dict], requested_runs: int) -> dict:
    token_input = sum(int(row.get("token_input", 0)) for row in rows)
    token_output = sum(int(row.get("token_output", 0)) for row in rows)
    durations = [float(row.get("duration_seconds", 0.0)) for row in rows]
    invocation_count = sum(int(row.get("retry_count", 0)) + 1 for row in rows)
    invalid_schema_count = sum(int(row.get("schema_invalid_attempts", 0)) for row in rows)
    suggestion_count = sum(int(row.get("output_suggested_intents_count", 0)) for row in rows)
    duplicate_intent_count = sum(int(row.get("duplicate_intent_count", 0)) for row in rows)
    fact_count = sum(int(row.get("output_facts_count", 0)) for row in rows)
    unsupported_fact_count = sum(int(row.get("unsupported_fact_count", 0)) for row in rows)
    unresolved_relation_count = sum(int(row.get("unresolved_relation_count", 0)) for row in rows)
    completed = sum(
        row.get("status") == "completed" and row.get("schema_valid") is True for row in rows
    )
    return {
        "requested_runs": requested_runs,
        "persisted_runs": len(rows),
        "completed_valid_runs": completed,
        "success_rate": completed / requested_runs if requested_runs else 0.0,
        "pi_invocations": invocation_count,
        "schema_invalid_attempts": invalid_schema_count,
        "invalid_schema_rate": invalid_schema_count / invocation_count if invocation_count else 0.0,
        "suggested_intents": suggestion_count,
        "duplicate_intents": duplicate_intent_count,
        "duplicate_intent_rate": duplicate_intent_count / suggestion_count
        if suggestion_count
        else 0.0,
        "facts": fact_count,
        "unsupported_facts": unsupported_fact_count,
        "unsupported_fact_rate": unsupported_fact_count / fact_count if fact_count else 0.0,
        "unresolved_relations": unresolved_relation_count,
        "token_input_total": token_input,
        "token_input_mean_per_run": token_input / len(rows) if rows else 0.0,
        "token_output_total": token_output,
        "token_output_mean_per_run": token_output / len(rows) if rows else 0.0,
        "duration_total_seconds": sum(durations),
        "duration_mean_seconds": sum(durations) / len(durations) if durations else 0.0,
    }


def _configured_provider_model(command: str) -> tuple[str, str]:
    parts = shlex.split(command, posix=True)
    provider = model = None
    for index, part in enumerate(parts):
        if part == "--provider" and index + 1 < len(parts):
            provider = parts[index + 1]
        if part == "--model" and index + 1 < len(parts):
            model = parts[index + 1]
    if model and "/" in model:
        provider_from_model, model = model.split("/", 1)
        provider = provider or provider_from_model
    if not provider or not model:
        raise RuntimeError(
            "For reproducibility set CAIRN_PI_COMMAND with explicit --provider and --model"
        )
    return provider, model


def _pi_version(command: str) -> str:
    argv = PiDriver.resolve_command(command)
    completed = subprocess.run(
        [*argv, "--version"], capture_output=True, text=True, check=True, timeout=20
    )
    return completed.stdout.strip() or completed.stderr.strip()


def _database_path(database_url: str) -> str:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database:
        return str(Path(url.database).resolve())
    return f"{url.get_backend_name()} database (path not applicable)"


async def run_experiment(runs: int = 20) -> dict:
    settings = get_settings()
    command = settings.pi_command
    provider, model = _configured_provider_model(command)
    version = _pi_version(command)
    experiment_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat()
    prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    schema_json = json.dumps(
        WorkerOutput.model_json_schema(), sort_keys=True, separators=(",", ":")
    )
    schema_hash = hashlib.sha256(schema_json.encode("utf-8")).hexdigest()
    worker_run_ids: list[str] = []
    per_run: list[dict] = []
    fatal_error = None

    await create_schema()
    async with SessionLocal() as session:
        project = await seed_demo(session)
        project.config = {
            **project.config,
            "worker_experiment_id": experiment_id,
            "worker_experiment_runs": runs,
        }
        worker = await session.scalar(
            select(Worker).where(Worker.project_id == project.id).order_by(Worker.created_at)
        )
        if worker is None:
            raise RuntimeError("seed_demo did not create a worker")
        worker.name = f"pi-validation-{experiment_id[:8]}"
        worker.driver = "pi"
        worker.model = None
        worker.metadata_json = {**worker.metadata_json, "experiment_id": experiment_id}
        await session.commit()
        project_id = project.id
        budget = project.config.get("budget", {})

        for index in range(1, runs + 1):
            if index > 1:
                claimable_pi_intent = await session.scalar(
                    select(Intent.id)
                    .where(
                        Intent.project_id == project_id,
                        Intent.status == "open",
                        Intent.creator == f"worker:{worker.id}",
                    )
                    .limit(1)
                )
                if claimable_pi_intent is None:
                    await create_intent(
                        session,
                        project_id,
                        IntentCreate(
                            description=(
                                f"Continue Pi closed-loop verification {index:02d}: "
                                "analyze the supplied license-validation graph."
                            ),
                            creator="pi-experiment",
                            metadata={"experiment_id": experiment_id, "sequence": index},
                        ),
                    )
                    await session.commit()
            result = await run_once(session, project_id, worker.id)
            if result is None:
                fatal_error = f"No claimable intent for sequential run {index}"
                break
            run = await session.get(WorkerRun, result.worker_run_id)
            if run is None:
                fatal_error = f"WorkerRun {result.worker_run_id} was not persisted"
                break
            worker_run_ids.append(run.id)
            metric_keys = (
                "schema_valid",
                "retry_count",
                "schema_invalid_attempts",
                "duration_seconds",
                "output_observations_count",
                "output_evidence_count",
                "output_hypotheses_count",
                "output_facts_count",
                "output_relations_count",
                "output_suggested_intents_count",
                "output_artifacts_count",
                "duplicate_intent_count",
                "unsupported_fact_count",
                "unresolved_relation_count",
            )
            per_run.append(
                {
                    "worker_run_id": run.id,
                    "intent_id": run.intent_id,
                    "status": run.status,
                    "error": run.error,
                    **{key: run.output_summary.get(key, 0) for key in metric_keys},
                    "token_input": run.token_input,
                    "token_output": run.token_output,
                }
            )
            await session.commit()
            if (
                run.status == "failed"
                and run.error
                and (
                    "provider request failed" in run.error.lower()
                    or "could not run" in run.error.lower()
                )
            ):
                fatal_error = run.error
                break

        persisted_runs = (
            list(
                (
                    await session.scalars(select(WorkerRun).where(WorkerRun.id.in_(worker_run_ids)))
                ).all()
            )
            if worker_run_ids
            else []
        )
        duplicate_nodes = await session.scalar(
            select(func.count()).select_from(
                select(GraphNode.entity_key)
                .where(GraphNode.project_id == project_id)
                .group_by(GraphNode.entity_key)
                .having(func.count(GraphNode.id) > 1)
                .subquery()
            )
        )
        duplicate_edges = await session.scalar(
            select(func.count()).select_from(
                select(GraphEdge.source_node_id, GraphEdge.target_node_id, GraphEdge.kind)
                .where(GraphEdge.project_id == project_id)
                .group_by(GraphEdge.source_node_id, GraphEdge.target_node_id, GraphEdge.kind)
                .having(func.count(GraphEdge.id) > 1)
                .subquery()
            )
        )
        duplicate_intents = await session.scalar(
            select(func.count()).select_from(
                select(Intent.dedupe_key)
                .where(Intent.project_id == project_id)
                .group_by(Intent.dedupe_key)
                .having(func.count(Intent.id) > 1)
                .subquery()
            )
        )
        inconsistent_runs = []
        for run in persisted_runs:
            intent = await session.get(Intent, run.intent_id)
            output = run.output_summary.get("worker_output")
            if not intent or intent.status != run.status:
                inconsistent_runs.append(run.id)
            if output and output.get("status") != run.status:
                inconsistent_runs.append(run.id)
        worker = await session.get(Worker, worker.id)
        all_consistent = (
            not inconsistent_runs
            and worker.status == "idle"
            and worker.metadata_json.get("last_run_status")
            == (per_run[-1]["status"] if per_run else None)
        )

    finished_at = datetime.now(UTC).isoformat()
    metrics = summarize_metrics(per_run, runs)
    pass_experiment = (
        len(worker_run_ids) == runs
        and metrics["completed_valid_runs"] == runs
        and all_consistent
        and duplicate_nodes == 0
        and duplicate_edges == 0
        and duplicate_intents == 0
        and metrics["unsupported_facts"] == 0
        and metrics["unresolved_relations"] == 0
        and not fatal_error
    )
    return {
        "experiment_id": experiment_id,
        "project_id": project_id,
        "database_path": _database_path(settings.database_url),
        "pi_version": version,
        "provider": provider,
        "model": model,
        "budget": budget,
        "prompt_sha256": prompt_hash,
        "schema_sha256": schema_hash,
        "started_at": started_at,
        "finished_at": finished_at,
        "worker_run_ids": worker_run_ids,
        "metrics": metrics,
        "duplicate_graph_nodes": duplicate_nodes,
        "duplicate_graph_edges": duplicate_edges,
        "duplicate_intent_rows": duplicate_intents,
        "state_consistent": all_consistent,
        "fatal_error": fatal_error,
        "passed": pass_experiment,
        "per_run": per_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real sequential Pi Worker validation.")
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    report = asyncio.run(run_experiment(args.runs))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
