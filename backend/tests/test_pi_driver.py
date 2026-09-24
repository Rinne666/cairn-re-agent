import asyncio
import json
import sys
from pathlib import Path

import pytest

from app.drivers.pi import SYSTEM_PROMPT, PiDriver
from app.worker_protocol import AgentRun, WorkerContext


def context():
    return WorkerContext(goal="goal", intent="inspect function", available_tools=[])


def valid_worker_output():
    return {
        "observations": [],
        "evidence": [],
        "hypotheses": [],
        "facts": [],
        "relations": [],
        "artifacts": [],
        "suggested_intents": [],
        "status": "completed",
        "summary": "No new claims are justified.",
    }


def event_stream(text: str, input_tokens=12, output_tokens=5) -> bytes:
    events = [
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "usage": {"input": input_tokens, "output": output_tokens},
            },
        },
        {"type": "agent_end"},
    ]
    return "\n".join(json.dumps(item) for item in events).encode()


class FakeProcess:
    def __init__(self, returncode, stdout, stderr=b""):
        self.returncode = returncode
        self.stdout = FakePipe(stdout)
        self.stderr = FakePipe(stderr)
        self.killed = False

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


class FakePipe:
    def __init__(self, payload):
        self.lines = payload.splitlines(keepends=True)
        self.payload = payload
        self.read_complete = False

    async def readline(self):
        return self.lines.pop(0) if self.lines else b""

    async def read(self):
        self.read_complete = True
        return self.payload


@pytest.mark.asyncio
async def test_pi_driver_parses_final_json_event_and_usage(monkeypatch):
    expected = valid_worker_output()
    process = FakeProcess(0, event_stream(json.dumps(expected)))

    async def spawn(*argv, **kwargs):
        assert "--mode" in argv and "json" in argv
        assert "--no-tools" in argv and "--no-session" in argv
        assert "--no-extensions" in argv and "--no-skills" in argv
        assert "--no-prompt-templates" in argv and "--no-context-files" in argv
        return process

    monkeypatch.setattr("app.drivers.pi.asyncio.create_subprocess_exec", spawn)
    run = await PiDriver("node C:/pi/cli.js").run_agent(context())
    assert isinstance(run, AgentRun)
    assert run.output.model_dump() == expected
    assert (run.token_input, run.token_output) == (12, 5)
    assert run.schema_valid is True
    assert process.killed is False


@pytest.mark.asyncio
async def test_invalid_schema_retries_exactly_once_then_preserves_diagnostics(monkeypatch):
    invalid = event_stream("```json\n{}\n```", input_tokens=3, output_tokens=4)
    process_outputs = [
        FakeProcess(0, invalid, b"first stderr\n"),
        FakeProcess(0, invalid, b"last stderr\n"),
    ]
    prompts = []

    async def spawn(*argv, **kwargs):
        prompts.append(argv[-1])
        return process_outputs.pop(0)

    monkeypatch.setattr("app.drivers.pi.asyncio.create_subprocess_exec", spawn)
    run = await PiDriver("node C:/pi/cli.js").run_agent(context())
    assert run.output is None
    assert run.retry_count == 1
    assert run.schema_valid is False
    assert run.schema_invalid_attempts == 2
    assert run.stdout
    assert run.stderr == "first stderr\nlast stderr\n"
    assert run.token_input == 6 and run.token_output == 8
    assert len(prompts) == 2
    assert "schema" in prompts[1].lower() or "json" in prompts[1].lower()


@pytest.mark.asyncio
async def test_invalid_json_is_not_repaired_and_process_error_is_not_retried(monkeypatch):
    calls = 0

    async def spawn(*argv, **kwargs):
        nonlocal calls
        calls += 1
        return FakeProcess(1, b"plain text", b"provider unavailable")

    monkeypatch.setattr("app.drivers.pi.asyncio.create_subprocess_exec", spawn)
    run = await PiDriver("node C:/pi/cli.js").run_agent(context())
    assert calls == 1
    assert run.retry_count == 0
    assert run.output is None
    assert run.stderr == "provider unavailable"


@pytest.mark.asyncio
async def test_well_formed_failed_status_is_valid_and_not_retried(monkeypatch):
    payload = valid_worker_output()
    payload["status"] = "failed"
    calls = 0

    async def spawn(*argv, **kwargs):
        nonlocal calls
        calls += 1
        return FakeProcess(0, event_stream(json.dumps(payload)))

    monkeypatch.setattr("app.drivers.pi.asyncio.create_subprocess_exec", spawn)
    run = await PiDriver("node C:/pi/cli.js").run_agent(context())
    assert calls == 1
    assert run.output.status == "failed"
    assert run.schema_valid is True


