"""Optional per-task wall-clock deadline (off unless TASK_TIMEOUT_SECONDS > 0).
When enabled, a timeout counts as an incorrect trajectory.

The deadline is a hang guard, not a scoring knob: it must be generous enough
that a healthy task never hits it. Two rules keep it from manufacturing its own
failures:

* Requests are never issued with a read timeout below ``MIN_REQUEST_BUDGET``.
  A 2-second read timeout against a thinking model cannot succeed, so issuing
  it (and then retrying it) only burns the remaining budget.
* Once the remaining budget drops below that floor the task aborts immediately
  instead of entering a retry storm of doomed requests.
"""
from __future__ import annotations

import os
import threading
import time

_tls = threading.local()

# A request needs at least this many seconds to have a realistic chance against
# a thinking model. Below it, abort the task instead of issuing a doomed call.
MIN_REQUEST_BUDGET = float(os.environ.get("TASK_MIN_REQUEST_BUDGET", "20"))


class TaskTimeout(Exception):
    """Raised when a single task exceeds TASK_TIMEOUT_SECONDS."""


def task_timeout_seconds() -> float:
    """0 (the default) disables the deadline, matching the official harness."""
    return max(0.0, float(os.environ.get("TASK_TIMEOUT_SECONDS", "0")))


def start_task_deadline(seconds: float | None = None) -> float:
    budget = task_timeout_seconds() if seconds is None else float(seconds)
    _tls.deadline = time.monotonic() + budget if budget > 0 else None
    _tls.started = time.monotonic()
    return budget


def clear_task_deadline() -> None:
    _tls.deadline = None


def remaining_seconds() -> float:
    deadline = getattr(_tls, "deadline", None)
    if deadline is None:
        return float("inf")
    return deadline - time.monotonic()


def elapsed_seconds() -> float:
    started = getattr(_tls, "started", None)
    if started is None:
        return 0.0
    return time.monotonic() - started


def check_deadline() -> None:
    rem = remaining_seconds()
    if rem != float("inf") and rem <= 0:
        raise TaskTimeout(f"task exceeded {task_timeout_seconds():.0f}s limit")


def has_budget_for_request() -> bool:
    """True when enough budget remains for a request to plausibly succeed."""
    rem = remaining_seconds()
    return rem == float("inf") or rem >= MIN_REQUEST_BUDGET


def request_timeout(default_read: float) -> tuple[float, float]:
    """Connect/read timeouts for a request that still has a real chance.

    Raises ``TaskTimeout`` rather than returning a stub timeout that is certain
    to expire, so callers never retry a request that cannot finish in time.
    """
    check_deadline()
    rem = remaining_seconds()
    if rem == float("inf"):
        return (min(30.0, default_read), default_read)
    if rem < MIN_REQUEST_BUDGET:
        raise TaskTimeout(
            f"task exceeded {task_timeout_seconds():.0f}s limit "
            f"(remaining {rem:.1f}s < {MIN_REQUEST_BUDGET:.0f}s minimum request budget)"
        )
    return (min(30.0, rem), min(default_read, rem))
