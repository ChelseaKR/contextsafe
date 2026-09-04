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
    "f34e58fa642ec0ac5a2368834324d55f1aacbf5f0b51c1ac0cff5c72ea3dce80"
)
"""SHA-256 of the reference ``evaluate`` document, terminal newline included."""

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
    "lis-csv": "f05fccb363fc34fe65aa0b05b414206208b46e1ad025e6b690caab83704756c3",
    "lis-json": "d76e4d08e02538ca6d8499de5c55893dca6d42b52feadd3027dd115e5138e395",
}
"""SHA-256 of ``import`` over each reference LIS export, terminal newline included.

Two constants because the two exports are different bytes and every
observation carries its source's digest; everything else in the two
documents is identical, which ``tests/test_lis_import.py`` pins. They move
only with the reference exports, the case document, or the LIS profile
version.
"""

MAPPED_OBSERVATIONS_SHA256: dict[str, str] = {
    "canonical-json": "4433f908c6075efe1954b6f3830215879d5d4631f5b47e9ba0e2c0fdad1b4327",
    "fhir-r4-json": "fb9511062f9b8e4673fb9b1d64caf3d967a7ad50baa00816db72a5031604022a",
    "hl7v2-er7": "9931fceddc9d9199f5468188f716e8a426b9dd084cb32d996560cc0d54dcba21",
    "lis-csv": "806bce429f12329bef50f79830d4d4c94b09b1247e034b96aea1258c8129e39e",
    "lis-json": "e60f8b50f05839d9b7ffc3853e90444c1393b0252bdb62872096ecee86733b17",
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
