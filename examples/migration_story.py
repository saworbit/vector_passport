#!/usr/bin/env python3
"""
The Migration Story - Vector Passport Flagship Demo.

A guided, single-script tour that tells the end-to-end story behind the
Vector Passport specification:

    Act 1  Setup           Ingest documents into Qdrant with full passports.
    Act 2  The Pain        Show what migration looks like WITHOUT passports.
    Act 3  The Switch      Move Qdrant -> LanceDB with provenance intact.
    Act 4  Model Upgrade   Upgrade v1.5 -> v2, re-embedding only what needs it.
    Act 5  The Win         Powerful queries you can now answer in one lookup.
    Final  Summary         Before vs After table.

The demo runs entirely offline (Qdrant :memory:, LanceDB in a temp dir,
deterministic simulated embeddings) and finishes in a few seconds.

Run:
    pip install -r requirements.txt
    python examples/migration_story.py
"""

from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
except ImportError as error:  # pragma: no cover - user environment dependent.
    raise SystemExit(
        "The migration story needs qdrant-client. Install with: pip install -r requirements.txt"
    ) from error

try:
    import lancedb
except ImportError as error:  # pragma: no cover - user environment dependent.
    raise SystemExit(
        "The migration story needs lancedb. Install with: pip install -r requirements.txt"
    ) from error

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    Console = None
    Panel = None
    Table = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "v1.0" / "schema.json"
QDRANT_COLLECTION = "migration_story_qdrant"
LANCEDB_TABLE = "migration_story_lancedb"
DIMENSION = 8
RICH_AVAILABLE = Console is not None and Table is not None and Panel is not None
CONSOLE = Console(width=132) if Console is not None else None

LEGACY_MODEL = "nomic-embed-text-v1.5"
TARGET_MODEL = "nomic-embed-text-v2"
THIRD_PARTY_MODEL = "text-embedding-3-small"


# The corpus. `embedded` is what the original ingest run saw; `current` is
# what the source looks like today (some documents have drifted).
DOCUMENTS = [
    {
        "uri": "s3://corp/q3-financial-report.pdf",
        "mime_type": "application/pdf",
        "section": "Revenue Summary",
        "priority": "high",
        "embedded": (
            "Q3 revenue grew 27% year-over-year to $48.2M. "
            "Operating margin improved to 18%."
        ),
        "current": (
            "Q3 revenue grew 31% year-over-year to $50.1M. "
            "Operating margin improved to 19%. Restated after audit."
        ),
        "model": LEGACY_MODEL,
    },
    {
        "uri": "s3://corp/product-roadmap-2026.md",
        "mime_type": "text/markdown",
        "section": "AI Platform",
        "priority": "high",
        "embedded": "2026 roadmap: agentic workflows, multimodal search, on-device inference.",
        "current": "2026 roadmap: agentic workflows, multimodal search, on-device inference.",
        "model": LEGACY_MODEL,
    },
    {
        "uri": "s3://corp/security-policy-v2.pdf",
        "mime_type": "application/pdf",
        "section": "Access Control",
        "priority": "critical",
        "embedded": "All employees must complete annual security training.",
        "current": (
            "All employees must complete annual security training. "
            "Hardware security keys are now mandatory for production access."
        ),
        "model": LEGACY_MODEL,
    },
    {
        "uri": "s3://corp/hr-handbook.md",
        "mime_type": "text/markdown",
        "section": "Remote Work",
        "priority": "low",
        "embedded": "Remote work policy updated January 2026.",
        "current": "Remote work policy updated January 2026.",
        "model": THIRD_PARTY_MODEL,
    },
    {
        "uri": "s3://corp/customer-faq.md",
        "mime_type": "text/markdown",
        "section": "General FAQ",
        "priority": "low",
        "embedded": "How do I reset my password? Visit account settings and follow the prompts.",
        "current": "How do I reset my password? Visit account settings and follow the prompts.",
        "model": LEGACY_MODEL,
    },
]


# ---------------------------------------------------------------------------
# Narration helpers
# ---------------------------------------------------------------------------

def banner(text: str) -> None:
    line = "=" * max(58, len(text) + 4)
    print(f"\n{line}\n {text}\n{line}")


