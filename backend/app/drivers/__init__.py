from app.config import get_settings
from app.drivers.mock import MockDriver
from app.drivers.pi import PiDriver


def get_driver(name: str):
    if name == "mock":
        return MockDriver()
    if name == "pi":
        return PiDriver(get_settings().pi_command)
    raise ValueError(f"unknown worker driver: {name}")


def get_orchestrator_driver():
    if not get_settings().pi_command:
        raise RuntimeError("Graph Orchestrator requires CAIRN_PI_COMMAND")
    return PiDriver(get_settings().pi_command)


__all__ = ["MockDriver", "PiDriver", "get_driver", "get_orchestrator_driver"]
