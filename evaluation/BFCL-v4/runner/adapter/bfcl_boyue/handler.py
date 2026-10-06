from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from bfcl_eval.constants.enums import ModelStyle
from bfcl_eval.model_handler.api_inference.openai_completion import (
    OpenAICompletionsHandler,
)
from bfcl_eval.model_handler.base_handler import BaseHandler

from .config import (
    CONTRACTS,
    MAX_SEND_ATTEMPTS,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_CAP,
    RETRYABLE_STATUS_CODES,
)
from .trace import TraceWriter, to_jsonable


class BoyueInferenceError(RuntimeError):
    pass


def _status_code(value: Any) -> int | None:
    status = getattr(value, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(value, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _response_body(value: Any) -> bytes:
    response = getattr(value, "response", None)
    body = getattr(response, "content", b"")
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8", errors="replace")
    return b""


def _error_category(error: BaseException, status: int | None) -> str:
    if status in {401, 403}:
        return "authentication"
    if status == 404:
        return "endpoint_not_supported"
    if status == 429:
        return "quota_or_rate_limit"
    if status is not None:
        return "http_status"
    if type(error).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectionError",
        "TimeoutError",
    }:
        return "transport"
    return "response_schema"


def _backoff_seconds(attempt: int) -> float:
    """Wait before the next send, growing geometrically up to a ceiling.

    The ceiling matters as much as the growth: without it a late attempt would
    sleep for most of an hour, and with ten attempts the run would stall rather
    than fail. With the defaults, ten attempts span roughly seven minutes,
    which covers the plaza outages observed so far.
    """
    return min(RETRY_BACKOFF_CAP, RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))


def _is_retryable(error: BaseException, status: int | None) -> bool:
    return status in RETRYABLE_STATUS_CODES or type(error).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectionError",
        "TimeoutError",
    }


