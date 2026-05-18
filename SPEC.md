# Vector Passport Specification

**Version:** 1.0  
**Status:** Draft  
**License:** Apache 2.0  
**Canonical schema:** [spec/v1.0/schema.json](spec/v1.0/schema.json)

## 1. Abstract

Vector Passport is an open, lightweight metadata standard that attaches rich, self-describing provenance information to every embedding vector used in AI, RAG, and semantic search systems.

A Vector Passport travels with the vector and records:

- the original source object and exact source region
- the chunking strategy used
- the embedding model and parameters
- timestamps and hashes for change detection
- lifecycle and staleness state
- optional cryptographic signature for integrity
- extension metadata for project or vendor-specific needs

The goal is to turn vectors from opaque lists of numbers into managed, portable, and auditable data assets.

## 2. Motivation

Modern RAG and semantic search systems suffer from several systemic problems.

| Problem | Current State | Impact |
| --- | --- | --- |
| Vector lock-in | Vectors are tightly coupled to one system | Hard to migrate between vector databases or storage platforms |
| Expensive re-embedding | No reliable way to know what needs refreshing | Teams re-embed everything on model upgrades or data changes |
| Poor observability | Little visibility into vector provenance | Hard to debug, audit, or explain AI answers |
| Fragile pipelines | Custom scripts manage chunking and embedding | Brittle when models or chunking strategies change |
| Weak lifecycle management | Stale vectors are hard to identify reliably | Indexes drift away from the source corpus |

Vector Passport addresses these by making provenance first-class data that travels with every vector.

### 2.1 Positioning: The Vector As A Lossy Retrieval View

The passport is built on a deliberate framing: a vector is a lossy projection of a canonical source object, not the source itself. The passport's job is to keep that projection tied back to the canonical source — by URI, content hash, exact span, parser, and model version — so the vector remains rebuildable, auditable, and portable when it leaves the system that created it.

Two consequences follow from this framing and inform the rest of this specification:

1. The passport must point at the canonical source, not attempt to replace it. Fields like `source.uri`, `source.hash`, `chunk.start`/`chunk.end`, and `chunk.strategy` exist so the projection can be reconstructed or compared against the live source. They are not a substitute for faithful source storage.
2. Where a system already provides strong native provenance — for example, a vector database that embeds lineage natively, or a source-faithful store that holds canonical bytes — much of the passport's value is already covered. The passport is most useful in mixed, migrating, or multi-platform environments where there is no single store responsible for that context.

