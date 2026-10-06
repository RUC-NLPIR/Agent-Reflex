"""Native OpenAI function-calling AgentLoop for official EnvScaler RL tasks."""

import json
import logging
import os
from copy import deepcopy
from typing import Any
from uuid import uuid4

from verl.experimental.agent_loop.agent_loop import (
    AgentLoopBase,
    AgentLoopOutput,
    register,
)
from verl.experimental.agent_loop.tool_parser import ToolParser
from verl.utils.profiler import simple_timer

from .adapters.envscaler import EnvScalerAdapter
from .tool_execution import execute_calls_in_order, stable_call_id
from .tool_fault_injection import DEFAULT_FAULT_RATE, FaultInjector

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("VERL_LOGGING_LEVEL", "WARN"))


@register("envscaler_openai_fc")
class EnvScalerOpenAIFCAgentLoop(AgentLoopBase):
    """Run one stateful EnvScaler episode using message-level OpenAI FC semantics."""

    @classmethod
    def init_class(cls, config, tokenizer, processor, **kwargs):
        if cls._class_initialized:
            return
        cls._class_initialized = True
        cls.tokenizer = tokenizer
        cls.processor = processor
        if processor is not None:
            raise ValueError(
                "EnvScalerOpenAIFCAgentLoop currently supports text-only models"
            )

        rollout = config.actor_rollout_ref.rollout
        multi_turn = rollout.get("multi_turn", {})
        cls.max_assistant_turns = multi_turn.get("max_assistant_turns") or 40
        cls.max_parallel_calls = multi_turn.get("max_parallel_calls", 5)
        if cls.max_parallel_calls != 5:
            logger.warning(
                "max_parallel_calls=%s; this recipe is designed and tested with 5",
                cls.max_parallel_calls,
            )
        cls.max_tool_response_length = multi_turn.get("max_tool_response_length", 1024)
        cls.tool_response_truncate_side = multi_turn.get(
            "tool_response_truncate_side", "middle"
        )
        cls.max_tokens_per_step = multi_turn.get("max_tokens_per_step")
        cls.response_length = rollout.response_length
        cls.apply_chat_template_kwargs = dict(
            config.data.get("apply_chat_template_kwargs", {})
        )
        cls.tool_parser = ToolParser.get_tool_parser(
            multi_turn.get("format", "hermes"), tokenizer
        )
        cls._base_prefix_ids = tokenizer.apply_chat_template(
            [{}],
            add_generation_prompt=False,
            tokenize=True,
            **{
                k: v
                for k, v in cls.apply_chat_template_kwargs.items()
                if k != "enable_thinking"
            },
        )

        # Tool-fault injection for the perturbed rollouts of each group.
        # An absent or unreadable catalog falls back to uniform family weights
        # rather than silently disabling injection.
        cls.fault_rate = float(multi_turn.get("noise_rate") or DEFAULT_FAULT_RATE)
        cls.fault_model_id = str(config.trainer.get("experiment_name", "policy"))
        catalog_path = multi_turn.get("noise_catalog_path") or ""
        cls.fault_catalog = {}
        if catalog_path:
            try:
                with open(catalog_path, encoding="utf-8") as stream:
                    cls.fault_catalog = json.load(stream)
            except (OSError, json.JSONDecodeError):
                logger.warning(
                    "noise_catalog_path=%s unreadable; using uniform fault weights",
                    catalog_path,
                )

    async def run(self, sampling_params: dict[str, Any], **kwargs) -> AgentLoopOutput:
        metrics: dict[str, float] = {}
        request_id = uuid4().hex
        raw_prompt = deepcopy(kwargs["raw_prompt"])
        extra = deepcopy(kwargs.get("extra_info") or {})
        task_id = str(extra.get("task_id", "unknown"))
        environment = extra.get("environment") or {}
        verifier = extra.get("verifier") or {}
        adapter = EnvScalerAdapter(environment, verifier)

        # The trainer marks a fraction (noise_rollout_fraction) of every rollout
        # group as perturbed. The seed includes the global step so a task
        # recurring across updates does not replay an identical fault pattern.
        injector = None
        if int(extra.get("noise_rollout", 0)):
            injector = FaultInjector.for_trajectory(
                self.fault_catalog,
                run_fingerprint=f"{self.fault_model_id}\0step{int(extra.get('global_step', 0))}",
                task_id=task_id,
                model_id=self.fault_model_id,
                rollout_index=int(extra.get("rollout_index", 0)),
                rate=self.fault_rate,
            )
        injected_calls = 0

        tools = adapter.get_tools()
        openai_trace = deepcopy(raw_prompt)
        response_ids: list[int] = []
        response_mask: list[int] = []
        assistant_turns = 0
        tool_results = 0
        dropped_calls = 0
        malformed_calls = 0
        aborted = False
        reward = 0.0
        score_details = {"passed": 0, "total": len(verifier.get("checklist") or [])}

        try:
            await adapter.build_env()
            prompt_ids = await self._apply_template(
                raw_prompt, tools, add_generation_prompt=True
            )
            all_ids = list(prompt_ids)

            for turn_index in range(self.max_assistant_turns):
                remaining = self.response_length - len(response_ids)
                if remaining <= 0:
                    break
                step_params = dict(sampling_params)
                if self.max_tokens_per_step is not None:
                    step_params["max_new_tokens"] = min(
                        int(self.max_tokens_per_step), remaining
                    )

                with simple_timer("generate_sequences", metrics):
                    output = await self.server_manager.generate(
                        request_id=request_id,
                        prompt_ids=all_ids,
                        sampling_params=step_params,
                    )
                generated = list(output.token_ids)
                if not generated:
                    break
                generated = generated[:remaining]
                all_ids.extend(generated)
                response_ids.extend(generated)
                response_mask.extend([1] * len(generated))
                assistant_turns += 1

                content, calls = await self.tool_parser.extract_tool_calls(generated)
                decoded = await self.loop.run_in_executor(
                    None,
                    lambda token_ids=generated: self.tokenizer.decode(
                        token_ids, skip_special_tokens=False
                    ),
                )
                if not calls:
                    if "<tool_call>" in decoded or "</tool_call>" in decoded:
                        invalid_id = stable_call_id(turn_index, 0)
                        openai_trace.append(
                            {
                                "role": "assistant",
                                "content": content or "",
                                "tool_calls": [
                                    {
                                        "id": invalid_id,
                                        "type": "function",
                                        "function": {
                                            "name": "__invalid_tool_call__",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            }
                        )
                        error_message = {
                            "role": "tool",
                            "tool_call_id": invalid_id,
                            "content": "Error: malformed tool call; emit valid JSON and try again.",
                        }
                        openai_trace.append(error_message)
                        tool_results += 1
                        malformed_calls += 1
                        observation_ids = await self._tokenize_tool_messages(
                            [error_message]
                        )
                    else:
                        openai_trace.append({"role": "assistant", "content": decoded})
                        break
                else:
                    with simple_timer("tool_calls", metrics):
                        turn = await execute_calls_in_order(
                            adapter,
                            calls,
                            turn_index=turn_index,
                            max_calls=self.max_parallel_calls,
                            assistant_content=content,
                            injector=injector,
                        )
                    openai_trace.append(turn.assistant_message)
                    openai_trace.extend(turn.tool_messages)
                    tool_results += turn.executed
                    dropped_calls += turn.dropped
                    malformed_calls += turn.malformed
                    injected_calls += turn.injected
                    aborted = turn.abort
                    observation_ids = await self._tokenize_tool_messages(
                        turn.tool_messages
                    )

                if aborted:
                    break
                remaining = self.response_length - len(response_ids)
                if not observation_ids or len(observation_ids) > remaining:
                    break
                all_ids.extend(observation_ids)
                response_ids.extend(observation_ids)
                response_mask.extend([0] * len(observation_ids))

            if not aborted:
                reward, score_details = await adapter.score()
        except Exception:
            logger.exception("[%s] EnvScaler episode failed", task_id)
            aborted = True
            if "prompt_ids" not in locals():
                prompt_ids = await self._apply_template(
                    raw_prompt, tools, add_generation_prompt=True
                )
        finally:
            await adapter.close()

        if not response_ids:
            response_ids = [self.tokenizer.eos_token_id or 0]
            response_mask = [1]
        return AgentLoopOutput(
            prompt_ids=list(prompt_ids),
            response_ids=response_ids[: self.response_length],
            response_mask=response_mask[: self.response_length],
            response_logprobs=None,
            multi_modal_data={},
            reward_score=0.0 if aborted else float(reward),
            num_turns=1 + assistant_turns + tool_results,
            metrics=metrics,
            extra_fields={
                "task_id": task_id,
                "envscaler_score": 0.0 if aborted else float(reward),
                "checks_passed": int(score_details.get("passed", 0)),
                "checks_total": int(score_details.get("total", 0)),
                "tool_results": tool_results,
                "dropped_tool_calls": dropped_calls,
                "malformed_tool_calls": malformed_calls,
                "aborted": int(aborted),
                "injected_tool_calls": injected_calls,
                "fault_injection_json": (
                    json.dumps(injector.audit_record(), ensure_ascii=False)
                    if injector is not None
                    else ""
                ),
                "openai_trace_json": json.dumps(openai_trace, ensure_ascii=False),
            },
        )

    async def _apply_template(
        self, messages: list[dict], tools: list[dict], add_generation_prompt: bool
    ) -> list[int]:
        kwargs = dict(self.apply_chat_template_kwargs)
        kwargs.pop("tools", None)
        return await self.loop.run_in_executor(
            None,
            lambda: self.tokenizer.apply_chat_template(
                messages,
                tools=tools,
                add_generation_prompt=add_generation_prompt,
                tokenize=True,
                **kwargs,
            ),
        )

    async def _tokenize_tool_messages(self, messages: list[dict]) -> list[int]:
        truncated = []
        for message in messages:
            message = dict(message)
            message["content"] = await self._truncate_tool_text(
                str(message.get("content", ""))
            )
            truncated.append(message)

        kwargs = dict(self.apply_chat_template_kwargs)
        kwargs.pop("tools", None)
        ids = await self.loop.run_in_executor(
            None,
            lambda: self.tokenizer.apply_chat_template(
                truncated,
                add_generation_prompt=True,
                tokenize=True,
                **kwargs,
            ),
        )
        return list(ids[len(self._base_prefix_ids) :])

    async def _truncate_tool_text(self, text: str) -> str:
        max_length = int(self.max_tool_response_length)
        ids = await self.loop.run_in_executor(
            None, lambda: self.tokenizer.encode(text, add_special_tokens=False)
        )
        if len(ids) <= max_length:
            return text
        side = self.tool_response_truncate_side
        marker = self.tokenizer.encode(
            "\n... tool result truncated ...\n", add_special_tokens=False
        )
        budget = max(0, max_length - len(marker))
        if side == "left":
            kept = marker + ids[-budget:]
        elif side == "right":
            kept = ids[:budget] + marker
        elif side == "middle":
            left = budget // 2
            kept = ids[:left] + marker + ids[-(budget - left) :]
        else:
            raise ValueError(f"unknown tool_response_truncate_side={side!r}")
        return await self.loop.run_in_executor(
            None, lambda: self.tokenizer.decode(kept)
        )