@pytest.mark.asyncio
async def test_fact_without_verified_by_evidence_gets_one_validation_retry(monkeypatch):
    unsupported = valid_worker_output()
    unsupported["facts"] = [
        {
            "kind": "Fact",
            "label": "unsupported claim",
            "entity_key": "fact:unsupported",
            "properties": {},
            "confidence": 0.9,
        }
    ]
    processes = [
        FakeProcess(0, event_stream(json.dumps(unsupported))),
        FakeProcess(0, event_stream(json.dumps(valid_worker_output()))),
    ]
    prompts = []

    async def spawn(*argv, **kwargs):
        prompts.append(argv[-1])
        return processes.pop(0)

    monkeypatch.setattr("app.drivers.pi.asyncio.create_subprocess_exec", spawn)
    run = await PiDriver("node C:/pi/cli.js").run_agent(context())

    assert run.schema_valid is True
    assert run.retry_count == 1
    assert run.schema_invalid_attempts == 1
    assert run.output.facts == []
    assert "verified_by" in prompts[1]


@pytest.mark.asyncio
async def test_pi_api_error_is_process_failure_not_schema_retry(monkeypatch):
    calls = 0
    process = None
    error_event = json.dumps(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
                "errorMessage": "429 quota exceeded",
                "usage": {"input": 0, "output": 0},
            },
        }
    ).encode()

    async def spawn(*argv, **kwargs):
        nonlocal calls, process
        calls += 1
        process = FakeProcess(0, error_event)
        return process

    monkeypatch.setattr("app.drivers.pi.asyncio.create_subprocess_exec", spawn)
    run = await PiDriver("node C:/pi/cli.js").run_agent(context())
    assert calls == 1
    assert run.output is None
    assert run.retry_count == 0
    assert run.schema_invalid_attempts == 0
    assert "429 quota exceeded" in run.error
    assert process.killed


@pytest.mark.asyncio
async def test_pi_driver_reads_jsonl_events_larger_than_default_stream_limit():
    source = "import json; print(json.dumps({'type': 'agent_end', 'payload': 'x' * 100_000}))"

    returncode, stdout, stderr, interrupted = await PiDriver("unused")._invoke(
        [sys.executable, "-c", source]
    )

    assert returncode == 0
    assert len(stdout) > 100_000
    assert stderr == ""
    assert interrupted is False


@pytest.mark.asyncio
async def test_cancellation_kills_pi_child_process(monkeypatch):
    started = asyncio.Event()

    class BlockingPipe:
        async def readline(self):
            await asyncio.Event().wait()

        async def read(self):
            return b""

    class BlockingProcess:
        returncode = None
        stdout = BlockingPipe()
        stderr = BlockingPipe()
        killed = False

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            return self.returncode

    process = BlockingProcess()

    async def spawn(*argv, **kwargs):
        started.set()
        return process

    monkeypatch.setattr("app.drivers.pi.asyncio.create_subprocess_exec", spawn)
    task = asyncio.create_task(PiDriver("node C:/pi/cli.js").run_agent(context()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed


def test_windows_npm_command_shim_resolves_node_entrypoint_with_space_paths(tmp_path):
    npm_dir = tmp_path / "Node Tools" / "npm"
    npm_dir.mkdir(parents=True)
    shim = npm_dir / "pi.cmd"
    shim.write_text('"%dp0%\\node_modules\\pi\\dist\\cli.js"', encoding="utf-8")
    cli = npm_dir / "node_modules" / "pi" / "dist" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")

    args = PiDriver.resolve_command(
        "pi", platform="win32", which=lambda name: str(shim) if name == "pi" else "node"
    )
    assert args[0] == "node"
    assert args[1] == str(cli)


def test_windows_powershell_shim_resolves_node_entrypoint_with_space_paths(tmp_path):
    npm_dir = tmp_path / "Node Tools" / "npm"
    npm_dir.mkdir(parents=True)
    shim = npm_dir / "pi.ps1"
    shim.write_text(
        '& "$basedir/node.exe" "$basedir/node_modules/@vendor/pi/dist/cli.js"',
        encoding="utf-8",
    )
    cli = npm_dir / "node_modules" / "@vendor" / "pi" / "dist" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("", encoding="utf-8")

    args = PiDriver.resolve_command(
        "pi", platform="win32", which=lambda name: str(shim) if name == "pi" else "node.exe"
    )
    assert args == ["node.exe", str(cli)]


def test_explicit_node_entrypoint_command_preserves_argument_boundaries():
    args = PiDriver.resolve_command('node "C:/Program Files/Pi/cli.js"', platform="win32")
    assert len(args) == 2
    assert args[1] == "C:/Program Files/Pi/cli.js"


def test_pi_prompt_enforces_evidence_separation_and_explicit_graph_relations():
    prompt = PiDriver._prompt(context())
    for required in (
        "Observation != Evidence",
        "Evidence != Hypothesis",
        "Hypothesis != Fact",
        "verified_by",
        "available_tools is empty",
        "Do not use Markdown",
        "derived_from",
        "contradicts",
        "at most three",
        "Insufficient evidence is not a worker execution failure",
        "status is completed when the context was analyzed, even if no conclusion is supported",
        "Use failed only if you cannot analyze the request or produce a WorkerOutput",
        "Do not return only reasoning or an empty text message",
    ):
        assert required.lower() in prompt.lower() or required.lower() in SYSTEM_PROMPT.lower()


def test_unresolvable_windows_shim_fails_clearly(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: "not a node shim")
    with pytest.raises(RuntimeError, match="resolve.*Pi|Node entrypoint"):
        PiDriver.resolve_command("pi", platform="win32", which=lambda _: "C:/npm/pi.cmd")
