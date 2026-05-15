# Vector Passport

**An open, vendor-neutral standard for self-describing, portable AI embedding vectors.**

> **The problem:** Embedding vectors are stored as anonymous lists of numbers plus inconsistent ad-hoc metadata. Change your embedding model, chunking strategy, or vector database and you lose the context needed to safely reuse what you already have — so most teams re-embed everything, every time.
>
> **The fix:** A Vector Passport is a small JSON record (typically under 1 KB) that travels with every vector and records its source, chunk, embedding model, hashes, lifecycle state, and optional signature. Vectors become first-class, portable, auditable data assets instead of opaque numbers.
>
> **Why it's neutral:** Vector Passport standardizes the metadata *around* vectors. It does not standardize how vectors are made, which model you use, or which database you store them in. Works on top of Qdrant, LanceDB, Chroma, pgvector, Weaviate, Milvus, Pinecone, or anything that stores JSON alongside a vector.

**Formal specification:** See [SPEC.md](SPEC.md) for the complete v1.0 draft specification, including the data model, workflows, design rationale, security considerations, and governance.

This repository also includes a reference CLI, a Python helper, and integration demos for Qdrant, LanceDB, Chroma, and pgvector.

---

**Contents:** [Why It Exists](#why-it-exists) · [What It Enables](#what-it-enables) · [Features](#features) · [Installation](#installation) · [Quick Start](#quick-start) · [Quickstart For Existing Pipelines](#quickstart-for-existing-pipelines) · [Vector Database Integration](#vector-database-integration) · [Schema](#schema) · [Staleness Detection](#staleness-detection) · [Overhead And Trade-offs](#overhead-and-trade-offs) · [Security And Privacy](#security-and-privacy) · [Roadmap And Known Gaps](#roadmap-and-known-gaps)

## Why It Exists

Today, vectors are often stored as lists of numbers plus inconsistent ad hoc metadata. When you move between vector databases, upgrade embedding models, change chunking strategies, or migrate storage systems, you can lose the context needed to safely reuse what you already have.

A Vector Passport travels with every vector and answers:

- Which original file did this come from?
- Which exact chunk, page, region, or time span does it represent?
- Which chunking strategy and embedding model created it?
- When was it created?
- Has the source changed since the vector was created?
- Is the passport signature valid?

The goal is to standardize the metadata and tracking layer around vectors, without standardizing how vectors must be created.

## What It Enables

Vector Passports make vectors actionable, not just documented.

They enable:

- cheap partial re-embedding when sources, models, or chunking strategies change
- migration between vector databases without losing provenance
- automated vector hygiene and stale-vector detection
- audit, compliance, and explainability workflows
- better tooling across RAG pipelines, storage systems, and model upgrade processes

The core problem is practical: large RAG systems eventually need to change models, storage, chunking, or vector databases without blindly re-embedding everything.

See [What Vector Passports Actually Enable](docs/what-vector-passports-enable.md) for the detailed use cases and next build opportunities.

## Features

- Create passports with automatic source hashing and vector hashing
- Read embedding vectors from file or stdin
- `--dry-run` mode for safe testing
- Cryptographic signing with ECDSA
- Signature verification
- Validate single files or whole folders
- Pretty batch validation tables with `rich` when installed
- JSON Schema v1.0 stored in [spec/v1.0/schema.json](spec/v1.0/schema.json)
- Works with any embedding model and any vector database

## Installation

Install the recommended dependencies:

```bash
pip install -r requirements.txt
```

Or install them directly:

```bash
pip install jsonschema cryptography rich
```

Then run the CLI directly:

```bash
python vector_passport.py --help
```

## Quick Start

### Practical Demo (Try It Now)

Run the full end-to-end demo:

```bash
pip install -r requirements.txt
python examples/demo.py
```

The demo creates a realistic Q3 financial report, simulates chunking and embedding, builds a complete Vector Passport, signs it with ECDSA, validates it against [spec/v1.0/schema.json](spec/v1.0/schema.json), verifies the signature, and prints the final passport JSON.

Run the model-upgrade use-case demo:

```bash
python examples/model_upgrade_demo.py
```

This demo shows why passports matter in practice: it simulates upgrading from `nomic-embed-text-v1.5` to `nomic-embed-text-v2`, detects which source documents changed, and recommends which vectors must be re-embedded now, which should be re-embedded for quality, and which can be deferred.

Run the source-change detection demo:

```bash
python examples/source_change_detection_demo.py
```

This demo simulates documents that were embedded months ago, then compares each passport's stored `source.hash` with the current source hash to identify stale vectors. It shows exactly which vectors should be re-embedded and which can be kept.

Run the Qdrant integration demo:

```bash
python examples/qdrant_integration.py
```

This demo stores vectors plus full passports as Qdrant payload metadata, filters vectors by `passport.embedding.model`, and detects stale vectors by comparing `passport.source.hash` with simulated current source hashes.

Run the Chroma integration demo:

```bash
python examples/chroma_integration.py
```

This demo stores the full passport as a JSON string plus flat filter keys in Chroma metadata, queries by `passport_embedding_model`, and detects stale vectors.

Run the pgvector integration demo (dry run by default — no Postgres required):

```bash
python examples/pgvector_integration.py
```

This demo prints the SQL pattern for storing passports as JSONB with generated columns for hot filter keys, and simulates the staleness check. Use `--live` with `DATABASE_URL` set to execute against a real pgvector-enabled Postgres.

### 1. Create A Passport

```bash
python vector_passport.py create \
  --source-uri "s3://company-docs/q3-report.pdf" \
  --source-file ./q3-report.pdf \
  --chunk-start 1247 \
  --chunk-end 1873 \
  --model "nomic-embed-text-v1.5" \
  --dimension 768 \
  --vector-file ./vector.json \
  --output passport.json
```

The vector file should be a JSON array:

```json
[0.0123, -0.0456, 0.0789]
```

### 2. Create From Stdin

This is useful for pipelines where another process generates the embedding.

```bash
cat my-vector.json | python vector_passport.py create \
  --source-uri "s3://company-docs/q3-report.pdf" \
  --source-file ./q3-report.pdf \
  --chunk-start 1247 \
  --chunk-end 1873 \
  --model "nomic-embed-text-v1.5" \
  --dimension 768 \
  --vector-stdin \
  --output passport.json
```

On Windows PowerShell:

```powershell
Get-Content -Raw .\my-vector.json | python vector_passport.py create `
  --source-uri "s3://company-docs/q3-report.pdf" `
  --source-file .\q3-report.pdf `
  --chunk-start 1247 `
  --chunk-end 1873 `
  --model "nomic-embed-text-v1.5" `
  --dimension 768 `
  --vector-stdin `
  --output passport.json
```

### 3. Dry Run

Preview what would be created without writing a file.

```bash
python vector_passport.py create \
  --source-uri "s3://company-docs/q3-report.pdf" \
  --source-file ./q3-report.pdf \
  --chunk-start 1247 \
  --chunk-end 1873 \
  --model "nomic-embed-text-v1.5" \
  --dimension 768 \
  --vector-file ./vector.json \
  --dry-run
```

### 4. Validate A Single File

```bash
python vector_passport.py validate passport.json
```

### 5. Validate A Folder

```bash
python vector_passport.py validate-folder ./passports/
```

`validate-folder` checks every `*.json` file recursively, so the folder should contain passport JSON files only.

### 6. Sign A Passport

```bash
python vector_passport.py create \
  --source-uri "s3://company-docs/q3-report.pdf" \
  --source-file ./q3-report.pdf \
  --chunk-start 1247 \
  --chunk-end 1873 \
  --model "nomic-embed-text-v1.5" \
  --dimension 768 \
  --vector-file ./vector.json \
  --sign \
  --private-key ./private_key.pem \
  --output signed-passport.json
```

### 7. Verify A Signature

```bash
python vector_passport.py verify-signature signed-passport.json --public-key ./public_key.pem
```

## Quickstart For Existing Pipelines

You don't need to restructure your ingestion code to start using passports. The pattern is:

1. Embed as you do today.
2. Wrap the result in a passport.
3. Store the passport alongside the vector in your existing database.

### Generic pattern (any framework, any vector DB)

```python
from implementations.python.vector_passport import create_vector_passport_with_hash

# Whatever your pipeline already produces.
text = "Our revenue grew 27%..."
vector = embed_model.encode(text)
vector_values = vector.tolist() if hasattr(vector, "tolist") else list(vector)

passport = create_vector_passport_with_hash(
    source_uri="s3://company-docs/q3-report.pdf",
    source_hash="sha256:abc123...",          # hash of the original source object
    chunk_strategy="recursive-character-512-50@1.0.0",
    chunk_start=1247,
    chunk_end=1873,
    embedding_model="nomic-embed-text-v1.5",
    embedding_dimension=768,
    vector=vector_values,
)

# Hand the passport to whatever vector DB you use.
vector_db.upsert(id=passport["vector_id"], vector=vector_values, payload={"text": text, "passport": passport})
```

That's it. Your vectors now travel with provenance, can be filtered by model or source, and can be checked for staleness later.

### Where this fits in popular frameworks

| Framework | Where to add the passport |
| --- | --- |
| **Direct ingestion script** | Right after `embed()`, before `upsert()`. See the pattern above. |
| **LangChain** | In a custom `Document` `metadata` field, or wrap your embeddings function so each embedded chunk is paired with a passport in `metadata["passport"]`. |
| **LlamaIndex** | Attach the passport to `Node.metadata["passport"]` in your ingestion pipeline, or in a custom `TransformComponent`. |
| **Haystack** | Add the passport to the `Document.meta["passport"]` field before writing to the document store. |
| **Custom pipelines** | Anywhere you already build per-vector metadata. The passport is just JSON. |

Native framework adapters are on the [roadmap](#roadmap-and-known-gaps). Until then, the helper above works in any pipeline that lets you attach metadata to a vector — which is essentially all of them.

## Key Generation

To use `--sign` and `verify-signature`, generate an ECDSA key pair.

Using the CLI:

```bash
python vector_passport.py generate-keypair \
  --private-key private_key.pem \
  --public-key public_key.pem
```

The command refuses to overwrite existing key files unless you pass `--force`.

Using OpenSSL:

```bash
openssl ecparam -genkey -name prime256v1 -noout -out private_key.pem
openssl ec -in private_key.pem -pubout -out public_key.pem
```

Keep `private_key.pem` secure. Distribute `public_key.pem` to anyone who needs to verify signatures.

## Vector Database Integration

Vector Passports become most powerful when stored inside a vector database as rich per-vector metadata.

Most modern vector databases, including Qdrant, Chroma, Weaviate, LanceDB, and others, support attaching JSON metadata to vectors. The core pattern is:

```json
{
  "id": 123,
  "vector": [0.0123, -0.0456, 0.0789],
  "payload": {
    "text": "Our revenue grew 27%...",
    "passport": {
      "passport_version": "1.0",
      "source": {
        "uri": "s3://company-docs/q3-report.pdf",
        "hash": "sha256:..."
      },
      "embedding": {
        "model": "nomic-embed-text-v1.5",
        "dimension": 768
      }
    }
  }
}
```

This makes vectors self-describing and queryable inside the database.

| Capability | Without Passports | With Passports In The Vector DB |
| --- | --- | --- |
| Filter by embedding model | Difficult or inconsistent | Query `passport.embedding.model` |
| Detect stale vectors | Hard to do reliably | Compare `passport.source.hash` with the current source hash |
| Smart partial re-embedding | Usually custom pipeline work | Built from passport metadata |
| Audit and provenance | Weak or scattered | Stored alongside each vector |
| Safe migration between databases | Painful | Passport travels with the vector |

Try the Qdrant demo:

```bash
python examples/qdrant_integration.py
```

It uses Qdrant in-memory mode, so it does not require a running Qdrant server.

Try the LanceDB demo:

```bash
python examples/lancedb_integration.py
```

It creates a temporary local LanceDB database, stores vectors plus full passports in the table, filters by passport model metadata, and detects stale vectors using `source.hash`.

LanceDB is a strong fit for Vector Passport because it is embedded, local-first, columnar, and designed to keep vectors together with rich metadata.

Try the Chroma demo:

```bash
python examples/chroma_integration.py
```

It uses Chroma's in-memory `EphemeralClient`, stores vectors with the full passport as a JSON string plus a handful of flat filter keys, queries by `passport_embedding_model`, and detects stale vectors using `passport.source.hash`. The "full + flat" pattern works around Chroma's flat-only metadata model.

Try the pgvector demo (no Postgres needed — runs as a dry-run by default):

```bash
python examples/pgvector_integration.py
```

The dry run prints the SQL it would execute (including the `JSONB` column for the full passport and `GENERATED ALWAYS AS (...) STORED` columns for hot filter keys) and simulates the staleness check in memory. To execute against a real pgvector-enabled Postgres:

```bash
pip install "psycopg[binary]" pgvector
export DATABASE_URL=postgresql://user:pass@localhost:5432/vp_demo
python examples/pgvector_integration.py --live
```

## What Gets Created

The `create` command automatically computes:

- `source.hash`
- `source.last_modified`
- `source.size_bytes`
- `vector_hash`
- `created_at`
- `staleness.status`
- optional `signature`

Example passport:

```json
{
  "passport_version": "1.0",
  "vector_id": "uuid-or-content-addressed-id",
  "source": {
    "uri": "s3://bucket/path/document.pdf",
    "hash": "sha256:...",
    "last_modified": "2026-05-08T14:22:01Z",
    "mime_type": "application/pdf",
    "size_bytes": 2481932
  },
  "chunk": {
    "id": "chunk-0008",
    "strategy": "recursive-character-512-50@1.0.0",
    "unit": "character",
    "start": 1247,
    "end": 1873,
    "page": 8,
    "metadata": {
      "heading": "Q3 Revenue Summary"
    }
  },
  "embedding": {
    "model": "nomic-embed-text-v1.5",
    "model_version": "1.5.0",
    "provider": "nomic-ai",
    "dimension": 768,
    "parameters": {
      "normalize": true
    }
  },
  "created_at": "2026-05-08T14:22:05Z",
  "created_by": "vector-passport-cli",
  "staleness": {
    "status": "current",
    "checked_at": "2026-05-08T14:22:05Z"
  },
  "vector_hash": "sha256:...",
  "modality": "text",
  "lineage": [
    {
      "event": "initial_creation",
      "timestamp": "2026-05-08T14:22:05Z",
      "details": {
        "tool": "vector_passport.py"
      }
    }
  ],
  "signature": null,
  "extensions": {}
}
```

## Schema

The canonical JSON Schema is stored at:

- [spec/v1.0/schema.json](spec/v1.0/schema.json)

The schema's canonical `$id` is the URN `urn:vector-passport:schema:1.0` — immutable but non-resolvable. A stable hosted URL that resolves to this schema is on the [roadmap](#roadmap-and-known-gaps). Until then, fetch the file directly from this repository, pinned by commit SHA or release tag.

Key fields include:

- `source`: URI, content hash, modified time, MIME type, size
- `chunk`: strategy, offsets, unit, page, chunk metadata
- `embedding`: model, version, provider, dimension, parameters
- `vector_hash`: hash of the actual embedding vector
- `staleness`: current source validity state
- `lineage`: vector lifecycle events
- `signature`: optional ECDSA signature
- `extensions`: vendor or project-specific metadata

## Design Principles

| Principle | Details |
| --- | --- |
| **Open** | Apache 2.0 license. No vendor lock-in. |
| **Portable** | Works across storage systems, vector databases, and retrieval stacks. |
| **Minimal** | Small JSON payload, typically under 1 KB. |
| **Extensible** | `extensions` object for vendor-specific or project-specific data. |
| **Auditable** | Every vector can trace back to its exact source, chunk, and model. |
| **Future-proof** | `passport_version` and `lineage` support evolution over time. |
| **Model-neutral** | Works with any embedding model and any chunking strategy. |

**What Vector Passport standardizes:** source provenance, chunk identity and location, embedding model metadata, timestamps, content hashes, staleness state, lineage events, optional tamper-evidence, and extension points. This is the stable layer that makes vectors understandable across tools.

**What Vector Passport does not standardize:** the actual chunking rules, the embedding model, the vector database, the storage backend, the retrieval framework, or the application ranking strategy. Different documents need different chunking, and embedding models move quickly. A standard that forces one model or one chunking method would become obsolete.

## Staleness Detection

The minimum staleness rule is:

1. Read the current source object.
2. Compute its content hash.
3. Compare the current hash with `source.hash`.
4. If the hash differs, mark affected vectors as `stale`.

Suggested staleness states:

- `current`: source and chunk are known to match
- `stale`: source or chunk changed
- `source_missing`: original source cannot be found
- `unchecked`: validity has not been checked recently
- `superseded`: vector has been replaced by a newer vector

More advanced systems can compare chunk-level hashes to avoid re-embedding every chunk in a modified file.

### Client-side vs database-side staleness

The hash comparison itself is inherently client-side today: the database has no way to know the current source hash without being told. But teams who want fast queries for "which of my vectors are stale right now?" should **store `passport.staleness.status` as a filterable field** and update it from a periodic job that walks the source corpus.

| DB | Query stale vectors |
| --- | --- |
| Qdrant | Filter on `passport.staleness.status == "stale"` |
| Chroma | `where={"passport_staleness_status": "stale"}` (Chroma metadata is flat — duplicate the field as a flat key at ingest time; see `examples/chroma_integration.py`) |
| pgvector | `WHERE passport->'staleness'->>'status' = 'stale'` against a JSONB column |
| LanceDB | Promote `staleness.status` to a top-level column for predicate pushdown |
| Weaviate / Milvus / Pinecone | Promote `staleness_status` to a typed metadata field at ingest time |

The pattern is: keep the full passport for portability, *and* duplicate the handful of fields you filter on (typically `embedding.model`, `source.uri`, `staleness.status`) as flat columns or typed metadata fields for your specific database.

### Chunking strategy consistency

Vector Passport intentionally does **not** standardize chunking. But teams that share vectors across pipelines benefit from naming their chunking strategies consistently. See the [chunking strategy registry](docs/chunking-strategy-registry.md) for a starting list of common names and versions.

## Overhead And Trade-offs

A typical passport is ~700–1200 bytes of JSON. The trade-off matters at scale:

| Scale | Per-vector overhead | Total passport storage |
| --- | --- | --- |
| 10k vectors | ~1 KB | ~10 MB |
| 1M vectors | ~1 KB | ~1 GB |
| 100M vectors | ~1 KB | ~100 GB |

For most production RAG systems this is negligible compared to the cost of the vectors themselves (768 × 4 bytes ≈ 3 KB for a small embedding, often 10–30 KB for larger models). At very large scale, consider:

- Storing the full passport in an object store keyed by `vector_id`, and only the filterable subset (model, source URI, staleness status) in the vector database row.
- Dropping optional fields you don't use (`lineage`, `chunk.metadata`, `extensions`) at write time.
- Compressing the passport column (LanceDB, Parquet-backed stores, and Postgres TOAST all do this transparently).

The passport is designed to be ignorable when you don't need it and rich when you do.

## Python Helper

The reference Python helper can create passports and automatically compute `vector_hash` from embedding values.

```python
from implementations.python.vector_passport import create_vector_passport_with_hash

vector = embed_model.encode("Your chunk text here...")
vector_values = vector.tolist() if hasattr(vector, "tolist") else vector

passport = create_vector_passport_with_hash(
    source_uri="s3://company-docs/q3-report.pdf",
    source_hash="sha256:abc123",
    chunk_strategy="recursive-character-512-50",
    chunk_start=1247,
    chunk_end=1873,
    embedding_model="nomic-embed-text-v1.5",
    embedding_dimension=768,
    vector=vector_values,
)
```

## Security And Privacy

Vector passports may expose sensitive information through source paths, filenames, document headings, user identifiers, or text previews.

Implementations should consider:

- redacting sensitive source URIs
- avoiding raw text previews in regulated environments
- hashing or tokenizing internal identifiers
- encrypting passports at rest
- signing passports where tamper evidence matters
- separating public portability metadata from private operational metadata

## Governance

Vector Passport is an early-stage open standard. The specification uses semantic versioning, with the authoritative JSON Schema maintained for each released version. Vendor-specific or project-specific fields belong under `extensions`, keeping the core schema stable. See [SPEC.md § 9](SPEC.md#9-schema-evolution-and-versioning-strategies) for detailed evolution and versioning guidance, and [CONTRIBUTING.md](CONTRIBUTING.md) for the proposal checklist.

## Roadmap And Known Gaps

Vector Passport v1.0 is an early standard. The schema and CLI work today; the surrounding ecosystem is still being built. The most important gaps, in rough priority order:

- **Framework adapters.** Native LangChain, LlamaIndex, and Haystack helpers so that "add a passport to my pipeline" is a one-line import. Until then, see [Quickstart For Existing Pipelines](#quickstart-for-existing-pipelines) for the manual pattern.
- **More integration examples.** Qdrant, LanceDB, Chroma, and pgvector demos exist. Weaviate, Milvus, and Pinecone are open.
- **Server-side native adoption.** The endgame is vector databases that understand passports natively — parsing lineage, verifying hashes, and running staleness checks server-side. Today this is all client-side. See [docs/what-vector-passports-enable.md § Integration Layer](docs/what-vector-passports-enable.md#integration-layer-and-the-path-to-native-adoption) for the strategy.
- **Non-Python implementations.** The reference implementation is Python. Large-scale migration tooling will eventually want Rust or Go for throughput and concurrency.
- **Chunking strategy registry.** A community-maintained list of named chunking strategies with versions. A starting point lives at [docs/chunking-strategy-registry.md](docs/chunking-strategy-registry.md).
- **Vector lifecycle manager.** A standalone tool that scans passports and decides what to refresh, verify, supersede, or delete. The metadata is here; the tool isn't.
- **Hosted schema URL.** The schema currently lives only in this repository. A stable hosted URL (so passports can reference the schema by canonical address rather than commit SHA) is desirable but no domain is registered yet.

If any of these matter to you, open an issue or PR. The standard is more valuable the more places it shows up.

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.

## Contributing

Feedback, schema improvements, vector database adapters, and additional language implementations are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

If you want to help shape portable vector metadata, open an issue or pull request.

**Vector Passport: because your vectors should know where they came from.**
