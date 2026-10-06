"""Pure-Python sequential execution policy for one assistant tool-call turn."""

import json
from dataclasses import dataclass
from typing import Any

from .adapters.base import EnvAdapter, ToolExecutionError
from .tool_fault_injection import canonical_json


@dataclass
class ToolTurnResult:
    assistant_message: dict
    tool_messages: list[dict]
    executed: int
    dropped: int
    malformed: int
    injected: int
    abort: bool


def stable_call_id(turn_index: int, call_index: int) -> str:
    return f"call_{turn_index:03d}_{call_index:02d}"


def _call_parts(call: Any) -> tuple[str, str | dict]:
    if hasattr(call, "name") and hasattr(call, "arguments"):
        return call.name, call.arguments
    function = call.get("function", call)
    return str(function.get("name", "")), function.get("arguments", "{}")


async def execute_calls_in_order(
    adapter: EnvAdapter,
    calls: list[Any],
    *,
    turn_index: int,
    max_calls: int,
    assistant_content: str = "",
    injector: Any | None = None,
) -> ToolTurnResult:
    """Execute at most ``max_calls`` serially and construct one OpenAI FC turn.

    When ``injector`` is given, every attempted tool call draws once from it in
    the order the model emitted the calls. A drawn fault short-circuits the real
    tool, so the environment state is left untouched, and the simulated error is
    handed back as an ordinary tool message the model can react to.
    """
    selected = calls[:max_calls]
    normalized_calls = []
    tool_messages = []
    malformed = 0
    injected = 0
    abort = False

    for call_index, call in enumerate(selected):
        call_id = stable_call_id(turn_index, call_index)
        name, raw_arguments = _call_parts(call)
        if isinstance(raw_arguments, str):
            arguments_text = raw_arguments
        else:
            arguments_text = json.dumps(raw_arguments, ensure_ascii=False)
        normalized_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments_text},
            }
        )

        try:
            arguments = json.loads(arguments_text)
            if not isinstance(arguments, dict):
                raise TypeError("arguments must decode to a JSON object")
        except (json.JSONDecodeError, TypeError) as exc:
            malformed += 1
            content = f"Error: invalid tool arguments for '{name}': {exc}"
        else:
            fault_payload = None
            if injector is not None:
                _, fault_payload = injector.prepare_call(
                    tool_call_id=call_id,
                    tool_name=name,
                    assistant_turn=turn_index,
                )
            if fault_payload is not None:
                # Simulated failure: the real tool is never called, and abort
                # stays false so the model can retry or replan.
                injected += 1
                content = canonical_json(fault_payload)
            else:
                try:
                    content = await adapter.call_tool(name, arguments)
                except ToolExecutionError as exc:
                    content = str(exc)
                    abort = True

        tool_messages.append(
            {"role": "tool", "tool_call_id": call_id, "content": str(content)}
        )
        if abort:
            break

    if abort:
        normalized_calls = normalized_calls[: len(tool_messages)]
    assistant_message = {
        "role": "assistant",
        "content": assistant_content or "",
        "tool_calls": normalized_calls,
    }
    return ToolTurnResult(
        assistant_message=assistant_message,
        tool_messages=tool_messages,
        executed=len(tool_messages),
        dropped=max(0, len(calls) - max_calls),
        malformed=malformed,
        injected=injected,
        abort=abort,
    )
