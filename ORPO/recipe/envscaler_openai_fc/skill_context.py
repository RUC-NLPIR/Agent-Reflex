"""Privileged skill context used only for ORPO reflection-OPD re-scoring.

Rollout never sees this block. Training inserts the offline RSD skill into the
ordinary history, then re-scores the already sampled action tokens.
"""

from __future__ import annotations

import copy
import re
from typing import Any

SKILL_BLOCK_TEMPLATE = (
    "\n\n# Reflection Skill (training-only privileged guidance)\n"
    "The following environment-specific recovery skill is available only during "
    "training. Follow it when deciding the next tool call or final answer.\n"
    "{skill}\n"
)


def skill_text_from_extra(extra: dict | None) -> str:
    if not isinstance(extra, dict):
        return ""
    skill = extra.get("rsd_skill") or extra.get("skill") or ""
    if isinstance(skill, list):
        skill = "\n".join(str(item).strip() for item in skill if str(item).strip())
    return str(skill).strip()


def insert_skill_into_messages(messages: list[dict], skill: str) -> list[dict]:
    """Deterministic H(h, κ): append the skill to the first system message."""
    if not skill:
        return copy.deepcopy(messages)
    updated = copy.deepcopy(messages)
    block = SKILL_BLOCK_TEMPLATE.format(skill=skill.strip())
    if updated and updated[0].get("role") == "system":
        content = updated[0].get("content") or ""
        if "# Reflection Skill" not in content:
            updated[0]["content"] = content + block
        return updated
    updated.insert(0, {"role": "system", "content": block.lstrip()})
    return updated


def camel_tokens(text: str) -> list[str]:
    parts = re.findall(r"[A-Za-z]+|[0-9]+|[\u4e00-\u9fff]+", text or "")
    tokens: list[str] = []
    for part in parts:
        split = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+|[\u4e00-\u9fff]+", part)
        tokens.extend(token.lower() for token in split if len(token) > 1)
    return tokens


def openai_tool_names(tools: list | None) -> list[str]:
    names = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if isinstance(function, dict) and function.get("name"):
            names.append(str(function["name"]))
        elif tool.get("name"):
            names.append(str(tool["name"]))
    return names


def extra_tools(extra: dict | None) -> list[Any]:
    if not isinstance(extra, dict):
        return []
    environment = extra.get("environment") or {}
    if isinstance(environment, dict) and environment.get("tools"):
        return environment["tools"]
    tools = extra.get("tools")
    return tools if isinstance(tools, list) else []
