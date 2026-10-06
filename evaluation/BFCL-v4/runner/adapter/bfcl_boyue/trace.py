from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any


_SAFE_COMPONENT = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _validate_component(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"unsafe {field}")
    return value


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return to_jsonable(model_dump())
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_jsonable(item) for item in value]
    raise TypeError(f"value is not JSON serializable: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            to_jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


class TraceWriter:
    def __init__(self, root: Path):
        self.root = Path(root)

    def write_attempt(
        self,
        *,
        registry_id: str,
        test_id: str,
        request_ordinal: int,
        attempt: int,
        request: dict,
        response_body: bytes,
        metadata: dict,
    ) -> str:
        _validate_component(registry_id, "registry_id")
        _validate_component(test_id, "test_id")
        if not isinstance(request_ordinal, int) or request_ordinal < 1:
            raise ValueError("request_ordinal must be a positive integer")
        if not isinstance(attempt, int) or attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if not isinstance(response_body, bytes):
            raise TypeError("response_body must be bytes")

        relative = (
            Path(registry_id)
            / test_id
            / f"{request_ordinal:04d}-{attempt}"
        )
        target = self.root / relative
        target.mkdir(parents=True, mode=0o700, exist_ok=True)

        request_bytes = canonical_json_bytes(request)
        enriched = {
            **to_jsonable(metadata),
            "request_sha256": sha256(request_bytes).hexdigest(),
            "response_body_sha256": sha256(response_body).hexdigest(),
        }
        atomic_write(target / "request.json", request_bytes)
        atomic_write(target / "response.body", response_body)
        atomic_write(
            target / "metadata.json",
            canonical_json_bytes(enriched),
        )
        return relative.as_posix()
