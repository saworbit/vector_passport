#!/usr/bin/env python3
"""
Vector Passport v1.0 - pgvector (PostgreSQL) Integration Demo.

Shows the recommended pattern for storing Vector Passports in a pgvector table:

    CREATE TABLE documents (
        id            BIGSERIAL PRIMARY KEY,
        text          TEXT,
        embedding     vector(8),
        passport      JSONB NOT NULL,
        -- Generated columns let the planner use a btree index for hot filters
        -- without giving up the full JSONB document for portability.
        embedding_model    TEXT GENERATED ALWAYS AS (passport->'embedding'->>'model') STORED,
        source_uri         TEXT GENERATED ALWAYS AS (passport->'source'->>'uri') STORED,
        source_hash        TEXT GENERATED ALWAYS AS (passport->'source'->>'hash') STORED,
        staleness_status   TEXT GENERATED ALWAYS AS (passport->'staleness'->>'status') STORED
    );

Filtering example:

    SELECT id, text
    FROM documents
    WHERE embedding_model = 'nomic-embed-text-v1.5'
      AND staleness_status = 'current';

Staleness check (client side): compare passport->'source'->>'hash' against the
current source hash, then UPDATE the row's `passport` jsonb (the generated
columns follow automatically).

By default this demo runs in DRY RUN mode: it prints the SQL it would execute
and simulates the queries in-memory so you can read the integration pattern
without setting up Postgres.

Run live (requires a running pgvector-enabled Postgres):
    pip install "psycopg[binary]" pgvector rich
    export DATABASE_URL=postgresql://user:pass@localhost:5432/vp_demo
    python examples/pgvector_integration.py --live
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
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
TABLE_NAME = "vector_passport_demo_documents"
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


SCHEMA_DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS {TABLE_NAME};

CREATE TABLE {TABLE_NAME} (
    id                BIGSERIAL PRIMARY KEY,
    text              TEXT NOT NULL,
    embedding         vector({DIMENSION}) NOT NULL,
    passport          JSONB NOT NULL,
    embedding_model   TEXT GENERATED ALWAYS AS (passport->'embedding'->>'model') STORED,
    source_uri        TEXT GENERATED ALWAYS AS (passport->'source'->>'uri') STORED,
    source_hash       TEXT GENERATED ALWAYS AS (passport->'source'->>'hash') STORED,
    staleness_status  TEXT GENERATED ALWAYS AS (passport->'staleness'->>'status') STORED
);

CREATE INDEX IF NOT EXISTS {TABLE_NAME}_model_idx ON {TABLE_NAME} (embedding_model);
CREATE INDEX IF NOT EXISTS {TABLE_NAME}_staleness_idx ON {TABLE_NAME} (staleness_status);
""".strip()


INSERT_SQL = f"""
INSERT INTO {TABLE_NAME} (text, embedding, passport)
VALUES (%(text)s, %(embedding)s, %(passport)s::jsonb)
""".strip()


FILTER_BY_MODEL_SQL = f"""
SELECT id, source_uri, embedding_model
FROM {TABLE_NAME}
WHERE embedding_model = %(model)s;
""".strip()


SELECT_ALL_SQL = f"""
SELECT id, source_uri, embedding_model, source_hash, passport
FROM {TABLE_NAME};
""".strip()


MARK_STALE_SQL = f"""
UPDATE {TABLE_NAME}
SET passport = jsonb_set(
    passport,
    '{{staleness}}',
    jsonb_build_object('status', 'stale', 'checked_at', %(checked_at)s, 'reason', 'source_hash_mismatch')
)
WHERE id = %(id)s;
""".strip()


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
            "metadata": {"heading": "Primary chunk"},
        },
        "embedding": {
            "model": model,
            "model_version": "1.5.0" if model == "nomic-embed-text-v1.5" else "2026-01-01",
            "provider": "nomic-ai" if model == "nomic-embed-text-v1.5" else "openai",
            "dimension": DIMENSION,
            "parameters": {"normalize": True, "pooling": "mean"},
        },
        "created_at": created_at,
        "created_by": "examples/pgvector_integration.py",
        "staleness": {"status": "current", "checked_at": created_at},
        "vector_hash": sha256_text(json.dumps(deterministic_vector(chunk_text), separators=(",", ":"))),
        "modality": "text",
        "lineage": [
            {
                "event": "initial_creation",
                "timestamp": created_at,
                "details": {"storage": "pgvector", "demo": True},
            }
        ],
        "signature": None,
        "extensions": {},
    }


def build_rows() -> tuple[list[dict[str, Any]], dict[str, str]]:
    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    rows = []
    current_hashes = {}

    for uri, doc in DOCUMENTS.items():
        passport = make_passport(uri, doc["embedded"], doc["model"], doc["mime_type"])
        validator.validate(passport)
        current_hashes[uri] = sha256_text(doc["current"])
        rows.append(
            {
                "text": doc["embedded"],
                "embedding": deterministic_vector(doc["embedded"]),
                "passport": passport,
            }
        )

    return rows, current_hashes


def shorten_hash(value: str) -> str:
    return value[:22] + "..."


def freshness_results_from_rows(
    rows: list[dict[str, Any]], current_hashes: dict[str, str]
) -> list[dict[str, str]]:
    results = []
    for row in rows:
        passport = row["passport"]
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


