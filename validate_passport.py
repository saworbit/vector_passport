#!/usr/bin/env python3
"""
Vector Passport v1.0 Validator

Usage:
    python validate_passport.py examples/sample-passport.json
    python validate_passport.py examples/sample-passport.json --verbose
    python validate_passport.py --self-test

The validator reads spec/v1.0/schema.json so the CLI stays aligned with the
canonical schema in this repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, SchemaError, ValidationError


ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = ROOT / "spec" / "v1.0" / "schema.json"
DEFAULT_SAMPLE_PATH = ROOT / "examples" / "sample-passport.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_passport(passport: dict[str, Any], schema: dict[str, Any], verbose: bool = False) -> bool:
    """Validate a passport object against the Vector Passport schema."""
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(passport)
    except ValidationError as error:
        print("INVALID: Schema validation failed.")
        path = ".".join(str(part) for part in error.path) or "<root>"
        print(f"  Path: {path}")
        print(f"  Problem: {error.message}")
        return False
    except SchemaError as error:
        print("SCHEMA ERROR: The schema itself is invalid.")
        print(f"  Problem: {error.message}")
        return False

    print("VALID: Passport is correctly formed.")
    if verbose:
        print(json.dumps(passport, indent=2, sort_keys=True))
    return True


def validate_file(passport_path: Path, schema_path: Path = DEFAULT_SCHEMA_PATH, verbose: bool = False) -> bool:
    try:
        schema = load_json(schema_path)
        passport = load_json(passport_path)
    except json.JSONDecodeError as error:
        print(f"INVALID JSON: {error}")
        return False
    except OSError as error:
        print(f"FILE ERROR: {error}")
        return False

    print(f"Validating {passport_path}")
    return validate_passport(passport, schema, verbose=verbose)


def run_self_test() -> bool:
    schema = load_json(DEFAULT_SCHEMA_PATH)
    sample = load_json(DEFAULT_SAMPLE_PATH)

    print("=== Testing valid passport ===")
    valid_ok = validate_passport(sample, schema)

    print("\n=== Testing invalid passport (missing required field) ===")
    invalid_sample = dict(sample)
    invalid_sample.pop("passport_version", None)
    invalid_ok = not validate_passport(invalid_sample, schema)

    return valid_ok and invalid_ok


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate Vector Passport v1.0 JSON files.")
    parser.add_argument("file", nargs="?", help="Path to the passport JSON file.")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print the full passport content if valid.",
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA_PATH),
        help="Path to the Vector Passport JSON Schema.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the built-in valid and invalid sample checks.",
    )
    args = parser.parse_args(argv[1:])

    if args.self_test:
        return 0 if run_self_test() else 1

    if not args.file:
        parser.error("the following arguments are required unless --self-test is used: file")

    return 0 if validate_file(Path(args.file), schema_path=Path(args.schema), verbose=args.verbose) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
