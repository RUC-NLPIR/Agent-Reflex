#!/usr/bin/env python3
"""Clean / Tool / User / Avg table for one AgentNoiseBench run (paper Table: noise results).

Tool and User are pooled pass rates over their cells; Avg = (Tool + User) / 2.
Overall = mean of the tau2 and Vita Avg columns.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TOOLS = ["fault", "incomplete", "induce", "redundant", "wrong"]
USERS = {
    "tau2": ["ambiguity", "topic_shift", "conflict", "redundancy", "boundary", "cognition"],
    "vita": ["ambiguity", "topic_shift", "conflict", "redundancy", "boundary"],
}
DOMAINS = {"tau2": ["airline", "retail", "telecom"], "vita": ["delivery", "instore", "ota"]}


def load_cell(sim_dir: Path, prefix: str, tag: str, domain: str, tool: str, user: str):
    path = sim_dir / f"{prefix}-{domain}-{tool}-{user}-{tag}.json"
    if not path.exists():
        return 0.0, 0
    sims = json.loads(path.read_text()).get("simulations") or []
    rewards = {str(s.get("task_id")): float((s.get("reward_info") or {}).get("reward") or 0) for s in sims}
    return sum(rewards.values()), len(rewards)


def pooled(sim_dir, prefix, tag, domains, cells):
    p = n = 0
    for d in domains:
        for tool, user in cells:
            a, c = load_cell(sim_dir, prefix, tag, d, tool, user)
            p, n = p + a, n + c
    return (100.0 * p / n if n else None), n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench-root", type=Path, required=True)
    ap.add_argument("--tau2-data", type=Path, required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--run-tag", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    sim_dirs = {
        "tau2": args.tau2_data / "simulations",
        "vita": args.bench_root / "repo" / "vitabench" / "data" / "simulations",
    }
    table = {}
    for bench, sim_dir in sim_dirs.items():
        groups = {
            "clean": [("others", "original")],
            "tool": [(t, "original") for t in TOOLS],
            "user": [("others", u) for u in USERS[bench]],
        }
        row = {}
        for name, cells in groups.items():
            row[name], row[f"{name}_n"] = pooled(sim_dir, args.prefix, args.run_tag, DOMAINS[bench], cells)
        if row["tool"] is not None and row["user"] is not None:
            row["avg"] = (row["tool"] + row["user"]) / 2
        table[bench] = row

    avgs = [r["avg"] for r in table.values() if r.get("avg") is not None]
    table["overall"] = sum(avgs) / len(avgs) if len(avgs) == 2 else None
    ran = sum(r[f"{k}_n"] for r in table.values() if isinstance(r, dict) for k in ("clean", "tool", "user"))
    table["status"] = "PASS" if ran else "FAIL"
    args.output.write_text(json.dumps(table, indent=2) + "\n")
    print(json.dumps(table, indent=2))


if __name__ == "__main__":
    main()
