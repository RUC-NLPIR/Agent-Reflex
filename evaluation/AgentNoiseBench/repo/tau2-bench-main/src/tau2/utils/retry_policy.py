"""Shared retry classification for every LLM call in the eval chain.

Retrying is only worth wall-clock time when the failure is transient. Two
classes of failure previously burned the whole per-task budget:

* Deterministic 4xx (a context-length ``400`` from vLLM, a bad key, a rejected
  payload) was retried 11 times with exponential backoff, ~211s of sleep for a
  request that could never succeed.
* Read timeouts were retried with the same aggression, re-queueing an
  expensive long generation each time.

External gateways also flap with HTTP 500. Those *are* worth a long retry
window; a 25% 500 rate dies in 11 attempts only when the outage lasts the
whole backoff budget.

``classify`` decides retryability; ``backoff_seconds`` bounds the sleep so a
retry chain can never outlast the remaining task budget.
"""
from __future__ import annotations

import random

import requests

# Deterministic client errors: the same request will fail the same way.
NON_RETRYABLE_STATUS = frozenset({400, 401, 403, 404, 405, 406, 409, 410, 413, 414, 415, 422})
# Transient server / throttling errors worth another attempt.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 529})

# Timeouts are transient but expensive; retry far less than ordinary errors.
MAX_TIMEOUT_RETRIES = 2
# Boyue / proxy 5xx bursts can last a couple of minutes.
MAX_TRANSIENT_RETRIES = 5


def status_of(exc: BaseException) -> int | None:
    """HTTP status behind a failure, for both `requests` and the OpenAI SDK."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, requests.exceptions.Timeout) or "timed out" in str(exc).lower()


def classify(
    exc: BaseException,
    attempt: int,
    max_retries: int,
    *,
    local_model: bool = False,
) -> tuple[bool, str]:
    """Return ``(should_retry, reason)`` for a failed LLM call.

    Local vLLM timeouts are expensive (a thinking generation) so they stop
    after ``MAX_TIMEOUT_RETRIES``. External GPT/proxy timeouts are cheap
    flaps and use the long transient budget instead.
    """
    status = status_of(exc)
    if status in NON_RETRYABLE_STATUS:
        return False, f"non-retryable HTTP {status}"
    if status is not None and status not in RETRYABLE_STATUS and 400 <= status < 500:
        return False, f"non-retryable HTTP {status}"

    if is_timeout(exc):
        limit = MAX_TIMEOUT_RETRIES if local_model else MAX_TRANSIENT_RETRIES
        if attempt >= limit:
            return False, f"timeout retry budget exhausted after {attempt + 1} attempts"
        return True, "timeout"

    limit = max(max_retries, MAX_TRANSIENT_RETRIES)
    if attempt >= limit:
        return False, "retries exhausted"
    return True, "transient"


def backoff_seconds(attempt: int, remaining: float, reason: str = "transient") -> float:
    """Exponential backoff with jitter, capped by the remaining task budget."""
    cap = 30.0 if reason == "transient" else 10.0
    delay = min(2.0**attempt, cap) * (0.5 + random.random())
    if remaining != float("inf"):
        delay = min(delay, max(0.0, remaining - 1.0))
    return delay