def act(number: int, title: str, subtitle: str) -> None:
    header = f"Act {number}: {title}"
    if RICH_AVAILABLE and CONSOLE is not None and Panel is not None:
        CONSOLE.print()
        CONSOLE.print(Panel.fit(f"[bold]{header}[/bold]\n[dim]{subtitle}[/dim]", border_style="cyan"))
        return
    banner(header)
    print(subtitle)


def narrate(text: str) -> None:
    for line in textwrap.wrap(text, width=96):
        print(f"  {line}")


# ---------------------------------------------------------------------------
# Passport + embedding helpers (self-contained, deterministic)
# ---------------------------------------------------------------------------

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def deterministic_vector(text: str, model: str, dimension: int = DIMENSION) -> list[float]:
    # Different model => different vector. Bake the model name into the seed so
    # "re-embedding under v2" actually produces a different vector_hash.
    digest = hashlib.sha256(f"{model}::{text}".encode("utf-8")).digest()
    return [round((digest[index % len(digest)] / 255.0) - 0.5, 6) for index in range(dimension)]


def hash_vector(values: list[float]) -> str:
    payload = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return sha256_text("") if not values else "sha256:" + hashlib.sha256(payload).hexdigest()


def to_storage_precision(vector: list[float]) -> list[float]:
    # LanceDB persists vectors as float32. Round each value through f32 so the
    # values we hash match the values LanceDB returns on read. Without this, a
    # freshly-generated f64 vector and its f32-stored counterpart have different
    # JSON reprs, and passport.vector_hash drifts away from the readback.
    # Explicit little-endian for deterministic round-trip across platforms.
    return [struct.unpack("<f", struct.pack("<f", value))[0] for value in vector]


def reconcile_vector_hash(
    passport: dict[str, Any],
    actual_vector: list[float],
    *,
    transformation: str,
    during: str,
    validator: Draft202012Validator,
) -> tuple[dict[str, Any], bool]:
    """Ensure passport.vector_hash describes actual_vector.

    Returns (possibly-updated passport, was_reconciled). When the existing hash
    already matches, the passport is returned unchanged. Otherwise the hash is
    updated and a 'representation_change' lineage event is appended so the
    transformation is auditable. The returned passport is always re-validated
    against the schema before return, regardless of branch, so callers can rely
    on a schema-valid result without pre-validating themselves.
    """
    actual_hash = hash_vector(actual_vector)
    if actual_hash == passport["vector_hash"]:
        validator.validate(passport)
        return passport, False
    reconciled = dict(passport)
    reconciled["lineage"] = list(reconciled.get("lineage", [])) + [
        {
            "event": "representation_change",
            "timestamp": utc_now(),
            "details": {
                "from_hash": reconciled["vector_hash"],
                "to_hash": actual_hash,
                "transformation": transformation,
                "during": during,
            },
        }
    ]
    reconciled["vector_hash"] = actual_hash
    validator.validate(reconciled)
    return reconciled, True


def load_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def stable_vector_id(uri: str) -> str:
    return "vec-" + hashlib.sha256(uri.encode("utf-8")).hexdigest()[:16]


def make_passport(document: dict[str, Any], model: str) -> dict[str, Any]:
    created_at = utc_now()
    chunk_text = document["embedded"][:500]
    vector = deterministic_vector(chunk_text, model)
    provider = "nomic-ai" if model.startswith("nomic-") else "openai"
    model_version = "1.5.0" if model == LEGACY_MODEL else ("2.0.0" if model == TARGET_MODEL else "2026-01-01")

    return {
        "passport_version": "1.0",
        "vector_id": stable_vector_id(document["uri"]),
        "source": {
            "uri": document["uri"],
            "hash": sha256_text(document["embedded"]),
            "last_modified": "2026-04-10T10:00:00Z",
            "mime_type": document["mime_type"],
            "size_bytes": len(document["embedded"].encode("utf-8")),
        },
        "chunk": {
            "id": "chunk-0000",
            "strategy": "recursive-character-512-50@1.0.0",
            "unit": "character",
            "start": 0,
            "end": len(chunk_text),
            "hash": sha256_text(chunk_text),
            "metadata": {
                "section": document["section"],
                "business_priority": document["priority"],
            },
        },
        "embedding": {
            "model": model,
            "model_version": model_version,
            "provider": provider,
            "dimension": DIMENSION,
            "parameters": {"normalize": True, "pooling": "mean"},
        },
        "created_at": created_at,
        "created_by": "examples/migration_story.py",
        "staleness": {"status": "current", "checked_at": created_at},
        "vector_hash": hash_vector(vector),
        "modality": "text",
        "lineage": [
            {
                "event": "initial_creation",
                "timestamp": created_at,
                "details": {"pipeline": "migration-story", "act": 1},
            }
        ],
        "signature": None,
        "extensions": {},
    }


