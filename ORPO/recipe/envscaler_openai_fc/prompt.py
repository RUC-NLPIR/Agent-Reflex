"""Prompt construction for non-conversational EnvScaler tasks.

Tool schemas deliberately do not appear in the system text. The tokenizer's
native ``apply_chat_template(..., tools=...)`` path injects them later.
"""

NON_CONVERSATION_SYSTEM_PROMPT = (
    "You are a helpful assistant. Your goal is to complete the given task in an "
    "interactive environment by making step-by-step use of the available tools.\n"
    "- At each step, use the available tool results to decide the next action. "
    "Provide complete, valid arguments for every tool call.\n"
    "- Prefer querying the environment before making changes when the current "
    "state is uncertain.\n"
    "- You may issue multiple tool calls in one assistant turn when they are "
    "independent. The environment executes at most five calls in model-output "
    "order.\n"
    "- When the task is complete, respond with a concise final answer without "
    "making another tool call."
)


def build_environment_introduction(env_metadata: dict) -> str:
    description = env_metadata.get("environment_introduction", "") or ""
    constraints = env_metadata.get("constraints_rules") or []
    if not description and not constraints:
        return ""

    rules = "\n".join(f"- {rule}" for rule in constraints if isinstance(rule, str))
    return (
        "# Environment Information\n\n"
        f"## Brief Introduction\n{description}\n\n"
        f"## Rules and Constraints\n{rules}"
    ).rstrip()


def build_prompt(task: str, env_metadata: dict) -> list[dict]:
    system = NON_CONVERSATION_SYSTEM_PROMPT
    introduction = build_environment_introduction(env_metadata)
    if introduction:
        system = f"{system}\n\n{introduction}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]
