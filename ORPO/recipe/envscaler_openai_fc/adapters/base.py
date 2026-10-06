"""Minimal adapter contract used by the native-FC agent loop."""

from abc import ABC, abstractmethod


class ToolExecutionError(RuntimeError):
    """A whitelisted environment method raised while executing a tool call."""

    def __init__(self, tool_name: str, original: BaseException):
        self.tool_name = tool_name
        self.original = original
        super().__init__(f"Error executing '{tool_name}': {original}")


class EnvAdapter(ABC):
    """One isolated, stateful environment instance for one rollout."""

    @abstractmethod
    async def build_env(self) -> None:
        """Create the live environment and apply its initial state."""

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """Return OpenAI function schemas for this episode."""

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict) -> str:
        """Execute one tool call and return a textual observation."""

    @abstractmethod
    def snapshot_state(self) -> dict:
        """Return a deep copy of the current environment state."""

    @abstractmethod
    async def score(self) -> tuple[float, dict]:
        """Score the final state and return ``(reward, details)``."""

    async def close(self) -> None:
        """Release resources. EnvScaler's in-process environment is a no-op."""
