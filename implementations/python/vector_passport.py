from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_vector(values: list[float]) -> str:
    payload = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return sha256_digest(payload)


def create_vector_passport(
    *,
    source_uri: str,
    source_content: bytes,
    chunk_text: str,
    chunk_start: int,
    chunk_end: int,
    embedding_model: str,
    embedding_dimension: int,
    vector_values: list[float] | None = None,
    source_last_modified: str | None = None,
    source_mime_type: str | None = None,
    model_version: str | None = None,
    provider: str | None = None,
    chunk_id: str | None = None,
    chunk_strategy: str = "recursive-character-512-50@1.0.0",
    chunk_unit: str = "character",
    page: int | None = None,
    created_by: str | None = None,
    modality: str = "text",
    embedding_parameters: dict[str, Any] | None = None,
    chunk_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_chunk_range(chunk_start, chunk_end)
    if vector_values is not None:
        _validate_dimension(vector_values, embedding_dimension)

    created_at = utc_now()

    passport: dict[str, Any] = {
        "passport_version": "1.0",
        "vector_id": str(uuid.uuid4()),
        "source": {
            "uri": source_uri,
            "hash": sha256_digest(source_content),
            "last_modified": source_last_modified or created_at,
            "mime_type": source_mime_type,
            "size_bytes": len(source_content),
        },
        "chunk": {
            "id": chunk_id or f"{chunk_unit}-{chunk_start}-{chunk_end}",
            "strategy": chunk_strategy,
            "unit": chunk_unit,
            "start": chunk_start,
            "end": chunk_end,
            "page": page,
            "hash": sha256_digest(chunk_text.encode("utf-8")),
            "metadata": chunk_metadata or {},
        },
        "embedding": {
            "model": embedding_model,
            "model_version": model_version,
            "provider": provider,
            "dimension": embedding_dimension,
            "parameters": embedding_parameters or {},
        },
        "created_at": created_at,
        "created_by": created_by,
        "staleness": {
            "status": "current",
            "checked_at": created_at,
        },
        "vector_hash": hash_vector(vector_values) if vector_values is not None else None,
        "modality": modality,
        "lineage": [
            {
                "event": "initial_creation",
                "timestamp": created_at,
                "details": {},
            }
        ],
        "signature": None,
        "extensions": {},
    }

    return _drop_none(passport)


def create_vector_passport_with_hash(
    *,
    source_uri: str,
    source_hash: str,
    chunk_strategy: str,
    chunk_start: int,
    chunk_end: int,
    embedding_model: str,
    embedding_dimension: int,
    vector: list[float],
    model_version: str | None = "1.5.0",
    provider: str | None = "nomic-ai",
    page: int | None = None,
    created_by: str = "ingestion-pipeline",
    embedding_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a minimal text passport when the source and vector already exist."""
    _validate_chunk_range(chunk_start, chunk_end)
    _validate_dimension(vector, embedding_dimension)

    created_at = utc_now()

    return _drop_none(
        {
            "passport_version": "1.0",
            "vector_id": str(uuid.uuid4()),
            "source": {
                "uri": source_uri,
                "hash": source_hash,
            },
            "chunk": {
                "strategy": chunk_strategy,
                "start": chunk_start,
                "end": chunk_end,
                "page": page,
            },
            "embedding": {
                "model": embedding_model,
                "model_version": model_version,
                "provider": provider,
                "dimension": embedding_dimension,
                "parameters": embedding_parameters or {"normalize": True},
            },
            "created_at": created_at,
            "created_by": created_by,
            "vector_hash": hash_vector(vector),
            "modality": "text",
            "lineage": [
                {
                    "event": "initial_creation",
                    "timestamp": created_at,
                    "details": {},
                }
            ],
        }
    )


def mark_stale(passport: dict[str, Any], reason: str) -> dict[str, Any]:
    updated = dict(passport)
    updated["staleness"] = {
        "status": "stale",
        "checked_at": utc_now(),
        "reason": reason,
    }
    updated.setdefault("lineage", []).append(
        {
            "event": "marked_stale",
            "timestamp": updated["staleness"]["checked_at"],
            "details": {"reason": reason},
        }
    )
    return updated


def _validate_chunk_range(chunk_start: int, chunk_end: int) -> None:
    # chunk.start is inclusive, chunk.end is exclusive (SPEC §4.3). end <= start
    # is meaningless to embed; refuse to write a poisoned passport.
    if chunk_end <= chunk_start:
        raise ValueError(
            f"chunk_end ({chunk_end}) must be greater than chunk_start ({chunk_start}); "
            f"chunk.end is exclusive of chunk.start."
        )


def _validate_dimension(vector: list[float], embedding_dimension: int) -> None:
    if len(vector) != embedding_dimension:
        raise ValueError(
            f"Vector length ({len(vector)}) does not match embedding_dimension "
            f"({embedding_dimension}). embedding.dimension is trusted metadata."
        )


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    return value
