import asyncio
import json
import shlex

from app.worker_protocol import WorkerContext, WorkerOutput


class PiDriver:
    """Pi adapter using one JSON request/response over stdio.

    The command is configured externally so the graph engine has no dependency on
    Pi's installation layout. The child must read one JSON object from stdin and
    write a WorkerOutput JSON object to stdout.
    """

    def __init__(self, command: str) -> None:
        self.command = command.strip()

    async def run_agent(self, context: WorkerContext) -> WorkerOutput:
        if not self.command:
            raise RuntimeError("Pi driver selected but CAIRN_PI_COMMAND is not configured")
        argv = shlex.split(self.command, posix=False)
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(json.dumps(context.model_dump()).encode("utf-8"))
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"Pi process failed ({process.returncode}): {detail}")
        try:
            return WorkerOutput.model_validate_json(stdout)
        except Exception as exc:
            raise RuntimeError("Pi process returned invalid WorkerOutput JSON") from exc
