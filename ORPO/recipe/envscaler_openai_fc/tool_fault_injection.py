#!/usr/bin/env python3
"""Reproducible per-tool-call fault injection for tool-use rollouts.

The module has no third-party dependencies.  It can:

1. build a weighted error catalog from historical JSONL trajectories;
2. perform an independent Bernoulli draw for every tool call;
3. replace a selected real tool result with a canonical simulated error;
4. preserve enough audit information to reproduce injected positions.

``prepare_call`` is the entry point used by the async rollout path: it performs
the single Bernoulli draw for one tool call and records the audit event, leaving
the caller to await the real tool when nothing was injected.  ``invoke`` keeps
the synchronous convenience API and is implemented on top of it, so both paths
share one place that draws and counts.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


DEFAULT_FAULT_RATE = 0.10

FAULT_FAMILIES = (
    "timeout",
    "rate_limit",
    "auth_permission",
    "not_found",
    "invalid_input",
    "server_unavailable",
    "connection",
    "execution_failure",
)

# The order is significant: classify_error returns the first matching family.
ERROR_PATTERNS = {
    "timeout": re.compile(
        r"timeout|timed out|deadline exceeded|gateway timeout|\b504\b", re.I
    ),
    "rate_limit": re.compile(
        r"rate.?limit|too many requests|quota exceeded|throttl|\b429\b", re.I
    ),
    "auth_permission": re.compile(
        r"unauthenticated|unauthorized|permission denied|forbidden|access denied|"
        r"invalid api.?key|\b401\b|\b403\b",
        re.I,
    ),
    "not_found": re.compile(
        r"not found|does not exist|unknown (?:resource|record|entity)|\b404\b", re.I
    ),
    "invalid_input": re.compile(
        r"invalid (?:input|argument|parameter|request)|validation error|"
        r"missing required|required field|unprocessable|\b400\b|\b422\b",
        re.I,
    ),
    "server_unavailable": re.compile(
        r"service unavailable|server unavailable|temporarily unavailable|"
        r"bad gateway|\b502\b|\b503\b",
        re.I,
    ),
    "connection": re.compile(
        r"connection (?:error|failed|refused|reset|closed)|network error|"
        r"dns|name resolution|broken pipe",
        re.I,
    ),
    "execution_failure": re.compile(
        r"execution.?failure|internal (?:server )?error|tool.?execution.?error|"
        r"exception|traceback|command failed|return code [1-9]|\b500\b",
        re.I,
    ),
}

FAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "timeout": {
        "error": {
            "type": "timeout",
            "code": 504,
            "message": "Tool request timed out.",
        }
    },
    "rate_limit": {
        "error": {
            "type": "rate_limit",
            "code": 429,
            "message": "Too many requests; retry later.",
        }
    },
    "auth_permission": {
        "error": {
            "type": "permission_denied",
            "code": 403,
            "message": "The tool request is not authorized.",
        }
    },
    "not_found": {
        "error": {
            "type": "not_found",
            "code": 404,
            "message": "The requested resource was not found.",
        }
    },
    "invalid_input": {
        "error": {
            "type": "invalid_input",
            "code": 422,
            "message": "The tool request failed input validation.",
        }
    },
    "server_unavailable": {
        "error": {
            "type": "service_unavailable",
            "code": 503,
            "message": "The tool service is temporarily unavailable.",
        }
    },
    "connection": {
        "error": {
            "type": "connection_error",
            "code": 502,
            "message": "The tool connection failed.",
        }
    },
    "execution_failure": {
        "error": {
            "type": "execution_failure",
            "code": 500,
            "message": "The tool failed during execution.",
        }
    },
}


def canonical_json(value: Any) -> str:
    """Serialize a value deterministically for hashing or tool messages."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def stable_seed(
    run_fingerprint: str,
    task_id: str,
    model_id: str,
    rollout_index: int = 0,
) -> int:
    """Return the deterministic 64-bit seed for one task/model trajectory."""

    raw = (
        f"{run_fingerprint}\0{task_id}\0{model_id}\0{rollout_index}"
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for child in value.values() for text in _flatten_strings(child)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [text for child in value for text in _flatten_strings(child)]
    return []


def strict_error_candidate(content: Any) -> tuple[bool, str]:
    """Decide whether a historical tool message explicitly represents failure."""

    parsed = content
    if isinstance(content, str):
        text = content
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = content
    else:
        text = canonical_json(content)

    if not isinstance(text, str):
        text = " ".join(_flatten_strings(parsed))

    structured_error = False
    if isinstance(parsed, Mapping):
        structured_error = any(
            parsed.get(key) not in (None, "", False, [], {})
            for key in ("error", "errors", "exception")
        )
        structured_error = structured_error or parsed.get("ok") is False
        structured_error = structured_error or parsed.get("success") is False
        structured_error = structured_error or str(parsed.get("status", "")).lower() in {
            "error",
            "failed",
            "failure",
        }

    explicit_error = bool(
        re.search(
            r"(?:^|[\n\"'])\s*(?:error|exception|traceback|failed to call tool)\b|"
            r"client error '[45]\d\d|command completed with return code: [1-9]",
            text,
            re.I,
        )
    )
    return bool(structured_error or explicit_error), text


def classify_error(content: Any) -> str | None:
    """Classify a historical tool failure into one canonical family."""

    candidate, text = strict_error_candidate(content)
    if not candidate:
        return None
    for family in FAULT_FAMILIES:
        if ERROR_PATTERNS[family].search(text):
            return family
    return "execution_failure"


def build_error_catalog(
    input_paths: Iterable[str | Path],
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Stream historical trajectory JSONL files and build family weights.

    Expected input records contain a ``messages`` list.  Only messages with
    ``role == 'tool'`` are considered.  Malformed JSONL lines are skipped and
    counted in the catalog.
    """

    counts: Counter[str] = Counter()
    per_file: dict[str, dict[str, int]] = {}
    total_tool_messages = 0
    malformed_lines = 0

    for raw_path in input_paths:
        path = Path(raw_path)
        file_counts: Counter[str] = Counter()
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    sample = json.loads(line)
                except json.JSONDecodeError:
                    malformed_lines += 1
                    continue
                for message in sample.get("messages", []):
                    if message.get("role") != "tool":
                        continue
                    total_tool_messages += 1
                    family = classify_error(message.get("content", ""))
                    if family is not None:
                        counts[family] += 1
                        file_counts[family] += 1
        per_file[str(path)] = {
            family: file_counts[family] for family in FAULT_FAMILIES
        }

    classified = sum(counts.values())
    if classified == 0:
        raise ValueError("No structured historical tool errors were found")

    catalog = {
        "schema_version": "tool_fault_catalog_v1",
        "total_tool_messages": total_tool_messages,
        "classified_error_messages": classified,
        "malformed_jsonl_lines": malformed_lines,
        "source_files": per_file,
        "families": [
            {
                "id": family,
                "count": counts[family],
                "weight": counts[family] / classified,
            }
            for family in FAULT_FAMILIES
        ],
    }

    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
    return catalog


@dataclasses.dataclass(frozen=True)
class InjectionDecision:
    injected: bool
    random_value: float
    family: str | None


@dataclasses.dataclass(frozen=True)
class FaultSampler:
    families: tuple[str, ...]
    weights: tuple[float, ...]
    rate: float = DEFAULT_FAULT_RATE

    def __post_init__(self) -> None:
        if not 0.0 <= self.rate <= 1.0:
            raise ValueError("rate must be between 0 and 1")
        if len(self.families) != len(self.weights) or not self.families:
            raise ValueError("families and weights must be non-empty and aligned")
        if any(family not in FAULT_FAMILIES for family in self.families):
            raise ValueError("catalog contains an unsupported fault family")
        if any(weight < 0 for weight in self.weights) or sum(self.weights) <= 0:
            raise ValueError("weights must be non-negative and sum to more than zero")

    @classmethod
    def from_catalog(
        cls,
        catalog: Mapping[str, Any],
        rate: float = DEFAULT_FAULT_RATE,
    ) -> "FaultSampler":
        rows = [
            row
            for row in catalog.get("families", [])
            if row.get("id") in FAULT_FAMILIES
        ]
        total = sum(float(row.get("weight", 0)) for row in rows)
        if not rows or total <= 0:
            uniform = 1.0 / len(FAULT_FAMILIES)
            return cls(FAULT_FAMILIES, (uniform,) * len(FAULT_FAMILIES), rate)
        return cls(
            tuple(str(row["id"]) for row in rows),
            tuple(float(row.get("weight", 0)) for row in rows),
            rate,
        )

    def draw(self, rng: random.Random) -> InjectionDecision:
        """Run one Bernoulli trial; call exactly once per attempted tool call."""

        value = rng.random()
        if value >= self.rate:
            return InjectionDecision(False, value, None)
        family = rng.choices(self.families, weights=self.weights, k=1)[0]
        return InjectionDecision(True, value, family)


class FaultInjector:
    """Trajectory-scoped injector.  Do not share one instance across rollouts."""

    def __init__(self, sampler: FaultSampler, seed: int):
        self.sampler = sampler
        self.seed = seed
        self.rng = random.Random(seed)
        self.events: list[dict[str, Any]] = []
        self.tool_call_count = 0

    @classmethod
    def for_trajectory(
        cls,
        catalog: Mapping[str, Any],
        run_fingerprint: str,
        task_id: str,
        model_id: str,
        rollout_index: int = 0,
        rate: float = DEFAULT_FAULT_RATE,
    ) -> "FaultInjector":
        return cls(
            FaultSampler.from_catalog(catalog, rate=rate),
            stable_seed(run_fingerprint, task_id, model_id, rollout_index),
        )

    def prepare_call(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        assistant_turn: int | None = None,
    ) -> tuple[InjectionDecision, dict[str, Any] | None]:
        """Draw once for one attempted tool call.

        Returns the decision and, when a fault was injected, the simulated error
        payload that must be returned *instead of* executing the real tool. The
        caller is responsible for executing the tool when the payload is None,
        which is what lets the async rollout path await the environment.
        """

        self.tool_call_count += 1
        decision = self.sampler.draw(self.rng)
        if not decision.injected:
            return decision, None

        assert decision.family is not None
        self.events.append(
            {
                "tool_call_index": self.tool_call_count,
                "assistant_turn": assistant_turn,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "random_value": decision.random_value,
                "family": decision.family,
                "short_circuited": True,
            }
        )
        return decision, FAULT_TEMPLATES[decision.family]

    def invoke(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        executor: Callable[..., Any],
        assistant_turn: int | None = None,
        catch_real_exceptions: bool = True,
    ) -> tuple[dict[str, Any], InjectionDecision]:
        """Inject a simulated error or execute the real tool.

        Returns an OpenAI-style tool message plus the sampling decision.  When
        ``decision.injected`` is true, ``executor`` is never called.
        """

        decision, payload = self.prepare_call(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            assistant_turn=assistant_turn,
        )

        if payload is None:
            try:
                payload = executor(**dict(arguments))
            except Exception as error:
                if not catch_real_exceptions:
                    raise
                # A real execution failure is not a simulated injection event.
                payload = {
                    "error": {
                        "type": "tool_execution_error",
                        "message": f"{type(error).__name__}: {str(error)[:500]}",
                    }
                }

        message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": canonical_json(payload),
        }
        return message, decision

    def audit_record(self) -> dict[str, Any]:
        return {
            "rate": self.sampler.rate,
            "seed": self.seed,
            "tool_calls": self.tool_call_count,
            "events": list(self.events),
        }


def _load_catalog(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def _demo(catalog_path: Path) -> None:
    catalog = _load_catalog(catalog_path)
    injector = FaultInjector.for_trajectory(
        catalog,
        run_fingerprint="demo-run-v1",
        task_id="task-001",
        model_id="demo-model",
    )

    def add(a: int, b: int) -> dict[str, int]:
        return {"sum": a + b}

    for index in range(1, 21):
        message, decision = injector.invoke(
            tool_call_id=f"call-{index}",
            tool_name="add",
            arguments={"a": index, "b": 1},
            executor=add,
            assistant_turn=index,
        )
        print(
            canonical_json(
                {
                    "decision": dataclasses.asdict(decision),
                    "tool_message": message,
                }
            )
        )
    print(json.dumps(injector.audit_record(), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build-catalog", help="Build weighted fault families from JSONL trajectories"
    )
    build.add_argument("inputs", nargs="+", type=Path)
    build.add_argument("--output", required=True, type=Path)

    demo = subparsers.add_parser("demo", help="Run a deterministic 20-call example")
    demo.add_argument("--catalog", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "build-catalog":
        result = build_error_catalog(args.inputs, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "demo":
        _demo(args.catalog)


if __name__ == "__main__":
    main()
