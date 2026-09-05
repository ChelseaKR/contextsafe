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
from contextsafe.html_receipt import render_receipt_page
from contextsafe.i18n import SOURCE_LOCALE, Surface, available_locales, source_catalog
from contextsafe.importers import (
    available_formats,
    checkpoint_value,
    compile_profile,
    import_source,
    load_profile,
)
from contextsafe.jsonio import load_json
from contextsafe.models import EvaluationBundle, OutcomeStatus
from contextsafe.pack import compile_pack
from contextsafe.plan import parse_plan, validate_plan
from contextsafe.preflight import preflight_source
from contextsafe.receipt import build_receipt_document, input_payload, render_receipt
from contextsafe.receipt_delta import diff_receipts, parse_receipt_document
from contextsafe.reference_fixtures import (
    DEFAULT_EXPORT_DIRECTORY,
    export_reference_fixtures,
)
from contextsafe.review import (
    append_review_event,
    derive_review_state,
    refuse_output_over_log,
)
from contextsafe.validation import parse_bundle, parse_case

EXIT_SUCCESS = 0
"""The command completed and every requested contract check passed."""

EXIT_FINDING = 1
"""A receipt was produced, and an opt-in ``--fail-on`` threshold was met.

The artifact is valid and fully emitted; the exit code reports what the
receipt found, so a caller wiring ``evaluate`` into a pipeline can block on
findings without re-parsing the document. Default behaviour is unchanged.
"""

EXIT_CONTRACT_ERROR = 2
"""A fail-closed contract rejection; stderr carries one stable JSON error."""

EXIT_USAGE_ERROR = 64
"""The command line itself was invalid before any input file was opened."""

_HELP = Surface(name="cli-help", catalog=source_catalog())
"""Help text comes from the catalog, and only ever in the source locale.

Externalizing it removes the second copy of every sentence, but the CLI is
deliberately not localized at runtime: stdout, stderr, and ``--output`` bytes
are pinned across time zones, locales, and platforms by
``tests/test_determinism.py``, and text that changed with the environment
would break the guarantee those artifacts exist to give. The localized surface
is the rendered HTML page, where a reader — not a hash — is the consumer.
"""


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
        "--quiet", action="store_true", help=_HELP.text("cli.flag.quiet")
    )
    parent.add_argument(
        "--no-color", action="store_true", help=_HELP.text("cli.flag.no_color")
    )
    parent.add_argument(
        "--log-dir",
        type=Path,
        help=(
            "append one closed-vocabulary event record to a local log in this "
            "directory. Off unless given, never read from the environment, and "
            "the record carries the command, the outcome, the error code, and "
            "the command's own warning codes only: no message, no path, no "
            "clock reading"
        ),
    )
    return parent


