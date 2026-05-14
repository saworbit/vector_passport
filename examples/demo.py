#!/usr/bin/env python3
"""
Vector Passport v1.0 - Practical End-to-End Demo.

This script demonstrates the full lifecycle:
1. Create a sample Q3 financial report.
2. Simulate chunking and embedding.
3. Build a complete Vector Passport.
4. Sign it with an ephemeral ECDSA key.
5. Validate it against the canonical JSON Schema.
6. Verify the signature.

Run:
    python examples/demo.py
"""

from __future__ import annotations

import hashlib
import json
import random
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError as error:  # pragma: no cover - exercised by user environment.
    raise SystemExit(
        "The demo requires cryptography. Install dependencies with: "
        "pip install -r requirements.txt"
    ) from error


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "spec" / "v1.0" / "schema.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_passport_bytes(passport: dict[str, Any]) -> bytes:
    unsigned = dict(passport)
    unsigned.pop("signature", None)
    return json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode("utf-8")


def create_sample_document(workdir: Path) -> Path:
    content = """Q3 2026 Financial Performance Summary

Revenue grew 27% year-over-year, reaching $48.2 million.
Key drivers:
- Enterprise segment grew 34%
- New customer acquisition increased 41%
- Average contract value rose from $87k to $112k

Challenges:
- Supply chain delays impacted hardware revenue by approximately $2.1M
- Marketing spend increased 18% due to competitive pressure

Outlook remains positive for Q4 with a strong pipeline.
"""
    path = workdir / "q3-financial-report.txt"
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def simulated_embedding(text: str, dimension: int = 768) -> list[float]:
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
    generator = random.Random(seed)
    return [round(generator.uniform(-0.8, 0.8), 6) for _ in range(dimension)]


def build_passport(source_path: Path, chunk_text: str, vector: list[float]) -> dict[str, Any]:
    created_at = utc_now()
    source_stat = source_path.stat()
    source_modified = (
        datetime.fromtimestamp(source_stat.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    chunk_start = 0
    chunk_end = len(chunk_text)

    return {
        "passport_version": "1.0",
        "vector_id": str(uuid.uuid4()),
        "source": {
            "uri": source_path.resolve().as_uri(),
            "hash": sha256_digest(source_path.read_bytes()),
            "last_modified": source_modified,
            "mime_type": "text/plain",
            "size_bytes": source_stat.st_size,
        },
        "chunk": {
            "id": f"character-{chunk_start}-{chunk_end}",
            "strategy": "recursive-character-512-50@1.0.0",
            "unit": "character",
            "start": chunk_start,
            "end": chunk_end,
            "hash": sha256_digest(chunk_text.encode("utf-8")),
            "metadata": {
                "section": "Financial Performance",
                "heading": "Q3 2026 Financial Performance Summary",
            },
        },
        "embedding": {
            "model": "nomic-embed-text-v1.5",
            "model_version": "1.5.0",
            "provider": "nomic-ai",
            "dimension": len(vector),
            "parameters": {
                "normalize": True,
                "pooling": "mean",
            },
        },
        "created_at": created_at,
        "created_by": "examples/demo.py",
        "staleness": {
            "status": "current",
            "checked_at": created_at,
        },
        "vector_hash": sha256_digest(
            json.dumps(vector, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ),
        "modality": "text",
        "lineage": [
            {
                "event": "initial_creation",
                "timestamp": created_at,
                "details": {
                    "demo": True,
                    "embedding": "simulated",
                },
            }
        ],
        "signature": None,
        "extensions": {
            "demo": {
                "note": "Embedding values are deterministic simulated data.",
            }
        },
    }


def sign_passport(passport: dict[str, Any]) -> tuple[dict[str, Any], ec.EllipticCurvePublicKey]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    signature = private_key.sign(canonical_passport_bytes(passport), ec.ECDSA(hashes.SHA256()))

    signed = dict(passport)
    signed["signature"] = signature.hex()
    return signed, public_key


def verify_signature(passport: dict[str, Any], public_key: ec.EllipticCurvePublicKey) -> bool:
    signature = passport.get("signature")
    if not isinstance(signature, str):
        return False

    try:
        public_key.verify(
            bytes.fromhex(signature),
            canonical_passport_bytes(passport),
            ec.ECDSA(hashes.SHA256()),
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def validate_passport(passport: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(passport)


def print_step(number: int, title: str) -> None:
    print(f"\n{number}. {title}")
    print("-" * (len(title) + 3))


def main() -> int:
    print("Vector Passport v1.0 - Practical End-to-End Demo")
    print("=" * 58)

    with tempfile.TemporaryDirectory(prefix="vector-passport-demo-") as tmp:
        workdir = Path(tmp)

        print_step(1, "Creating a sample Q3 financial report")
        document = create_sample_document(workdir)
        document_text = document.read_text(encoding="utf-8")
        print(f"Created: {document}")
        print(f"Size: {document.stat().st_size} bytes")
        print("Preview:")
        print(indent_preview(document_text, max_chars=220))

        print_step(2, "Simulating chunking and embedding")
        chunk_text = document_text[:500]
        vector = simulated_embedding(chunk_text)
        print(f"Chunk range: characters 0-{len(chunk_text)}")
        print("Embedding model: nomic-embed-text-v1.5 (simulated)")
        print(f"Vector dimension: {len(vector)}")
        print(f"First 8 vector values: {vector[:8]}")

        print_step(3, "Building the Vector Passport")
        passport = build_passport(document, chunk_text, vector)
        print(f"Vector ID: {passport['vector_id']}")
        print(f"Source hash: {passport['source']['hash']}")
        print(f"Vector hash: {passport['vector_hash']}")

        print_step(4, "Signing with an ephemeral ECDSA key")
        passport, public_key = sign_passport(passport)
        print("Signature algorithm: ECDSA P-256 with SHA-256")
        print(f"Signature length: {len(passport['signature'])} hex characters")

        print_step(5, "Validating against the canonical JSON Schema")
        validate_passport(passport)
        print(f"Schema: {SCHEMA_PATH}")
        print("Result: valid")

        print_step(6, "Verifying the signature")
        if not verify_signature(passport, public_key):
            print("Result: invalid")
            return 1
        print("Result: valid")

        print_step(7, "Final Vector Passport JSON")
        print(json.dumps(passport, indent=2, sort_keys=True))

    print("\nDemo complete.")
    print("This is the full passport lifecycle: source -> chunk -> embedding -> passport -> signature -> validation.")
    return 0


def indent_preview(text: str, max_chars: int) -> str:
    preview = text[:max_chars].strip()
    if len(text) > max_chars:
        preview += "..."
    return "\n".join(f"  {line}" for line in preview.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