See [README § Related Projects And Adjacent Standards](README.md#related-projects-and-adjacent-standards) for adjacent projects, including source-faithful retrieval work that complements the passport's role.

## 3. Design Goals

| Goal | Description | Priority |
| --- | --- | --- |
| Portability | Vectors and metadata should be movable between systems with minimal friction | High |
| Lightweight | Small enough to store alongside every vector without significant overhead | High |
| Self-describing | A passport should be understandable without external context | High |
| Extensible | Easy to add vendor-specific or future fields without breaking compatibility | High |
| Model and chunking agnostic | Works with any embedding model and chunking strategy | High |
| Multimodal ready | Supports text, image, video, audio, multimodal, and other content | High |
| Security and integrity | Optional signing and hashes for tamper and change detection | Medium |
| Human and machine readable | Easy for engineers and automated systems to consume | Medium |

Non-goals:

- standardizing how chunking or embedding is performed
- replacing existing vector database schemas
- mandating any specific embedding model
- mandating any specific vector database or storage backend
- defining retrieval ranking, reranking, or application behavior

## 4. Data Model

A Vector Passport is a JSON object. The authoritative field constraints are defined in [spec/v1.0/schema.json](spec/v1.0/schema.json).

### 4.1 Top-Level Fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `passport_version` | string | Yes | Version of this specification. Must be `"1.0"`. |
| `vector_id` | string | Yes | Unique identifier for this vector. UUIDs or content-addressed IDs are recommended. |
| `source` | object | Yes | Information about the original source object. |
| `chunk` | object | Yes | Information about the source region represented by the vector. |
| `embedding` | object | Yes | Embedding model metadata and parameters. |
| `created_at` | string | Yes | ISO 8601 timestamp when the vector was created. |
| `created_by` | string | No | Pipeline, service, user, or process that created the vector. |
| `staleness` | object | No | Current validity state relative to the source object. |
| `vector_hash` | string | No | Hash of the vector values, prefixed with the hash algorithm. |
| `modality` | string | No | Content type: `text`, `image`, `video`, `audio`, `multimodal`, or `other`. |
| `lineage` | array | No | History of lifecycle events such as creation, staleness checks, re-embedding, or model upgrades. |
| `signature` | string or null | No | Optional cryptographic signature over canonical passport content. |
| `extensions` | object | No | Vendor, project, or deployment-specific extension fields. |

Top-level fields not listed above are not allowed in v1.0. Custom data belongs under `extensions`.

### 4.2 `source` Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `uri` | string | Yes | Location or stable identifier for the original source object. Examples: `s3://`, `file://`, `https://`. |
| `hash` | string | Yes | Content hash of the source object at the time of vector creation. Format should be algorithm-prefixed, such as `sha256:...`. |
| `last_modified` | string | No | Observed source modification timestamp when the vector was created. |
| `mime_type` | string | No | MIME type of the source object. |
| `size_bytes` | integer | No | Size of the source object in bytes. |
| `metadata` | object | No | Additional source-level metadata. |

### 4.3 `chunk` Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | No | Stable identifier for this chunk within the source object. |
| `strategy` | string | Yes | Name and optional version of the chunking strategy. Example: `recursive-character-512-50@1.0.0`. |
| `unit` | string | No | Unit for offsets. Allowed values: `byte`, `character`, `token`, `page`, `time`, `pixel`, `frame`, `region`, `other`. |
| `start` | integer | No | Inclusive chunk start offset in the chosen unit. |
| `end` | integer | No | Exclusive chunk end offset in the chosen unit. |
| `page` | integer | No | Page number for paged documents. |
| `hash` | string | No | Hash of the exact chunk payload represented by the vector. |
| `metadata` | object | No | Additional chunk metadata, such as heading, section, speaker, slide, or bounding box. |

### 4.4 `embedding` Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `model` | string | Yes | Name of the embedding model. |
| `model_version` | string | No | Exact model version, revision, or release identifier. |
| `provider` | string | No | Model provider or publisher. |
| `dimension` | integer | Yes | Dimensionality of the vector. |
| `parameters` | object | No | Model-specific embedding parameters. |

### 4.5 `staleness` Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `status` | string | No | One of `current`, `stale`, `source_missing`, `unchecked`, or `superseded`. |
| `checked_at` | string | No | ISO 8601 timestamp for the last staleness check. |
| `reason` | string | No | Human-readable explanation for the current status. |

### 4.6 `lineage` Events

Each lineage item is an object with:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `event` | string | Yes | Event name, such as `initial_creation`, `marked_stale`, `reembedded`, or `model_upgraded`. |
| `timestamp` | string | Yes | ISO 8601 timestamp for the event. |
| `details` | object | No | Event-specific details. |

Lineage should be append-only where practical.

## 5. JSON Schema

The authoritative JSON Schema for v1.0 is located at:

- **Repository path:** [spec/v1.0/schema.json](spec/v1.0/schema.json)
- **Canonical `$id`:** `urn:vector-passport:schema:1.0` (URN, immutable, non-resolvable)
- **Hosted URL:** none yet. A stable URL that resolves to this schema is desirable but no domain is registered; until then, fetch the file directly from this repository, pinned by commit SHA or release tag.

Implementations should validate passports against the JSON Schema when creating, importing, exporting, or migrating vectors.

**When to validate:**

| Operation | Validation Guidance |
| --- | --- |
| Creating a new passport | Validate before storing. Reject invalid passports at the source. |
| Importing from another system | Validate on import. Log or quarantine passports that fail validation. |
| Exporting to another system | Validate before export to avoid propagating invalid data. |
| Migrating between schema versions | Validate against both the source and target schemas during migration. |
| Reading in application code | Validate if the passport source is untrusted. Skip if the pipeline guarantees schema compliance. |

## 6. Recommended Workflows

### 6.1 Creation Workflow

Creating a vector with a passport follows these steps:

```
Source Object
  │
  ▼
Extract Content ─── read the source file and compute source.hash
  │
  ▼
Chunking Strategy ── split content into chunks, record strategy and offsets
  │
  ▼
Generate Embedding ─ pass chunk text to the embedding model
  │
  ▼
Create Passport ──── assemble passport with source, chunk, embedding,
  │                   staleness, lineage, and vector_hash fields
  ▼
Optional Signature ─ sign the canonical passport with ECDSA if required
  │
  ▼
Store ──────────────  persist the vector and passport together
```

**Minimum required actions:**

1. **Hash the source.** Read the source object and compute a content hash (e.g. `sha256:...`). Store it in `source.hash`.
2. **Record the chunk.** Capture the chunking strategy name, unit, start offset, and end offset.
3. **Embed.** Generate the embedding vector. Record the model name and dimension.
4. **Compute vector hash.** Hash the raw embedding values and store the result in `vector_hash`.
5. **Assemble the passport.** Populate all required fields: `passport_version`, `vector_id`, `source`, `chunk`, `embedding`, and `created_at`.
6. **Append a lineage event.** Add an `initial_creation` event with the current timestamp.
7. **Sign (optional).** If tamper evidence is needed, sign the canonical passport bytes (defined in [§ 8.1 Signature Canonicalization](#81-signature-canonicalization)) using ECDSA and store the resulting hex string in `signature`.
8. **Store together.** Persist the vector and its passport in the same record, payload, or metadata layer.

### 6.2 Staleness Detection Workflow

Staleness detection determines whether an existing vector still reflects its source:

```
Existing Vector + Passport
  │
  ▼
Read source.hash from the passport
  │
  ▼
Fetch the current source object and recompute its hash
  │
  ▼
Compare hashes
  │
  ├── Match ──────► Vector is current ── set staleness.status = "current"
  │
  └── Mismatch ──► Vector is stale ──── set staleness.status = "stale"
                     │
                     ▼
                   Re-embed affected chunks
                     │
                     ▼
                   Append lineage events ("marked_stale", "reembedded")
```

**Steps in detail:**

1. **Read stored hash.** Extract `source.hash` from the passport.
2. **Recompute current hash.** Fetch the source object at `source.uri` and compute its content hash using the same algorithm.
3. **Compare.** If the hashes match, the vector is still current. Update `staleness.status` to `"current"` and `staleness.checked_at` to the current timestamp.
4. **Handle mismatch.** If the hashes differ:
   - Set `staleness.status` to `"stale"` and `staleness.reason` to a human-readable explanation.
   - Append a `marked_stale` lineage event.
   - Re-embed the affected chunk using the current embedding model.
   - Create a new passport for the re-embedded vector and append a `reembedded` lineage event.
5. **Handle missing source.** If the source object cannot be found, set `staleness.status` to `"source_missing"`.

For large corpora, chunk-level hashes (`chunk.hash`) allow finer detection: only chunks whose content actually changed need re-embedding, even if the parent document changed.

### 6.3 Model Upgrade Workflow

Model upgrades re-embed vectors to take advantage of a newer or better embedding model:

```
New model available
  │
  ▼
Scan existing passports
  │
  ▼
Filter candidates ── source changed? old model? high priority? stale?
  │
  ├── Must re-embed ──► re-embed now, update passport + lineage
  │
  ├── Should re-embed ► schedule for quality improvement
  │
  └── Skip ───────────► keep existing vector
```

**Steps in detail:**

1. **Announce target model.** Define the new embedding model name, version, and any changed parameters.
2. **Scan passports.** Query or iterate over existing passports and read `embedding.model`, `embedding.model_version`, and `staleness.status`.
3. **Classify each vector.** For each passport, decide whether re-embedding is required, recommended, or unnecessary:
   - **Must re-embed:** source has changed (`staleness.status` is `"stale"` or `"source_missing"`), or the vector is marked `"superseded"`.
   - **Should re-embed:** the embedding model differs from the target model and the chunk is high priority or frequently retrieved.
   - **Skip:** the source is unchanged, the current model is acceptable, and the vector is still `"current"`.
4. **Re-embed the subset.** For each vector that needs re-embedding, generate a new vector with the target model and create a new passport.
5. **Update lineage.** Append a `model_upgraded` event recording the old model, new model, and timestamp. If the old vector is retained, set its `staleness.status` to `"superseded"`.

This approach avoids the cost of blindly re-embedding an entire vector estate when only a fraction of vectors actually benefit from the new model.

### 6.4 Vector Database Integration

Store the passport alongside the vector in the vector database metadata or payload layer. Most modern vector databases (Qdrant, Chroma, Weaviate, LanceDB, Milvus, Pinecone, and others) support attaching JSON metadata to each vector.

**Nested JSON pattern** (passport as a structured object inside the payload):

```json
{
  "id": "vector-id",
  "vector": [0.0123, -0.0456, 0.0789],
  "payload": {
    "text": "Our revenue grew 27%...",
    "passport": {
      "passport_version": "1.0",
      "vector_id": "vec-abc-001",
      "source": {
        "uri": "s3://company-docs/q3-report.pdf",
        "hash": "sha256:a1b2c3..."
      },
      "chunk": {
        "strategy": "recursive-character-512-50@1.0.0",
        "start": 1247,
        "end": 1873
      },
      "embedding": {
        "model": "nomic-embed-text-v1.5",
        "dimension": 768
      },
      "created_at": "2026-05-08T14:22:05Z",
      "staleness": {
        "status": "current",
        "checked_at": "2026-05-08T14:22:05Z"
      }
    }
  }
}
```

**Flattened pattern** (passport stored as a JSON string plus selected indexed columns):

```json
{
  "id": "vector-id",
  "vector": [0.0123, -0.0456, 0.0789],
  "payload": {
    "text": "Our revenue grew 27%...",
    "passport_json": "{...}",
    "passport_model": "nomic-embed-text-v1.5",
    "passport_source_hash": "sha256:a1b2c3...",
    "passport_staleness": "current"
  }
}
```

Both patterns are valid as long as the full passport can be recovered and validated. The nested pattern preserves structure and is easier to query. The flattened pattern is useful when the database supports filtering on top-level payload fields but not nested objects.

**Integration checklist:**

- Store the complete passport, not just selected fields. Partial passports lose portability.
- Index `embedding.model` if you need to filter vectors by model during upgrades.
- Index `staleness.status` if you run automated freshness checks.
- Index `source.hash` if you compare against current source hashes at query time.
- Preserve `extensions` during import and export, even if your system does not use them.

## 7. Use Cases

| Use Case | Description | Value |
| --- | --- | --- |
| Smart re-embedding | Only re-embed vectors whose source changed or that benefit from a new model | High |
| Cross-platform migration | Move vectors between vector databases or storage systems safely | High |
| Automated data hygiene | Continuously detect and refresh stale vectors | High |
| Audit and compliance | Maintain provenance for every vector used in AI responses | Medium-high |
| Multi-model strategies | Run multiple embedding models and compare results with clear metadata | Medium |
| Debugging and explainability | Trace exactly which document chunk and model produced a vector | Medium |
| Vector observability | Build dashboards over freshness, model mix, source coverage, and lineage | Medium |

## 8. Security And Privacy Considerations

- **Integrity:** `source.hash`, `chunk.hash`, and `vector_hash` support change and integrity checks.
- **Signing:** The optional `signature` field can hold an ECDSA signature over the canonical bytes defined in [§ 8.1 Signature Canonicalization](#81-signature-canonicalization).
- **Trust:** Signatures allow downstream systems to verify that a passport came from a trusted pipeline.
- **Privacy:** Source URIs, filenames, headings, and extension metadata may reveal sensitive information.
- **Redaction:** Sensitive operational details should be redacted, tokenized, encrypted, or placed in controlled `extensions`.
- **Key management:** Private signing keys must be stored securely (POSIX `0600` or equivalent, encrypted at rest where supported) and rotated according to local security policy.

### 8.1 Signature Canonicalization

Signatures are computed and verified over **canonical passport bytes**, which are normatively defined as:

1. Start from the passport JSON object.
2. **Remove the `signature` key entirely** if present. Do not set it to `null`; remove the key.
3. Serialize the resulting object to UTF-8 JSON with:
   - keys sorted lexicographically at every depth,
   - no insignificant whitespace (`","` and `":"` separators, no spaces, no trailing newline).
4. The resulting bytes are the input to the signing or verification operation.

Reference Python:

```python
import json

def canonical_passport_bytes(passport: dict) -> bytes:
    unsigned = dict(passport)
    unsigned.pop("signature", None)  # remove, do not set to None
    return json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode("utf-8")
```

This is the single canonical form. Implementations that set `signature` to `null` before signing will produce signatures that other v1.0 implementations reject. The remove-the-key rule is normative for v1.0.

The signature algorithm for v1.0 is **ECDSA over the NIST P-256 curve** (`secp256r1` / `prime256v1`) **with SHA-256**.

**Signature wire format (normative):** the signature is the fixed-width raw concatenation `r || s`, where each of `r` and `s` is the corresponding ECDSA component encoded as a 32-byte big-endian unsigned integer (left-zero-padded if necessary). The total length is exactly 64 bytes. Set the `signature` field to the lowercase hex encoding of these 64 bytes (128 hex characters). This is the same convention as RFC 7518 §3.4 (JWS ES256).

Implementations that use libraries returning DER-encoded ECDSA signatures (OpenSSL, Python `cryptography`, etc.) must convert DER to raw `r || s` before encoding. Reference Python:

```python
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from cryptography.hazmat.primitives import hashes

# Sign:
der = private_key.sign(canonical_passport_bytes(passport), ec.ECDSA(hashes.SHA256()))
r, s = asym_utils.decode_dss_signature(der)
raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")   # 64 bytes
passport["signature"] = raw.hex()                     # 128 hex chars

# Verify:
raw = bytes.fromhex(passport["signature"])
assert len(raw) == 64
r = int.from_bytes(raw[:32], "big")
s = int.from_bytes(raw[32:], "big")
der = asym_utils.encode_dss_signature(r, s)
public_key.verify(der, canonical_passport_bytes(passport), ec.ECDSA(hashes.SHA256()))
```

Passports whose `signature` is not exactly 128 lowercase hex characters MUST be rejected by v1.0 verifiers as malformed, independent of whether the underlying ECDSA math would otherwise succeed.

## 9. Schema Evolution And Versioning Strategies

Vector Passport is designed for long-term evolution while preserving compatibility across tools, vector databases, storage systems, and organizations.

The key tension is deliberate: the core passport schema should be stable enough for interoperability, but flexible enough for new modalities, model metadata, lifecycle events, and vendor-specific capabilities.

### 9.1 Core Principles

| Principle | Description | Why It Matters |
| --- | --- | --- |
| Backward compatibility | Any v1.x implementation should be able to read passports created under earlier v1.y versions. | Prevents ecosystem fragmentation and protects existing vector estates. |
| Forward compatibility | Older implementations should either ignore unsupported optional data or preserve it under `extensions`. | Enables gradual adoption across mixed toolchains. |
| Explicit versioning | Every passport declares `passport_version`. | Allows consumers to branch behavior safely. |
| Minimal breaking changes | Major version bumps are rare and require clear migration guidance. | Protects operational systems that may store millions or billions of passports. |
| Extensibility through `extensions` | Vendor-specific, project-specific, or experimental fields live under `extensions`. | Keeps the core schema stable while allowing innovation. |
| Schema as contract | The JSON Schema is the machine-readable compatibility boundary. | Makes validation, CI, import/export, and migration tooling reliable. |
| Preserve provenance | Evolution must not weaken traceability to source, chunk, model, and lifecycle state. | Provenance is the primary value of the standard. |

### 9.2 Recommended Evolution Strategies

| Strategy | When To Use | Implementation Guidance | Compatibility Impact |
| --- | --- | --- | --- |
| Add optional top-level or nested field | Broadly useful new capabilities that should become part of the common contract. | Add the field as optional in a minor version, document default behavior, and add examples. | Backward safe for newer readers; older strict v1.0 validators may reject it unless validating against the newer schema. |
| Use `extensions` | Vendor-specific data, experimental features, deployment-specific metadata, or temporary workarounds. | Place data under `extensions.{vendor_or_project}.{field}`. Preserve it during import/export. | Safest path. v1.0 readers should accept and round-trip it. |
| Append to `lineage` | Recording lifecycle events such as re-embedding, model upgrades, source re-chunking, staleness checks, or migrations. | Append new events. Avoid editing historical entries except for explicit repair workflows. | Safe when event consumers tolerate unknown event names. |
| Introduce a new `modality` value | Supporting new content types such as `code`, `table`, `geospatial`, or domain-specific media. | Prefer a minor version. Older systems may treat unsupported values as `other` or route to fallback handling. | Mostly safe, but strict enum validation requires an updated schema. |
| Deprecate a field | A field is being replaced by a clearer or more precise alternative. | Mark as deprecated in docs, keep reading it for at least two minor versions, and provide migration guidance. | Backward safe if consumers keep supporting the old field. |
| Add stricter validation | Clarifying allowed values, patterns, or constraints. | Use cautiously. Prefer warnings before hard validation errors. | Can break existing data if previously accepted values become invalid. |
| Major version bump | Required fields or core field semantics must change. | Publish a migration guide, conversion tooling, and compatibility examples. | Breaking by design. Should be rare. |

### 9.3 Minor Version Rules

Minor versions, such as `1.0` to `1.1`, are for compatible evolution.

Allowed minor-version changes:

- add optional fields
- add optional nested objects
- add new lineage event names
- add new extension guidance
- add new examples
- add new non-normative recommendations
- clarify field descriptions without changing meaning
- add new enum values only when fallback behavior is documented

Minor versions must not:

- remove existing fields
- make optional fields required
- change the type of an existing field
- change the meaning of an existing field
- make previously valid v1.x passports invalid without a documented transition path

### 9.4 Major Version Rules

Major versions, such as `1.x` to `2.0`, are reserved for breaking changes.

Examples of major-version changes:

- making `vector_hash` required
- changing the required structure of `embedding`
- replacing `source.hash` semantics
- removing or renaming a core field
- changing the meaning of `chunk.start` and `chunk.end`
- requiring signatures for all passports

Major version changes must include:

- a clear migration guide
- examples before and after migration
- compatibility notes for vector databases and payload formats
- recommended reader behavior for older passports
- preferably an automated migration script or CLI command

Implementations should continue to read older major versions for a documented support window where practical.

### 9.5 Handling Unknown Fields

The v1.0 schema uses `additionalProperties: false` at the top level and inside core objects. This is intentional: the shared interoperability surface should remain predictable.

Therefore:

- unknown top-level fields are not valid v1.0 passport fields
- unknown fields inside `source`, `chunk`, `embedding`, `staleness`, and `lineage` items are not valid unless allowed by the schema
- custom or experimental fields must be placed under `extensions`
- implementations should preserve and round-trip `extensions`
- implementations should ignore extension namespaces they do not understand

Recommended extension shape:

```json
{
  "extensions": {
    "example.com/my-system": {
      "retrieval_score": 0.92,
      "index_name": "finance-prod-v3"
    }
  }
}
```

Extension namespace recommendations:

- use a domain name, package name, or project slug
- avoid short generic keys such as `custom` or `misc`
- document extension fields if other systems are expected to consume them
- avoid storing secrets or sensitive raw text unless encrypted or access-controlled

### 9.6 Future-Proofing Reader Implementations

Readers should:

- check `passport_version` before applying version-specific behavior
- validate against the matching schema when possible
- tolerate missing optional fields
- preserve `extensions` during migration and export
- treat unknown extension namespaces as opaque data
- avoid assuming a passport is text-only
- avoid assuming offsets are character offsets unless `chunk.unit` says so
- avoid assuming one embedding model per database or collection

Writers should:

- emit the most specific `passport_version` they support
- avoid adding non-standard top-level fields
- include hashes wherever practical
- include `created_at`
- include enough model metadata to distinguish incompatible embeddings
- include lineage events when modifying or superseding vectors

### 9.7 Example Evolution Path

**v1.0**

- Core provenance fields
- Source, chunk, embedding, staleness, lineage, signature, and extensions
- JSON Schema stored at `spec/v1.0/schema.json`

**v1.1** example future minor version:

- add optional `quality` object for retrieval or evaluation metadata
- add optional `embedding.context_window`
- add optional `chunk.language`
- add new `modality` value: `code`
- document additional lineage events such as `quality_evaluated`

**v1.2** example future minor version:

- add optional `source.version_id` for object stores with native versioning
- add optional `signature.algorithm`
- add optional `signature.key_id`

**v2.0** example future major version:

- make `vector_hash` required
- replace string `signature` with a structured signature object
- require `chunk.unit` whenever `chunk.start` or `chunk.end` is present
- provide migration tooling that converts v1.x signatures and backfills missing fields where possible

These examples are illustrative, not commitments.

### 9.8 Governance Of Evolution

Changes to the core schema should be proposed through public issues or pull requests.

Schema change proposals should include:

- the interoperability problem being solved
- whether the change is optional or required
- compatibility impact
- example passports before and after the change
- privacy and security implications
- migration guidance when applicable
- updates to reference examples and validation tests

Breaking changes require strong justification and broad consensus. The specification should evolve slowly and deliberately. Stability is a feature.

## 10. Governance

This specification is maintained as an open standard under the Apache 2.0 license.

**Contribution process:**

- Schema changes, new fields, and specification clarifications are proposed through pull requests and issues.
- Each proposal should follow the checklist described in Section 9.8.
- Breaking changes require strong justification, broad consensus, and migration guidance.

**Reference artifacts:**

| Artifact | Path | Description |
| --- | --- | --- |
| JSON Schema | [spec/v1.0/schema.json](spec/v1.0/schema.json) | Authoritative machine-readable schema for v1.0 |
| Example Passport | [examples/sample-passport.json](examples/sample-passport.json) | Complete example passport with all fields populated |
| Reference CLI | [vector_passport.py](vector_passport.py) | Python CLI for creating, validating, signing, and verifying passports |
| Contributing Guide | [CONTRIBUTING.md](CONTRIBUTING.md) | Guidelines for proposing changes to the specification |

## Appendix A: Example Passport

A complete example passport with all fields populated is available at [examples/sample-passport.json](examples/sample-passport.json).

The example demonstrates a text-modality vector from a PDF source with character-based chunk offsets, an `initial_creation` lineage event, and a `current` staleness status.

## Appendix B: Reference Demos

The following demos show Vector Passport workflows end to end. Each can be run independently.

| Demo | Path | What It Shows |
| --- | --- | --- |
| End-to-end lifecycle | [examples/demo.py](examples/demo.py) | Creates a passport, signs it with ECDSA, validates against the schema, verifies the signature, and prints the result. |
| Model upgrade analysis | [examples/model_upgrade_demo.py](examples/model_upgrade_demo.py) | Simulates upgrading from one embedding model to another and recommends which vectors to re-embed. |
| Source-change detection | [examples/source_change_detection_demo.py](examples/source_change_detection_demo.py) | Compares stored `source.hash` values against current source hashes to identify stale vectors. |
| Qdrant integration | [examples/qdrant_integration.py](examples/qdrant_integration.py) | Stores passports as Qdrant payload metadata, filters by model, and detects stale vectors. |
| LanceDB integration | [examples/lancedb_integration.py](examples/lancedb_integration.py) | Stores passports in LanceDB table metadata for filtering and stale-vector detection. |

---

This document, together with [spec/v1.0/schema.json](spec/v1.0/schema.json), constitutes the Vector Passport v1.0 draft specification.
