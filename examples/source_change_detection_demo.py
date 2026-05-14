#!/usr/bin/env python3
"""
Vector Passport v1.0 - Source File Change Detection Demo.

This demo shows a common production RAG problem:

You embedded documents months ago. Some source documents changed later.
Which existing vectors are now stale?

Without passports, teams often re-embed everything to be safe.
With passports, teams can compare the stored source hash with the current
source hash and refresh only affected vectors.

Run:
    python examples/source_change_detection_demo.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:
    Console = None
    Table = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "v1.0" / "schema.json"
RICH_AVAILABLE = Console is not None and Table is not None
CONSOLE = Console(width=120) if Console is not None else None


DOCUMENTS = {
    "q3-financial-report": {
        "original": "Revenue grew 27% year-over-year. Operating margin improved to 18%.",
        "current": "Revenue grew 27% year-over-year. Operating margin improved to 18%. New AI initiative announced.",
        "mime_type": "text/markdown",
    },
    "product-roadmap-2026": {
        "original": "Key initiatives: Agentic workflows, multimodal search, and enterprise security.",
        "current": "Key initiatives: Agentic workflows, multimodal search, and enterprise security. Q4 focus: cost optimization.",
        "mime_type": "text/markdown",
    },
    "security-policy-v2": {
        "original": "All customer data must be encrypted at rest using AES-256.",
        "current": "All customer data must be encrypted at rest using AES-256. Zero-trust architecture is now mandatory.",
        "mime_type": "application/pdf",
    },
    "hr-handbook": {
        "original": "Remote work policy updated January 2025.",
        "current": "Remote work policy updated January 2025.",
        "mime_type": "text/markdown",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_schema() -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def create_sample_passport(doc_name: str, chunk_id: int, original_content: str, mime_type: str) -> dict[str, Any]:
    created_at = "2025-01-15T10:05:00Z"
    chunk_start = 100 * chunk_id
    chunk_end = chunk_start + 80
    chunk_text = f"{doc_name}: chunk {chunk_id}: {original_content}"

    return {
        "passport_version": "1.0",
        "vector_id": f"vec-{doc_name}-{chunk_id}",
        "source": {
            "uri": f"s3://company-docs/{doc_name}.md",
            "hash": compute_hash(original_content),
            "last_modified": "2025-01-15T10:00:00Z",
            "mime_type": mime_type,
            "size_bytes": len(original_content.encode("utf-8")),
        },
        "chunk": {
            "id": f"{doc_name}-chunk-{chunk_id}",
            "strategy": "recursive-character-512-50@1.0.0",
            "unit": "character",
            "start": chunk_start,
            "end": chunk_end,
            "hash": compute_hash(chunk_text),
            "metadata": {
                "heading": f"Section {chunk_id + 1}",
                "document": doc_name,
            },
        },
        "embedding": {
            "model": "nomic-embed-text-v1.5",
            "model_version": "1.5.0",
            "provider": "nomic-ai",
            "dimension": 768,
            "parameters": {
                "normalize": True,
                "pooling": "mean",
            },
        },
        "created_at": created_at,
        "created_by": "legacy-ingestion-pipeline-v1",
        "staleness": {
            "status": "current",
            "checked_at": created_at,
        },
        "vector_hash": compute_hash(f"vector:{doc_name}:{chunk_id}"),
        "modality": "text",
        "lineage": [
            {
                "event": "initial_creation",
                "timestamp": created_at,
                "details": {
                    "pipeline_version": "1.0.0",
                },
            }
        ],
        "signature": None,
        "extensions": {},
    }


def create_existing_passports() -> list[tuple[str, dict[str, Any]]]:
    passports = []
    for doc_name, content in DOCUMENTS.items():
        for chunk_id in range(2):
            passports.append(
                (
                    doc_name,
                    create_sample_passport(
                        doc_name,
                        chunk_id,
                        content["original"],
                        content["mime_type"],
                    ),
                )
            )
    return passports


def validate_passports(passports: list[tuple[str, dict[str, Any]]]) -> None:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    for _, passport in passports:
        validator.validate(passport)


def detect_source_changes(passports: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    results = []
    for doc_name, passport in passports:
        original_hash = passport["source"]["hash"]
        current_hash = compute_hash(DOCUMENTS[doc_name]["current"])
        is_stale = original_hash != current_hash

        results.append(
            {
                "document": doc_name,
                "chunk": passport["chunk"]["metadata"]["heading"],
                "original_hash": shorten_hash(original_hash),
                "current_hash": shorten_hash(current_hash),
                "status": "STALE" if is_stale else "FRESH",
                "action": "RE-EMBED" if is_stale else "KEEP",
            }
        )
    return results


def shorten_hash(value: str) -> str:
    return value[:22] + "..."


def print_results(results: list[dict[str, Any]]) -> None:
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title="Source File Change Detection Results", show_lines=True)
        table.add_column("Document", style="cyan")
        table.add_column("Chunk", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Action", justify="center")
        table.add_column("Stored Source Hash", style="dim")
        table.add_column("Current Source Hash", style="dim")

        for result in results:
            status = "[red]STALE[/red]" if result["status"] == "STALE" else "[green]FRESH[/green]"
            action = "[yellow]RE-EMBED[/yellow]" if result["action"] == "RE-EMBED" else "[green]KEEP[/green]"
            table.add_row(
                result["document"],
                result["chunk"],
                status,
                action,
                result["original_hash"],
                result["current_hash"],
            )
        CONSOLE.print(table)
        return

    print("=" * 112)
    print(f"{'Document':<28} {'Chunk':<12} {'Status':<10} {'Action':<10} {'Stored Hash':<25} Current Hash")
    print("=" * 112)
    for result in results:
        print(
            f"{result['document']:<28} {result['chunk']:<12} {result['status']:<10} "
            f"{result['action']:<10} {result['original_hash']:<25} {result['current_hash']}"
        )
    print("=" * 112)


def print_summary(results: list[dict[str, Any]]) -> None:
    stale_count = sum(1 for result in results if result["status"] == "STALE")
    fresh_count = len(results) - stale_count

    print("\nSummary")
    print("=" * 80)
    print(f"Total vectors analyzed: {len(results)}")
    print(f"Fresh, still valid:     {fresh_count}")
    print(f"Stale, source changed:  {stale_count}")
    print()
    print("Without Vector Passports, the safe fallback is often to re-embed everything.")
    print(f"With passports, this run avoids re-embedding {fresh_count} vectors immediately.")
    print("The decision is driven by provenance: stored source.hash vs current source hash.")
    print("=" * 80)


def main() -> int:
    print("Vector Passport - Source File Change Detection Demo")
    print("=" * 64)
    print("Scenario: documents were embedded months ago with nomic-embed-text-v1.5.")
    print("Some source documents have since been edited by the business.")
    print("Question: which existing vectors are now stale?\n")

    print("1. Creating existing passports...")
    passports = create_existing_passports()
    print(f"   Created {len(passports)} passports across {len(DOCUMENTS)} source documents.")

    print("2. Validating passports against the canonical schema...")
    validate_passports(passports)
    print(f"   Schema: {SCHEMA_PATH}")
    print("   Result: valid")

    print("3. Comparing stored source hashes with current source hashes...")
    results = detect_source_changes(passports)
    print_results(results)
    print_summary(results)

    print("\nKey insight")
    print("=" * 80)
    print("Vector Passports turn stale-vector detection into a deterministic hash comparison.")
    print("That is what enables targeted re-embedding instead of expensive blanket refreshes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
