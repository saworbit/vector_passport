# Contributing

Vector Passport is an open standard for vector metadata and provenance. Contributions are welcome, whether they are schema improvements, documentation fixes, new language implementations, vector database adapters, or additional examples.

## Design Boundary

All contributions should preserve the core design boundary:

- **Standardize:** metadata, provenance, validity, portability, and lifecycle tracking.
- **Do not standardize:** embedding models, chunking algorithms, vector databases, storage backends, or retrieval frameworks.

If you are unsure whether a proposed change crosses this boundary, open an issue to discuss before submitting a pull request.

## Types Of Contributions

| Contribution | Where It Goes | Notes |
| --- | --- | --- |
| Schema field additions | `spec/v1.0/schema.json` and `SPEC.md` | Follow the proposal checklist below. |
| Documentation fixes | `SPEC.md`, `README.md`, or `docs/` | Typos, clarifications, and improved examples are always welcome. |
| New examples or demos | `examples/` | Should be self-contained and runnable. |
| Vector database adapters | `examples/` or a new `adapters/` directory | Should demonstrate passport storage, retrieval, and staleness detection. |
| Language implementations | `implementations/{language}/` | Should support creating, validating, and reading passports. |
| Bug fixes | Relevant source files | Include a test or example that reproduces the issue. |

## Compatibility Rules

- **Patch releases** clarify wording or fix schema mistakes without changing behavior.
- **Minor releases** add optional fields, new enum values, or new lineage event names.
- **Major releases** may add required fields or change existing field semantics. These are rare and require migration guidance.
- **Vendor-specific fields** belong under `extensions`, not as new top-level fields.

See [SPEC.md § 9](SPEC.md#9-schema-evolution-and-versioning-strategies) for the full versioning and evolution policy.

## Proposal Checklist

When proposing a schema change, your pull request should explain:

- [ ] What interoperability problem does it solve?
- [ ] Is the new field required or optional?
- [ ] How should older readers behave when they encounter this field?
- [ ] Does it apply to text only, or to multiple modalities?
- [ ] Are there privacy or security implications?
- [ ] Example passport JSON before and after the change.
- [ ] Any updates needed to validation tests or the reference CLI.

## Running Tests Locally

Before submitting a pull request, verify that the existing validation and demo scripts still work:

```bash
pip install -r requirements.txt
python vector_passport.py validate examples/sample-passport.json
python examples/demo.py
```

## Code Style

- Keep JSON examples valid and formatted with 2-space indentation.
- Keep documentation concise. Prefer tables over long prose where the content is structured.
- Use ISO 8601 timestamps in all examples.

