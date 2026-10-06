from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .trace import atomic_write, canonical_json_bytes


SERPER_ENDPOINT = "https://google.serper.dev/search"


def _region_payload(region: str | None) -> dict[str, str]:
    if not region or region == "wt-wt" or "-" not in region:
        return {}
    country, language = region.split("-", 1)
    result: dict[str, str] = {}
    if len(country) == 2 and country not in {"xa", "xl", "ue"}:
        result["gl"] = country
    if len(language) == 2:
        result["hl"] = language
    return result


def _normalize_results(
    payload: dict[str, Any], *, max_results: int, show_snippet: bool
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    organic = payload.get("organic", [])
    if not isinstance(organic, list):
        return results
    for item in organic[:max_results]:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        link = item.get("link")
        if not isinstance(title, str) or not isinstance(link, str):
            continue
        result = {"title": title, "href": link}
        if show_snippet:
            snippet = item.get("snippet", "")
            result["body"] = snippet if isinstance(snippet, str) else ""
        results.append(result)
    return results


def _write_search_trace(record: dict[str, Any]) -> None:
    configured = os.environ.get("BFCL_SEARCH_TRACE_ROOT")
    if not configured:
        return
    root = Path(configured)
    root.mkdir(parents=True, exist_ok=True)
    name = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ-")
        + uuid.uuid4().hex
        + ".json"
    )
    atomic_write(root / name, canonical_json_bytes(record))


def _serper_search_engine_query(
    self,
    keywords: str,
    max_results: int | None = 10,
    region: str | None = "wt-wt",
) -> list[dict[str, str]] | dict[str, str]:
    key = os.environ.get("SERPER_API_KEY")
    if not key:
        return {"error": "SERPER_API_KEY is missing"}
    limit = 10 if max_results is None else max(1, int(max_results))
    request_payload: dict[str, Any] = {"q": keywords, "num": limit}
    request_payload.update(_region_payload(region))
    timeout = float(os.environ.get("SERPER_REQUEST_TIMEOUT", "30"))
    trace: dict[str, Any] = {
        "provider": "serper",
        "endpoint": SERPER_ENDPOINT,
        "query": keywords,
        "region": region,
        "max_results": limit,
        "request": request_payload,
    }
    try:
        import requests

        response = requests.post(
            SERPER_ENDPOINT,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json=request_payload,
            timeout=timeout,
        )
        trace["http_status"] = response.status_code
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Serper response is not a JSON object")
        normalized = _normalize_results(
            payload,
            max_results=limit,
            show_snippet=bool(getattr(self, "show_snippet", True)),
        )
        trace["response"] = payload
        trace["normalized_results"] = normalized
        trace["state"] = "PASS"
        _write_search_trace(trace)
        if not normalized:
            return {"error": "Serper returned no organic search results"}
        return normalized
    except Exception as error:
        trace["state"] = "FAIL"
        trace["error_type"] = type(error).__name__
        trace["error"] = str(error)
        try:
            trace["response_text"] = response.text  # type: ignore[possibly-undefined]
        except Exception:
            pass
        _write_search_trace(trace)
        return {"error": f"Serper request failed: {type(error).__name__}: {error}"}


def install_serper_search() -> None:
    from bfcl_eval.eval_checker.multi_turn_eval.func_source_code.web_search import (
        WebSearchAPI,
    )

    if getattr(WebSearchAPI, "_bfcl_serper_installed", False):
        return
    WebSearchAPI.search_engine_query = _serper_search_engine_query
    WebSearchAPI._bfcl_serper_installed = True
