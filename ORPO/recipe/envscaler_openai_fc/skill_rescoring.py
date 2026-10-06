"""Rebuild a skill-conditioned teacher batch for ORPO reflection OPD.

Ordinary rollout tokens stay unchanged. Only the initial system prompt is
augmented with the offline RSD skill; the already sampled response suffix is
concatenated and re-scored.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from recipe.envscaler_openai_fc.skill_context import (
    extra_tools,
    insert_skill_into_messages,
    skill_text_from_extra,
)
from verl import DataProto
from verl.utils.model import compute_position_id_with_mask


def _as_mapping(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return _as_mapping(value.item())
        return {}
    if hasattr(value, "item"):
        try:
            return _as_mapping(value.item())
        except Exception:
            return {}
    return {}


def _as_messages(value: Any) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _row_messages(extra: dict, raw_prompt: Any) -> list[dict]:
    extra = _as_mapping(extra)
    messages = _as_messages(extra.get("raw_messages"))
    if messages:
        return messages
    return _as_messages(raw_prompt)


def _chat_template_kwargs(config) -> dict:
    raw = {}
    if config is not None:
        raw = config.data.get("apply_chat_template_kwargs", {}) or {}
        try:
            from omegaconf import OmegaConf

            if OmegaConf.is_config(raw):
                raw = OmegaConf.to_container(raw, resolve=True) or {}
        except Exception:
            raw = dict(raw) if raw else {}
    raw = dict(raw)
    raw.pop("tools", None)
    return raw


def build_skill_teacher_batch(
    batch: DataProto,
    tokenizer,
    config=None,
) -> tuple[DataProto, torch.Tensor]:
    """Return (teacher_batch, opd_step_mask).

    ``teacher_batch`` has the same response tokens as ``batch`` but a
    skill-conditioned prompt prefix. Samples without a skill reuse the
    original prompt and are masked out of OPD.
    """
    extras = batch.non_tensor_batch.get("extra_info")
    raw_prompts = batch.non_tensor_batch.get("raw_prompt")
    responses = batch.batch["responses"]
    if "prompts" in batch.batch.keys():
        orig_prompts = batch.batch["prompts"]
    else:
        orig_prompts = batch.batch["input_ids"][:, : batch.batch["input_ids"].size(1) - responses.size(1)]
    # Same padded width as ordinary rollout prompts (data.max_prompt_length=8192).
    prompt_len = orig_prompts.size(1)
    pad_id = tokenizer.pad_token_id
    if pad_id is None:
        pad_id = 0
    kwargs = _chat_template_kwargs(config)

    new_prompts = []
    opd_flags = []
    batch_size = responses.size(0)
    for index in range(batch_size):
        extra = extras[index] if extras is not None else {}
        extra = _as_mapping(extra)
        skill = skill_text_from_extra(extra)
        raw_prompt = raw_prompts[index] if raw_prompts is not None else None
        messages = _row_messages(extra, raw_prompt)
        if not skill or not messages:
            new_prompts.append(orig_prompts[index].detach().clone())
            opd_flags.append(0.0)
            continue
        skill_messages = insert_skill_into_messages(messages, skill)
        tools = extra_tools(extra)
        rendered = tokenizer.apply_chat_template(
            skill_messages,
            tools=tools or None,
            add_generation_prompt=True,
            tokenize=False,
            **kwargs,
        )
        token_ids = tokenizer.encode(rendered, add_special_tokens=False)
        if len(token_ids) > prompt_len:
            token_ids = token_ids[-prompt_len:]
        if len(token_ids) < prompt_len:
            token_ids = [pad_id] * (prompt_len - len(token_ids)) + token_ids
        new_prompts.append(
            torch.tensor(token_ids, dtype=orig_prompts.dtype, device=orig_prompts.device)
        )
        opd_flags.append(1.0)

    prompt_tensor = torch.stack(new_prompts, dim=0)
    input_ids = torch.cat([prompt_tensor, responses], dim=1)
    prompt_mask = (prompt_tensor != pad_id).to(dtype=batch.batch["attention_mask"].dtype)
    response_attn = batch.batch["attention_mask"][:, -responses.size(1) :]
    attention_mask = torch.cat([prompt_mask, response_attn], dim=1)
    position_ids = compute_position_id_with_mask(attention_mask)
    opd_step_mask = torch.tensor(opd_flags, dtype=torch.float32, device=responses.device)

    teacher_batch = DataProto.from_dict(
        tensors={
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "position_ids": position_ids,
            "responses": responses,
        },
        meta_info=dict(batch.meta_info),
    )
    return teacher_batch, opd_step_mask