# ---------------------------------------------------------------------------
# Act 1: Setup
# ---------------------------------------------------------------------------

def act1_ingest_into_qdrant(validator: Draft202012Validator) -> tuple[QdrantClient, dict[str, str]]:
    act(
        1,
        "Setup - ingest documents into Qdrant with Vector Passports",
        "We start where most RAG systems live today: vectors in a vector DB, plus rich provenance.",
    )

    client = QdrantClient(":memory:")
    if client.collection_exists(QDRANT_COLLECTION):
        client.delete_collection(QDRANT_COLLECTION)
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=DIMENSION, distance=Distance.COSINE),
    )

    points: list[PointStruct] = []
    current_hashes: dict[str, str] = {}
    for index, document in enumerate(DOCUMENTS):
        passport = make_passport(document, document["model"])
        validator.validate(passport)
        vector = deterministic_vector(document["embedded"][:500], document["model"])
        current_hashes[document["uri"]] = sha256_text(document["current"])
        points.append(
            PointStruct(
                id=index,
                vector=vector,
                payload={"text": document["embedded"], "passport": passport},
            )
        )

    client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    narrate(
        f"Ingested {len(points)} documents into Qdrant. Each point carries a "
        f"schema-valid Vector Passport in its payload (source URI, source hash, chunk span, "
        f"embedding model, model version, vector hash, lineage)."
    )
    return client, current_hashes


# ---------------------------------------------------------------------------
# Act 2: The Pain Moment
# ---------------------------------------------------------------------------

def act2_pain_without_passports(client: QdrantClient) -> None:
    act(
        2,
        "The Pain - what migration looks like WITHOUT Vector Passports",
        "Imagine the same vectors were stored with no provenance. Just floats and raw text.",
    )

    stored, _ = client.scroll(collection_name=QDRANT_COLLECTION, with_payload=True, with_vectors=True, limit=100)
    naked_rows = [
        {"text": point.payload["text"], "vector_preview": list(point.vector)[:3]}
        for point in stored
    ]

    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title="What you would migrate without passports", show_lines=True, border_style="red")
        table.add_column("Text", style="white", overflow="fold")
        table.add_column("Vector (first 3 dims)", style="dim")
        for row in naked_rows:
            table.add_row(row["text"], json.dumps(row["vector_preview"]))
        CONSOLE.print(table)
    else:
        print("\nWhat you would migrate without passports:")
        for row in naked_rows:
            print(f"  - {row['text'][:70]:<70}  vec={row['vector_preview']}")

    narrate(
        "Without passports, the receiving system has no idea which model produced these vectors, "
        "which source file they came from, whether the source has changed since, or which chunk span "
        "they cover. The safe default is to throw them away and re-embed everything from scratch."
    )
    questions = [
        '"Which embedding model produced this vector?"            -> UNKNOWN',
        '"Which source file does this vector represent?"          -> UNKNOWN',
        '"Has the source changed since this was embedded?"        -> UNKNOWABLE',
        '"Can I move this to LanceDB without losing context?"     -> NO',
    ]
    print()
    for question in questions:
        print(f"  {question}")


# ---------------------------------------------------------------------------
# Act 3: The Switch (Qdrant -> LanceDB)
# ---------------------------------------------------------------------------

