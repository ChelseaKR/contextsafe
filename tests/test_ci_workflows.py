"""What the workflows claim, re-derived from the workflows.

Four properties of `.github/workflows/` are load-bearing and none of them was
asserted anywhere, so each drifted or could have:

* **`ci.yml` runs on every pull request.** It carried `paths-ignore` for
  `**.md`, `docs/**` and `LICENSE`, and four stages of `make verify` are
  documentation gates. A README-only change could therefore break `make claims`
  and merge green, leaving the next code pull request to inherit the failure
  (#102). The skip also made `verify` unusable as a required status check (#75).
* **The mutation gate runs somewhere automatically.** `make mutants` is
  deliberately outside `make verify` for runtime, and until 2026-09-04 it was
  outside CI as well, which meant the evidence that the suite would *notice* a
  change existed only when somebody produced it by hand (#80).
* **Every action is pinned to a full SHA, and to the same SHA everywhere.** Two
  files pinning `actions/checkout` to two different commits is the drift shape
  that let two pins sit behind upstream for three weeks (#91).
* **A document that explains why a workflow has never fired names every
  trigger it has, and prices what running it would assert.** `package.yml`
  fires on a tag *and* on `workflow_dispatch`, and its `provenance` job has no
  ref guard, so a dispatch attests a wheel carrying `pyproject.toml`'s
  version. Documents said it had never fired "for the same reason
  `release.yml` has not", and recommended dispatching it as an act costing no
  version claim -- two sentences that cannot both be checked by reading prose
  (#100).

What this file cannot see, stated rather than implied: whether a pinned SHA is
the current upstream release. That is a fact about GitHub, not about this tree,
and answering it needs the network call `gh api repos/OWNER/REPO/git/ref/tags/vX.Y.Z`
makes. The README's Security and Supply-Chain row carries the standing
disclosure when a pin is knowingly behind.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

USES = re.compile(
    r"^\s*(?:-\s+)?uses:\s*(?P<action>[^\s@]+)@(?P<ref>\S+)(?:\s+#\s*(?P<comment>.+))?$",
    re.MULTILINE,
)

ANY_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<target>\S+)", re.MULTILINE)
"""Every `uses:` line, whatever shape it is in.

`USES` only matches the `owner/repo@ref` form, and everything below reads
`USES`. A step written some other way -- `uses: docker://image:tag`, a bare
`uses: owner/repo` with no ref -- would therefore sit outside "every action is
pinned to a full SHA" without a single assertion noticing. `ANY_USES` is what
makes the pin checks exhaustive rather than merely true of what they matched.
"""


def _workflows() -> list[Path]:
    found = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert found, "no workflow was read, so nothing below examined anything"
    return found


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _uncommented(text: str) -> str:
    """The workflow with its comment lines dropped.

    Every check here is about what the workflow *does*. A comment explaining why
    a `paths-ignore` was removed would otherwise read as the `paths-ignore`
    still being there.
    """

    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


# --- #102: the gates that read documentation must see documentation ---------


def test_ci_runs_on_every_pull_request() -> None:
    """No `paths-ignore`, in any trigger, in the workflow that runs `make verify`."""

    assert "paths-ignore" not in _uncommented(_text("ci.yml"))


def test_ci_still_runs_the_same_gate_a_contributor_runs() -> None:
    body = _uncommented(_text("ci.yml"))
    assert "make verify" in body
    assert "pull_request:" in body


def test_no_workflow_skips_documentation() -> None:
    """The rule generalized: a `paths-ignore` for Markdown is how #102 happened."""

    for path in _workflows():
        body = _uncommented(path.read_text(encoding="utf-8"))
        assert "paths-ignore" not in body, path.name


# --- #80: mutation evidence runs without anybody remembering ----------------


def test_the_mutation_gate_has_a_workflow() -> None:
    running = [p.name for p in _workflows() if "make mutants" in p.read_text("utf-8")]
    assert running, "`make mutants` runs in no workflow, so it runs only by hand"


def test_the_mutation_workflow_runs_without_being_asked() -> None:
    """A schedule or a path trigger. Dispatch-only is evidence nobody produces."""

    body = _uncommented(_text("mutation.yml"))
    assert "schedule:" in body
    assert "cron:" in body
    assert "pull_request:" in body


def test_the_mutation_gate_stays_out_of_verify() -> None:
    """Deliberate and documented: every mutant is a separate test run."""

    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    stages = re.search(r"^verify:[ \t]*(.*)$", makefile, re.MULTILINE)
    assert stages is not None
    assert "mutants" not in stages.group(1).split()


ASSURANCE = REPO_ROOT / "docs" / "18-ASSURANCE-PROGRAM.md"

