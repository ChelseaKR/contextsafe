"""Three-run, cross-environment determinism evidence for command artifacts.

R-10 rates local cross-platform nondeterminism as a live risk,
[Test and evaluation](../docs/09-TEST-AND-EVALUATION.md) section 3 makes
invariant 10 merge-blocking, and RG-15 requires identical deterministic JSON
across three runs. ``tests/test_property_invariants.py`` covers the in-process
half of that invariant: the same bundle, permuted, produces the same payload.
This module covers the process half. Every scenario runs three times in three
fresh interpreters under a deliberately hostile spread of environments —
different time zone, locale, hash seed, UTF-8 mode, working directory, and
input directory — and requires byte-identical exit codes, stdout, stderr, and
``--output`` artifacts.

The pinned digest carries the cross-platform half of the claim: the same
constant must be reproduced by the CI determinism matrix on Ubuntu, macOS, and
Windows, so a platform-dependent line ending, encoding, clock, locale, or path
leak fails here rather than in a partner's release evidence. It changes only
when a reviewed contract, fixture, or runner version changes; it is not a
value to refresh casually.

Scope: this is byte-level reproducibility of the shipped offline commands on
the platforms the matrix runs. It is not fresh-install packaging evidence
(B-045), not the full RG-15 gate, and not a claim about any other platform.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from contextsafe import jsonio
from contextsafe.cli import main
from contextsafe.errors import ContextSafeError
from contextsafe.models import Checkpoint
from contextsafe.reference_fixtures import REFERENCE_ROOT

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REFERENCE_ROOT

RECEIPT_DOCUMENT_SHA256 = (
    "b3fbedaed8158d6c627543d4bf690255ec9b7c2faa7bc7b55222833c89ff2537"
)
"""SHA-256 of the reference ``evaluate`` document, terminal newline included.

Moved on 2026-09-04, when the receipt contract went from 0.1 to 0.2 for the
B-028 predicate reasons: the payload's ``schema_version`` is inside the hashed
payload, so the document digest moved with it while ``input_sha256``,
``result_sha256``, and ``rule_set_sha256`` did not. Moved again the same day
for 0.3 (B-031): every outcome gained a ``trace`` and the payload gained a
``divergence`` section, so ``result_sha256`` moved with the digest;
``input_sha256`` and ``rule_set_sha256`` did not, and the fixtures did not
change.
"""

PREDICATE_RECEIPT_DOCUMENT_SHA256 = (
    "5456e60084b7d01ed4a893b43508c48cbd2380185124a6ee838374742b8994e7"
)
"""SHA-256 of the ``evaluate`` document for the packaged predicate pair.

``rules-predicates.json`` against ``observations-predicates.json``: every
predicate in the 0.2.0 rule-set contract, evaluated once, pinned to the same
standard as the exact-only reference receipt. Moved on 2026-09-04, when the
pair gained A-I09, the ``exact`` rule beside its ``not_coerced`` rule, so
``rule_set_sha256`` and the outcome list changed; the observation set and the
case did not. Moved again the same day for receipt contract 0.3 (B-031), for
the same reason as the reference digest above.
"""

IMPORTED_OBSERVATIONS_SHA256 = (
    "9d7e92c2b771d5aafd00e21bd81debf8c306dde7ed6adff8eafd79b5ae8d9f74"
)
"""SHA-256 of ``import`` over the reference source, terminal newline included.

Pinned for the same reason as the receipt digest: the observation set an
import produces is the input to a receipt, so a platform that changed one
byte of it would change every receipt downstream. It moves only with the
reference source, the case document, or the importer's mapping version.
"""

IMPORTED_FHIR_OBSERVATIONS_SHA256 = (
    "ab739138a46ba7f62216f889950578c5df262660240731bdd8884d38c938b760"
)
"""SHA-256 of ``import --format fhir-r4-json`` over the reference Patient.

Pinned for the same reason as the canonical import digest. It moves only
with the reference Patient fixture, the case document, or the FHIR reader's
profile version.
"""

IMPORTED_HL7V2_OBSERVATIONS_SHA256 = (
    "b6f4e5d1d9e5c928eeba84d6a0171d679cca2ad440695d308e018c6b373831bc"
)
"""SHA-256 of ``import --format hl7v2-er7`` over the reference message.

Pinned for the same reason as the canonical JSON import digest. The ER7
fixture ends every segment with a bare carriage return, so this constant is
also the check that no platform's end-of-line handling touched the source
bytes on the way in. It moves only with the reference message, the case
document, or the importer's mapping version.
"""

LIS_OBSERVATIONS_SHA256: dict[str, str] = {
    "lis-csv": "06e69099d28c12ec6e86a27038c8f22d78d69b80e339240a5192679eb052dd64",
    "lis-json": "19ce395255f2b3343dab40521a33d431c7fff7773718a0b9ada53c6531721072",
}
"""SHA-256 of ``import`` over each reference LIS export, terminal newline included.