def _parser() -> argparse.ArgumentParser:
    modes = _mode_flags()
    parser = _Parser(
        prog="contextsafe",
        description=_HELP.text("cli.description"),
        epilog=_HELP.text("cli.epilog"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "evaluate"):
        subparser = subparsers.add_parser(
            command, parents=[modes], help=_HELP.text(f"cli.command.{command}")
        )
        subparser.add_argument("--case", required=True, type=Path)
        subparser.add_argument("--observations", required=True, type=Path)
        subparser.add_argument("--rules", required=True, type=Path)
        if command == "evaluate":
            subparser.add_argument("--output", type=Path)
            subparser.add_argument(
                "--claimed-generated-at",
                help=_HELP.text("cli.flag.claimed_generated_at"),
            )
            subparser.add_argument(
                "--fail-on",
                choices=("nothing", "finding"),
                default="nothing",
                help=_HELP.text("cli.flag.fail_on"),
            )
            subparser.set_defaults(fail_on="nothing", receipt_failing_outcomes=0)
    render_parser = subparsers.add_parser(
        "render", parents=[modes], help=_HELP.text("cli.command.render")
    )
    render_parser.add_argument(
        "--receipt", required=True, type=Path, help=_HELP.text("cli.flag.receipt")
    )
    render_parser.add_argument(
        "--lang",
        default=SOURCE_LOCALE,
        choices=available_locales(),
        help=_HELP.text("cli.flag.lang"),
    )
    render_parser.add_argument("--output", type=Path)
    # `render` stays a top-level command for now; it may move under the
    # `receipt` group in a later pass, and its arguments would not change.
    receipt_parser = subparsers.add_parser(
        "receipt",
        help="Compare receipt documents; verification and signing are not here.",
    )
    receipt_subparsers = receipt_parser.add_subparsers(
        dest="receipt_command", required=True
    )
    diff_help = (
        "emit the deterministic delta between two compatible receipt "
        "documents: per rule, the status and reason in each, whether the "
        "outcome changed, and whether the evidence hashes changed. Both "
        "receipts are unsigned, so 'before' and 'after' are the caller's "
        "labels and prove nothing about which run came first"
    )
    receipt_diff = receipt_subparsers.add_parser(
        "diff", parents=[modes], help=diff_help, description=diff_help
    )
    receipt_diff.add_argument(
        "--before",
        required=True,
        type=Path,
        help="the receipt document the caller treats as the earlier one",
    )
    receipt_diff.add_argument(
        "--after",
        required=True,
        type=Path,
        help="the receipt document the caller treats as the later one",
    )
    receipt_diff.add_argument("--output", type=Path)
    pack_parser = subparsers.add_parser("pack", help=_HELP.text("cli.command.pack"))
    pack_subparsers = pack_parser.add_subparsers(dest="pack_command", required=True)
    pack_validate = pack_subparsers.add_parser(
        "validate", parents=[modes], help=_HELP.text("cli.command.pack.validate")
    )
    pack_validate.add_argument("--pack", required=True, type=Path)
    pack_validate.add_argument("--as-of", required=True)
    pack_validate.add_argument("--output", type=Path)
    plan_parser = subparsers.add_parser("plan", help=_HELP.text("cli.command.plan"))
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command", required=True)
    plan_validate = plan_subparsers.add_parser(
        "validate", parents=[modes], help=_HELP.text("cli.command.plan.validate")
    )
    plan_validate.add_argument("--engagement", required=True, type=Path)
    plan_validate.add_argument("--plan", required=True, type=Path)
    plan_validate.add_argument("--pack", required=True, type=Path)
    plan_validate.add_argument("--as-of", required=True)
    plan_validate.add_argument("--output", type=Path)
    evidence_parser = subparsers.add_parser(
        "evidence", help=_HELP.text("cli.command.evidence")
    )
    evidence_subparsers = evidence_parser.add_subparsers(
        dest="evidence_command", required=True
    )
    evidence_preflight = evidence_subparsers.add_parser(
        "preflight", parents=[modes], help=_HELP.text("cli.command.evidence.preflight")
    )
    evidence_preflight.add_argument("--source", required=True, type=Path)
    evidence_preflight.add_argument("--plan", required=True, type=Path)
    evidence_preflight.add_argument("--case-token", required=True)
    evidence_preflight.add_argument("--checkpoint", required=True)
    evidence_preflight.add_argument("--source-type", required=True)
    evidence_preflight.add_argument("--media-type", required=True)
    evidence_preflight.add_argument("--output", type=Path)
    import_parser = subparsers.add_parser(
        "import", parents=[modes], help=_HELP.text("cli.command.import")
    )
    # ``choices`` makes argparse echo an unrecognized format name on stderr,
    # as ``--fail-on`` and ``--lang`` already do. A format name is a registry
    # key, not identity data. Do not extend the pattern to ``--checkpoint`` or
    # to any flag whose value comes from a source: those are validated by the
    # command and rejected with a code and a location, never echoed.
    import_parser.add_argument(
        "--format",
        required=True,
        choices=available_formats(),
        help=_HELP.text("cli.flag.format"),
    )
    import_parser.add_argument("--source", required=True, type=Path)
    import_parser.add_argument("--case", required=True, type=Path)
    import_parser.add_argument("--checkpoint", required=True)
    import_parser.add_argument(
        "--mapping",
        type=Path,
        help=(
            "a mapping profile to apply after the conversion; without it every "
            "value is the source's own token. The profile is validated first, "
            "must be for the same format, and its review status can only be "
            "not_reviewed; every emitted observation then records the "
            "profile's sha256 and version"
        ),
    )
    import_parser.add_argument("--output", type=Path)
    mapping_parser = subparsers.add_parser(
        "mapping",
        help=(
            "Work with mapping profiles: validate one and emit its canonical "
            "unsigned form and digest. There is no mapping sign command"
        ),
    )
    mapping_subparsers = mapping_parser.add_subparsers(
        dest="mapping_command", required=True
    )
    mapping_validate = mapping_subparsers.add_parser(
        "validate",
        parents=[modes],
        help=(
            "validate a mapping profile against the registered importers and "
            "emit its canonical unsigned form with its sha256; a profile "
            "declaring any review status but not_reviewed is rejected"
        ),
    )
    mapping_validate.add_argument("--profile", required=True, type=Path)
    mapping_validate.add_argument("--output", type=Path)

    finding_parser = subparsers.add_parser(
        "finding",
        help=(
            "record and derive unsigned finding dispositions in an append-only "
            "review log; every event is declared, not verified"
        ),
    )
    finding_subparsers = finding_parser.add_subparsers(
        dest="finding_command", required=True
    )
    finding_review = finding_subparsers.add_parser(
        "review",
        parents=[modes],
        help=(
            "validate one review event against a receipt and the log's prior "
            "state, then append one canonical line; refuses an out-of-order "
            "transition and a log whose earlier lines do not re-hash"
        ),
    )
    finding_review.add_argument("--receipt", required=True, type=Path)
    finding_review.add_argument("--event", required=True, type=Path)
    finding_review.add_argument("--log", required=True, type=Path)
    finding_review.add_argument("--output", type=Path)
    finding_list = finding_subparsers.add_parser(
        "list",
        parents=[modes],
        help=(
            "derive the current disposition per outcome from a review log "
            "without changing it"
        ),
    )
    finding_list.add_argument("--log", required=True, type=Path)
    finding_list.add_argument("--output", type=Path)
    fixtures_parser = subparsers.add_parser(
        "fixtures",
        help="Work with the synthetic reference fixtures the package carries.",
    )
    fixtures_subparsers = fixtures_parser.add_subparsers(
        dest="fixtures_command", required=True
    )
    fixtures_export = fixtures_subparsers.add_parser(
        "export",
        parents=[modes],
        help=(
            "copy the packaged synthetic reference fixtures into a directory, "
            "so the documented commands run from an installed wheel exactly "
            "as they run from a clone"
        ),
    )
    fixtures_export.add_argument(
        "--directory",
        type=Path,
        default=DEFAULT_EXPORT_DIRECTORY,
        help=(
            "where to write them; defaults to fixtures/reference under the "
            "current directory. A file already there that is byte-identical is "
            "left alone and reported as unchanged; one that differs is a "
            "contract error, and then nothing is written"
        ),
    )
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
    if args.command == "fixtures":
        if args.fixtures_command != "export":
            raise ContextSafeError(
                "unsupported_command", "$", "fixtures command is unsupported"
            )
        return f"{canonical_json(export_reference_fixtures(args.directory))}\n"
    if args.command == "finding":
        return _finding_command(args)
    return None


def _import_command(args: argparse.Namespace) -> str:
    """Convert one boundary-scanned source into an observation-set document.

    Read-only: the source is opened once through the evidence boundary
    scan, never copied, indexed, or logged, and the only thing emitted is
    the document ``evaluate --observations`` accepts. The result's counts
    stay in process because that contract has no field for them; its
    closed-vocabulary warnings are handed to the event log, which is the one
    surface that already carries closed codes, so a profile that binds
    nothing is visible to an operator who asked for a log rather than to the
    test suite alone.
    """

    mapping_path: Path | None = args.mapping
    profile = None if mapping_path is None else load_profile(load_json(mapping_path))
    result = import_source(
        args.format,
        args.source,
        case=parse_case(load_json(args.case)),
        checkpoint=checkpoint_value(args.checkpoint, "$.checkpoint"),
        profile=profile,
    )
    args.event_warnings = tuple(item.value for item in result.warnings)
    return f"{canonical_json(result.observation_set())}\n"


def _mapping_command(args: argparse.Namespace) -> str:
    """Validate one mapping profile and emit its canonical form and digest.

    ``mapping validate`` is the only mapping command. ``mapping sign``
    (Architecture section 7) is not built: no signer key, trust manifest, or
    enrolled reviewer exists, and the compiled document says so.
    """

    if args.mapping_command != "validate":
        raise ContextSafeError(
            "unsupported_command", "$", "mapping command is unsupported"
        )
    return f"{canonical_json(compile_profile(load_json(args.profile)).to_dict())}\n"


def _finding_command(args: argparse.Namespace) -> str:
    """Append one declared review event, or derive the log's current state.

    Both print the derived state document: the disposition of every outcome
    the log has seen, the log head hash, and the pinned limitations. The
    receipt is read for its hashes and its finding outcomes only, and it is
    never changed.
    """

    refuse_output_over_log(args.output, args.log)
    if args.finding_command == "review":
        state = append_review_event(
            args.log, load_json(args.event), load_json(args.receipt)
        )
        refuse_output_over_log(args.output, args.log)
        return f"{canonical_json(state.to_dict())}\n"
    if args.finding_command == "list":
        return f"{canonical_json(derive_review_state(args.log).to_dict())}\n"
    raise ContextSafeError("unsupported_command", "$", "finding command is unsupported")


def _render_command(args: argparse.Namespace) -> str:
    document = load_json(args.receipt)
    if not isinstance(document, dict):
        raise ContextSafeError(
            "invalid_receipt_document",
            "$",
            "receipt document must be a JSON object",
        )
    return render_receipt_page(document, locale=args.lang)


def _conversion_command(args: argparse.Namespace) -> str | None:
    """Handle the commands that turn one document into another, or None."""

    if args.command == "render":
        return _render_command(args)
    if args.command == "import":
        return _import_command(args)
    if args.command == "mapping":
        return _mapping_command(args)
    return None


def _receipt_command(args: argparse.Namespace) -> str | None:
    """Handle the commands that read receipt documents, or return None."""

    if args.command == "render":
        return _render_command(args)
    if args.command != "receipt":
        return None
    if args.receipt_command != "diff":
        raise ContextSafeError(
            "unsupported_command", "$", "receipt command is unsupported"
        )
    before = parse_receipt_document(load_json(args.before), path="$.before")
    after = parse_receipt_document(load_json(args.after), path="$.after")
    return f"{canonical_json(diff_receipts(before, after).to_dict())}\n"


def _governance_command(args: argparse.Namespace) -> str | None:
    """Run a pack, plan, or evidence command, or return None for another.

    These three share a shape: a subcommand this iteration does not implement
    is refused rather than ignored, and each emits one canonical artifact.
    They live here rather than in ``_run`` so that adding a command group
    does not push the dispatcher past the complexity the gate allows.
    """

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
    return None


def _run(args: argparse.Namespace) -> str:
    operator = _operator_command(args)
    if operator is not None:
        return operator
    conversion = _conversion_command(args)
    if conversion is not None:
        return conversion

    receipt = _receipt_command(args)
    if receipt is not None:
        return receipt
    governance = _governance_command(args)
    if governance is not None:
        return governance
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
    return _evaluate_command(args, bundle)


def _evaluate_command(args: argparse.Namespace, bundle: EvaluationBundle) -> str:
    claimed_raw: str | None = args.claimed_generated_at
    claimed = (
        None
        if claimed_raw is None
        else timestamp_value(claimed_raw, "$.claimed_generated_at")
    )
    outcomes = evaluate(bundle)
    if args.fail_on == "finding":
        args.receipt_failing_outcomes = sum(
            1 for outcome in outcomes if outcome.status is OutcomeStatus.FAIL
        )
    document = build_receipt_document(bundle, outcomes, claimed_generated_at=claimed)
    return render_receipt(document)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a stable, documented process exit code.

    ``EXIT_SUCCESS`` (0) reports success, ``EXIT_FINDING`` (1) reports that
    ``evaluate --fail-on finding`` produced a valid receipt whose payload
    contains at least one ``fail`` outcome — the artifact is fully emitted
    first and is byte-identical to its ``EXIT_SUCCESS`` form,
    ``EXIT_CONTRACT_ERROR`` (2) reports a fail-closed contract rejection with
    one JSON error object on stderr, and ``EXIT_USAGE_ERROR`` (64) reports an
    invalid command line; ``--help`` exits 0. Output never contains ANSI
    escape sequences in any mode, and every success payload, ``--output``
    artifact, and stderr error object is the same UTF-8 byte sequence on every
    supported platform.
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
        if (
            getattr(args, "fail_on", "nothing") == "finding"
            and args.receipt_failing_outcomes > 0
        ):
            return EXIT_FINDING
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

    ``event_warnings`` is set by the command that ran, if it carried any:
    only ``import`` does. A command that failed set none, so a rejected
    record's warning list is empty.
    """

    log_dir: Path | None = getattr(args, "log_dir", None)
    if log_dir is None:
        return
    warnings: tuple[str, ...] = getattr(args, "event_warnings", ())
    try:
        append_event(
            log_dir,
            command=args.command,
            outcome=outcome,
            error_code=error_code,
            warnings=warnings,
        )
    except ContextSafeError as exc:
        failure: dict[str, JsonValue] = {"error": as_json_value(exc.to_dict())}
        _emit(sys.stderr, f"{canonical_json(failure)}\n")