def act3_migrate_to_lancedb(
    client: QdrantClient,
    validator: Draft202012Validator,
    workdir: Path,
) -> Any:
    act(
        3,
        "The Switch - migrate Qdrant -> LanceDB with provenance intact",
        "The passport travels with the vector. Nothing is rebuilt; nothing is lost.",
    )

    stored, _ = client.scroll(collection_name=QDRANT_COLLECTION, with_payload=True, with_vectors=True, limit=100)
    rows: list[dict[str, Any]] = []
    bit_exact = 0
    reconciled = 0
    for index, point in enumerate(stored):
        passport = dict(point.payload["passport"])
        validator.validate(passport)  # passport still valid on the way out
        stored_vector = [float(value) for value in point.vector]

        # Qdrant returns vectors in its own representation (cosine collections
        # normalize on write, vectors are stored as float32). The vector landing
        # in LanceDB is not the vector hashed at creation. Reconcile so the
        # passport describes what we are actually storing.
        passport, was_reconciled = reconcile_vector_hash(
            passport,
            stored_vector,
            transformation="qdrant_cosine_normalized_float32_cast",
            during="qdrant_to_lancedb_migration",
            validator=validator,
        )
        if was_reconciled:
            reconciled += 1
        else:
            bit_exact += 1

        rows.append(
            {
                "id": index,
                "vector": stored_vector,
                "text": point.payload["text"],
                "vector_id": passport["vector_id"],
                "source_uri": passport["source"]["uri"],
                "embedding_model": passport["embedding"]["model"],
                "source_hash": passport["source"]["hash"],
                "passport_json": json.dumps(passport, separators=(",", ":"), sort_keys=True),
            }
        )

    db = lancedb.connect(str(workdir))
    table = db.create_table(LANCEDB_TABLE, rows, mode="overwrite")

    narrate(
        f"Migrated {len(rows)} vectors from Qdrant to LanceDB. Every passport was re-validated "
        f"against the canonical schema before and after the move. "
        f"{bit_exact} vectors round-tripped bit-exact; {reconciled} had their representation rewritten "
        f"by Qdrant (cosine normalization + float32 storage). For those, the migration updated "
        f"vector_hash to describe the values being stored and appended a 'representation_change' "
        f"lineage event so the transformation is auditable - the integrity claim always describes "
        f"the stored vector values."
    )
    return table


# ---------------------------------------------------------------------------
# Act 4: Model upgrade with smart partial re-embedding
# ---------------------------------------------------------------------------

def demo_rows(table: Any) -> list[dict[str, Any]]:
    # Tiny-demo shortcut: this is a top-k vector search with an arbitrary cap,
    # not a real table scan. The corpus is 5 rows so ordering and limit do not
    # matter. Production code should use a proper scan (e.g. table.to_arrow()).
    return table.search(deterministic_vector("query", LEGACY_MODEL)).limit(100).to_list()


def decide_action(passport: dict[str, Any], current_hash: str, target_model: str) -> tuple[str, str]:
    priority = passport["chunk"]["metadata"].get("business_priority", "medium")
    current_model = passport["embedding"]["model"]
    source_changed = passport["source"]["hash"] != current_hash

    if source_changed:
        return "RE-EMBED (source changed)", f"Source hash drift detected for {priority}-priority chunk."
    if current_model == target_model:
        return "KEEP (already on target model)", "Source is current and the model already matches."
    if current_model != LEGACY_MODEL:
        return "KEEP (different model family)", f"Vector was produced by {current_model}; out of upgrade scope."
    if priority in {"critical", "high"}:
        return "RE-EMBED (quality)", "High-priority chunk should ride the better model."
    return "DEFER (still valid)", "Source is current. Defer cost until quality gains justify it."


