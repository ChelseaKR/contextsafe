"""What the workflows claim, re-derived from the workflows.

Three properties of `.github/workflows/` are load-bearing and none of them was
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
