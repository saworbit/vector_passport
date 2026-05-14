# Vector Passport

**An open standard for self-describing, portable AI embedding vectors.**

Vector Passport turns every embedding vector into a traceable, portable record that knows where it came from, how it was made, and whether it is still valid.

This solves one of the biggest practical problems in production RAG and semantic search systems: **vector lock-in** and painful re-embedding when you change models, chunking strategies, storage platforms, or vector databases.

**Formal specification:** See [SPEC.md](SPEC.md) for the complete v1.0 draft specification, including the data model, workflows, design rationale, security considerations, and governance.

This repository also includes a reference CLI implementation and practical demos.

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

Planned hosted schema URL:

- `https://vectorpassport.org/schema/v1.0`

Key fields include:

- `source`: URI, content hash, modified time, MIME type, size
- `chunk`: strategy, offsets, unit, page, chunk metadata
- `embedding`: model, version, provider, dimension, parameters
- `vector_hash`: hash of the actual embedding vector
- `staleness`: current source validity state
- `lineage`: vector lifecycle events
- `signature`: optional ECDSA signature
- `extensions`: vendor or project-specific metadata

## What Should Be Standardized

Vector Passport standardizes the metadata and tracking contract:

- source provenance
- chunk identity and location
- embedding model metadata
- timestamps
- hashes
- staleness state
- lineage events
- optional tamper-evidence
- extension points

This is the stable layer that makes vectors understandable across tools.

## What Should Not Be Standardized

Vector Passport does not standardize:

- the actual chunking rules
- the embedding model
- the vector database
- the storage backend
- the retrieval framework
- the application ranking strategy

Different documents need different chunking. A legal contract, PowerPoint deck, video, support ticket, scanned form, and transcript all have different structural boundaries.

Embedding models also move quickly. A standard that forces one model or one chunking method would become obsolete and would slow progress.

## Design Goals

- **Open**: Apache 2.0 license. No vendor lock-in.
- **Portable**: Works across storage systems, vector databases, and retrieval stacks.
- **Minimal**: Small JSON payload, typically under 1 KB.
- **Extensible**: `extensions` object for vendor-specific data.
- **Auditable**: Every vector can point back to its source.
- **Future-proof**: `passport_version` and `lineage` allow evolution over time.
- **Model-neutral**: Works with any embedding model.

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

This is an early-stage open standard. A practical path forward:

- publish the specification in a public repository
- use semantic versioning
- maintain a JSON Schema for each released version
- provide reference implementations in Python, TypeScript, and Go
- require compatibility tests for schema changes
- keep vendor extensions under `extensions`
- publish examples for text, image, audio, video, and multimodal use cases

## License

Apache License 2.0.

## Contributing

Feedback, schema improvements, adapters for vector databases, and additional language implementations are welcome.

If you want to help shape portable vector metadata, open an issue or pull request.

**Vector Passport: because your vectors should know where they came from.**
