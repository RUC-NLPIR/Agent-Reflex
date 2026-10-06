"""
BFCL Agent Loop for verl multi-turn tool-use RL validation.

注册名：bfcl_agent（与 bfcl_val.jsonl 的 agent_name 字段对应）。

设计：
  - 驱动移植后的 BfclEnv（去 gem 依赖，普通类）的状态机。
  - BfclEnv.step(action_text) 内部已处理：
      * entry_completed（问题耗尽 + "Task Completed"）→ 算二值 reward，terminated=True
      * turn_completed（"Task Completed" 但还有问题）→ pop 下一个 question 作为 user observation
      * 否则 → 解析 <tool_call> → call_tool → 返回 tool 结果 observation
  - AgentLoop 负责：generate → decode → env.step → 把 observation token 化拼进序列。
  - Tool 格式用 Qwen3 native FC（apply_chat_template(tools=) + role:tool），对齐 SFT 模型分布。
    BfclEnv 的 XMLParser(fields=["think","tool_call"]) 正好解析 FC 的 Hermes <tool_call> 输出。
  - response_mask：LLM 生成 token=1，env observation token=0。
  - reward：env 终止时 BfclReward.unified_reward_func 给二值分数，塞 reward_score。
"""
import json
import logging
import os
import traceback
from copy import deepcopy
from typing import Any
from uuid import uuid4

from verl.experimental.agent_loop.agent_loop import AgentLoopBase, AgentLoopOutput, register
from verl.experimental.agent_loop.bfcl_env.env import BfclEnv
from verl.utils.profiler import simple_timer

logger = logging.getLogger(__file__)
logger.setLevel(os.getenv("VERL_LOGGING_LEVEL", "WARN"))