Two constants because the two exports are different bytes and every
observation carries its source's digest; everything else in the two
documents is identical, which ``tests/test_lis_import.py`` pins. They move
only with the reference exports, the case document, or the LIS profile
version -- and both moved on 2026-09-04 for the last of those reasons: the
profile is 0.2.0 since it began emitting laboratory result observations, and
the version every identity observation records moved with what the profile
emits, so two behaviours of one profile can never share a run identity.
"""

MAPPED_OBSERVATIONS_SHA256: dict[str, str] = {
    "canonical-json": "4433f908c6075efe1954b6f3830215879d5d4631f5b47e9ba0e2c0fdad1b4327",
    "fhir-r4-json": "fb9511062f9b8e4673fb9b1d64caf3d967a7ad50baa00816db72a5031604022a",
    "hl7v2-er7": "9931fceddc9d9199f5468188f716e8a426b9dd084cb32d996560cc0d54dcba21",
    "lis-csv": "4118a0d9bd552026082b372033c118130943c88fc7d4149c6458265b31067381",
    "lis-json": "2fe48e2102f18acc019a7a6f67b3a0d7b5aa73b9d6643ad4de4bb994ebc8e844",
}
"""SHA-256 of ``import --mapping`` over each reference source with its profile.

One constant per registered format, because every observation carries the
profile's digest and version beside the source's digest, so a platform that
changed one byte of a profile's canonical form would change every bound
observation set. They move only with the reference sources, the case
document, the importers' mapping versions, or the reference profiles.
"""

COMPILED_MAPPING_PROFILE_SHA256 = (
    "779d687047e2f93f314c52b52e15398af9c46be99fad4fa9e805d3e45c7d0228"
)
"""SHA-256 of ``mapping validate`` over the reference FHIR profile.

