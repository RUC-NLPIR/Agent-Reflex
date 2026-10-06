"""Mine EnvScaler RSD skills from RL pos/neg rollouts.

Follows Agent-Reflex RSD (contrast success/failure → Trigger–Diagnosis–Recovery)
and the original environment_skills.jsonl schema: one bad_pattern + one skill
per environment, written in the same Chinese style.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from recipe.envscaler_openai_fc.skill_context import openai_tool_names

TOOL_NAME_RE = re.compile(r'"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_]{1,80})"')
ERROR_RE = re.compile(
    r"(VALIDATION_ERROR|NOT_FOUND|FORBIDDEN|UNAUTHORIZED|RATE_LIMITED|"
    r"CONFLICT|INVALID_ARGUMENT|TOOL_ERROR|KeyError|TypeError|ValueError|"
    r"missing required|invalid argument|does not exist|not found|failed)",
    re.I,
)
INTRO_RE = re.compile(
    r"## Brief Introduction\s*(.+?)(?:\n\s*## |\n\s*user\n)",
    re.S,
)

QUERY_PREFIXES = ("get_", "list_", "search_", "check_", "find_", "lookup_", "read_")
WRITE_PREFIXES = (
    "create_",
    "update_",
    "add_",
    "set_",
    "cancel_",
    "delete_",
    "remove_",
    "send_",
    "book_",
    "enroll_",
    "reserve_",
    "mark_",
    "halt_",
    "invalidate_",
)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def intro_key(text: str) -> str:
    match = INTRO_RE.search(text or "")
    blob = match.group(1) if match else (text or "")
    blob = re.sub(r"\s+", " ", blob).strip()
    return blob[:180]


def split_tools(names: list[str]) -> tuple[list[str], list[str]]:
    query, write, other = [], [], []
    for name in names:
        lower = name.lower()
        if lower.startswith(QUERY_PREFIXES):
            query.append(name)
        elif lower.startswith(WRITE_PREFIXES):
            write.append(name)
        else:
            other.append(name)
    return query or other[:4], write or other[4:8]


def build_env_index(train_path: Path) -> dict[str, dict]:
    index = {}
    with train_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            extra = row.get("extra_info") or {}
            environment = extra.get("environment") or {}
            class_name = environment.get("class_name")
            if not class_name or class_name in index:
                continue
            system = ""
            for message in row.get("prompt") or []:
                if message.get("role") == "system":
                    system = message.get("content") or ""
                    break
            tools = environment.get("tools") or []
            index[class_name] = {
                "env_id": extra.get("env_id") or environment.get("env_id"),
                "class_name": class_name,
                "tools": tools,
                "tool_names": openai_tool_names(tools),
                "intro_key": intro_key(system),
                "description": (
                    environment.get("environment_introduction")
                    or intro_key(system)
                    or class_name
                ),
            }
    by_intro = {item["intro_key"]: item for item in index.values() if item["intro_key"]}
    return {"by_class": index, "by_intro": by_intro}


def mine_rollouts(paths: list[Path], env_index: dict, max_step: int) -> dict[str, dict]:
    stats = {
        class_name: {
            "n": 0,
            "pos": 0,
            "neg": 0,
            "scores": [],
            "pos_tools": Counter(),
            "neg_tools": Counter(),
            "errors": Counter(),
        }
        for class_name in env_index["by_class"]
    }
    for root in paths:
        files = sorted(Path(root).glob("*.jsonl"), key=lambda path: int(path.stem))
        for path in files:
            step = int(path.stem)
            keep_text = step <= max_step
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    key = intro_key(row.get("input") or "")
                    env = env_index["by_intro"].get(key)
                    if env is None:
                        continue
                    bucket = stats[env["class_name"]]
                    score = float(row.get("score") or 0.0)
                    bucket["n"] += 1
                    bucket["scores"].append(score)
                    if score <= 1e-6:
                        bucket["neg"] += 1
                        kind = "neg"
                    elif score >= 0.25:
                        bucket["pos"] += 1
                        kind = "pos"
                    else:
                        kind = "mid"
                    if not keep_text:
                        continue
                    output = row.get("output") or ""
                    if not output:
                        continue
                    names = [
                        name
                        for name in TOOL_NAME_RE.findall(output)
                        if name in set(env["tool_names"]) or name.startswith(QUERY_PREFIXES + WRITE_PREFIXES)
                    ]
                    if kind == "pos":
                        bucket["pos_tools"].update(names[:12])
                    elif kind == "neg":
                        bucket["neg_tools"].update(names[:12])
                        bucket["errors"].update(token.lower() for token in ERROR_RE.findall(output))
    return stats


def compose_bad_pattern(env: dict, stat: dict) -> str:
    env_id = env["env_id"]
    query, write = split_tools(env["tool_names"])
    errors = [name for name, _ in stat["errors"].most_common(3)]
    error_text = "、".join(errors) if errors else "空回执或校验失败"
    return (
        f"在环境 {env_id}中，未先用 {', '.join(query[:3]) or '查询工具'} 核对对象标识和当前状态"
        f"就调用 {', '.join(write[:3]) or '写工具'}，随后把{error_text}或默认值当成已完成事实，"
        f"导致相似记录被混入、目标记录被漏掉，最终把不完整结果报告给用户。"
    )


def compose_skill(env: dict, stat: dict) -> str:
    env_id = env["env_id"]
    query, write = split_tools(env["tool_names"])
    pos_tools = [name for name, _ in stat["pos_tools"].most_common(4)]
    recovery_query = pos_tools[:2] or query[:2]
    recovery_write = [name for name in (pos_tools[2:] + write) if name not in recovery_query][:2] or write[:2]
    return (
        f"使用环境 {env_id}时，先用 {', '.join(recovery_query) or '查询工具'} 锁定资源、对象和筛选边界，"
        f"再按回执逐步调用 {', '.join(recovery_write) or '写工具'}；"
        f"每步核验对象标识、状态字段、数量和关联记录，不要把摘要、默认值或请求受理当作事实；"
        f"遇到校验失败、对象不存在或空结果时先修正标识与必填参数再重试，不要跳过失败回执继续推断。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--rollout-dir", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", default="")
    parser.add_argument("--max-step-with-text", type=int, default=50)
    args = parser.parse_args()

    env_index = build_env_index(Path(args.train))
    stats = mine_rollouts([Path(path) for path in args.rollout_dir], env_index, args.max_step_with_text)

    catalog = []
    report_rows = []
    for class_name, env in sorted(env_index["by_class"].items()):
        stat = stats[class_name]
        scores = stat["scores"]
        mean = sum(scores) / len(scores) if scores else 0.0
        record = {
            "env_id": env["env_id"],
            "env_name": class_name,
            "environment_description": env["description"],
            "tools": env["tools"],
            "bad_patterns": [compose_bad_pattern(env, stat)],
            "skills": [compose_skill(env, stat)],
            "source": {
                "rollout_n": stat["n"],
                "pos": stat["pos"],
                "neg": stat["neg"],
                "mean_score": round(mean, 4),
                "top_errors": stat["errors"].most_common(5),
                "top_pos_tools": stat["pos_tools"].most_common(8),
            },
        }
        catalog.append(record)
        report_rows.append(
            {
                "class_name": class_name,
                "env_id": env["env_id"],
                "rollout_n": stat["n"],
                "pos": stat["pos"],
                "neg": stat["neg"],
                "mean_score": round(mean, 4),
            }
        )

    write_jsonl(catalog, Path(args.output))
    summary = {
        "environments": len(catalog),
        "matched_rollouts": sum(item["rollout_n"] for item in report_rows),
        "unmatched_envs": [item["class_name"] for item in report_rows if item["rollout_n"] == 0],
        "rows": report_rows,
    }
    print(json.dumps({k: summary[k] for k in ("environments", "matched_rollouts", "unmatched_envs")}, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