def act4_model_upgrade(
    table: Any,
    current_hashes: dict[str, str],
    validator: Draft202012Validator,
) -> None:
    act(
        4,
        f"Model Upgrade - {LEGACY_MODEL} -> {TARGET_MODEL}",
        "Decide per vector. Re-embed what must move. Defer what does not. Keep what is fine.",
    )

    plan: list[dict[str, Any]] = []
    for row in demo_rows(table):
        passport = json.loads(row["passport_json"])
        action, reason = decide_action(passport, current_hashes[passport["source"]["uri"]], TARGET_MODEL)
        plan.append({"row": row, "passport": passport, "action": action, "reason": reason})

    _render_plan_table(plan)

    # Apply the decisions: re-embed under TARGET_MODEL for anything marked RE-EMBED.
    refreshed = 0
    for entry in plan:
        if not entry["action"].startswith("RE-EMBED"):
            continue
        refreshed += 1
        document = next(d for d in DOCUMENTS if d["uri"] == entry["passport"]["source"]["uri"])
        new_chunk_text = document["current"][:500]
        # Cast to LanceDB's storage precision before hashing so vector_hash
        # describes the values LanceDB will return on read, not the raw f64
        # values LanceDB will round down on write.
        new_vector = to_storage_precision(deterministic_vector(new_chunk_text, TARGET_MODEL))
        updated = json.loads(entry["row"]["passport_json"])

        updated["source"]["hash"] = sha256_text(document["current"])
        updated["source"]["size_bytes"] = len(document["current"].encode("utf-8"))
        updated["chunk"]["end"] = len(new_chunk_text)
        updated["chunk"]["hash"] = sha256_text(new_chunk_text)
        updated["embedding"]["model"] = TARGET_MODEL
        updated["embedding"]["model_version"] = "2.0.0"
        updated["embedding"]["provider"] = "nomic-ai"
        updated["vector_hash"] = hash_vector(new_vector)
        updated["staleness"] = {"status": "current", "checked_at": utc_now()}
        updated["lineage"].append(
            {
                "event": "re_embedded",
                "timestamp": utc_now(),
                "details": {
                    "from_model": LEGACY_MODEL,
                    "to_model": TARGET_MODEL,
                    "reason": entry["reason"],
                },
            }
        )

        validator.validate(updated)

        # LanceDB does not give us in-place row mutation across all versions in the
        # same way, so delete-then-add the updated row. Reuse the original numeric id.
        table.delete(f"id = {entry['row']['id']}")
        table.add(
            [
                {
                    "id": entry["row"]["id"],
                    "vector": new_vector,
                    "text": document["current"],
                    "vector_id": updated["vector_id"],
                    "source_uri": updated["source"]["uri"],
                    "embedding_model": updated["embedding"]["model"],
                    "source_hash": updated["source"]["hash"],
                    "passport_json": json.dumps(updated, separators=(",", ":"), sort_keys=True),
                }
            ]
        )

    total = len(plan)
    deferred = sum(1 for entry in plan if entry["action"].startswith("DEFER"))
    out_of_scope = sum(1 for entry in plan if entry["action"].startswith("KEEP"))
    print()
    narrate(
        f"Blind upgrade would have re-embedded all {total} vectors. Passport-driven upgrade "
        f"re-embedded {refreshed}, deferred {deferred} (still valid, defer the cost), and kept "
        f"{out_of_scope} out of scope (different model family). Each refresh appended a lineage "
        f"event so the next operator can see exactly when, why, and from which model the vector moved."
    )


def _render_plan_table(plan: list[dict[str, Any]]) -> None:
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title=f"Per-vector upgrade decisions ({LEGACY_MODEL} -> {TARGET_MODEL})", show_lines=True)
        table.add_column("Source", style="cyan", overflow="fold")
        table.add_column("Section", style="magenta")
        table.add_column("Priority", justify="center")
        table.add_column("Model", style="dim")
        table.add_column("Action", style="bold")
        table.add_column("Reason", overflow="fold")
        for entry in plan:
            passport = entry["passport"]
            colour = {
                "RE-EMBED (source changed)": "[red]RE-EMBED (source changed)[/red]",
                "RE-EMBED (quality)": "[yellow]RE-EMBED (quality)[/yellow]",
                "DEFER (still valid)": "[green]DEFER (still valid)[/green]",
                "KEEP (already on target model)": "[green]KEEP[/green]",
                "KEEP (different model family)": "[green]KEEP (out of scope)[/green]",
            }.get(entry["action"], entry["action"])
            table.add_row(
                Path(passport["source"]["uri"]).name,
                passport["chunk"]["metadata"].get("section", ""),
                passport["chunk"]["metadata"].get("business_priority", ""),
                passport["embedding"]["model"],
                colour,
                entry["reason"],
            )
        CONSOLE.print(table)
        return

    print(f"\nPer-vector upgrade decisions ({LEGACY_MODEL} -> {TARGET_MODEL}):")
    for entry in plan:
        passport = entry["passport"]
        name = Path(passport["source"]["uri"]).name
        print(f"  - {name:<32} [{passport['chunk']['metadata'].get('business_priority','?'):<8}] "
              f"{entry['action']:<30} {entry['reason']}")


