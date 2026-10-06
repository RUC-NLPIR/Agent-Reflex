import asyncio

from recipe.envscaler_openai_fc.adapters.base import EnvAdapter, ToolExecutionError
from recipe.envscaler_openai_fc.tool_execution import execute_calls_in_order


class RecordingAdapter(EnvAdapter):
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    async def build_env(self):
        return None

    def get_tools(self):
        return []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == self.fail_on:
            raise ToolExecutionError(name, RuntimeError("failed"))
        return f"result-{name}"

    def snapshot_state(self):
        return {}

    async def score(self):
        return 0.0, {}


def call(index):
    return {"name": f"tool_{index}", "arguments": {"index": index}}


def test_calls_are_serial_and_capped_at_five():
    async def run():
        adapter = RecordingAdapter()
        result = await execute_calls_in_order(
            adapter, [call(i) for i in range(7)], turn_index=3, max_calls=5
        )
        assert adapter.calls == [(f"tool_{i}", {"index": i}) for i in range(5)]
        assert result.executed == 5
        assert result.dropped == 2
        assert [item["tool_call_id"] for item in result.tool_messages] == [
            f"call_003_{i:02d}" for i in range(5)
        ]
        assert result.assistant_message["tool_calls"][0]["id"] == "call_003_00"

    asyncio.run(run())


def test_invalid_json_is_recoverable_and_environment_exception_aborts_order():
    async def run():
        adapter = RecordingAdapter(fail_on="tool_2")
        calls = [call(0), {"name": "bad", "arguments": "[1]"}, call(2), call(3)]
        result = await execute_calls_in_order(adapter, calls, turn_index=0, max_calls=5)
        assert adapter.calls == [("tool_0", {"index": 0}), ("tool_2", {"index": 2})]
        assert result.malformed == 1
        assert result.abort is True
        assert result.executed == 3
        assert len(result.tool_messages) == 3

    asyncio.run(run())