The compiled document carries the profile's canonical form and the digest
of that form, so this pin also covers the row ordering the canonical form
fixes. It moves only with the reference profile.
"""

_MAPPED_SOURCES: dict[str, tuple[str, str]] = {
    "canonical-json": ("evidence-source.json", "ehr"),
    "fhir-r4-json": ("fhir-patient.json", "ehr"),
    "hl7v2-er7": ("hl7v2-er7-message.hl7", "ehr"),
    "lis-csv": ("lis-export.csv", "lis_return"),
    "lis-json": ("lis-export.json", "lis_return"),
}

_ENVIRONMENTS: tuple[dict[str, str], ...] = (
    {
        "TZ": "UTC",
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONHASHSEED": "0",
        "PYTHONUTF8": "0",
    },
    {
        "TZ": "Pacific/Kiritimati",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "PYTHONHASHSEED": "1",
        "PYTHONUTF8": "1",
    },
    {
        "TZ": "Etc/GMT+12",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "4294967295",
        "PYTHONUTF8": "0",
    },
)
"""Three environments that must not change one byte of any artifact."""

_WINDOWS_UNSUPPORTED = (
    "descriptor-relative no-follow input is a POSIX guarantee; commands that "
    "need it fail closed elsewhere, which "
    "test_platforms_without_descriptor_relative_open_fail_closed pins"
)


@dataclass(frozen=True, slots=True)
class _Run:
    """One complete child-process invocation and everything it emitted."""

    returncode: int
    stdout: bytes
    stderr: bytes
    artifact: bytes | None


def _reference_copies(root: Path) -> tuple[Path, ...]:
    """Return three interchangeable reference directories at different paths."""

    copies = [REFERENCE]
    for name in ("inputs-b", "a-much-longer-input-directory-name-c"):
        destination = root / name
        shutil.copytree(REFERENCE, destination)
        copies.append(destination)
    return tuple(copies)


def _run_cli(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    output: Path | None,
) -> _Run:
    command = [sys.executable, "-m", "contextsafe", *argv]
    if output is not None:
        command = [*command, "--output", str(output)]
    child_environment = dict(os.environ)
    child_environment.update(environment)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=child_environment,
        capture_output=True,
        check=False,
    )
    return _Run(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        artifact=None if output is None else output.read_bytes(),
    )


def _three_runs(
    root: Path,
    build_argv: Callable[[Path], list[str]],
    *,
    with_output: bool = False,
) -> tuple[_Run, ...]:
    """Run one scenario three times across environments, directories, and paths."""

    references = _reference_copies(root)
    working_directories = (ROOT, root, references[-1])
    runs: list[_Run] = []
    for index, environment in enumerate(_ENVIRONMENTS):
        runs.append(
            _run_cli(
                build_argv(references[index]),
                cwd=working_directories[index],
                environment=environment,
                output=root / f"artifact-{index}.json" if with_output else None,
            )
        )
    return tuple(runs)


def _assert_identical(runs: Sequence[_Run]) -> None:
    first = runs[0]
    for other in runs[1:]:
        assert other.returncode == first.returncode
        assert other.stdout == first.stdout
        assert other.stderr == first.stderr
        assert other.artifact == first.artifact


def _fixture_argv(command: str, reference: Path) -> list[str]:
    return [
        command,
        "--case",
        str(reference / "case.json"),
        "--observations",
        str(reference / "observations.json"),
        "--rules",
        str(reference / "rules.json"),
    ]


def _evaluate_argv(reference: Path) -> list[str]:
    return _fixture_argv("evaluate", reference)


def _predicate_evaluate_argv(reference: Path) -> list[str]:
    return [
        "evaluate",
        "--case",
        str(reference / "case.json"),
        "--observations",
        str(reference / "observations-predicates.json"),
        "--rules",
        str(reference / "rules-predicates.json"),
    ]


def _assert_canonical_line(payload: bytes) -> None:
    """A canonical artifact is one UTF-8 JSON line with one terminal newline."""

    assert b"\r" not in payload
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    json.loads(payload.decode("utf-8"))


def _execution_plan_document() -> dict[str, object]:
    """Return the shared synthetic plan as a document a subprocess can read."""

    return {
        "schema_version": "contextsafe.plan/1.0.0",
        "plan_id": "PLAN-SYNTHETIC-TEST",
        "engagement_id": "ENG-SYNTHETIC-TEST",
        "engagement_sha256": "1" * 64,
        "compiled_pack_sha256": "2" * 64,
        "environment": {
            "classification": "staging",
            "name": "SYNTHETIC-STAGING-A",
            "non_production_attested": True,
            "production_access_prohibited": True,
        },
        "target_hosts": ["staging.contextsafe.invalid"],
        "synthetic_namespace": {
            "system": "urn:contextsafe:synthetic",
            "value_prefix": "CSYN-",
        },
        "owners": {
            "technical_owner_id": "TEST-TECHNICAL-OWNER",
            "clinical_owner_id": "TEST-CLINICAL-OWNER",
            "privacy_owner_id": "TEST-PRIVACY-OWNER",
            "cleanup_owner_id": "TEST-CLEANUP-OWNER",
        },
        "cleanup": {
            "owner_id": "TEST-CLEANUP-OWNER",
            "system_ids": ["SYS-STAGING-EHR"],
            "due_on": "2026-08-01",
        },
        "checkpoints": [item.value for item in Checkpoint],
        "case_tokens": ["CSYN-CTP-I01"],
        "valid_from": "2026-07-13",
        "valid_until": "2026-08-01",
    }


def test_validate_is_byte_identical_across_runs_environments_and_paths(
    tmp_path: Path,
) -> None:
    """Invariant 10, process form: nothing outside the inputs reaches stdout."""

    runs = _three_runs(tmp_path, lambda reference: _fixture_argv("validate", reference))
    _assert_identical(runs)
    assert runs[0].returncode == 0
    assert runs[0].stderr == b""
    _assert_canonical_line(runs[0].stdout)


def test_evaluate_artifact_is_byte_identical_and_matches_stdout(
    tmp_path: Path,
) -> None:
    """The receipt a release decision would carry is byte-stable everywhere."""

    runs = _three_runs(tmp_path, _evaluate_argv, with_output=True)
    _assert_identical(runs)
    artifact = runs[0].artifact
    assert artifact is not None
    assert runs[0].returncode == 0
    assert runs[0].stdout == b""
    assert runs[0].stderr == b""
    _assert_canonical_line(artifact)

    printed = _three_runs(tmp_path / "printed", _evaluate_argv)
    _assert_identical(printed)
    assert printed[0].stdout == artifact


def test_evaluate_receipt_digest_is_pinned_on_every_platform(tmp_path: Path) -> None:
    """The cross-platform claim: one constant digest, every matrix platform.

    This fails on a platform that translates the terminal newline, encodes
    with anything other than UTF-8, or lets a clock, locale, hash seed, or
    absolute input path reach the document.
    """

    runs = _three_runs(tmp_path, _evaluate_argv, with_output=True)
    artifact = runs[0].artifact
    assert artifact is not None
    assert hashlib.sha256(artifact).hexdigest() == RECEIPT_DOCUMENT_SHA256


def test_predicate_evaluate_artifact_is_byte_identical_and_pinned(
    tmp_path: Path,
) -> None:
    """The predicate rule set is held to the same three-run, pinned standard."""

    runs = _three_runs(tmp_path, _predicate_evaluate_argv, with_output=True)
    _assert_identical(runs)
    artifact = runs[0].artifact
    assert artifact is not None
    assert runs[0].returncode == 0
    assert runs[0].stderr == b""
    _assert_canonical_line(artifact)
    assert hashlib.sha256(artifact).hexdigest() == PREDICATE_RECEIPT_DOCUMENT_SHA256
    document = json.loads(artifact.decode("utf-8"))
    assert document["payload"]["summary"]["pass"] == 9
    for fragment in (str(tmp_path), "forbidden", "preserved_from", "expected_count"):
        assert fragment.encode("utf-8") not in artifact


def test_no_input_path_or_environment_value_reaches_an_artifact(
    tmp_path: Path,
) -> None:
    """A receipt carries hashes and statuses, never the caller's filesystem."""

    runs = _three_runs(tmp_path, _evaluate_argv, with_output=True)
    artifact = runs[0].artifact
    assert artifact is not None
    for fragment in (str(tmp_path), str(ROOT), "Kiritimati", "en_US", "inputs-b"):
        assert fragment.encode("utf-8") not in artifact