# ---------------------------------------------------------------------------
# Act 5: The Win
# ---------------------------------------------------------------------------

def act5_powerful_queries(table: Any) -> None:
    act(
        5,
        "The Win - queries you could not answer before",
        "All three of these are one filter on passport metadata that travelled with the vector.",
    )

    _verify_storage_integrity(demo_rows(table))

    # A new edit happens AFTER the migration so the staleness query has something to find.
    fresh_drift_uri = "s3://corp/product-roadmap-2026.md"
    new_source = (
        "2026 roadmap: agentic workflows, multimodal search, on-device inference, "
        "and a new evals platform announced in May."
    )
    live_hashes = {document["uri"]: sha256_text(document["current"]) for document in DOCUMENTS}
    live_hashes[fresh_drift_uri] = sha256_text(new_source)

    rows = demo_rows(table)
    target_uri = "s3://corp/q3-financial-report.pdf"
    target_vector_id = stable_vector_id(target_uri)

    # Q1: every vector still on v1.5 from a specific source file
    q1_matches = [
        row
        for row in rows
        if row["source_uri"] == target_uri and json.loads(row["passport_json"])["embedding"]["model"] == LEGACY_MODEL
    ]

    # Q2: chunks now stale because the source drifted since the passport was written
    q2_matches = []
    for row in rows:
        passport = json.loads(row["passport_json"])
        live_hash = live_hashes[passport["source"]["uri"]]
        if live_hash != passport["source"]["hash"]:
            q2_matches.append((row, passport, live_hash))

    # Q3: full provenance for a single vector by vector_id
    q3_row = next((row for row in rows if row["vector_id"] == target_vector_id), None)

    _render_query_one(target_uri, q1_matches)
    _render_query_two(q2_matches)
    _render_query_three(target_vector_id, q3_row)


def _verify_storage_integrity(rows: list[dict[str, Any]]) -> None:
    mismatches: list[str] = []
    for row in rows:
        passport = json.loads(row["passport_json"])
        stored_hash = hash_vector([float(value) for value in row["vector"]])
        if stored_hash != passport["vector_hash"]:
            mismatches.append(passport["vector_id"])

    total = len(rows)
    if mismatches:
        raise SystemExit(
            f"FINAL INTEGRITY CHECK FAILED: {len(mismatches)}/{total} stored vectors "
            f"do not match their passport.vector_hash: {mismatches}"
        )
    print()
    narrate(
        f"Final integrity check: {total}/{total} stored vectors hash-match their passport.vector_hash. "
        f"Every passport's integrity claim matches the vector values LanceDB returns on read."
    )


def _render_query_one(uri: str, matches: list[dict[str, Any]]) -> None:
    print()
    print(f'  Q1. "Show me every vector still on {LEGACY_MODEL} from {uri}"')
    if not matches:
        print(f"      -> 0 matches. Every vector from this source has moved off {LEGACY_MODEL}.")
        return
    for row in matches:
        passport = json.loads(row["passport_json"])
        print(
            f"      -> vector_id={passport['vector_id']}  "
            f"chunk={passport['chunk']['start']}-{passport['chunk']['end']}  "
            f"model={passport['embedding']['model']}"
        )


def _render_query_two(matches: list[tuple[dict[str, Any], dict[str, Any], str]]) -> None:
    print()
    print('  Q2. "Which chunks are now stale because the source changed?"')
    if not matches:
        print("      -> 0 matches. Index is in sync with all known sources.")
        return
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(show_lines=True)
        table.add_column("Source", style="cyan", overflow="fold")
        table.add_column("Stored hash", style="dim")
        table.add_column("Live hash", style="dim")
        table.add_column("Action", justify="center", style="bold yellow")
        for _, passport, live_hash in matches:
            table.add_row(
                passport["source"]["uri"],
                passport["source"]["hash"][:24] + "...",
                live_hash[:24] + "...",
                "RE-EMBED",
            )
        CONSOLE.print(table)
        return
    for _, passport, live_hash in matches:
        print(
            f"      -> {passport['source']['uri']}  "
            f"stored={passport['source']['hash'][:24]}...  live={live_hash[:24]}...  RE-EMBED"
        )