RAN_SINCE = re.compile(
    r"mutation\.yml[^.|\n]{0,80}\b(?:since|has been running|running since)\b"
    r"|\b(?:running automatically|run by)\b[^.|\n]{0,80}mutation\.yml[^.|\n]{0,40}since",
)


def test_the_assurance_ledger_claims_configuration_not_execution() -> None:
    """A workflow nobody has watched run is wired up, not running.

    `docs/18-ASSURANCE-PROGRAM.md` is the one file whose whole purpose is
    separating claimed assurance from demonstrated assurance, and it read
    "running automatically since 2026-09-04" over a workflow that had never
    executed -- two lines below a row of its own table that sets the opposite
    standard, "proved locally rather than by a CI job nobody has watched run".
    ADR 0009 says the same thing in its own words: its first real run is the
    evidence, not its existence. Nothing in a checkout can see a workflow run,
    so nothing in a checkout may date one.
    """

    body = ASSURANCE.read_text(encoding="utf-8")
    assert "mutation.yml" in body, "the ledger stopped naming the workflow"
    assert "first run has not been observed" in body
    assert "first run not yet observed" in body
    found = RAN_SINCE.search(body)
    assert found is None, f"the ledger dates a run it cannot see: {found}"


def test_the_sast_scan_is_judged_by_the_gate_and_not_by_its_exit_code() -> None:
    """#114: a partial parse left the SAST job green over a safety module.

    The scanner reports a file its parser could not finish as a warning and
    still exits 0, so `--error --strict` decided the job by whichever code the
    run happened to produce. `tools/sast_gate.py` reads the scan's JSON instead.
    A workflow that went back to reading the exit code would restore the hole,
    so the check is both directions: the gate runs, and the flags that used to
    stand in for it are gone. See ADR 0012.
    """

    body = _uncommented(_text("security.yml"))
    assert "tools/sast_gate.py" in body, "the SAST job no longer runs the gate"
    assert "--error" not in body
    assert "--strict" not in body


def test_no_workflow_softens_a_gate_it_runs() -> None:
    """A run that could not happen is not a pass, and neither is one ignored."""

    for path in _workflows():
        body = _uncommented(path.read_text(encoding="utf-8"))
        assert "continue-on-error" not in body, path.name
        assert "|| true" not in body, path.name


# --- #91: pins that can be read, and that agree with each other -------------


def _pins() -> dict[str, set[str]]:
    pins: dict[str, set[str]] = {}
    for path in _workflows():
        for match in USES.finditer(path.read_text(encoding="utf-8")):
            action = match.group("action")
            if action.startswith("./"):
                continue  # a local composite action, versioned by this repository
            pins.setdefault(action, set()).add(match.group("ref"))
    assert pins, "no `uses:` was found, so the checks below examined nothing"
    return pins


def test_every_step_that_uses_something_is_one_the_pin_checks_can_read() -> None:
    """No `uses:` line escapes the checks below by not looking like an action.

    `_pins` reads `USES`, which matches `owner/repo@ref` and nothing else. A
    `uses: docker://image:tag` step, or one naming an action with no ref at
    all, would be skipped in silence, and "every action is pinned to a full
    SHA" would be a true statement about a set that did not contain it.
    """

    for path in _workflows():
        text = path.read_text(encoding="utf-8")
        pinned = {match.start("action") for match in USES.finditer(text)}
        for match in ANY_USES.finditer(text):
            target = match.group("target")
            readable = target.startswith("./") or match.start("target") in pinned
            assert readable, f"{path.name}: {match.group(0).strip()}"


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    """A tag is a moving target; a short SHA is a collidable one."""

    for action, refs in _pins().items():
        for ref in refs:
            assert re.fullmatch(r"(?:sha256:)?[0-9a-f]{40,71}", ref), f"{action}@{ref}"


def test_every_pin_carries_the_version_it_is() -> None:
    """The SHA is what runs; the comment is the only thing a reader can check."""

    for path in _workflows():
        for match in USES.finditer(path.read_text(encoding="utf-8")):
            if match.group("action").startswith("./"):
                continue
            comment = match.group("comment")
            assert comment is not None, f"{path.name}: {match.group(0).strip()}"
            assert comment.strip(), f"{path.name}: {match.group(0).strip()}"


def test_one_action_is_pinned_to_one_sha_everywhere() -> None:
    """Two files at two commits is a bump that half happened."""

    disagreeing = {a: sorted(refs) for a, refs in _pins().items() if len(refs) > 1}
    assert disagreeing == {}


# --- #100: a workflow's triggers, and the prose that explains its silence ----


def _on_block(name: str) -> str:
    """The `on:` mapping of one workflow, comments dropped.

    Read by indentation rather than with a YAML parser, because this
    repository has no runtime or test dependency on one and a trigger list is
    two levels deep.
    """

    lines = _uncommented(_text(name)).splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == "on:")
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith((" ", "\t")):
            break
        block.append(line)
    assert block, f"{name}: the `on:` block read as empty"
    return "\n".join(block)


