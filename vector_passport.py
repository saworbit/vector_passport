#!/usr/bin/env python3
"""
Vector Passport v1.0 - Create + Validate + Sign Tool.

Usage examples:
    python vector_passport.py create --source-uri "s3://company-docs/q3-report.pdf" --source-file q3-report.pdf --chunk-start 1247 --chunk-end 1873 --model "nomic-embed-text-v1.5" --dimension 768 --vector-file vector.json --output passport.json
    type vector.json | python vector_passport.py create --source-uri "s3://company-docs/q3-report.pdf" --source-file q3-report.pdf --chunk-start 1247 --chunk-end 1873 --model "nomic-embed-text-v1.5" --dimension 768 --vector-stdin --output passport.json
    python vector_passport.py create ... --dry-run
    python vector_passport.py create ... --sign --private-key private_key.pem
    python vector_passport.py validate passport.json
    python vector_passport.py validate-folder ./passports/
    python vector_passport.py generate-keypair --private-key private_key.pem --public-key public_key.pem
    python vector_passport.py verify-signature signed-passport.json --public-key public_key.pem
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, SchemaError, ValidationError

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:
    Console = None
    Table = None

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    InvalidSignature = None
    hashes = None
    serialization = None
    ec = None


ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = ROOT / "spec" / "v1.0" / "schema.json"
RICH_AVAILABLE = Console is not None and Table is not None
CRYPTO_AVAILABLE = all(item is not None for item in (InvalidSignature, hashes, serialization, ec))
CONSOLE = Console() if Console is not None else None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compute_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def hash_vector(values: Any) -> str:
    payload = json.dumps(values, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return sha256_digest(payload)


def canonical_passport_bytes(passport: dict[str, Any]) -> bytes:
    unsigned = dict(passport)
    unsigned.pop("signature", None)
    return json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode("utf-8")


def load_vector(args: argparse.Namespace) -> list[Any]:
    if args.vector_stdin and args.vector_file:
        raise ValueError("Use either --vector-file or --vector-stdin, not both.")

    if args.vector_stdin:
        try:
            vector = json.load(sys.stdin)
        except json.JSONDecodeError as error:
            raise ValueError(f"Failed to read valid JSON vector from stdin: {error}") from error
    elif args.vector_file:
        vector = load_json(Path(args.vector_file))
    else:
        raise ValueError("Provide either --vector-file or --vector-stdin.")

    if not isinstance(vector, list):
        raise ValueError("Vector input must be a JSON array of numbers.")
    if not all(isinstance(item, int | float) and not isinstance(item, bool) for item in vector):
        raise ValueError("Vector input must contain only numeric values.")

    return vector


def drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [drop_none(item) for item in value]
    return value


def load_schema(schema_path: Path) -> dict[str, Any]:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    return schema


def create_passport(args: argparse.Namespace) -> dict[str, Any]:
    source_path = Path(args.source_file)

    if not source_path.is_file():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    vector = load_vector(args)

    created_at = utc_now()
    source_stat = source_path.stat()
    source_modified = (
        datetime.fromtimestamp(source_stat.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    passport = {
        "passport_version": "1.0",
        "vector_id": str(uuid.uuid4()),
        "source": {
            "uri": args.source_uri,
            "hash": compute_file_hash(source_path),
            "last_modified": source_modified,
            "mime_type": args.mime_type,
            "size_bytes": source_stat.st_size,
        },
        "chunk": {
            "id": args.chunk_id,
            "strategy": args.chunk_strategy,
            "unit": args.chunk_unit,
            "start": args.chunk_start,
            "end": args.chunk_end,
            "page": args.page,
            "metadata": {},
        },
        "embedding": {
            "model": args.model,
            "model_version": args.model_version,
            "provider": args.provider,
            "dimension": args.dimension,
            "parameters": {"normalize": args.normalize},
        },
        "created_at": created_at,
        "created_by": args.created_by,
        "staleness": {
            "status": "current",
            "checked_at": created_at,
        },
        "vector_hash": hash_vector(vector),
        "modality": args.modality,
        "lineage": [
            {
                "event": "initial_creation",
                "timestamp": created_at,
                "details": {"tool": "vector_passport.py"},
            }
        ],
        "signature": None,
        "extensions": {},
    }

    return drop_none(passport)


def sign_passport(passport: dict[str, Any], private_key_path: Path) -> dict[str, Any]:
    if not CRYPTO_AVAILABLE or serialization is None or ec is None or hashes is None:
        raise RuntimeError("The 'cryptography' package is required for signing. Install with: pip install cryptography")

    with private_key_path.open("rb") as handle:
        private_key = serialization.load_pem_private_key(handle.read(), password=None)

    signature = private_key.sign(canonical_passport_bytes(passport), ec.ECDSA(hashes.SHA256()))
    signed = dict(passport)
    signed["signature"] = signature.hex()
    return signed


def verify_signature(passport: dict[str, Any], public_key_path: Path) -> tuple[bool, str | None]:
    if not CRYPTO_AVAILABLE or serialization is None or ec is None or hashes is None or InvalidSignature is None:
        return False, "The 'cryptography' package is required for verification. Install with: pip install cryptography"

    signature = passport.get("signature")
    if not isinstance(signature, str) or not signature:
        return False, "Passport does not contain a signature string."

    try:
        signature_bytes = bytes.fromhex(signature)
    except ValueError as error:
        return False, f"Signature is not valid hex: {error}"

    try:
        with public_key_path.open("rb") as handle:
            public_key = serialization.load_pem_public_key(handle.read())
        public_key.verify(signature_bytes, canonical_passport_bytes(passport), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False, "Signature does not match passport content."
    except OSError as error:
        return False, f"Public key file error: {error}"
    except ValueError as error:
        return False, f"Public key or signature error: {error}"

    return True, None


def generate_keypair(private_key_path: Path, public_key_path: Path, force: bool = False) -> None:
    if not CRYPTO_AVAILABLE or serialization is None or ec is None:
        raise RuntimeError("The 'cryptography' package is required for key generation. Install with: pip install cryptography")
    if not force:
        existing = [path for path in (private_key_path, public_key_path) if path.exists()]
        if existing:
            names = ", ".join(str(path) for path in existing)
            raise FileExistsError(f"Refusing to overwrite existing key file(s): {names}. Use --force to overwrite.")

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_key_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def validate_passport_file(path: Path, schema: dict[str, Any], verbose: bool = False) -> tuple[bool, str | None]:
    try:
        passport = load_json(path)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(passport)
    except json.JSONDecodeError as error:
        return False, f"Invalid JSON: {error}"
    except ValidationError as error:
        schema_path = ".".join(str(part) for part in error.path) or "<root>"
        return False, f"Path: {schema_path}; Problem: {error.message}"
    except OSError as error:
        return False, f"File error: {error}"

    if verbose:
        print(json.dumps(passport, indent=2, sort_keys=True))
    return True, None


def validate_folder(folder: Path, schema: dict[str, Any], verbose: bool = False) -> bool:
    json_files = sorted(folder.rglob("*.json"))
    if not json_files:
        print(f"No JSON files found in {folder}")
        return False

    results: list[tuple[Path, bool, str | None]] = []
    for path in json_files:
        is_valid, error = validate_passport_file(path, schema, verbose=verbose)
        results.append((path, is_valid, error))

    print_folder_results(folder, results)
    return all(is_valid for _, is_valid, _ in results)


def print_folder_results(folder: Path, results: list[tuple[Path, bool, str | None]]) -> None:
    valid_count = sum(1 for _, is_valid, _ in results if is_valid)
    invalid_count = len(results) - valid_count

    if RICH_AVAILABLE and CONSOLE is not None and Table is not None:
        table = Table(title=f"Vector Passport Batch Validation: {folder}", show_lines=True)
        table.add_column("File", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Details", style="red")
        for path, is_valid, error in results:
            status = "[green]VALID[/green]" if is_valid else "[red]INVALID[/red]"
            details = "" if is_valid else shorten(error or "", 100)
            table.add_row(str(path), status, details)
        CONSOLE.print(table)
        CONSOLE.print(f"[bold]Summary:[/bold] {valid_count} valid / {invalid_count} invalid out of {len(results)}")
        return

    print(f"Validating {len(results)} passport(s) in {folder}...")
    print("=" * 100)
    print(f"{'File':<58} {'Status':<10} Details")
    print("=" * 100)
    for path, is_valid, error in results:
        status = "VALID" if is_valid else "INVALID"
        print(f"{str(path):<58} {status:<10} {shorten(error or '', 28)}")
    print("=" * 100)
    print(f"Summary: {valid_count} valid / {invalid_count} invalid out of {len(results)}")


def shorten(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vector Passport v1.0 - Create and Validate Tool")
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA_PATH),
        help="Path to the Vector Passport JSON Schema.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a new Vector Passport")
    create_parser.add_argument("--source-uri", required=True, help="URI of the original file.")
    create_parser.add_argument("--source-file", required=True, help="Local source file used to compute source.hash.")
    create_parser.add_argument("--chunk-start", type=int, required=True)
    create_parser.add_argument("--chunk-end", type=int, required=True)
    create_parser.add_argument("--chunk-id", help="Stable identifier for the chunk.")
    create_parser.add_argument("--chunk-strategy", default="recursive-character-512-50@1.0.0")
    create_parser.add_argument(
        "--chunk-unit",
        default="character",
        choices=["byte", "character", "token", "page", "time", "pixel", "frame", "region", "other"],
    )
    create_parser.add_argument("--page", type=int)
    create_parser.add_argument("--model", required=True)
    create_parser.add_argument("--model-version", default="1.5.0")
    create_parser.add_argument("--provider", default="nomic-ai")
    create_parser.add_argument("--dimension", type=int, required=True)
    create_parser.add_argument("--vector-file", help="JSON file containing the embedding vector array.")
    create_parser.add_argument("--vector-stdin", action="store_true", help="Read embedding vector JSON from stdin.")
    create_parser.add_argument("--mime-type", default="application/octet-stream")
    create_parser.add_argument(
        "--modality",
        default="text",
        choices=["text", "image", "video", "audio", "multimodal", "other"],
    )
    create_parser.add_argument("--created-by", default="vector-passport-cli")
    create_parser.add_argument("--normalize", action=argparse.BooleanOptionalAction, default=True)
    create_parser.add_argument("--output", "-o", help="Output file. Prints to stdout if omitted.")
    create_parser.add_argument("--dry-run", action="store_true", help="Print the passport without writing a file.")
    create_parser.add_argument("--sign", action="store_true", help="Sign the passport after creation.")
    create_parser.add_argument("--private-key", help="Path to PEM private key for signing.")

    validate_parser = subparsers.add_parser("validate", help="Validate one or more passport files")
    validate_parser.add_argument("files", nargs="+", help="Passport JSON file(s) to validate.")
    validate_parser.add_argument("-v", "--verbose", action="store_true")

    folder_parser = subparsers.add_parser("validate-folder", help="Validate all JSON passports in a folder")
    folder_parser.add_argument("folder", help="Folder containing passport JSON files.")
    folder_parser.add_argument("-v", "--verbose", action="store_true")

    verify_parser = subparsers.add_parser("verify-signature", help="Verify a passport cryptographic signature")
    verify_parser.add_argument("file", help="Passport JSON file to verify.")
    verify_parser.add_argument("--public-key", required=True, help="Path to PEM public key.")

    key_parser = subparsers.add_parser("generate-keypair", help="Generate an ECDSA key pair for passport signing")
    key_parser.add_argument("--private-key", default="private_key.pem", help="Output path for the PEM private key.")
    key_parser.add_argument("--public-key", default="public_key.pem", help="Output path for the PEM public key.")
    key_parser.add_argument("--force", action="store_true", help="Overwrite existing key files.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        schema = load_schema(Path(args.schema))
    except (OSError, json.JSONDecodeError, SchemaError) as error:
        print(f"SCHEMA ERROR: {error}")
        return 1

    if args.command == "create":
        try:
            passport = create_passport(args)
            if args.sign:
                if not args.private_key:
                    raise ValueError("--private-key is required when using --sign.")
                passport = sign_passport(passport, Path(args.private_key))
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(passport)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError, ValidationError) as error:
            print(f"CREATE FAILED: {error}")
            return 1

        if args.dry_run:
            print("DRY RUN: Passport that would be created:")
            print(json.dumps(passport, indent=2, sort_keys=True))
            return 0

        if args.output:
            write_json(Path(args.output), passport)
            print(f"Created passport: {args.output}")
            if args.sign:
                print("Signed passport successfully.")
        else:
            print(json.dumps(passport, indent=2, sort_keys=True))
        return 0

    if args.command == "validate":
        success = True
        for file_path in args.files:
            is_valid, error = validate_passport_file(Path(file_path), schema, verbose=args.verbose)
            if is_valid:
                print(f"VALID: {file_path}")
            else:
                print(f"INVALID: {file_path}")
                print(f"  {error}")
            success = is_valid and success
        return 0 if success else 1

    if args.command == "validate-folder":
        folder = Path(args.folder)
        if not folder.is_dir():
            print(f"Not a directory: {folder}")
            return 1
        return 0 if validate_folder(folder, schema, verbose=args.verbose) else 1

    if args.command == "verify-signature":
        try:
            passport = load_json(Path(args.file))
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(passport)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            print(f"VERIFY FAILED: {error}")
            return 1

        is_valid, error = verify_signature(passport, Path(args.public_key))
        if is_valid:
            print(f"Signature VALID: {args.file}")
            return 0
        print(f"Signature INVALID: {args.file}")
        print(f"  {error}")
        return 1

    if args.command == "generate-keypair":
        try:
            generate_keypair(Path(args.private_key), Path(args.public_key), force=args.force)
        except (OSError, RuntimeError) as error:
            print(f"KEY GENERATION FAILED: {error}")
            return 1
        print(f"Created private key: {args.private_key}")
        print(f"Created public key: {args.public_key}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
