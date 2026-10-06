import asyncio

import pytest

from recipe.envscaler_openai_fc.adapters.base import ToolExecutionError
from recipe.envscaler_openai_fc.adapters.envscaler import EnvScalerAdapter

ENV_SOURCE = """
class TinyEnv:
    def __init__(self, config=None):
        self.value = 0

    def set_value(self, value):
        self.value = value
        return {"value": self.value}

    def explode(self):
        raise RuntimeError("boom")
"""


def make_adapter() -> EnvScalerAdapter:
    return EnvScalerAdapter(
        environment={
            "class_name": "TinyEnv",
            "class_code": ENV_SOURCE,
            "initial_state": {"value": 1},
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "set_value",
                        "description": "set value",
                        "parameters": {
                            "type": "object",
                            "properties": {"value": {"type": "integer"}},
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "explode",
                        "description": "raise",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
            ],
        },
        verifier={
            "kind": "checklist_func",
            "checklist": [
                {
                    "check_item": "value changed",
                    "check_func": "def check_func(final_state):\n    return final_state['value'] == 7",
                }
            ],
        },
    )


def test_adapter_initial_state_tool_and_reward():
    async def run():
        adapter = make_adapter()
        await adapter.build_env()
        assert adapter.snapshot_state()["value"] == 1
        assert await adapter.call_tool("set_value", {"value": 7}) == "{'value': 7}"
        reward, details = await adapter.score()
        assert reward == 1.0
        assert details["passed"] == details["total"] == 1

    asyncio.run(run())


def test_unknown_tool_is_recoverable_but_method_exception_aborts():
    async def run():
        adapter = make_adapter()
        await adapter.build_env()
        assert "not exposed" in await adapter.call_tool("not_a_tool", {})
        with pytest.raises(ToolExecutionError, match="boom"):
            await adapter.call_tool("explode", {})

    asyncio.run(run())
