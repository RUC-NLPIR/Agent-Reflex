from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CONTRACTS


PINNED_BFCL_COMMIT = "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
MODEL_ALIASES = {"qwen3-8b-local": "local-qwen3-8b-FC"}
NON_WEB_CATEGORIES = (
    "simple_python",
    "simple_java",
    "simple_javascript",
    "multiple",
    "parallel",
    "parallel_multiple",
    "irrelevance",
    "live_simple",
    "live_multiple",
    "live_parallel",
    "live_parallel_multiple",
    "live_irrelevance",
    "live_relevance",
    "multi_turn_base",
    "multi_turn_miss_func",
    "multi_turn_miss_param",
    "multi_turn_long_context",
    "memory_kv",
    "memory_vector",
    "memory_rec_sum",
)
WEB_CATEGORIES = ("web_search_base", "web_search_no_snippet")
SUITES = {
    "all": ("all_scoring",),
    "non-web": NON_WEB_CATEGORIES,
    "web": WEB_CATEGORIES,
    "smoke": ("simple_python", "multi_turn_base"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_run_id(model: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{model.replace('.', '').replace('/', '-')}"


def resolve_registry(model: str) -> str:
    if model in MODEL_ALIASES:
        return MODEL_ALIASES[model]
    if model in CONTRACTS:
        return model
    supported = ", ".join(MODEL_ALIASES)
    raise ValueError(f"unknown model {model!r}; choose one of: {supported}")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_logged(command: list[str], *, env: dict[str, str], log: Path) -> int:
    with log.open("ab") as stream:
        stream.write(("$ " + " ".join(command) + "\n").encode())
        stream.flush()
        process = subprocess.Popen(
            command,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        for chunk in iter(lambda: process.stdout.read(64 * 1024), b""):
            stream.write(chunk)
            stream.flush()
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        return int(process.wait())


def _trace_summary(run_root: Path) -> dict[str, int]:
    passed = failed = 0
    for path in (run_root / "raw-api").glob("**/metadata.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8")).get("state")
        except Exception:
            failed += 1
            continue
        if state == "PASS":
            passed += 1
        else:
            failed += 1
    placeholders = 0
    result_root = run_root / "project-root" / "result"
    for path in result_root.glob("**/*.json"):
        try:
            placeholders += path.read_text(
                encoding="utf-8", errors="replace"
            ).count("Error during inference")
        except OSError:
            placeholders += 1
    search_calls = sum(1 for _ in (run_root / "search-trace").glob("*.json"))
    return {
        "model_api_attempts_passed": passed,
        "model_api_attempts_failed": failed,
        "error_placeholders": placeholders,
        "serper_calls_recorded": search_calls,
    }


def _base_environment(root: Path, run_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "BFCL_PROJECT_ROOT": str(run_root / "project-root"),
            "BFCL_BOYUE_TRACE_ROOT": str(run_root / "raw-api"),
            "BFCL_SEARCH_TRACE_ROOT": str(run_root / "search-trace"),
            "BFCL_SEARCH_PROVIDER": "serper",
            "HF_HOME": env.get("HF_HOME", str(root / "cache" / "huggingface")),
            "PYTHONPATH": str(root / "adapter")
            + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


def run_benchmark(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    registry_id = resolve_registry(args.model)
    contract = CONTRACTS[registry_id]
    categories = SUITES[args.suite]
    if (
        contract.api_key_required
        and contract.api_key_env
        and not os.environ.get(contract.api_key_env)
    ):
        raise RuntimeError(
            f"{contract.api_key_env} is missing; fill it in .env"
        )
    if args.suite in {"all", "web"} and not os.environ.get("SERPER_API_KEY"):
        raise RuntimeError("SERPER_API_KEY is missing; fill it in .env")
    run_id = args.run_id or _default_run_id(args.model)
    run_root = root / "runs" / run_id
    if run_root.exists():
        raise RuntimeError(f"run already exists: {run_root}")
    for directory in (
        run_root,
        run_root / "logs",
        run_root / "raw-api",
        run_root / "search-trace",
        run_root / "project-root",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    # bfcl_eval's own default is 0.001, i.e. every run on record is effectively
    # greedy. A temperature belongs in the manifest rather than only in the
    # command line, because two runs of the same registry are otherwise
    # indistinguishable on disk and the scores are not comparable.
    temperature = os.environ.get("BFCL_TEMPERATURE")

    manifest = {
        "run_id": run_id,
        "created_at_utc": _utc_now(),
        "bfcl_commit": PINNED_BFCL_COMMIT,
        "model": args.model,
        "registry_id": registry_id,
        "request_model": contract.request_model,
        "model_endpoint": contract.base_url,
        "max_total_tokens": contract.max_total_tokens,
        "suite": args.suite,
        "categories": list(categories),
        "workers": args.workers,
        "search_provider": "serper",
        "temperature": float(temperature) if temperature else None,
    }
    _write_json(run_root / "manifest.json", manifest)
    status = {
        **manifest,
        "execution_state": "RUNNING",
        "trace_complete": False,
    }
    _write_json(run_root / "status.json", status)

    env = _base_environment(root, run_root)
    python = sys.executable
    category_value = ",".join(categories)
    generate = [
        python,
        "-m",
        "bfcl_boyue",
        "generate",
        "--model",
        registry_id,
        "--test-category",
        category_value,
        "--include-input-log",
        "--skip-server-setup",
        "--num-threads",
        str(args.workers),
    ]
    if temperature:
        generate += ["--temperature", str(float(temperature))]
    generate_exit = _run_logged(
        generate, env=env, log=run_root / "logs" / "generate.log"
    )
    evaluate_exit: int | None = None
    if generate_exit == 0:
        evaluate = [
            python,
            "-m",
            "bfcl_boyue",
            "evaluate",
            "--model",
            registry_id,
            "--test-category",
            category_value,
        ]
        evaluate_exit = _run_logged(
            evaluate, env=env, log=run_root / "logs" / "evaluate.log"
        )

    trace = _trace_summary(run_root)
    trace_complete = generate_exit == 0 and trace["error_placeholders"] == 0
    passed = trace_complete and evaluate_exit == 0
    status.update(
        {
            "completed_at_utc": _utc_now(),
            "execution_state": "PASS" if passed else "FAIL",
            "trace_complete": trace_complete,
            "generate_exit": generate_exit,
            "evaluate_exit": evaluate_exit,
            "trace": trace,
            "paths": {
                "raw_model_api": str(run_root / "raw-api"),
                "raw_search_api": str(run_root / "search-trace"),
                "bfcl_result": str(run_root / "project-root" / "result"),
                "bfcl_score": str(run_root / "project-root" / "score"),
            },
        }
    )
    _write_json(run_root / "status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 10


def doctor(args: argparse.Namespace) -> int:
    result: dict[str, Any] = {
        "python": sys.version.split()[0],
        "boyue_key_present": bool(os.environ.get("BOYUE_API_KEY")),
        "serper_key_present": bool(os.environ.get("SERPER_API_KEY")),
        "local_vllm_configured": bool(os.environ.get("LOCAL_VLLM_BASE_URL")),
        "models": list(MODEL_ALIASES),
    }
    try:
        import bfcl_eval  # noqa: F401

        result["bfcl_import"] = "PASS"
    except Exception as error:
        result["bfcl_import"] = f"FAIL:{type(error).__name__}"
    result["state"] = (
        "PASS"
        if (result["boyue_key_present"] or result["local_vllm_configured"])
        and result["serper_key_present"]
        and result["bfcl_import"] == "PASS"
        else "FAIL"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["state"] == "PASS" else 10


def show_status(args: argparse.Namespace) -> int:
    path = Path(args.root).expanduser().resolve() / "runs" / args.run_id / "status.json"
    if not path.is_file():
        raise RuntimeError(f"status not found: {path}")
    print(path.read_text(encoding="utf-8"), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bfcl", description="BFCL Boyue trace runner")
    parser.add_argument("--root", default=os.environ.get("BFCL_ROOT", Path.cwd()))
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("models", help="list configured benchmark models")
    subcommands.add_parser("doctor", help="check the local environment without API calls")

    run = subcommands.add_parser("run", help="generate traces and run the BFCL scorer")
    run.add_argument("--model", required=True)
    run.add_argument("--suite", choices=tuple(SUITES), default="all")
    run.add_argument("--workers", type=int, default=int(os.environ.get("BFCL_WORKERS", "8")))
    run.add_argument("--run-id")

    status = subcommands.add_parser("status", help="show one run status")
    status.add_argument("run_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "models":
            for alias, registry in MODEL_ALIASES.items():
                print(f"{alias}\t{registry}")
            return 0
        if args.command == "doctor":
            return doctor(args)
        if args.command == "run":
            if args.workers < 1:
                raise ValueError("--workers must be positive")
            return run_benchmark(args)
        if args.command == "status":
            return show_status(args)
        parser.error("unknown command")
    except (RuntimeError, ValueError, OSError) as error:
        print(f"bfcl: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
