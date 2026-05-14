#!/usr/bin/env python3
"""
Vector Passport v1.0 - Model Upgrade Use Case Demo.

Scenario:
- Existing vectors were created with nomic-embed-text-v1.5.
- A better model, nomic-embed-text-v2, is now available.
- Some source documents changed after the original embedding run.

Without passports, teams often re-embed everything.
With passports, teams can make targeted decisions.

Run:
    python examples/model_upgrade_demo.py
"""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from dataclasses import dataclass
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
CONSOLE = Console(width=140) if Console is not None else None


@dataclass(frozen=True)
class SourceScenario:
    file_name: str
    section: str
    source_changed: bool
    business_priority: str


SCENARIOS = [
    SourceScenario("Q3-financial-report.pdf", "Revenue Summary", False, "high"),
    SourceScenario("Q3-financial-report.pdf", "Challenges", True, "high"),
    SourceScenario("product-roadmap-2026.md", "AI Features", False, "high"),
    SourceScenario("security-policy-v2.pdf", "Data Handling", False, "medium"),
    SourceScenario("security-policy-v2.pdf", "Access Control", True, "critical"),
    SourceScenario("customer-interviews-q3.txt", "Key Insights", False, "medium"),
    SourceScenario("marketing-strategy.pdf", "Q4 Campaigns", False, "low"),
    SourceScenario("engineering-handbook.md", "Architecture", False, "medium"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_schema() -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def create_simulated_passports() -> tuple[list[dict[str, Any]], dict[str, str]]:
    passports = []
    current_source_hashes: dict[str, str] = {}
    created_at = "2026-04-12T09:15:00Z"
    generator = random.Random(42)

    for index, scenario in enumerate(SCENARIOS):
        original_source_hash = sha256_text(f"{scenario.file_name}:original")
        current_source_hashes[scenario.file_name] = (
            sha256_text(f"{scenario.file_name}:modified") if scenario.source_changed else original_source_hash
        )

        start = generator.randint(100, 4500)
        end = start + generator.randint(400, 900)
        chunk_payload = f"{scenario.file_name}:{scenario.section}:{start}:{end}"

        passports.append(
            {
                "passport_version": "1.0",
                "vector_id": str(uuid.uuid4()),
                "source": {
                    "uri": f"s3://company-docs/{scenario.file_name}",
                    "hash": original_source_hash,
                    "last_modified": "2026-04-10T10:00:00Z",
                    "mime_type": infer_mime_type(scenario.file_name),
                    "size_bytes": generator.randint(20_000, 2_000_000),
                },
                "chunk": {
                    "id": f"chunk-{index:04d}",
                    "strategy": "recursive-character-512-50@1.0.0",
                    "unit": "character",
                    "start": start,
                    "end": end,
                    "hash": sha256_text(chunk_payload),
                    "metadata": {
                        "section": scenario.section,
                        "business_priority": scenario.business_priority,
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
                "vector_hash": sha256_text(f"vector:{index}"),
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
        )

    return passports, current_source_hashes


def infer_mime_type(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".txt":
        return "text/plain"
    return "application/octet-stream"


def validate_passports(passports: list[dict[str, Any]]) -> None:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    for passport in passports:
        validator.validate(passport)


def analyze_for_model_upgrade(
    passports: list[dict[str, Any]],
    current_source_hashes: dict[str, str],
    target_model: str = "nomic-embed-text-v2",
) -> list[dict[str, Any]]:
    results = []

    for passport in passports:
        file_name = Path(passport["source"]["uri"]).name
        current_hash = current_source_hashes[file_name]
        source_changed = current_hash != passport["source"]["hash"]
        priority = passport["chunk"]["metadata"].get("business_priority", "medium")
        current_model = passport["embedding"]["model"]

        if source_changed:
            recommendation = "RE-EMBED"
            reason = "Source file hash changed since this vector was created."
        elif current_model != target_model and priority in {"critical", "high"}:
            recommendation = "RE-EMBED FOR QUALITY"
            reason = "High-priority chunk should move to the better model."
        elif current_model != target_model:
            recommendation = "KEEP VALID"
            reason = "Source is current. Defer model upgrade until quality gains justify the cost."
        else:
            recommendation = "KEEP"
            reason = "Source and target model already match."

        results.append(
            {
                "file": file_name,
                "section": passport["chunk"]["metadata"].get("section", ""),
                "priority": priority,
                "source_changed": source_changed,
                "recommendation": recommendation,
                "reason": reason,
            }
        )

    return results


def print_analysis_table(results: list[dict[str, Any]]) -> None:
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title="Model Upgrade Analysis: nomic-embed-text-v1.5 -> v2", show_lines=True)
        table.add_column("File", style="cyan")
        table.add_column("Section", style="magenta")
        table.add_column("Priority", justify="center")
        table.add_column("Source Changed?", justify="center")
        table.add_column("Recommendation", style="bold")
        table.add_column("Reason")

        for result in results:
            changed = "[red]Yes[/red]" if result["source_changed"] else "[green]No[/green]"
            table.add_row(
                result["file"],
                result["section"],
                result["priority"],
                changed,
                color_recommendation(result["recommendation"]),
                result["reason"],
            )
        CONSOLE.print(table)
        return

    print("=" * 132)
    print(f"{'File':<30} {'Section':<18} {'Priority':<10} {'Changed?':<10} {'Recommendation':<22} Reason")
    print("=" * 132)
    for result in results:
        changed = "Yes" if result["source_changed"] else "No"
        print(
            f"{result['file']:<30} {result['section']:<18} {result['priority']:<10} "
            f"{changed:<10} {result['recommendation']:<22} {result['reason']}"
        )
    print("=" * 132)


def color_recommendation(value: str) -> str:
    colors = {
        "RE-EMBED": "[red]RE-EMBED[/red]",
        "RE-EMBED FOR QUALITY": "[yellow]RE-EMBED FOR QUALITY[/yellow]",
        "KEEP VALID": "[green]KEEP VALID[/green]",
        "KEEP": "[green]KEEP[/green]",
    }
    return colors.get(value, value)


def print_summary(results: list[dict[str, Any]]) -> None:
    total = len(results)
    must_reembed = sum(1 for result in results if result["recommendation"] == "RE-EMBED")
    quality_reembed = sum(1 for result in results if result["recommendation"] == "RE-EMBED FOR QUALITY")
    keep_valid = sum(1 for result in results if result["recommendation"] == "KEEP VALID")
    keep = sum(1 for result in results if result["recommendation"] == "KEEP")
    targeted_reembed_count = must_reembed + quality_reembed
    avoided = total - targeted_reembed_count

    print("\nSummary")
    print("=" * 80)
    print(f"Blind model-upgrade approach: re-embed all {total} vectors.")
    print(f"Passport-driven approach: re-embed {targeted_reembed_count} now.")
    print(f"Immediate re-embedding avoided: {avoided} vectors.")
    print()
    print(f"Must re-embed because source changed: {must_reembed}")
    print(f"Re-embed for quality because priority is high: {quality_reembed}")
    print(f"Still valid, defer model upgrade: {keep_valid}")
    print(f"Already on target model, keep as-is: {keep}")
    print("=" * 80)


def main() -> int:
    print("Vector Passport - Model Upgrade Use Case Demo")
    print("=" * 60)
    print("Scenario: existing vectors were created with nomic-embed-text-v1.5.")
    print("A better model, nomic-embed-text-v2, is now available.")
    print("Some source documents changed after the original embedding run.\n")

    print("1. Creating simulated existing passports...")
    passports, current_source_hashes = create_simulated_passports()
    print(f"   Created {len(passports)} passports.")

    print("2. Validating passports against the canonical schema...")
    validate_passports(passports)
    print(f"   Schema: {SCHEMA_PATH}")
    print("   Result: valid")

    print("3. Analyzing model-upgrade decisions...")
    results = analyze_for_model_upgrade(passports, current_source_hashes)
    print_analysis_table(results)
    print_summary(results)

    print("\nKey insight")
    print("=" * 80)
    print("Without passports, the safe default is to re-embed everything.")
    print("With passports, you can separate mandatory re-embedding from optional quality upgrades.")
    print("That is the difference between a blunt migration and a managed vector lifecycle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
