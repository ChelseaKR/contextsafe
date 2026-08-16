"""Offline CLI for validating and evaluating synthetic fixture files."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO, NoReturn, TextIO

from contextsafe.canonical import JsonValue, as_json_value, canonical_json, sha256_json
from contextsafe.contract_validation import date_value, timestamp_value
from contextsafe.diagnostics import (
    build_diagnostics,
    build_support_bundle,
    enumerate_cleanup,
    remove_cleanup,
)
from contextsafe.errors import ContextSafeError
from contextsafe.evaluator import evaluate
from contextsafe.eventlog import Outcome, append_event
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


def _emit(stream: TextIO, text: str) -> None:
    """Write exactly the UTF-8 bytes of ``text`` with no platform rewriting.

    Command output is a hash-covered artifact, not display text. A text-mode
    write translates a line feed into the platform line separator and encodes
    with the platform's preferred encoding, so the same receipt would leave a
    POSIX host and a Windows host with different bytes and different file
    digests. R-10 rates that cross-platform divergence as a live risk and
    RG-15 requires identical deterministic JSON across three runs and every
    supported operating system, so bytes are written to the binary buffer
    wherever the stream exposes one. A caller that substitutes a text-only
    stream in process still receives the identical text.
    """

    buffer: BinaryIO | None = getattr(stream, "buffer", None)
    if buffer is None:
        stream.write(text)
        return
    stream.flush()
    buffer.write(text.encode("utf-8"))
    buffer.flush()


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
    parent.add_argument(
        "--log-dir",
        type=Path,
        help=(
            "append one closed-vocabulary event record to a local log in this "
            "directory. Off unless given, never read from the environment, and "
            "the record carries the command, the outcome, and the error code "
            "only: no message, no path, no clock reading"
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
    evidence_preflight.add_argument("--output", type=Path)
    diagnostics_parser = subparsers.add_parser(
        "diagnostics",
        parents=[modes],
        help="Report what this installation can do, not what it has done.",
    )
    diagnostics_parser.add_argument("--workspace", type=Path)
    diagnostics_parser.add_argument("--output", type=Path)
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        parents=[modes],
        help="List what the tool created in a workspace; removal is explicit.",
    )
    cleanup_parser.add_argument("--workspace", required=True, type=Path)
    cleanup_parser.add_argument(
        "--remove",
        action="store_true",
        help=(
            "delete the entries this command lists. Never leaves the "
            "workspace, never follows a symbolic link, and never removes an "
            "entry it could not classify"
        ),
    )
    cleanup_parser.add_argument(
        "--confirm",
        action="store_true",
        help="required alongside --remove; without it nothing is deleted",
    )
    cleanup_parser.add_argument("--output", type=Path)
    bundle_parser = subparsers.add_parser(
        "support-bundle",
        parents=[modes],
        help="Assemble a support bundle redacted by construction.",
    )
    bundle_parser.add_argument("--workspace", type=Path)
    bundle_parser.add_argument(
        "--error-code",
        action="append",
        default=[],
        help=(
            "a ContextSafe error code to include. Recorded as a digest, "
            "because this command cannot know that what it was handed is one"
        ),
    )
    bundle_parser.add_argument("--output", type=Path)
    return parser


def _validated_inputs(
    args: argparse.Namespace,
) -> tuple[JsonValue, JsonValue, JsonValue]:
    return (
        load_json(args.case),
        load_json(args.observations),
        load_json(args.rules),
    )


def _operator_command(args: argparse.Namespace) -> str | None:
    """Handle the operator-facing commands, or return None for the rest."""

    if args.command == "diagnostics":
        return f"{canonical_json(build_diagnostics(args.workspace))}\n"
    if args.command == "cleanup":
        plan = enumerate_cleanup(args.workspace)
        summary = plan.to_dict()
        if args.remove:
            if not args.confirm:
                raise ContextSafeError(
                    "cleanup_not_confirmed",
                    "$",
                    "--remove requires --confirm; nothing was deleted",
                )
            removed, retained = remove_cleanup(plan)
            summary = {**summary, "removed": removed, "retained_count": retained}
        return f"{canonical_json(summary)}\n"
    if args.command == "support-bundle":
        bundle = build_support_bundle(args.workspace, error_codes=args.error_code)
        return f"{canonical_json(bundle)}\n"
    return None


def _run(args: argparse.Namespace) -> str:
    operator = _operator_command(args)
    if operator is not None:
        return operator
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
    0. Output never contains ANSI escape sequences in any mode, and every
    success payload, ``--output`` artifact, and stderr error object is the
    same UTF-8 byte sequence on every supported platform.
    """

    args = _parser().parse_args(argv)
    try:
        output = _run(args)
        output_path: Path | None = getattr(args, "output", None)
        if output_path is not None:
            try:
                output_path.write_bytes(output.encode("utf-8"))
            except OSError as exc:
                raise ContextSafeError(
                    "output_io_error", "$", "output could not be written"
                ) from exc
        elif not args.quiet:
            _emit(sys.stdout, output)
        _log(args, Outcome.ACCEPTED, None)
        return EXIT_SUCCESS
    except ContextSafeError as exc:
        error: dict[str, JsonValue] = {"error": as_json_value(exc.to_dict())}
        _emit(sys.stderr, f"{canonical_json(error)}\n")
        _log(args, Outcome.REJECTED, exc.code)
        return EXIT_CONTRACT_ERROR


def _log(args: argparse.Namespace, outcome: Outcome, error_code: str | None) -> None:
    """Append one event record, but only because ``--log-dir`` asked for it.

    A logging failure never changes the exit code of the command that was
    logged: the command already succeeded or already failed for its own
    reasons, and turning "the log directory is read-only" into "your evaluation
    failed" would be its own defect. The failure is reported on stderr as a
    structured error and nothing else changes.
    """

    log_dir: Path | None = getattr(args, "log_dir", None)
    if log_dir is None:
        return
    try:
        append_event(
            log_dir, command=args.command, outcome=outcome, error_code=error_code
        )
    except ContextSafeError as exc:
        failure: dict[str, JsonValue] = {"error": as_json_value(exc.to_dict())}
        _emit(sys.stderr, f"{canonical_json(failure)}\n")
