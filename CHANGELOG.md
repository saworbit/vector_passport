# Changelog

## 1.0.0 - Draft

- Initial Vector Passport concept.
- Added JSON Schema draft for passport version `1.0`.
- Added text-vector example.
- Added minimal Python reference helper.
- Added validation script and Python dependency file.
- Added CLI flags for file validation, verbose output, custom schema path, and self-test.
- Added Python helper for automatic `vector_hash` creation from embedding values.
- Added consolidated `vector_passport.py` CLI for create, validate, and recursive folder validation.
- Added stdin vector input, create dry-run mode, vector numeric checks, and optional rich table output for folder validation.
- Added ECDSA signing support during passport creation and a `verify-signature` command.
- Added `generate-keypair` command for creating ECDSA signing keys without OpenSSL.
- Added GitHub Actions CI for linting, validation, passport creation, folder validation, signing, verification, and Python compilation.
- Added GitHub Actions security scanning with Bandit, pip-audit JSON artifacts, and dependency review.
- Added practical end-to-end demo script in `examples/demo.py` and wired it into CI/security checks.
- Added documentation explaining the practical workflows Vector Passports enable.
- Added model-upgrade use-case demo showing targeted re-embedding decisions.
- Added source file change detection demo showing stale-vector detection with `source.hash`.
- Added Qdrant integration demo showing passports as vector database payload metadata.
- Added LanceDB integration demo showing passports as table metadata for filtering and stale-vector detection.
- Added Chroma integration demo showing full-passport JSON plus flat filterable metadata fields.
- Added pgvector integration demo showing JSONB passport storage, generated hot-filter columns, and dry-run SQL.
- Added draft chunking strategy registry with stable, versioned names for common chunking patterns.
- Added formal `SPEC.md` for the Vector Passport v1.0 draft specification.
- Expanded `SPEC.md` schema evolution and versioning guidance.
- Changed the v1.0 JSON Schema `$id` to the immutable URN `urn:vector-passport:schema:1.0`.
- Defined canonical v1.0 signature bytes and raw P-256 `r || s` signature wire format.
- Hardened CLI and Python helper validation for vector dimension mismatches and invalid chunk ranges.
- Added UTF-8 BOM-tolerant JSON input handling for Windows-authored files.
- Tightened generated private-key file permissions on POSIX systems.
- Broadened CI and security scans to cover new examples automatically.
- Added "vector as a lossy retrieval view" framing to the README, `SPEC.md` motivation, and `docs/what-vector-passports-enable.md`, clarifying that the passport points at a canonical source rather than replacing it.
- Added a "Related Projects And Adjacent Standards" section to the README, covering Spectrum as a project focused on keeping the original source intact, and positioning against platforms and tools with native provenance: Vectara (a retrieval and agent platform with an internal vector database) and HydraDB (a retrieval and context infrastructure platform exposing source and metadata controls through its platform SDK and API).
