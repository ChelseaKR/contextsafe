"""Offline CLI for validating and evaluating synthetic fixture files."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from contextsafe.canonical import JsonValue, as_json_value, canonical_json, sha256_json
from contextsafe.contract_validation import date_value, timestamp_value
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.evidence import build_evidence_scope
from contextsafe.jsonio import load_json
from contextsafe.pack import compile_pack
from contextsafe.plan import parse_plan, validate_plan
from contextsafe.preflight import preflight_source
from contextsafe.receipt import build_receipt_document, input_payload, render_receipt
from contextsafe.validation import parse_bundle

EXIT_SUCCESS = 0
"""The command completed and every requested contract check passed."""

EXIT_CONTRACT_ERROR = 2
"""A fail-closed contract rejection; stderr carries one stable JSON error."""

EXIT_USAGE_ERROR = 64
"""The command line itself was invalid before any input file was opened."""


class _Parser(argparse.ArgumentParser):
    """An argument parser whose usage failures have a distinct exit code."""

    def error(self, message: str) -> NoReturn:
        """Report a usage error on stderr and exit with ``EXIT_USAGE_ERROR``."""

        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE_ERROR, f"{self.prog}: error: {message}\n")


def _mode_flags() -> "_Parser":
    parent = _Parser(add_help=False)
    parent.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "suppress the success payload on stdout; exit codes, --output "
            "files, and stderr JSON errors are unchanged"
        ),
    )
    parent.add_argument(
        "--no-color",
        action="store_true",
        help=(
            "pin the plain-output contract; contextsafe output never "
            "contains ANSI escape sequences, with or without this flag"
        ),
    )
    return parent


def _parser() -> argparse.ArgumentParser:
    modes = _mode_flags()
    parser = _Parser(
        prog="contextsafe",
        description="Validate or evaluate bounded synthetic ContextSafe fixtures.",
        epilog=(
            "exit codes: 0 success, 2 contract rejection with one JSON error "
            "object on stderr, 64 command-line usage error"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "evaluate"):
        subparser = subparsers.add_parser(command, parents=[modes])
        subparser.add_argument("--case", required=True, type=Path)
        subparser.add_argument("--observations", required=True, type=Path)
        subparser.add_argument("--rules", required=True, type=Path)
        if command == "evaluate":
            subparser.add_argument("--output", type=Path)
            subparser.add_argument(
                "--claimed-generated-at",
                help=(
                    "Optional caller-declared whole-second UTC timestamp "
                    "(YYYY-MM-DDThh:mm:ssZ) recorded only in the untrusted "
                    "receipt envelope, never in the deterministic payload."
                ),
            )
    pack_parser = subparsers.add_parser(
        "pack", help="Compile and validate an unsigned governed pack."
    )
    pack_subparsers = pack_parser.add_subparsers(dest="pack_command", required=True)
    pack_validate = pack_subparsers.add_parser("validate", parents=[modes])
    pack_validate.add_argument("--pack", required=True, type=Path)
    pack_validate.add_argument("--as-of", required=True)
    pack_validate.add_argument("--output", type=Path)
    plan_parser = subparsers.add_parser(
        "plan", help="Validate an unsigned non-production execution plan."
    )
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command", required=True)
    plan_validate = plan_subparsers.add_parser("validate", parents=[modes])
    plan_validate.add_argument("--engagement", required=True, type=Path)
    plan_validate.add_argument("--plan", required=True, type=Path)
    plan_validate.add_argument("--pack", required=True, type=Path)
    plan_validate.add_argument("--as-of", required=True)
    plan_validate.add_argument("--output", type=Path)
    evidence_parser = subparsers.add_parser(
        "evidence", help="Run a read-only synthetic-evidence boundary check."
    )
    evidence_subparsers = evidence_parser.add_subparsers(
        dest="evidence_command", required=True
    )
    evidence_preflight = evidence_subparsers.add_parser("preflight", parents=[modes])
    evidence_preflight.add_argument("--source", required=True, type=Path)
    evidence_preflight.add_argument("--plan", required=True, type=Path)
    evidence_preflight.add_argument("--case-token", required=True)
    evidence_preflight.add_argument("--checkpoint", required=True)
    evidence_preflight.add_argument("--source-type", required=True)
    evidence_preflight.add_argument("--media-type", required=True)
    return parser


def _validated_inputs(
    args: argparse.Namespace,
) -> tuple[JsonValue, JsonValue, JsonValue]:
    return (
        load_json(args.case),
        load_json(args.observations),
        load_json(args.rules),
    )


def _run(args: argparse.Namespace) -> str:
    if args.command == "pack":
        if args.pack_command != "validate":
            raise ContextSafeError(
                "unsupported_command", "$", "pack command is unsupported"
            )
        pack_path: Path = args.pack
        compilation = compile_pack(
            load_json(pack_path),
            root=pack_path.parent,
            as_of=date_value(args.as_of, "$.as_of"),
        )
        return f"{canonical_json(compilation.to_dict())}\n"
    if args.command == "plan":
        if args.plan_command != "validate":
            raise ContextSafeError(
                "unsupported_command", "$", "plan command is unsupported"
            )
        as_of = date_value(args.as_of, "$.as_of")
        plan_pack_path: Path = args.pack
        pack = compile_pack(
            load_json(plan_pack_path), root=plan_pack_path.parent, as_of=as_of
        )
        plan_compilation = validate_plan(
            load_json(args.engagement),
            load_json(args.plan),
            pack=pack,
            as_of=as_of,
        )
        return f"{canonical_json(plan_compilation.to_dict())}\n"
    if args.command == "evidence":
        if args.evidence_command != "preflight":
            raise ContextSafeError(
                "unsupported_command", "$", "evidence command is unsupported"
            )
        plan = parse_plan(load_json(args.plan))
        scope = build_evidence_scope(
            plan,
            case_token=args.case_token,
            checkpoint=args.checkpoint,
            source_type=args.source_type,
            media_type=args.media_type,
        )
        result = preflight_source(args.source, scope)
        return f"{canonical_json(result.to_dict())}\n"
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
    claimed_raw: str | None = args.claimed_generated_at
    claimed = (
        None
        if claimed_raw is None
        else timestamp_value(claimed_raw, "$.claimed_generated_at")
    )
    document = build_receipt_document(
        bundle, evaluate(bundle), claimed_generated_at=claimed
    )
    return render_receipt(document)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a stable, documented process exit code.

    ``EXIT_SUCCESS`` (0) reports success, ``EXIT_CONTRACT_ERROR`` (2) reports a
    fail-closed contract rejection with one JSON error object on stderr, and
    ``EXIT_USAGE_ERROR`` (64) reports an invalid command line; ``--help`` exits
    0. Output never contains ANSI escape sequences in any mode.
    """

    args = _parser().parse_args(argv)
    try:
        output = _run(args)
        output_path: Path | None = getattr(args, "output", None)
        if output_path is not None:
            try:
                output_path.write_text(output, encoding="utf-8")
            except OSError as exc:
                raise ContextSafeError(
                    "output_io_error", "$", "output could not be written"
                ) from exc
        elif not args.quiet:
            sys.stdout.write(output)
        return EXIT_SUCCESS
    except ContextSafeError as exc:
        error: dict[str, JsonValue] = {"error": as_json_value(exc.to_dict())}
        sys.stderr.write(f"{canonical_json(error)}\n")
        return EXIT_CONTRACT_ERROR