def _render_query_three(vector_id: str, row: dict[str, Any] | None) -> None:
    print()
    print(f'  Q3. "Give me the source span and model version behind vector {vector_id}"')
    if row is None:
        print("      -> not found.")
        return
    passport = json.loads(row["passport_json"])
    answer = {
        "vector_id": passport["vector_id"],
        "source_uri": passport["source"]["uri"],
        "chunk": {
            "unit": passport["chunk"]["unit"],
            "start": passport["chunk"]["start"],
            "end": passport["chunk"]["end"],
            "section": passport["chunk"]["metadata"].get("section"),
        },
        "embedding": {
            "model": passport["embedding"]["model"],
            "model_version": passport["embedding"]["model_version"],
            "provider": passport["embedding"]["provider"],
        },
        "text_excerpt": row["text"][:140] + ("..." if len(row["text"]) > 140 else ""),
        "lineage_events": [event["event"] for event in passport.get("lineage", [])],
    }
    print(textwrap.indent(json.dumps(answer, indent=2), "      "))


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

SUMMARY_ROWS = [
    (
        "Migration Qdrant -> LanceDB",
        "Rebuild from scratch or lose context",
        "Vectors + full provenance copy over, schema-valid on arrival",
    ),
    (
        "Knowing what to refresh on a model upgrade",
        "Blind: re-embed everything",
        "Surgical: re-embed only what the passport says is stale or high-priority",
    ),
    (
        "Auditing a single vector",
        "Impossible without rebuilding the pipeline",
        "One lookup returns source URI, chunk span, model, and lineage",
    ),
    (
        "Cross-database portability",
        "Brittle, custom for every store",
        "Passport JSON is the portable contract that travels with the vector",
    ),
    (
        "Cost on a model upgrade in this demo",
        "100% of vectors re-embedded",
        "3 of 5 re-embedded for a real reason; 1 deferred safely; 1 kept (out of scope)",
    ),
]


def print_summary() -> None:
    if RICH_AVAILABLE and CONSOLE is not None and Panel is not None and Table is not None:
        CONSOLE.print()
        CONSOLE.print(
            Panel.fit(
                "[bold]Summary - Before vs After Vector Passport[/bold]",
                border_style="green",
            )
        )
    else:
        banner("Summary - Before vs After Vector Passport")
    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(show_lines=True, border_style="green")
        table.add_column("Capability", style="bold")
        table.add_column("Before Vector Passport", style="red")
        table.add_column("After Vector Passport", style="green")
        for capability, before, after in SUMMARY_ROWS:
            table.add_row(capability, before, after)
        CONSOLE.print(table)
    else:
        print()
        for capability, before, after in SUMMARY_ROWS:
            print(f"  {capability}")
            print(f"    Before: {before}")
            print(f"    After:  {after}")

    print()
    narrate(
        "Before Vector Passport: full re-embedding and lost context on every migration. "
        "After Vector Passport: clean migration, smart partial updates, and full auditability. "
        "Same vectors, same models, same database - just with the metadata that should have been there all along."
    )
    print()
    print("  Spec:    SPEC.md")
    print("  Schema:  spec/v1.0/schema.json")
    print("  README:  README.md  (Quick Start lists this demo first)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    banner("The Migration Story - Vector Passport flagship demo")
    narrate(
        "Five short acts that take a small corpus through ingestion, a failed migration, "
        "a clean migration, a smart model upgrade, and the queries that make the standard worth the bytes."
    )

    validator = load_validator()

    with tempfile.TemporaryDirectory(prefix="vector-passport-migration-") as tmp:
        workdir = Path(tmp)

        client, current_hashes = act1_ingest_into_qdrant(validator)
        act2_pain_without_passports(client)
        table = act3_migrate_to_lancedb(client, validator, workdir)
        act4_model_upgrade(table, current_hashes, validator)
        act5_powerful_queries(table)
        print_summary()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