@register("bfcl_agent")
class BfclAgentLoop(AgentLoopBase):
    """Agent loop that drives a BfclEnv episode for BFCL validation."""

    @classmethod
    def init_class(cls, config, tokenizer, processor, **kwargs):
        if cls._class_initialized:
            return
        cls._class_initialized = True

        cls.tokenizer = tokenizer
        cls.processor = processor

        mt_cfg = config.actor_rollout_ref.rollout.get("multi_turn", {})
        cls.max_turns = mt_cfg.get("max_assistant_turns", 40)
        cls.max_response_length = config.actor_rollout_ref.rollout.response_length

        cls.apply_chat_template_kwargs = dict(config.data.get("apply_chat_template_kwargs", {}))

        # Base prefix that apply_chat_template always prepends (for stripping when
        # tokenising only observation messages).
        cls._base_prefix_ids: list[int] = tokenizer.apply_chat_template(
            [{}],
            add_generation_prompt=False,
            tokenize=True,
            **{k: v for k, v in cls.apply_chat_template_kwargs.items() if k != "enable_thinking"},
        )

        logger.info(
            f"BfclAgentLoop initialised | max_turns={cls.max_turns} "
            f"max_response_length={cls.max_response_length} "
            f"apply_chat_template_kwargs={cls.apply_chat_template_kwargs}"
        )

    async def run(self, sampling_params: dict[str, Any], **kwargs) -> AgentLoopOutput:
        """
        Run one BFCL episode.

        kwargs:
            raw_prompt : list[dict]  — [system_msg, user_msg(=questions[0])]
            extra_info : dict        — id, questions, answers, initial_config,
                                       involved_classes, tools
        """
        metrics: dict[str, float] = {}
        request_id = uuid4().hex

        raw_prompt: list[dict] = list(kwargs["raw_prompt"])
        extra_info: dict = kwargs.get("extra_info", {})

        task_id: str = extra_info.get("id", "unknown")
        episode_tools: list[dict] = extra_info.get("tools", [])
        if isinstance(episode_tools, str):
            episode_tools = json.loads(episode_tools)

        # ── 1. 实例化 BfclEnv 并 reset 到指定 task ─────────────────────────
        env: BfclEnv
        observation_first: dict
        try:
            env = BfclEnv(mode="multi_turn_base")
            # 用 task_id（如 "multi_turn_base_0"）作为 task_index 精确定位
            observation_first, _info = env.reset(seed=0, task_index=task_id)
        except Exception:
            logger.error(f"[{task_id}] BfclEnv init/reset failed:\n{traceback.format_exc()}")
            return self._empty_output(raw_prompt, episode_tools, reward=0.0, metrics=metrics)

        # ── 2. 构建初始 prompt（FC 注入 tools）──────────────────────────────
        # raw_prompt 已是 [system, user(questions[0])]，直接用；tools 由 FC 注入。
        messages: list[dict] = deepcopy(raw_prompt)
        prompt_ids: list[int] = await self._apply_template(messages, episode_tools, add_gen=True)
        all_ids: list[int] = list(prompt_ids)

        response_ids: list[int] = []
        response_mask: list[int] = []
        num_turns: int = 1

        reward: float = 0.0
        terminated: bool = False

        # ── 3. 多轮循环 ─────────────────────────────────────────────────────
        for turn_idx in range(self.max_turns):
            # 3a. LLM 生成
            with simple_timer("generate_sequences", metrics):
                gen_output = await self.server_manager.generate(
                    request_id=request_id,
                    prompt_ids=all_ids,
                    sampling_params=sampling_params,
                )
            gen_ids: list[int] = gen_output.token_ids
            all_ids = all_ids + gen_ids
            response_ids = response_ids + gen_ids
            response_mask = response_mask + [1] * len(gen_ids)
            num_turns += 1

            # 3b. 长度上限检查
            if len(response_ids) >= self.max_response_length:
                logger.debug(f"[{task_id}] turn {turn_idx}: max response length reached")
                break

            # 3c. decode 并喂给 env.step（env 内部处理状态机）
            gen_text: str = await self.loop.run_in_executor(
                None, lambda gids=gen_ids: self.tokenizer.decode(gids, skip_special_tokens=False)
            )

            with simple_timer("env_step", metrics):
                observation, step_reward, terminated, truncated, info = env.step(action=gen_text)

            # 3d. episode 终止 → 取 reward，跳出
            #     用 env 返回的二值 final_score（全对才给分否则 0），对齐 ROLL/论文口径
            #     （ROLL bfcl_env.get_reward() 取 unified_reward_func 第一返回值=final_score）。
            if terminated:
                reward = float(step_reward)
                break

            # 3e. 未终止 → 把 observation 作为下一个 user/tool turn 拼进去
            obs_messages = self._observation_to_messages(observation)
            messages.extend(obs_messages)
            obs_ids = await self._tokenize_messages(obs_messages)

            if len(obs_ids) == 0:
                logger.warning(f"[{task_id}] turn {turn_idx}: empty observation tokens, stopping")
                break
            if len(response_ids) + len(obs_ids) >= self.max_response_length:
                logger.debug(f"[{task_id}] turn {turn_idx}: max length after observation")
                break

            all_ids = all_ids + obs_ids
            response_ids = response_ids + obs_ids
            response_mask = response_mask + [0] * len(obs_ids)  # env observation → mask 0

            if truncated:
                logger.debug(f"[{task_id}] turn {turn_idx}: env truncated")
                break

        # ── 4. 若循环耗尽仍未 terminated，补算一次 reward（用当前 env 状态）──
        #     同样取二值 final_score（get_reward 第一返回值），对齐 ROLL/论文口径
        if not terminated:
            try:
                _final, reward_info = env.get_reward()
                reward = float(_final)
            except Exception:
                reward = 0.0

        logger.info(
            f"[{task_id}] bfcl episode done | turns={num_turns} "
            f"response_len={len(response_ids)} reward={reward:.4f}"
        )

        # ── 5. 截断到 max_response_length ───────────────────────────────────
        response_ids = response_ids[: self.max_response_length]
        response_mask = response_mask[: self.max_response_length]

        return AgentLoopOutput(
            prompt_ids=list(prompt_ids),
            response_ids=response_ids,
            response_mask=response_mask,
            response_logprobs=None,
            multi_modal_data={},
            reward_score=reward,
            num_turns=num_turns,
            metrics=metrics,
            extra_fields={
                "bfcl_score": reward,
                "task_id": task_id,
            },
        )

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _observation_to_messages(observation: dict) -> list[dict]:
        """
        把 BfclEnv.step 返回的 observation 转成 chat messages。

        observation 格式（来自 env.py step）：
          - {"type": "user", "content": ...}  → 下一轮子问题 / "Trajectory finished."
          - {"type": "tool", "content": ...}  → 工具执行结果

        FC 格式下工具结果用 role:tool；user 类型用 role:user。
        """
        obs_type = observation.get("type", "user")
        content = observation.get("content", "")
        if obs_type == "tool":
            return [{"role": "tool", "tool_call_id": "0", "content": str(content)}]
        else:
            return [{"role": "user", "content": str(content)}]

    async def _apply_template(
        self, messages: list[dict], tools: list[dict], add_gen: bool = True
    ) -> list[int]:
        kwargs = dict(self.apply_chat_template_kwargs)

        def _encode():
            return self.tokenizer.apply_chat_template(
                messages,
                tools=tools if tools else None,
                add_generation_prompt=add_gen,
                tokenize=True,
                **kwargs,
            )

        return await self.loop.run_in_executor(None, _encode)

    async def _tokenize_messages(self, messages: list[dict]) -> list[int]:
        """
        Tokenise observation messages and return ONLY the new token IDs
        (stripping the base prefix that apply_chat_template always prepends).
        Uses the same fixed-prefix stripping strategy as VeRL's generic tool loop.
        """

        def _encode():
            ids = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
            )
            return ids[len(self._base_prefix_ids):]

        return await self.loop.run_in_executor(None, _encode)

    async def _empty_output(
        self, raw_prompt: list[dict], episode_tools: list[dict], reward: float, metrics: dict
    ) -> AgentLoopOutput:
        prompt_ids = await self._apply_template(raw_prompt, episode_tools, add_gen=True)
        return AgentLoopOutput(
            prompt_ids=list(prompt_ids),
            response_ids=[self.tokenizer.eos_token_id or 0],
            response_mask=[1],
            multi_modal_data={},
            reward_score=reward,
            num_turns=1,
            metrics=metrics,
            extra_fields={"bfcl_score": reward},
        )