class BoyueOpenAICompletionsHandler(OpenAICompletionsHandler):
    def __init__(
        self,
        model_name,
        temperature,
        registry_name,
        is_fc_model,
        *,
        transport=None,
        trace_writer=None,
        sleeper=time.sleep,
        **kwargs,
    ) -> None:
        BaseHandler.__init__(
            self,
            model_name,
            temperature,
            registry_name,
            is_fc_model,
            **kwargs,
        )
        self.model_style = ModelStyle.OPENAI_COMPLETIONS
        try:
            self.contract = CONTRACTS[registry_name]
        except KeyError as error:
            raise ValueError(f"unknown Boyue registry: {registry_name}") from error
        if model_name != self.contract.request_model:
            raise ValueError("registry model contract mismatch")
        self._transport = transport
        if trace_writer is None:
            trace_root = os.environ.get("BFCL_BOYUE_TRACE_ROOT")
            if not trace_root:
                raise BoyueInferenceError("trace_root_missing")
            trace_writer = TraceWriter(Path(trace_root))
        self._trace_writer = trace_writer
        self._sleeper = sleeper

    def _get_transport(self):
        if self._transport is not None:
            return self._transport
        key = (
            os.environ.get(self.contract.api_key_env)
            if self.contract.api_key_env
            else None
        )
        if self.contract.api_key_required and not key:
            raise BoyueInferenceError("credential_missing")
        from openai import OpenAI

        client = OpenAI(
            api_key=key or "not-required",
            base_url=self.contract.base_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )
        self._transport = client.chat.completions.with_raw_response
        return self._transport

    def _pre_query_processing_FC(
        self, inference_data: dict, test_entry: dict
    ) -> dict:
        inference_data["message"] = []
        inference_data["_boyue_trace"] = {
            "test_id": test_entry["id"],
            "request_ordinal": 0,
        }
        return inference_data

    def _query_FC(self, inference_data: dict):
        message = inference_data["message"]
        tools = inference_data["tools"]
        trace_state = inference_data.get("_boyue_trace")
        if not isinstance(trace_state, dict):
            raise BoyueInferenceError("trace_state_missing")
        test_id = trace_state.get("test_id")
        if not isinstance(test_id, str):
            raise BoyueInferenceError("trace_test_id_missing")
        trace_state["request_ordinal"] = int(
            trace_state.get("request_ordinal", 0)
        ) + 1
        request_ordinal = trace_state["request_ordinal"]

        request = {
            "messages": message,
            "model": self.model_name,
        }
        if self.contract.send_store:
            request["store"] = False
        if self.contract.send_temperature:
            request["temperature"] = self.temperature
        if tools:
            request["tools"] = tools
        request_options = inference_data.get("_boyue_request_options", {})
        if not isinstance(request_options, dict) or set(request_options) - {
            "parallel_tool_calls",
            "tool_choice",
        }:
            raise BoyueInferenceError("request_options_invalid")
        request.update(request_options)

        input_log = {
            "message": to_jsonable(message),
            "tools": to_jsonable(tools),
            "request": to_jsonable(request),
            "trace_ref": None,
        }
        inference_data["inference_input_log"] = input_log
        transport = self._get_transport()
        started = time.perf_counter()

        for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
            try:
                raw = transport.create(**request)
            except Exception as error:
                status = _status_code(error)
                category = _error_category(error, status)
                trace_ref = self._trace_writer.write_attempt(
                    registry_id=self.registry_name,
                    test_id=test_id,
                    request_ordinal=request_ordinal,
                    attempt=attempt,
                    request=request,
                    response_body=_response_body(error),
                    metadata={
                        "state": "FAIL",
                        "error_category": category,
                        "exception_type": type(error).__name__,
                        "http_status": status,
                        "requested_model": self.model_name,
                        "returned_model": None,
                        "usage_present": False,
                    },
                )
                input_log["trace_ref"] = trace_ref
                if attempt < MAX_SEND_ATTEMPTS and _is_retryable(error, status):
                    self._sleeper(_backoff_seconds(attempt))
                    continue
                raise BoyueInferenceError(
                    f"{category}; trace_ref={trace_ref}"
                ) from None

            body = b""
            http_status = None
            try:
                http_response = raw.http_response
                body = http_response.content
                if not isinstance(body, bytes):
                    raise TypeError("raw response body is not bytes")
                http_status = getattr(http_response, "status_code", None)
                parsed = raw.parse()
            except Exception as error:
                trace_ref = self._trace_writer.write_attempt(
                    registry_id=self.registry_name,
                    test_id=test_id,
                    request_ordinal=request_ordinal,
                    attempt=attempt,
                    request=request,
                    response_body=body,
                    metadata={
                        "state": "FAIL",
                        "error_category": "response_schema",
                        "exception_type": type(error).__name__,
                        "http_status": http_status,
                        "requested_model": self.model_name,
                        "returned_model": None,
                        "usage_present": False,
                    },
                )
                input_log["trace_ref"] = trace_ref
                raise BoyueInferenceError(
                    f"response_schema; trace_ref={trace_ref}"
                ) from None

            returned_model = getattr(parsed, "model", None)
            usage_present = getattr(parsed, "usage", None) is not None
            category = None
            if returned_model not in self.contract.accepted_response_models:
                category = "model_identity"
            elif self.contract.require_usage and not usage_present:
                category = "usage_missing"

            trace_ref = self._trace_writer.write_attempt(
                registry_id=self.registry_name,
                test_id=test_id,
                request_ordinal=request_ordinal,
                attempt=attempt,
                request=request,
                response_body=body,
                metadata={
                    "state": "FAIL" if category else "PASS",
                    "error_category": category,
                    "http_status": http_status,
                    "requested_model": self.model_name,
                    "returned_model": returned_model,
                    "usage_present": usage_present,
                },
            )
            input_log["trace_ref"] = trace_ref
            if category:
                raise BoyueInferenceError(f"{category}; trace_ref={trace_ref}")
            return parsed, time.perf_counter() - started

        raise AssertionError("bounded request loop exhausted")

    def _parse_query_response_FC(self, api_response: Any) -> dict:
        response_data = super()._parse_query_response_FC(api_response)
        self._add_reasoning_content_if_available_FC(api_response, response_data)
        return response_data
