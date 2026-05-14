# Contributing

Vector Passport is intended to be an open standard for vector metadata and provenance.

Contributions should preserve the main design boundary:

- standardize metadata, provenance, validity, and portability
- do not standardize embedding models, chunking algorithms, vector databases, or retrieval frameworks

## Compatibility Rules

- Patch releases clarify wording or fix schema mistakes without changing behavior.
- Minor releases add optional fields.
- Major releases may add required fields or change existing field semantics.
- Vendor-specific fields belong under `extensions`.

## Proposal Checklist

When proposing a schema change, explain:

- what interoperability problem it solves
- whether the field is required or optional
- how older readers should behave
- whether it applies to text only or to multiple modalities
- privacy or security implications