def print_freshness_table(results: list[dict[str, str]], title: str) -> None:
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title=title, show_lines=True)
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

    print(title)
    print("=" * 132)
    print(f"{'Document':<38} {'Model':<28} {'Stored Hash':<25} {'Current Hash':<25} {'Status':<8} Action")
    print("=" * 132)
    for result in results:
        print(
            f"{result['document']:<38} {result['model']:<28} {result['stored_hash']:<25} "
            f"{result['current_hash']:<25} {result['status']:<8} {result['action']}"
        )
    print("=" * 132)


def run_dry_run(rows: list[dict[str, Any]], current_hashes: dict[str, str]) -> int:
    print("Vector Passport + pgvector Integration Demo (DRY RUN)")
    print("=" * 64)
    print("This dry run prints the SQL a real pgvector pipeline would execute")
    print("and simulates the staleness check in memory. Pass --live with a")
    print("DATABASE_URL set to run against a real pgvector-enabled Postgres.\n")

    print("-- 1. Schema --")
    print(SCHEMA_DDL)
    print()

    print("-- 2. Inserting passports (one statement per row) --")
    print(INSERT_SQL)
    print()
    print(f"Would insert {len(rows)} rows. First passport (truncated):")
    sample = dict(rows[0]["passport"])
    sample.pop("lineage", None)
    print(json.dumps(sample, indent=2)[:600] + "\n  ...\n")

    print("-- 3. Filter by embedding model (uses generated-column index) --")
    print(FILTER_BY_MODEL_SQL)
    print(f"Would return {sum(1 for row in rows if row['passport']['embedding']['model'] == 'nomic-embed-text-v1.5')} "
          f"rows for model='nomic-embed-text-v1.5'.\n")

    print("-- 4. Staleness check (client-side compare + UPDATE) --")
    print(MARK_STALE_SQL)
    print()

    results = freshness_results_from_rows(rows, current_hashes)
    print_freshness_table(results, "Simulated Vector Freshness Check (pgvector)")

    stale_count = sum(1 for r in results if r["status"] == "STALE")
    print()
    print(f"Would issue {stale_count} UPDATE statements to mark stale rows.")
    print()
    print("Notes:")
    print("  - JSONB keeps the full passport. Generated columns expose the hot")
    print("    filter keys (embedding_model, source_uri, source_hash,")
    print("    staleness_status) for cheap btree lookups.")
    print("  - The full passport is the source of truth. Generated columns")
    print("    auto-update whenever the passport JSONB is rewritten.")
    return 0


def run_live(rows: list[dict[str, Any]], current_hashes: dict[str, str], dsn: str) -> int:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as error:
        print("--live requires psycopg. Install it with: pip install 'psycopg[binary]' pgvector", file=sys.stderr)
        raise SystemExit(1) from error

    try:
        from pgvector.psycopg import register_vector
    except ImportError as error:
        print("--live requires pgvector. Install it with: pip install pgvector", file=sys.stderr)
        raise SystemExit(1) from error

    print("Vector Passport + pgvector Integration Demo (LIVE)")
    print("=" * 64)
    print(f"Connecting to {dsn.split('@')[-1]}\n")

    with psycopg.connect(dsn, autocommit=True) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            for statement in SCHEMA_DDL.split(";"):
                statement = statement.strip()
                if statement:
                    cur.execute(statement)

            for row in rows:
                cur.execute(
                    INSERT_SQL,
                    {
                        "text": row["text"],
                        "embedding": row["embedding"],
                        "passport": Jsonb(row["passport"]),
                    },
                )
            print(f"Inserted {len(rows)} rows.\n")

            cur.execute(FILTER_BY_MODEL_SQL, {"model": "nomic-embed-text-v1.5"})
            nomic_rows = cur.fetchall()
            print(f"Filter by embedding_model='nomic-embed-text-v1.5': {len(nomic_rows)} rows.\n")

            cur.execute(SELECT_ALL_SQL)
            db_rows = cur.fetchall()

            results = []
            stale_ids = []
            for row in db_rows:
                row_id, source_uri, model, stored_hash, _passport_json = row
                current_hash = current_hashes[source_uri]
                stale = stored_hash != current_hash
                results.append(
                    {
                        "document": source_uri,
                        "model": model,
                        "stored_hash": shorten_hash(stored_hash),
                        "current_hash": shorten_hash(current_hash),
                        "status": "STALE" if stale else "FRESH",
                        "action": "RE-EMBED" if stale else "KEEP",
                    }
                )
                if stale:
                    stale_ids.append(row_id)

            print_freshness_table(results, "Vector Freshness Check (pgvector live)")

            for row_id in stale_ids:
                cur.execute(MARK_STALE_SQL, {"id": row_id, "checked_at": utc_now()})
            print(f"\nMarked {len(stale_ids)} rows as stale via UPDATE.")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vector Passport + pgvector integration demo")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run against a live Postgres at $DATABASE_URL (default: dry run)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, current_hashes = build_rows()

    if args.live:
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            print("--live requires DATABASE_URL to be set.", file=sys.stderr)
            return 1
        return run_live(rows, current_hashes, dsn)

    return run_dry_run(rows, current_hashes)


if __name__ == "__main__":
    raise SystemExit(main())
