#!/usr/bin/env python3
"""
Vector Passport v1.0 - LanceDB Integration Demo.

This demo shows how Vector Passports work with LanceDB:

- vectors and passport metadata live in the same table
- passport fields can drive filtering and lifecycle decisions
- source hash comparison identifies stale vectors

For maximum compatibility across LanceDB versions, the demo stores each
passport as a JSON string column. Production systems may also store selected
passport fields as first-class columns for faster filtering.

Run:
    pip install lancedb rich
    python examples/lancedb_integration.py
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    import lancedb
except ImportError as error:  # pragma: no cover - user environment dependent.
    raise SystemExit("Install the LanceDB demo dependency with: pip install lancedb") from error

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:
    Console = None
    Table = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "v1.0" / "schema.json"
TABLE_NAME = "documents_with_vector_passports"
DIMENSION = 8
RICH_AVAILABLE = Console is not None and Table is not None
CONSOLE = Console(width=132) if Console is not None else None


DOCUMENTS = [
    {
        "uri": "s3://company-docs/q3-financial-report.pdf",
        "embedded": "Our revenue grew 27% year-over-year. Operating margin improved to 18%.",
        "current": "Our revenue grew 31% year-over-year. Operating margin improved to 19%.",
        "model": "nomic-embed-text-v1.5",
        "mime_type": "application/pdf",
    },
    {
        "uri": "s3://company-docs/product-roadmap-2026.pdf",
        "embedded": "Key initiatives for 2026 include AI platform modernization and multimodal search.",
        "current": "Key initiatives for 2026 include AI platform modernization and multimodal search.",
        "model": "nomic-embed-text-v1.5",
        "mime_type": "application/pdf",
    },
    {
        "uri": "s3://company-docs/security-policy-v2.pdf",
        "embedded": "All employees must complete security training annually.",
        "current": "All employees must complete security training annually. Hardware keys are now mandatory.",
        "model": "nomic-embed-text-v1.5",
        "mime_type": "application/pdf",
    },
    {
        "uri": "s3://company-docs/hr-handbook.md",
        "embedded": "Remote work policy updated January 2026.",
        "current": "Remote work policy updated January 2026.",
        "model": "text-embedding-3-small",
        "mime_type": "text/markdown",
    },
]


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


def make_passport(source_uri: str, source_content: str, model: str, mime_type: str) -> dict[str, Any]:
    created_at = utc_now()
    chunk_text = source_content[:500]

    return {
        "passport_version": "1.0",
        "vector_id": "vec-" + hashlib.sha256(source_uri.encode("utf-8")).hexdigest()[:16],
        "source": {
            "uri": source_uri,
            "hash": sha256_text(source_content),
            "last_modified": "2026-04-10T10:00:00Z",
            "mime_type": mime_type,
            "size_bytes": len(source_content.encode("utf-8")),
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
        "created_by": "examples/lancedb_integration.py",
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
                    "storage": "lancedb",
                    "demo": True,
                },
            }
        ],
        "signature": None,
        "extensions": {},
    }


def build_rows() -> tuple[list[dict[str, Any]], dict[str, str]]:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    rows = []
    current_hashes = {}

    for index, document in enumerate(DOCUMENTS):
        passport = make_passport(
            document["uri"],
            document["embedded"],
            document["model"],
            document["mime_type"],
        )
        validator.validate(passport)

        current_hashes[document["uri"]] = sha256_text(document["current"])
        rows.append(
            {
                "id": index,
                "vector": deterministic_vector(document["embedded"]),
                "text": document["embedded"],
                "source_uri": document["uri"],
                "embedding_model": passport["embedding"]["model"],
                "source_hash": passport["source"]["hash"],
                "passport_json": json.dumps(passport, separators=(",", ":"), sort_keys=True),
            }
        )

    return rows, current_hashes


def table_rows(table: Any) -> list[dict[str, Any]]:
    return table.search(deterministic_vector("query")).limit(100).to_list()


def filter_by_model(rows: list[dict[str, Any]], model: str) -> list[dict[str, str]]:
    filtered = []
    for row in rows:
        passport = json.loads(row["passport_json"])
        if passport["embedding"]["model"] == model:
            filtered.append(
                {
                    "document": Path(passport["source"]["uri"]).name,
                    "model": passport["embedding"]["model"],
                    "source": passport["source"]["uri"],
                }
            )
    return filtered


def freshness_results(rows: list[dict[str, Any]], current_hashes: dict[str, str]) -> list[dict[str, str]]:
    results = []
    for row in rows:
        passport = json.loads(row["passport_json"])
        source_uri = passport["source"]["uri"]
        stored_hash = passport["source"]["hash"]
        current_hash = current_hashes[source_uri]
        stale = stored_hash != current_hash
        results.append(
            {
                "document": Path(source_uri).name,
                "stored_hash": shorten_hash(stored_hash),
                "current_hash": shorten_hash(current_hash),
                "status": "STALE" if stale else "FRESH",
                "action": "RE-EMBED" if stale else "KEEP",
            }
        )
    return results


def shorten_hash(value: str) -> str:
    return value[:22] + "..."


def print_filter_results(rows: list[dict[str, str]], model: str) -> None:
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title=f"Filtering By Passport Embedding Model: {model}", show_lines=True)
        table.add_column("Document", style="cyan")
        table.add_column("Embedding Model", style="magenta")
        table.add_column("Source URI", style="dim")
        for row in rows:
            table.add_row(row["document"], row["model"], row["source"])
        CONSOLE.print(table)
        return

    print(f"Filtering By Passport Embedding Model: {model}")
    print("=" * 104)
    print(f"{'Document':<32} {'Embedding Model':<28} Source URI")
    print("=" * 104)
    for row in rows:
        print(f"{row['document']:<32} {row['model']:<28} {row['source']}")
    print("=" * 104)


def print_freshness_results(results: list[dict[str, str]]) -> None:
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title="Source Change Detection Using LanceDB + Passports", show_lines=True)
        table.add_column("Document", style="cyan")
        table.add_column("Stored Source Hash", style="dim")
        table.add_column("Current Source Hash", style="dim")
        table.add_column("Status", justify="center")
        table.add_column("Action", justify="center")
        for result in results:
            status = "[red]STALE[/red]" if result["status"] == "STALE" else "[green]FRESH[/green]"
            action = "[yellow]RE-EMBED[/yellow]" if result["action"] == "RE-EMBED" else "[green]KEEP[/green]"
            table.add_row(result["document"], result["stored_hash"], result["current_hash"], status, action)
        CONSOLE.print(table)
        return

    print("Source Change Detection Using LanceDB + Passports")
    print("=" * 104)
    print(f"{'Document':<32} {'Stored Hash':<25} {'Current Hash':<25} {'Status':<8} Action")
    print("=" * 104)
    for result in results:
        print(
            f"{result['document']:<32} {result['stored_hash']:<25} {result['current_hash']:<25} "
            f"{result['status']:<8} {result['action']}"
        )
    print("=" * 104)


def main() -> int:
    print("LanceDB + Vector Passport Integration Demo")
    print("=" * 56)

    rows, current_hashes = build_rows()

    with tempfile.TemporaryDirectory(prefix="vector-passport-lancedb-") as directory:
        db = lancedb.connect(directory)
        table = db.create_table(TABLE_NAME, rows, mode="overwrite")
        print(f"Created LanceDB table '{TABLE_NAME}' with {len(rows)} vector rows.")

        loaded_rows = table_rows(table)
        print("Stored each full passport in the 'passport_json' metadata column.")

        print("\n1. Filter vectors using passport metadata")
        model_matches = filter_by_model(loaded_rows, "nomic-embed-text-v1.5")
        print_filter_results(model_matches, "nomic-embed-text-v1.5")

        print("\n2. Detect stale vectors using passport source hashes")
        freshness = freshness_results(loaded_rows, current_hashes)
        print_freshness_results(freshness)

        stale_count = sum(1 for row in freshness if row["status"] == "STALE")
        fresh_count = len(freshness) - stale_count

    print("\nSummary")
    print("=" * 56)
    print(f"Total vectors checked: {len(rows)}")
    print(f"Stale vectors:         {stale_count}")
    print(f"Fresh vectors:         {fresh_count}")
    print()
    print("LanceDB is a strong fit because vectors and rich metadata can live together")
    print("in an embedded, local-first, columnar store. Passports provide the portable")
    print("contract that makes those rows understandable across systems.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