def test_claimed_time_moves_the_envelope_and_never_the_payload_digest(
    tmp_path: Path,
) -> None:
    """Envelope metadata is untrusted decoration; the payload hash ignores it."""

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            *_evaluate_argv(reference),
            "--claimed-generated-at",
            "2026-07-17T01:02:03Z",
        ],
        with_output=True,
    )
    _assert_identical(runs)
    claimed_artifact = runs[0].artifact
    baseline_artifact = _three_runs(
        tmp_path / "baseline", _evaluate_argv, with_output=True
    )[0].artifact
    assert claimed_artifact is not None
    assert baseline_artifact is not None
    claimed = json.loads(claimed_artifact.decode("utf-8"))
    baseline = json.loads(baseline_artifact.decode("utf-8"))
    assert claimed["envelope"]["claimed_generated_at"] == "2026-07-17T01:02:03Z"
    assert baseline["envelope"]["claimed_generated_at"] is None
    assert claimed["payload"] == baseline["payload"]
    assert claimed["payload_sha256"] == baseline["payload_sha256"]


def test_fail_closed_rejection_is_deterministic(tmp_path: Path) -> None:
    """A rejection is an artifact too: same bytes, same code, every run."""

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "pack",
            "validate",
            "--pack",
            str(reference / "pack-draft.json"),
            "--as-of",
            "2026-07-13",
        ],
    )
    _assert_identical(runs)
    assert runs[0].returncode == 2
    assert runs[0].stdout == b""
    _assert_canonical_line(runs[0].stderr)
    assert json.loads(runs[0].stderr.decode("utf-8"))["error"]["code"] == (
        "pack_not_active"
    )


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_evidence_preflight_result_is_deterministic(tmp_path: Path) -> None:
    """The read-only boundary check reports the same bytes on every run."""

    plan_source = tmp_path / "plan.json"
    plan_source.write_bytes(json.dumps(_execution_plan_document()).encode("utf-8"))
    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "evidence",
            "preflight",
            "--source",
            str(reference / "evidence-source.json"),
            "--plan",
            str(plan_source),
            "--case-token",
            "CSYN-CTP-I01",
            "--checkpoint",
            "ehr",
            "--source-type",
            "canonical_json",
            "--media-type",
            "application/vnd.contextsafe.evidence+json",
        ],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    artifact = runs[0].artifact
    assert artifact is not None
    _assert_canonical_line(artifact)
    assert json.loads(artifact.decode("utf-8"))["persisted"] is False


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_import_observation_set_is_deterministic_and_pinned(tmp_path: Path) -> None:
    """The conversion step is byte-stable, and its digest is one constant.

    The source digest on every observation is the digest of the reference
    bytes, which are identical in every copied input directory, so the
    artifact cannot depend on where the source was read from.
    """

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            "canonical-json",
            "--source",
            str(reference / "evidence-source.json"),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            "ehr",
        ],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    assert runs[0].stdout == b""
    assert runs[0].stderr == b""
    artifact = runs[0].artifact
    assert artifact is not None
    _assert_canonical_line(artifact)
    assert hashlib.sha256(artifact).hexdigest() == IMPORTED_OBSERVATIONS_SHA256
    for fragment in (str(tmp_path), str(ROOT), "Kiritimati", "en_US", "inputs-b"):
        assert fragment.encode("utf-8") not in artifact


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_hl7v2_import_observation_set_is_deterministic_and_pinned(
    tmp_path: Path,
) -> None:
    """The ER7 conversion is byte-stable, and its digest is one constant."""

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            "hl7v2-er7",
            "--source",
            str(reference / "hl7v2-er7-message.hl7"),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            "ehr",
        ],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    assert runs[0].stdout == b""
    assert runs[0].stderr == b""
    artifact = runs[0].artifact
    assert artifact is not None
    _assert_canonical_line(artifact)
    assert hashlib.sha256(artifact).hexdigest() == IMPORTED_HL7V2_OBSERVATIONS_SHA256
    for fragment in (
        str(tmp_path),
        str(ROOT),
        "Kiritimati",
        "en_US",
        "inputs-b",
        "ZZZTESTCONTEXTSAFE",
        "CSYN-LEGAL-I01",
    ):
        assert fragment.encode("utf-8") not in artifact


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_hl7v2_import_rejection_is_deterministic(tmp_path: Path) -> None:
    """A rejected ER7 import is the same one-line error object on every run."""

    rejection = tmp_path / "z-segment.hl7"
    rejection.write_bytes(
        (ROOT / "tests" / "fixtures" / "hl7v2" / "z-segment.hl7").read_bytes()
    )
    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            "hl7v2-er7",
            "--source",
            str(rejection),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            "ehr",
        ],
    )
    _assert_identical(runs)
    assert runs[0].returncode == 2
    assert runs[0].stdout == b""
    _assert_canonical_line(runs[0].stderr)
    assert json.loads(runs[0].stderr.decode("utf-8"))["error"] == {
        "code": "import_segment_not_allowed",
        "message": "segment is outside the profile's closed allowlist",
        "path": "$[7]",
    }


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_import_rejection_is_deterministic(tmp_path: Path) -> None:
    """A rejected import is the same one-line error object on every run."""

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            "canonical-json",
            "--source",
            str(reference / "evidence-source.json"),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            "interface",
        ],
    )
    _assert_identical(runs)
    assert runs[0].returncode == 2
    assert runs[0].stdout == b""
    _assert_canonical_line(runs[0].stderr)
    assert json.loads(runs[0].stderr.decode("utf-8"))["error"]["code"] == (
        "import_checkpoint_mismatch"
    )


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_fhir_import_observation_set_is_deterministic_and_pinned(
    tmp_path: Path,
) -> None:
    """The FHIR reader is byte-stable, and its digest is one constant.

    Every pointer is an RFC 6901 path into the document and every digest is
    the digest of the reference bytes, so the artifact cannot depend on the
    directory the source was read from or on anything in the environment.
    """

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            "fhir-r4-json",
            "--source",
            str(reference / "fhir-patient.json"),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            "ehr",
        ],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    assert runs[0].stdout == b""
    assert runs[0].stderr == b""
    artifact = runs[0].artifact
    assert artifact is not None
    _assert_canonical_line(artifact)
    assert hashlib.sha256(artifact).hexdigest() == IMPORTED_FHIR_OBSERVATIONS_SHA256
    for fragment in (str(tmp_path), str(ROOT), "Kiritimati", "en_US", "inputs-b"):
        assert fragment.encode("utf-8") not in artifact


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_fhir_import_rejection_is_deterministic(tmp_path: Path) -> None:
    """A rejected FHIR document is the same one-line error object on every run."""

    rejected = (
        ROOT / "tests" / "fixtures" / "fhir-r4-json" / "reject-spcu-extension.json"
    )
    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            "fhir-r4-json",
            "--source",
            str(rejected),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            "ehr",
        ],
    )
    _assert_identical(runs)
    assert runs[0].returncode == 2
    assert runs[0].stdout == b""
    _assert_canonical_line(runs[0].stderr)
    assert json.loads(runs[0].stderr.decode("utf-8"))["error"]["code"] == (
        "import_concept_not_convertible"
    )


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
@pytest.mark.parametrize(
    ("format_name", "source"),
    [
        ("lis-csv", "lis-export.csv"),
        ("lis-json", "lis-export.json"),
    ],
)
def test_lis_import_observation_set_is_deterministic_and_pinned(
    tmp_path: Path, format_name: str, source: str
) -> None:
    """Both LIS readers are byte-stable, and each digest is one constant.

    The CSV reader is a grammar of its own rather than the JSON parser, so
    it gets its own pin: a locale-dependent decode, a platform line-ending
    translation, or an ordering that depended on hash seed would show here.
    """

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            format_name,
            "--source",
            str(reference / source),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            "lis_return",
        ],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    assert runs[0].stdout == b""
    assert runs[0].stderr == b""
    artifact = runs[0].artifact
    assert artifact is not None
    _assert_canonical_line(artifact)
    assert hashlib.sha256(artifact).hexdigest() == LIS_OBSERVATIONS_SHA256[format_name]
    for fragment in (str(tmp_path), str(ROOT), "Kiritimati", "en_US", "inputs-b"):
        assert fragment.encode("utf-8") not in artifact


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_lis_import_rejection_is_deterministic(tmp_path: Path) -> None:
    """A rejected LIS import is the same one-line error object on every run."""

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            "lis-csv",
            "--source",
            str(reference / "lis-export.csv"),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            "ehr",
        ],
    )
    _assert_identical(runs)
    assert runs[0].returncode == 2
    assert runs[0].stdout == b""
    _assert_canonical_line(runs[0].stderr)
    assert json.loads(runs[0].stderr.decode("utf-8"))["error"]["code"] == (
        "import_checkpoint_mismatch"
    )


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
@pytest.mark.parametrize("format_name", sorted(_MAPPED_SOURCES))
def test_import_with_mapping_profile_is_deterministic_and_pinned(
    tmp_path: Path, format_name: str
) -> None:
    """A bound observation set is byte-stable, and each digest is one constant.

    The profile is read from the same copied input directory as the source,
    so the artifact cannot depend on where either was read from; the
    profile's digest on every observation is the digest of its canonical
    form, not of its bytes or its path.
    """

    source, checkpoint = _MAPPED_SOURCES[format_name]
    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "import",
            "--format",
            format_name,
            "--source",
            str(reference / source),
            "--case",
            str(reference / "case.json"),
            "--checkpoint",
            checkpoint,
            "--mapping",
            str(reference / f"mapping-{format_name}.json"),
        ],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    assert runs[0].stdout == b""
    assert runs[0].stderr == b""
    artifact = runs[0].artifact
    assert artifact is not None
    _assert_canonical_line(artifact)
    assert (
        hashlib.sha256(artifact).hexdigest() == MAPPED_OBSERVATIONS_SHA256[format_name]
    )
    for fragment in (str(tmp_path), str(ROOT), "Kiritimati", "en_US", "inputs-b"):
        assert fragment.encode("utf-8") not in artifact