def _triggers(name: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"^  ([a-z_]+):", _on_block(name), re.MULTILINE)
    }


def test_package_yml_has_a_trigger_that_needs_nobodys_tag() -> None:
    """The premise every sentence below has to account for.

    `release.yml` has one trigger and it has not occurred. `package.yml` has
    two, and one of them is a button. "It has never fired" is therefore true
    of both files for different reasons, and a document that gives them the
    same reason is wrong about the second.
    """

    assert _triggers("release.yml") == {"push"}
    assert _triggers("package.yml") == {"push", "workflow_dispatch"}


NEVER_FIRED = re.compile(r"\b(?:never fired|has never (?:fired|run|executed))\b")

EXPLAINS_SILENCE = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "docs" / "OPEN-DECISIONS.md",
)


def _blocks(text: str) -> list[str]:
    """Paragraphs, with a Markdown table row counting as one.

    A standards-table row is a single line carrying a whole argument, so
    splitting on blank lines alone would let a row make a claim and then be
    judged against the rest of the table.
    """

    blocks: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        blocks.extend(paragraph.splitlines() if "|" in paragraph else [paragraph])
    return blocks


def test_no_document_explains_package_yml_silence_by_the_missing_tag() -> None:
    """Saying why `package.yml` has not fired means naming both its triggers.

    The Release and Versioning row said it "triggers on the same tag shape",
    and the changelog said it "has never fired for the same reason
    `release.yml` has not". Both omit `workflow_dispatch` -- the trigger the
    recommendation in `docs/OPEN-DECISIONS.md` then proposes using, so one
    change both hid the trigger and relied on it.
    """

    if "workflow_dispatch" not in _triggers("package.yml"):
        return  # the shorter claim would be accurate; nothing to require
    examined = 0
    for path in EXPLAINS_SILENCE:
        for block in _blocks(path.read_text(encoding="utf-8")):
            if "package.yml" not in block or not NEVER_FIRED.search(block):
                continue
            examined += 1
            assert "workflow_dispatch" in block, f"{path.name}: {block[:200]}"
    assert examined, "no document explained the silence, so nothing was examined"


PROVENANCE_GUARD = re.compile(r"^\s+if:.*github\.ref", re.MULTILINE)

PROJECT_VERSION = re.compile(r'^version = "([^"]+)"', re.MULTILINE)


def _job(text: str, name: str) -> str:
    lines = _uncommented(text).splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"  {name}:")
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("    "):
            break
        block.append(line)
    assert block, f"the {name} job read as empty"
    return "\n".join(block)


def test_the_memo_prices_the_dispatch_it_recommends() -> None:
    """A dispatch that mints a signed attestation is not a free experiment.

    `package.yml`'s `provenance` job needs `build` and `fresh-install` and
    nothing else, so on `workflow_dispatch` it reaches
    `actions/attest-build-provenance` with `attestations: write` and stores a
    signed statement over the wheel `make package` built -- which carries
    `pyproject.toml`'s version. Either the job is guarded by the ref, or the
    document recommending the dispatch says what the dispatch would assert.
    """

    provenance = _job(_text("package.yml"), "provenance")
    if "attest-build-provenance" not in provenance:
        return  # nothing is minted, so there is nothing to price
    if PROVENANCE_GUARD.search(provenance):
        return  # a dispatch cannot reach the attestation
    recommendation = _recommendation(
        (REPO_ROOT / "docs" / "OPEN-DECISIONS.md").read_text(encoding="utf-8")
    )
    proposing = [
        block
        for block in _blocks(recommendation)
        if "workflow_dispatch" in block and "package.yml" in block
    ]
    if not proposing:
        return  # the memo no longer proposes a dispatch, so it owes no price
    version = PROJECT_VERSION.search(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert version is not None
    for block in proposing:
        assert "attest" in block, (
            f"a dispatch proposed without its attestation: {block}"
        )
        assert version.group(1) in block, (
            f"the version the attested wheel would carry is unnamed: {block}"
        )


def _recommendation(memo: str) -> str:
    """Section 1's recommendation, and only that.

    A cost stated in the section that describes the workflows is not the same
    as a cost stated beside the thing being recommended: a reader acting on
    the recommendation reads the recommendation.
    """

    section = memo.split("\n## 1. ", 1)
    assert len(section) == 2, "the memo no longer carries a section 1"
    body = section[1].split("\n## ", 1)[0]
    parts = body.split("\n### Recommendation\n", 1)
    assert len(parts) == 2, "section 1 no longer carries a recommendation"
    return parts[1]
