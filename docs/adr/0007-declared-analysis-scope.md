# ADR 0007 — Each analysis declares the trees it examines, and the declaration is checked

Status: accepted
Date: 2026-08-27
Decision owners: technical owner

## Context

After [ADR 0005](0005-hygiene-marker-exemptions.md), every gate in `make verify`
can tell "I looked and found nothing" apart from "I could not look". None of
them can tell either of those apart from a third state: **nobody ever pointed me
at that tree.**

That is not hypothetical. `tools/` holds five gate implementations that between
them decide whether anything merges, and until 2026-08-27 it was outside the
marker scan and outside the branch-coverage floor. Both gates reported clean,
correctly, over the trees they had been given. Nothing in the repository was in
a position to say a third tree of Python existed and neither gate had heard of
it. ADR 0005 closed those two holes by hand. Nothing stops the next one.

Measuring the same question against the other analyses found a third hole that
was still open. `make typecheck` was `uv run mypy --strict src`, so the five gate
programs were never type-checked. Running it over them reported seven errors,
six of which were `# type: ignore[arg-type]` comments on calls to `parse_bundle`,
whose three parameters are declared `object`. Those suppressions suppressed
nothing: a claim about a problem that was not there, sitting in the same
`tools/` tree as the gates this program exists to make honest.

## Decision

Add `tools/scope_gate.py`, wired into `make verify` as `make scope`. It scans no
files. It compares the trees each analysis *claims* against the tracked Python
that exists.

**A claim is read from the configuration that makes it, never from a copy.**

| Analysis | Claim read from |
| --- | --- |
| `marker-scan` | `tools/hygiene_gate.py` `MARKER_ROOTS`, by import: the tuple the scan iterates |
| `strict-typing` | `pyproject.toml` `[tool.mypy] files` |
| `branch-coverage` | `pyproject.toml` `[tool.coverage.run] source` |

For that to mean anything, the commands must not be able to override it, so
`make typecheck` now passes no path and `make test` passes a bare `--cov`. The
scope of each is `pyproject.toml` and nowhere else. The gate reads the two
Makefile recipes and refuses to run if either passes an argument that would win
against the config, because a claim it can read that the command does not obey
is worse than no claim.

**Three rules, and each is a disagreement between the claim and the tree.**

- `unclaimed-file`: tracked Python under no claimed root, and under no declared
  exception. This is the `tools/` hole.
- `empty-claim`: a claimed root with no tracked Python under it. An analysis
  pointed at a tree that is not there covers less than its configuration says.
- `stale-exception`: a declared exception excusing no file. It describes a
  repository that is not this one.

**A declared exception is data in the gate, with a reason, printed on every run.**
Two exist. `tests/` is outside strict typing, because the suite is not strictly
typed and `mypy --strict tests` reported 127 errors in 16 files on 2026-08-27;
that line is the declaration that it has not happened. `tests/` is outside the
coverage floor because the suite is the measuring instrument, and coverage of
the tests by the tests is a number that cannot fall. Both are printed clean or
dirty, so coverage declared away is as visible as coverage achieved.

**Strict typing extends to `tools/`,** and the seven errors are fixed: the six
dead `type: ignore` comments are deleted with a comment saying why they were
never doing anything, and `reference_document` returns the `dict[str, JsonValue]`
it actually returns, with the three functions that consume it taking a covariant
`Mapping`.

## Consequences

- A future tree of Python that no analysis covers fails `make verify` instead of
  waiting to be noticed. Narrowing `MARKER_ROOTS` and `[tool.mypy] files` back to
  what `main` carried produces ten `unclaimed-file` findings and exit 1.
- The gate refuses rather than passes when it cannot establish a claim: no
  tracked Python, no `git`, an unreadable or unparseable `pyproject.toml`, a
  missing config key, an empty list, a missing or unrecognised Makefile recipe,
  a `hygiene_gate.py` that will not import or defines no `MARKER_ROOTS`, or a
  command that overrides the configured scope. Every one is exit 2 with a
  message saying it is not a clean result.
- Scope now lives in `pyproject.toml` for two analyses that previously carried it
  as command arguments. `.pre-commit-config.yaml` runs `mypy --strict` with no
  path for the same reason, so the hook and the gate check the same trees.
- The gate is deliberately narrow: three file-scoped analyses over tracked
  Python. Ruff already runs over the whole tree, and the publication sweep and
  the stray-config check already read every tracked path, so neither has a
  scope that can silently narrow. Adding an analysis to the table is one entry
  and a claim source.
- `tools/scope_gate.py` is itself inside all three claims, which is the point.

## Rejected alternatives

- **A hand-written manifest of what each gate covers.** A second copy of the
  truth, which drifts, and drift here is invisible by construction. Every claim
  is read from the file that implements it instead.
- **Assert only that every tracked file is covered by at least one gate.** The
  publication sweep reads every tracked file, so that check passes
  unconditionally and is exactly the vacuous green this program exists to
  remove.
- **Extend strict typing to `tests/` in this change.** 127 errors in 16 files,
  mostly pytest and Hypothesis signatures. That is its own change with its own
  review; declaring it as an exception with the measurement is the honest state
  in the meantime, and the `stale-exception` rule means the declaration cannot
  outlive the gap.
- **Parse the whole Makefile.** The gate reads two named recipes and refuses if
  it cannot find or recognise either. Refusing on a shape it does not understand
  is correct: a changed shape needs re-reading, not guessing.
