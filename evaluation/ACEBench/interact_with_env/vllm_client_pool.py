"""
Thread-safe OpenAI-compatible client pool for local vLLM endpoints.
"""

import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from openai import OpenAI


ResponseHandler = Callable[[Any], Any]


def split_values(value: Any) -> List[str]:
    """Parse CLI/env values that may be lists, comma-separated, or whitespace-separated."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        values: List[str] = []
        for item in value:
            values.extend(split_values(item))
        return values

    text = str(value).strip()
    if not text:
        return []
    return [item for item in text.replace(",", " ").split() if item]


def values_from_env(names: Sequence[str]) -> List[str]:
    for name in names:
        values = split_values(os.getenv(name))
        if values:
            return values
    return []


class VLLMClientPool:
    """
    Synchronous multi-endpoint client pool.

    - Round-robins requests across endpoints.
    - Retries the current endpoint before failing over to other endpoints.
    - Keeps optional session_id sticky to the last successful endpoint.
    """

    def __init__(
        self,
        endpoints: Sequence[Optional[str]],
        api_keys: Optional[Sequence[Optional[str]]] = None,
        max_attempts_per_client: int = 3,
    ):
        if not endpoints:
            endpoints = [None]

        self.endpoints = [endpoint.rstrip("/") if endpoint else None for endpoint in endpoints]
        self.api_keys = self._normalize_api_keys(api_keys)
        self.clients = [
            self._build_client(endpoint=endpoint, api_key=api_key)
            for endpoint, api_key in zip(self.endpoints, self.api_keys)
        ]
        self.max_attempts_per_client = max(1, max_attempts_per_client)

        timeout_env = os.getenv("VLLM_REQUEST_TIMEOUT_SECONDS", "").strip()
        self.request_timeout_seconds = 240.0
        if timeout_env:
            try:
                self.request_timeout_seconds = float(timeout_env)
            except ValueError:
                self.request_timeout_seconds = 240.0

        self._lock = threading.Lock()
        self._current_idx = 0
        self._session_to_idx: Dict[str, int] = {}

    def _normalize_api_keys(
        self,
        api_keys: Optional[Sequence[Optional[str]]],
    ) -> List[Optional[str]]:
        keys = list(api_keys or [])
        if not keys:
            default_key = "EMPTY" if any(self.endpoints) else None
            return [default_key] * len(self.endpoints)
        if len(keys) == 1 and len(self.endpoints) > 1:
            return keys * len(self.endpoints)
        if len(keys) != len(self.endpoints):
            raise ValueError("len(api_keys) must be 1 or equal to len(endpoints)")
        return keys

    @staticmethod
    def _build_client(endpoint: Optional[str], api_key: Optional[str]) -> OpenAI:
        kwargs: Dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if endpoint:
            kwargs["base_url"] = endpoint
        return OpenAI(**kwargs)

    def _pick_client(self, session_id: Optional[str]) -> int:
        with self._lock:
            if session_id:
                idx = self._session_to_idx.get(session_id)
                if idx is not None:
                    return idx

            idx = self._current_idx
            self._current_idx = (self._current_idx + 1) % len(self.clients)
            if session_id:
                self._session_to_idx[session_id] = idx
            return idx

    def _bind_session(self, session_id: Optional[str], idx: int) -> None:
        if not session_id:
            return
        with self._lock:
            self._session_to_idx[session_id] = idx

    def _ordered_indices(self, preferred_idx: int) -> Iterable[int]:
        yield preferred_idx
        for idx in range(len(self.clients)):
            if idx != preferred_idx:
                yield idx

    def chat_completion(
        self,
        request_kwargs: Dict[str, Any],
        response_handler: Optional[ResponseHandler] = None,
        session_id: Optional[str] = None,
        max_attempts_per_client: Optional[int] = None,
    ) -> Any:
        handler = response_handler or (lambda response: response)
        attempts = max_attempts_per_client or self.max_attempts_per_client
        preferred_idx = self._pick_client(session_id)
        last_error = ""

        for idx in self._ordered_indices(preferred_idx):
            self._bind_session(session_id, idx)
            for attempt in range(1, attempts + 1):
                try:
                    kwargs = dict(request_kwargs)
                    if self.request_timeout_seconds > 0 and "timeout" not in kwargs:
                        kwargs["timeout"] = self.request_timeout_seconds
                    response = self.clients[idx].chat.completions.create(**kwargs)
                    return handler(response)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    endpoint = self.endpoints[idx] or "<default OpenAI endpoint>"
                    print(
                        "[VLLMClientPool] "
                        f"endpoint={endpoint} attempt={attempt}/{attempts} failed: {last_error}"
                    )
                    if attempt < attempts:
                        time.sleep(0.2 * attempt)

        raise RuntimeError(f"All chat completion endpoints failed. last_error={last_error}")


_POOL_REGISTRY: Dict[Tuple[Tuple[str, ...], Tuple[str, ...]], VLLMClientPool] = {}
_POOL_REGISTRY_LOCK = threading.Lock()


def _registry_key(
    endpoints: Sequence[Optional[str]],
    api_keys: Sequence[Optional[str]],
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    endpoint_key = tuple(endpoint or "" for endpoint in endpoints)
    api_key = tuple(key or "" for key in api_keys)
    return endpoint_key, api_key


def get_client_pool(
    base_urls: Any = None,
    api_keys: Any = None,
    base_url_env_names: Sequence[str] = ("OPENAI_BASE_URLS", "OPENAI_BASE_URL"),
    api_key_env_names: Sequence[str] = ("OPENAI_API_KEYS", "OPENAI_API_KEY"),
) -> VLLMClientPool:
    endpoints = split_values(base_urls) or values_from_env(base_url_env_names)
    if not endpoints:
        endpoints = [None]
    endpoints = [endpoint.rstrip("/") if endpoint else None for endpoint in endpoints]

    keys = split_values(api_keys) or values_from_env(api_key_env_names)
    if not keys:
        default_key = "EMPTY" if any(endpoints) else None
        keys = [default_key]
    if len(keys) == 1 and len(endpoints) > 1:
        keys = keys * len(endpoints)
    if len(keys) != len(endpoints):
        raise ValueError("len(api_keys) must be 1 or equal to len(endpoints)")

    key = _registry_key(endpoints, keys)
    with _POOL_REGISTRY_LOCK:
        existing_pool = _POOL_REGISTRY.get(key)
        if existing_pool is not None:
            return existing_pool
        max_attempts = int(os.getenv("VLLM_MAX_ATTEMPTS_PER_CLIENT", "3"))
        pool = VLLMClientPool(
            endpoints=endpoints,
            api_keys=keys,
            max_attempts_per_client=max_attempts,
        )
        _POOL_REGISTRY[key] = pool
        return pool
