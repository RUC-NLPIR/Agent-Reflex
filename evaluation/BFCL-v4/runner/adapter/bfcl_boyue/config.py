from __future__ import annotations

import os
from dataclasses import dataclass


BOYUE_BASE_URL = os.environ.get(
    "BOYUE_BASE_URL", os.environ.get("BOYUE_API_BASE_URL", "")
).rstrip("/")
if BOYUE_BASE_URL and not BOYUE_BASE_URL.endswith("/v1"):
    BOYUE_BASE_URL += "/v1"
LOCAL_VLLM_BASE_URL = os.environ.get(
    "LOCAL_VLLM_BASE_URL", "http://127.0.0.1:8000/v1"
)
LOCAL_VLLM_REQUEST_MODEL = os.environ.get(
    "LOCAL_VLLM_REQUEST_MODEL", "Qwen/Qwen3-8B"
)
# Recorded in the run manifest; matches the server's --max-model-len.
LOCAL_VLLM_MAX_TOTAL_TOKENS = int(
    os.environ.get("LOCAL_VLLM_MAX_TOTAL_TOKENS", "40960")
)
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("BOYUE_REQUEST_TIMEOUT", "120"))
MAX_SEND_ATTEMPTS = int(os.environ.get("BOYUE_MAX_SEND_ATTEMPTS", "2"))
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
# Exponential backoff, capped, so retries outlive a short gateway outage.
RETRY_BACKOFF_BASE = float(os.environ.get("BOYUE_RETRY_BACKOFF_BASE", "2"))
RETRY_BACKOFF_CAP = float(os.environ.get("BOYUE_RETRY_BACKOFF_CAP", "90"))


@dataclass(frozen=True)
class ModelContract:
    registry_id: str
    request_model: str
    display_name: str
    accepted_response_models: frozenset[str]
    send_temperature: bool
    base_url: str = BOYUE_BASE_URL
    api_key_env: str | None = "BOYUE_API_KEY"
    api_key_required: bool = True
    organization: str = "Boyue gateway"
    max_total_tokens: int | None = None
    send_store: bool = True
    require_usage: bool = True


CONTRACTS = {
    contract.registry_id: contract
    for contract in (
        ModelContract(
            registry_id="local-qwen3-8b-FC",
            request_model=LOCAL_VLLM_REQUEST_MODEL,
            display_name="Local vLLM Qwen3-8B (FC)",
            accepted_response_models=frozenset({LOCAL_VLLM_REQUEST_MODEL}),
            send_temperature=True,
            base_url=LOCAL_VLLM_BASE_URL,
            api_key_env="LOCAL_VLLM_API_KEY",
            api_key_required=False,
            organization="Local vLLM endpoint",
            max_total_tokens=LOCAL_VLLM_MAX_TOTAL_TOKENS,
            send_store=False,
            require_usage=True,
        ),
    )
}