def test_mapping_validate_is_deterministic_and_pinned(tmp_path: Path) -> None:
    """The compiled profile is byte-stable, and its digest is one constant."""

    runs = _three_runs(
        tmp_path,
        lambda reference: [
            "mapping",
            "validate",
            "--profile",
            str(reference / "mapping-fhir-r4-json.json"),
        ],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    assert runs[0].stdout == b""
    assert runs[0].stderr == b""
    artifact = runs[0].artifact
    assert artifact is not None
    _assert_canonical_line(artifact)
    assert hashlib.sha256(artifact).hexdigest() == COMPILED_MAPPING_PROFILE_SHA256
    for fragment in (str(tmp_path), str(ROOT), "Kiritimati", "en_US", "inputs-b"):
        assert fragment.encode("utf-8") not in artifact


def test_mapping_validate_rejection_is_deterministic(tmp_path: Path) -> None:
    """A refused profile is the same one-line error object on every run."""

    rejected = ROOT / "tests" / "fixtures" / "mapping" / "reject-gi-to-spcu.json"
    runs = _three_runs(
        tmp_path,
        lambda _reference: ["mapping", "validate", "--profile", str(rejected)],
    )
    _assert_identical(runs)
    assert runs[0].returncode == 2
    assert runs[0].stdout == b""
    _assert_canonical_line(runs[0].stderr)
    assert json.loads(runs[0].stderr.decode("utf-8"))["error"] == {
        "code": "prohibited_spcu_mapping",
        "message": "GI and RSG can never be mapped into SPCU",
        "path": "$.rows[0].target",
    }


def test_render_page_is_byte_identical_across_runs_environments_and_paths(
    tmp_path: Path,
) -> None:
    """The rendered page joins the matrix: same receipt, same locale, same bytes.

    ``tests/test_html_receipt.py`` already spreads the render across three
    environments; this row adds the working-directory and input-path spread
    the other commands get, so a path or locale leak into the page fails
    here with the rest.
    """

    receipt = tmp_path / "receipt.json"
    assert main([*_evaluate_argv(REFERENCE), "--quiet", "--output", str(receipt)]) == 0
    runs = _three_runs(
        tmp_path,
        lambda reference: ["render", "--receipt", str(receipt), "--lang", "es-US"],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    artifact = runs[0].artifact
    assert artifact is not None
    assert artifact.startswith(b"<!DOCTYPE html>")
    assert b'lang="es-US"' in artifact
    assert str(tmp_path).encode("utf-8") not in artifact


RECEIPT_DELTA_SHA256 = (
    "a0ec5e5e67da7272129ae8f26149bc7bf58835c2d5ae67a2a573cd12ad2a7380"
)
"""SHA-256 of ``receipt diff`` over the reference receipt against itself.

Pinned for the same reason as ``RECEIPT_DOCUMENT_SHA256`` and changing under
the same conditions: it moves when the receipt payload, the delta contract, or
the runner version moves, and at no other time.
"""


def _receipt_diff_scenario(tmp_path: Path) -> tuple[Path, Path]:
    """Write the two receipts the diff scenarios read, in process."""

    before = tmp_path / "before-receipt.json"
    assert main([*_evaluate_argv(REFERENCE), "--output", str(before)]) == 0
    observations = json.loads(
        (REFERENCE / "observations.json").read_text(encoding="utf-8")
    )
    observations["observations"][4]["value"]["value"] = "ze/hir"
    contradicted = tmp_path / "contradicted-observations.json"
    contradicted.write_text(json.dumps(observations), encoding="utf-8")
    after = tmp_path / "after-receipt.json"
    argv = _evaluate_argv(REFERENCE)
    argv[4] = str(contradicted)
    assert main([*argv, "--output", str(after)]) == 0
    return before, after


def test_receipt_diff_artifact_is_byte_identical_and_matches_stdout(
    tmp_path: Path,
) -> None:
    """The delta is an artifact too: same bytes in every environment."""

    before, after = _receipt_diff_scenario(tmp_path)
    argv = ["receipt", "diff", "--before", str(before), "--after", str(after)]
    runs = _three_runs(tmp_path, lambda _reference: argv, with_output=True)
    _assert_identical(runs)
    artifact = runs[0].artifact
    assert artifact is not None
    assert runs[0].returncode == 0
    assert runs[0].stdout == b""
    assert runs[0].stderr == b""
    _assert_canonical_line(artifact)
    delta = json.loads(artifact.decode("utf-8"))
    assert delta["summary"]["regressed"] == 1
    for fragment in (str(tmp_path), str(ROOT), "Kiritimati", "en_US", "ze/hir"):
        assert fragment.encode("utf-8") not in artifact

    printed = _three_runs(tmp_path / "printed", lambda _reference: argv)
    _assert_identical(printed)
    assert printed[0].stdout == artifact


def test_receipt_diff_digest_is_pinned_on_every_platform(tmp_path: Path) -> None:
    """One constant digest for the self-delta of the reference receipt."""

    before, _ = _receipt_diff_scenario(tmp_path)
    argv = ["receipt", "diff", "--before", str(before), "--after", str(before)]
    runs = _three_runs(tmp_path, lambda _reference: argv, with_output=True)
    _assert_identical(runs)
    artifact = runs[0].artifact
    assert artifact is not None
    assert hashlib.sha256(artifact).hexdigest() == RECEIPT_DELTA_SHA256


def test_incompatible_receipts_rejection_is_deterministic(tmp_path: Path) -> None:
    """A compatibility rejection names a field class, identically, every run."""

    before, after = _receipt_diff_scenario(tmp_path)
    document = json.loads(after.read_text(encoding="utf-8"))
    document["payload"]["case_id"] = "CTP-I02"
    document["payload_sha256"] = hashlib.sha256(
        json.dumps(document["payload"], sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    after.write_text(json.dumps(document), encoding="utf-8")
    argv = ["receipt", "diff", "--before", str(before), "--after", str(after)]
    runs = _three_runs(tmp_path, lambda _reference: argv)
    _assert_identical(runs)
    assert runs[0].returncode == 2
    assert runs[0].stdout == b""
    _assert_canonical_line(runs[0].stderr)
    error = json.loads(runs[0].stderr.decode("utf-8"))["error"]
    assert error["code"] == "incompatible_receipts"
    assert b"CTP-I0" not in runs[0].stderr


def _finding_inputs(root: Path) -> tuple[Path, Path]:
    """A receipt with one fail outcome and a confirmed event bound to it."""

    observations = json.loads(
        (REFERENCE / "observations.json").read_text(encoding="utf-8")
    )
    observations["observations"][4]["value"]["value"] = "ze/hir"
    observations_path = root / "mismatched-observations.json"
    observations_path.write_text(json.dumps(observations), encoding="utf-8")
    receipt_path = root / "receipt.json"
    argv = _evaluate_argv(REFERENCE)
    argv[4] = str(observations_path)
    assert main([*argv, "--output", str(receipt_path)]) == 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    event_path = root / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "schema_version": "contextsafe.review-event/1.0.0",
                "outcome": {
                    "rule_id": "A-I05",
                    "case_id": "CTP-I01",
                    "checkpoint": "ehr",
                    "concept": "pronouns",
                },
                "receipt": {
                    "payload_sha256": receipt["payload_sha256"],
                    "rule_set_sha256": receipt["payload"]["hashes"]["rule_set_sha256"],
                },
                "decision": "confirmed",
                "severity": "cs2_high",
                "owner": None,
                "rationale_code": "evidence_verified_against_source",
                "external_reference": "ticket.synthetic-a",
                "signers": [
                    {
                        "role": "contextsafe_clinical_safety_chair",
                        "organization_id": "ORG-CONTEXTSAFE-TEST",
                        "signature_status": "not_verified",
                    }
                ],
                "signature_status": "not_verified",
            }
        ),
        encoding="utf-8",
    )
    return receipt_path, event_path


@pytest.mark.skipif(os.name == "nt", reason=_WINDOWS_UNSUPPORTED)
def test_finding_review_and_list_are_byte_identical_across_runs(
    tmp_path: Path,
) -> None:
    """A review log and the state derived from it carry no clock and no path.

    Each run appends to its own fresh log, so the three logs must be
    byte-identical too: the file a later item would bind into a receipt is
    reproducible from the events alone.
    """

    receipt_path, event_path = _finding_inputs(tmp_path)
    logs = [tmp_path / f"review-{index}.jsonl" for index in range(3)]
    handed_out = iter(logs)
    runs = _three_runs(
        tmp_path,
        lambda _reference: [
            "finding",
            "review",
            "--receipt",
            str(receipt_path),
            "--event",
            str(event_path),
            "--log",
            str(next(handed_out)),
        ],
        with_output=True,
    )
    _assert_identical(runs)
    assert runs[0].returncode == 0
    assert runs[0].stderr == b""
    artifact = runs[0].artifact
    assert artifact is not None
    _assert_canonical_line(artifact)
    assert logs[0].read_bytes() == logs[1].read_bytes() == logs[2].read_bytes()
    _assert_canonical_line(logs[0].read_bytes())
    for fragment in (str(tmp_path), "Kiritimati", "en_US"):
        assert fragment.encode("utf-8") not in artifact
        assert fragment.encode("utf-8") not in logs[0].read_bytes()

    listed = _three_runs(
        tmp_path / "listed",
        lambda _reference: ["finding", "list", "--log", str(logs[0])],
    )
    _assert_identical(listed)
    assert listed[0].returncode == 0
    assert listed[0].stdout == artifact


def test_platforms_without_descriptor_relative_open_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without descriptor-relative no-follow open, component reads reject.

    ``docs/10-OPERATIONS-SRE.md`` names Windows 11 as a planned supported
    platform, and Windows offers neither ``O_NOFOLLOW`` nor ``dir_fd``. The
    commands that read pack components beneath a root therefore fail closed
    rather than silently weaken the guarantee. Pinning that here states the
    limitation on every platform instead of leaving it to a Windows-only CI
    observation.
    """

    monkeypatch.setattr(jsonio, "_DESCRIPTOR_RELATIVE_SUPPORTED", False)
    with pytest.raises(ContextSafeError) as raised:
        jsonio.load_json_beneath(REFERENCE, "case.json")
    assert raised.value.code == "input_path_unsupported"


def test_text_only_stream_still_receives_the_identical_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An in-process caller that substitutes a text stream loses no output."""

    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    assert main(_fixture_argv("validate", REFERENCE)) == 0
    assert json.loads(stream.getvalue())["valid"] is True


# --- the laboratory result family (B-030) ------------------------------------

LABORATORY_OUTCOMES_SHA256 = (
    "b923bec92cd2c69c0b7019d04c1d8d250786230467ae571a885f60f3a8466fd9"
)
"""SHA-256 of the canonical outcome report over the INV laboratory fixture.

The laboratory predicates reach no command, so this is evaluated in a child
process rather than through the CLI: the same script, three environments,
three working directories, and one digest. It moves only with the fixture,
the predicates, or the outcome shape.
"""

_LABORATORY_SCRIPT = """
import json, sys
from contextsafe.canonical import canonical_json
from contextsafe.laboratory import (
    evaluate_results,
    outcome_report,
    parse_result_bundle,
)

document = json.loads(open(sys.argv[1], encoding="utf-8").read())
bundle = parse_result_bundle(
    document["case"], document["results"], document["rules"]
)
sys.stdout.buffer.write(
    canonical_json(outcome_report(evaluate_results(bundle))).encode("utf-8")
)
"""


def test_laboratory_evaluation_is_deterministic_and_pinned(tmp_path: Path) -> None:
    """One bundle, three environments, three directories, one digest."""

    fixture = ROOT / "tests" / "fixtures" / "laboratory" / "inv.json"
    outputs: list[bytes] = []
    for index, environment in enumerate(_ENVIRONMENTS):
        child_environment = dict(os.environ)
        child_environment.update(environment)
        completed = subprocess.run(
            [sys.executable, "-c", _LABORATORY_SCRIPT, str(fixture)],
            cwd=(ROOT, tmp_path, ROOT / "tests")[index],
            env=child_environment,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        outputs.append(completed.stdout)
    assert len(set(outputs)) == 1
    assert hashlib.sha256(outputs[0]).hexdigest() == LABORATORY_OUTCOMES_SHA256
    assert json.loads(outputs[0])["summary"]["pass"] == 22
