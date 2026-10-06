"""Write EnvScaler RSD jsonl in the original skills schema and attach to train."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from recipe.envscaler_openai_fc.data.envscaler_rsd_skills import ENV_RSD


def main() -> None:
    train = REPO / "data/generated/train_envscaler_2550.jsonl"
    out_catalog = REPO / "data/generated/environment_skills_envscaler.jsonl"
    out_train = REPO / "data/generated/train_envscaler_2550_with_skills.jsonl"

    envs: dict[str, dict] = {}
    with train.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            extra = row.get("extra_info") or {}
            environment = extra.get("environment") or {}
            class_name = environment.get("class_name")
            env_id = extra.get("env_id") or environment.get("env_id")
            if not class_name or not env_id:
                continue
            envs.setdefault(
                env_id,
                {
                    "env_id": env_id,
                    "class_name": class_name,
                    "tools": environment.get("tools") or [],
                    "description": environment.get("environment_introduction") or class_name,
                },
            )

    extra = sorted(set(ENV_RSD) - {item["class_name"] for item in envs.values()})
    if extra:
        raise SystemExit(f"skill map has unknown classes: {extra}")

    catalog = []
    for env_id, meta in sorted(envs.items()):
        if meta["class_name"] not in ENV_RSD:
            continue
        bad, skill = ENV_RSD[meta["class_name"]]
        catalog.append(
            {
                "env_id": env_id,
                "env_name": meta["class_name"],
                "environment_description": meta["description"],
                "tools": meta["tools"],
                "bad_patterns": [bad.format(env_id=env_id)],
                "skills": [skill.format(env_id=env_id)],
            }
        )
    skill_texts = [row["skills"][0] for row in catalog]
    if len(set(skill_texts)) != len(skill_texts):
        raise SystemExit("duplicate skill text")
    with out_catalog.open("w", encoding="utf-8") as handle:
        for row in catalog:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    from recipe.envscaler_openai_fc.data.attach_environment_skills import (
        apply_assignment,
        choose_skill,
        env_key,
        precompute_skill,
    )

    precomputed = [precompute_skill(row) for row in catalog]
    attached = []
    methods = Counter()
    with train.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            skill, score, method = choose_skill(row.get("extra_info") or {}, precomputed)
            methods[method] += 1
            attached.append(apply_assignment(row, skill, score, method))
    with out_train.open("w", encoding="utf-8") as handle:
        for row in attached:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    names = Counter(row["extra_info"]["rsd_skill_meta"]["skill_env_name"] for row in attached)
    print(
        json.dumps(
            {
                "catalog": len(catalog),
                "train": len(attached),
                "methods": dict(methods),
                "unique_skills": len(names),
                "missing_text": sum(1 for row in attached if not row["extra_info"]["rsd_skill"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("sample", attached[0]["extra_info"]["environment"]["class_name"])
    print(attached[0]["extra_info"]["rsd_skill"][:180])


if __name__ == "__main__":
    main()
