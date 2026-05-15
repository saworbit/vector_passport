#!/usr/bin/env python3
"""
Vector Passport v1.0 - Chroma Integration Demo.

Shows the recommended pattern for storing Vector Passports in Chroma:

- The full passport is stored as a JSON string in metadata for portability.
- A handful of flat fields (embedding model, source URI, source hash,
  staleness status) are duplicated as top-level metadata keys so that
  Chroma's `where` filter can use them directly.

Chroma's metadata keys must be flat scalars (str, int, float, bool), so this
"full + flat" pattern is the idiomatic way to keep both portability and
queryability.

Run:
    pip install chromadb rich
    python examples/chroma_integration.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    import chromadb
except ImportError as error:  # pragma: no cover - user environment dependent.
    raise SystemExit("Install the Chroma demo dependency with: pip install chromadb") from error

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:
    Console = None
    Table = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "v1.0" / "schema.json"
COLLECTION_NAME = "company_docs_with_vector_passports"
DIMENSION = 8
RICH_AVAILABLE = Console is not None and Table is not None
CONSOLE = Console(width=132) if Console is not None else None


DOCUMENTS = {
    "s3://docs/q3-report.pdf": {
        "embedded": "Revenue grew 27% year-over-year. Operating margin improved to 18%.",
        "current": "Revenue grew 27% year-over-year. Operating margin improved to 18%. New AI initiative announced.",
        "model": "nomic-embed-text-v1.5",
        "mime_type": "application/pdf",
    },
    "s3://docs/product-roadmap-2026.md": {
        "embedded": "Our 2026 strategy focuses on agentic workflows and multimodal search.",
        "current": "Our 2026 strategy focuses on agentic workflows and multimodal search.",
        "model": "nomic-embed-text-v1.5",
        "mime_type": "text/markdown",
    },
    "s3://docs/security-policy-v2.pdf": {
        "embedded": "All employees must complete security training annually.",
        "current": "All employees must complete security training annually. Zero-trust controls are mandatory.",
        "model": "nomic-embed-text-v1.5",
        "mime_type": "application/pdf",
    },
    "s3://docs/hr-handbook.md": {
        "embedded": "Welcome to the team. Our values are trust, clarity, and ownership.",
        "current": "Welcome to the team. Our values are trust, clarity, and ownership.",
        "model": "text-embedding-3-small",
        "mime_type": "text/markdown",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_schema() -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def deterministic_vector(text: str, dimension: int = DIMENSION) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [round((digest[index % len(digest)] / 255.0) - 0.5, 6) for index in range(dimension)]


def make_passport(source_uri: str, embedded_content: str, model: str, mime_type: str) -> dict[str, Any]:
    created_at = utc_now()
    chunk_text = embedded_content[:500]

    return {
        "passport_version": "1.0",
        "vector_id": "vec-" + hashlib.sha256(source_uri.encode("utf-8")).hexdigest()[:16],
        "source": {
            "uri": source_uri,
            "hash": sha256_text(embedded_content),
            "last_modified": "2026-04-10T10:00:00Z",
            "mime_type": mime_type,
            "size_bytes": len(embedded_content.encode("utf-8")),
        },
        "chunk": {
            "id": "chunk-0000",
            "strategy": "recursive-character-512-50@1.0.0",
            "unit": "character",
            "start": 0,
            "end": len(chunk_text),
            "hash": sha256_text(chunk_text),
            "metadata": {
                "heading": "Primary chunk",
            },
        },
        "embedding": {
            "model": model,
            "model_version": "1.5.0" if model == "nomic-embed-text-v1.5" else "2026-01-01",
            "provider": "nomic-ai" if model == "nomic-embed-text-v1.5" else "openai",
            "dimension": DIMENSION,
            "parameters": {
                "normalize": True,
                "pooling": "mean",
            },
        },
        "created_at": created_at,
        "created_by": "examples/chroma_integration.py",
        "staleness": {
            "status": "current",
            "checked_at": created_at,
        },
        "vector_hash": sha256_text(json.dumps(deterministic_vector(chunk_text), separators=(",", ":"))),
        "modality": "text",
        "lineage": [
            {
                "event": "initial_creation",
                "timestamp": created_at,
                "details": {
                    "storage": "chroma",
                    "demo": True,
                },
            }
        ],
        "signature": None,
        "extensions": {},
    }


def flat_metadata(passport: dict[str, Any], text: str) -> dict[str, str | int | float | bool]:
    """Chroma metadata must be flat scalars. Duplicate filterable passport fields here."""
    return {
        "text": text,
        "passport_json": json.dumps(passport, separators=(",", ":"), sort_keys=True),
        "passport_embedding_model": passport["embedding"]["model"],
        "passport_source_uri": passport["source"]["uri"],
        "passport_source_hash": passport["source"]["hash"],
        "passport_staleness_status": passport["staleness"]["status"],
        "passport_modality": passport["modality"],
    }


def build_records() -> tuple[list[dict[str, Any]], dict[str, str]]:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    records = []
    current_hashes = {}

    for index, (uri, doc) in enumerate(DOCUMENTS.items()):
        passport = make_passport(uri, doc["embedded"], doc["model"], doc["mime_type"])
        validator.validate(passport)

        current_hashes[uri] = sha256_text(doc["current"])
        records.append(
            {
                "id": f"doc-{index}",
                "embedding": deterministic_vector(doc["embedded"]),
                "metadata": flat_metadata(passport, doc["embedded"]),
            }
        )

    return records, current_hashes


def populate_collection(collection: Any, records: list[dict[str, Any]]) -> None:
    collection.upsert(
        ids=[record["id"] for record in records],
        embeddings=[record["embedding"] for record in records],
        metadatas=[record["metadata"] for record in records],
    )


def find_by_model(collection: Any, model: str) -> dict[str, Any]:
    return collection.get(where={"passport_embedding_model": model})


def freshness_results(collection: Any, current_hashes: dict[str, str]) -> list[dict[str, str]]:
    records = collection.get()
    results = []

    for metadata in records["metadatas"]:
        passport = json.loads(metadata["passport_json"])
        source_uri = passport["source"]["uri"]
        stored_hash = passport["source"]["hash"]
        current_hash = current_hashes[source_uri]
        stale = stored_hash != current_hash
        results.append(
            {
                "document": source_uri,
                "model": passport["embedding"]["model"],
                "stored_hash": shorten_hash(stored_hash),
                "current_hash": shorten_hash(current_hash),
                "status": "STALE" if stale else "FRESH",
                "action": "RE-EMBED" if stale else "KEEP",
            }
        )

    return results


def shorten_hash(value: str) -> str:
    return value[:22] + "..."


def print_freshness_table(results: list[dict[str, str]]) -> None:
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title="Vector Freshness Check Using Passports In Chroma", show_lines=True)
        table.add_column("Document", style="cyan")
        table.add_column("Model", style="magenta")
        table.add_column("Stored Source Hash", style="dim")
        table.add_column("Current Source Hash", style="dim")
        table.add_column("Status", justify="center")
        table.add_column("Action", justify="center")

        for result in results:
            status = "[red]STALE[/red]" if result["status"] == "STALE" else "[green]FRESH[/green]"
            action = "[yellow]RE-EMBED[/yellow]" if result["action"] == "RE-EMBED" else "[green]KEEP[/green]"
            table.add_row(
                result["document"],
                result["model"],
                result["stored_hash"],
                result["current_hash"],
                status,
                action,
            )
        CONSOLE.print(table)
        return

    print("=" * 132)
    print(f"{'Document':<38} {'Model':<28} {'Stored Hash':<25} {'Current Hash':<25} {'Status':<8} Action")
    print("=" * 132)
    for result in results:
        print(
            f"{result['document']:<38} {result['model']:<28} {result['stored_hash']:<25} "
            f"{result['current_hash']:<25} {result['status']:<8} {result['action']}"
        )
    print("=" * 132)


def main() -> int:
    print("Vector Passport + Chroma Integration Demo")
    print("=" * 56)

    records, current_hashes = build_records()
    print(f"Created {len(records)} schema-valid passports.")

    client = chromadb.EphemeralClient()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    populate_collection(collection, records)
    print(f"Stored {len(records)} vectors with full passports in Chroma metadata.")

    print("\n1. Filter vectors by passport_embedding_model (flat metadata key)")
    nomic = find_by_model(collection, "nomic-embed-text-v1.5")
    print(f"Found {len(nomic['ids'])} vectors using nomic-embed-text-v1.5.")

    print("\n2. Detect stale vectors using passport.source.hash (from passport_json)")
    results = freshness_results(collection, current_hashes)
    print_freshness_table(results)

    stale_count = sum(1 for result in results if result["status"] == "STALE")
    fresh_count = len(results) - stale_count
    print("\nSummary")
    print("=" * 56)
    print(f"Total vectors checked: {len(results)}")
    print(f"Stale vectors:         {stale_count}")
    print(f"Fresh vectors:         {fresh_count}")
    print()
    print("Chroma stores flat metadata only, so the recommended pattern is:")
    print("  - Full passport as JSON in `passport_json`         (portability)")
    print("  - Filterable fields duplicated as flat keys        (queryability)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
