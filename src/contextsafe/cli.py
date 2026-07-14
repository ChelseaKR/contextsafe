"""Offline CLI for validating and evaluating synthetic fixture files."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from contextsafe.canonical import JsonValue, as_json_value, canonical_json, sha256_json
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.receipt import build_receipt, input_payload, render_receipt
from contextsafe.validation import parse_bundle

_MAX_INPUT_BYTES = 1_048_576


class _DuplicateKeyError(ValueError):
    """Signal that JSON contained a duplicate object member."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def _load_json(path: Path) -> JsonValue:
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise ContextSafeError(
            "input_io_error", "$", "input could not be read"
        ) from exc
    if len(raw) > _MAX_INPUT_BYTES:
        raise ContextSafeError(
            "input_too_large", "$", "input exceeds the one MiB limit"
        )
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except UnicodeDecodeError as exc:
        raise ContextSafeError("invalid_utf8", "$", "input must be UTF-8") from exc
    except _DuplicateKeyError as exc:
        raise ContextSafeError(
            "duplicate_json_key", "$", "duplicate object key is forbidden"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContextSafeError("invalid_json", "$", "input is not valid JSON") from exc
    return as_json_value(parsed)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextsafe",
        description="Validate or evaluate bounded synthetic ContextSafe fixtures.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "evaluate"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--case", required=True, type=Path)
        subparser.add_argument("--observations", required=True, type=Path)
        subparser.add_argument("--rules", required=True, type=Path)
        if command == "evaluate":
            subparser.add_argument("--output", type=Path)
    return parser


def _validated_inputs(
    args: argparse.Namespace,
) -> tuple[JsonValue, JsonValue, JsonValue]:
    return (
        _load_json(args.case),
        _load_json(args.observations),
        _load_json(args.rules),
    )


def _run(args: argparse.Namespace) -> str:
    case_value, observation_value, rule_value = _validated_inputs(args)
    bundle = parse_bundle(case_value, observation_value, rule_value)
    if args.command == "validate":
        report: dict[str, JsonValue] = {
            "case_id": bundle.case.case_id,
            "hashes": {
                "input_sha256": sha256_json(input_payload(bundle)),
                "rule_set_sha256": sha256_json(bundle.rule_set.to_dict()),
            },
            "observation_count": len(bundle.observations),
            "rule_count": len(bundle.rule_set.rules),
            "valid": True,
        }
        return f"{canonical_json(report)}\n"
    receipt = build_receipt(bundle, evaluate(bundle))
    return render_receipt(receipt)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a stable process exit code."""

    args = _parser().parse_args(argv)
    try:
        output = _run(args)
        output_path: Path | None = getattr(args, "output", None)
        if output_path is None:
            sys.stdout.write(output)
        else:
            try:
                output_path.write_text(output, encoding="utf-8")
            except OSError as exc:
                raise ContextSafeError(
                    "output_io_error", "$", "output could not be written"
                ) from exc
        return 0
    except ContextSafeError as exc:
        error: dict[str, JsonValue] = {"error": as_json_value(exc.to_dict())}
        sys.stderr.write(f"{canonical_json(error)}\n")
        return 2
