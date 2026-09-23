from typing import Any, Protocol


class ReverseToolProvider(Protocol):
    """Stable boundary implemented by a Ghidra, GDB, Frida or test provider."""

    @property
    def capabilities(self) -> set[str]: ...

    async def invoke(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
