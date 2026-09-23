import asyncio
import json
import shlex
from typing import Any

GHIDRA_CAPABILITIES = {
    "get_binary_info",
    "list_functions",
    "get_function",
    "decompile_function",
    "get_disassembly",
    "get_callers",
    "get_callees",
    "get_xrefs",
    "get_strings",
    "get_imports",
    "get_memory_map",
}


class StdioReverseToolProvider:
    """Tool bridge that keeps Ghidra/MCP process details out of the engine."""

    def __init__(self, command: str) -> None:
        self.command = command.strip()

    @property
    def capabilities(self) -> set[str]:
        return GHIDRA_CAPABILITIES.copy()

    async def invoke(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation not in GHIDRA_CAPABILITIES:
            raise ValueError(f"unsupported reverse operation: {operation}")
        if not self.command:
            raise RuntimeError("CAIRN_REVERSE_TOOL_COMMAND is not configured")
        process = await asyncio.create_subprocess_exec(
            *shlex.split(self.command, posix=False),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        request = {"operation": operation, "arguments": arguments}
        stdout, stderr = await process.communicate(json.dumps(request).encode())
        if process.returncode != 0:
            raise RuntimeError(stderr.decode(errors="replace")[-2000:])
        response = json.loads(stdout)
        if not isinstance(response, dict):
            raise RuntimeError("reverse tool provider returned a non-object response")
        return response
