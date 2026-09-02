# Pull request triage, 2026-08-28

Eight open pull requests, no open issues. This document reconstructs what each
one is for, whether it is correct, how they overlap, what the real merge state
is, and what should happen to it.

Nothing here was merged, pushed, closed, or commented on. It is a reading.

## Resolution, 2026-08-31

Recorded here because a triage document that stays frozen while the queue moves
becomes another sentence nobody re-derives.

Steps 1, 2 and 5 of "Safe order of operations" happened: #25, #26, #39 and #40
merged, and #46, #47 and #48 were closed as superseded. Step 3 -- the six
blocking items and the tests below them -- was done on
`assurance/phase-6-blocked-and-recorded` itself. Step 4 was done by merging
`main` into that branch rather than rebasing it, because its commits are records
under a preservation duty; the conflicts were the two tabled above plus the
`Makefile` and `CHANGELOG.md` placement of the `claims` gate, which landed on
`main` after this document was written. Step 6, `make mutants` on the merged
tree, reports 35 mutants over 143 covered lines, every one killed.

Every finding above is either fixed on that branch or, where it was a wrong
sentence, corrected there. The `CHANGELOG.md` entry for 2026-08-31 lists them
one by one, and each fix has a test that fails without it. Nothing in this
document has been edited: it is the reading that was made on 2026-08-28, and
this section is what happened next.


## Summary table

| PR | Base | What it is | Real merge state | Recommendation |
| --- | --- | --- | --- | --- |
| #49 | `main` | Assurance phases 3-6, cumulative | Green, conflicts on 2 files (not its fault) | **needs work** — see the list below |
| #48 | `main` | Phases 3-5, subset of #49 | Green, same conflicts | **close as superseded by #49** |
| #47 | `main` | Phases 3-4, subset of #48 | Green, same conflicts | **close as superseded by #49** |
| #46 | `main` | Phase 3, subset of #47 | Green, same conflicts | **close as superseded by #49** |
| #40 | `main` | `uv.lock`: coverage, hypothesis, mypy, **ruff 0.15→0.16** | Clean, green | **merge** |
| #39 | `main` | `setup-uv` 8.3.2 → 10.0.1 | Clean, green | **merge** |
| #26 | `main` | `setup-node` 6.0.0 → 7.0.0 | Clean, green | **merge** |
| #25 | `main` | `upload-artifact` 4.6.2 → 7.0.1 | Clean, green | **merge** |

## The first thing to know

**#46, #47, #48 and #49 are not four changes. They are four cumulative snapshots
of one change.**

- #46 = phase 3
- #47 = #46 + phase 4
- #48 = #47 + phase 5
- #49 = #48 + phase 6

Verified by comparing trees, not descriptions: no file introduced by #46, #47 or
#48 is absent from #49, and every difference is a later phase evolving an earlier
file further. Merging #49 delivers all four. Merging them in order delivers the
identical tree through four conflict resolutions instead of one.

All four descriptions say "Stacked on #48 → #47 → #46 → #45 → #44", but all four
now target `main`, and each was rebased onto `main` independently, so their
commit SHAs differ and git does not know they are related. A reviewer working
through them in order will do the same work four times.

## Why all four are red, and whose fault it is

Not theirs, and they are not failing.

All four passed all nine checks — `verify`, SAST, secret scanning, dependency
audit, publication sweep, accessibility, and determinism on Ubuntu, macOS and
Windows — at 2026-08-28T03:40Z. Those are real runs, checked at step level: the
`verify` job has 9 steps and its gate step ran 59 seconds.

**There is no billing starvation anywhere in this repository.** Of the last 100
workflow runs, 93 succeeded, 3 failed (all on `main`, all 2026-08-17, since
fixed), and 2 are `action_required` on a pull request that is already closed. No
0-step jobs, no budget annotations.

What happened is a timing accident. **#45 merged at 03:55:14Z, fifteen minutes
after all four branches were last rebased at 03:40Z.** Each still carries phase
2's two commits, and because #45 was squash-merged, git cannot recognise the
duplicates. Hence `DIRTY / CONFLICTING` on all four.

The conflict touches exactly two files and both resolutions are mechanical:

| File | Conflict | Resolution |
| --- | --- | --- |
| `CHANGELOG.md` | Both sides inserted at the same anchor under `### Changed`. Main's side of the region is empty. | Delete the three marker lines, keep both blocks. Nothing is lost. |
| `docs/18-ASSURANCE-PROGRAM.md` | One line. | Keep `Status: phases 1 to 5 built; phase 6 blocked, see below`; drop `Status: proposed, phases 1 and 2 built`. |

### The green survives the merge

The tree produced by merging #49 into current `main` differs from the tree CI
tested green by **exactly the seven conflict-marker lines and one superseded
status line**. Resolve as above and the result is byte-identical to the tree that
passed all nine checks. The CI green is not stale — it is the same tree.

### The four PRs make no net change to `src/` at all

GitHub shows #49 touching `src/contextsafe/preflight.py` (17+/57-),
`src/contextsafe/identifiers.py` (+184), `src/contextsafe/evidence.py`,
`src/contextsafe/contract_validation.py`, `tests/test_privacy_canaries.py` and
`schemas/contextsafe-evidence-v1.schema.json`. In a tool about identity-data
safety, that file list should stop a reviewer.

It is an artefact. Every one of those files is **byte-identical to what is
already on `main`** via #45. Merged onto current `main`, all four pull requests
produce **zero** net change to `src/`, `schemas/` and `fixtures/`. Verified by
comparing blob hashes in each merge-result tree against `main`.

The privacy, redaction and PHI-canary surface is untouched by every open pull
request. What these four actually change is `tools/`, `tests/`, `docs/`,
`Makefile`, `pyproject.toml` and `.pre-commit-config.yaml`.

## Stack diagram

```
main (b4c9d4a) ── #45 phase 2 (merged 03:55Z) ── #44 phase 1 (merged 01:48Z)
  │
  │   the four below were rebased at 03:40Z, before #45 landed, so each
  │   still carries phase 2 and each conflicts on the same two files
  │
  ├── #46  assurance/phase-3-declared-scope         = p2+p3
  ├── #47  assurance/phase-4-absent-tool-contract   = p2+p3+p4        ⊃ #46
  ├── #48  assurance/phase-5-mutation-evidence      = p2+p3+p4+p5     ⊃ #47
  ├── #49  assurance/phase-6-blocked-and-recorded   = p2+p3+p4+p5+p6  ⊃ #48
  │
  ├── #25  upload-artifact 4.6.2 -> 7.0.1    independent, clean, green
  ├── #26  setup-node      6.0.0 -> 7.0.0    independent, clean, green
  ├── #39  setup-uv        8.3.2 -> 10.0.1   independent, clean, green
  └── #40  uv.lock dev deps incl. ruff       independent, clean, green
```

**Auto-close exposure: none.** All eight target `main`, so no base merge can
auto-close any of them. Note the converse: because #46, #47 and #48 were rebased
into distinct SHAs, merging #49 will **not** auto-close them either. They will
sit open with an empty diff and must be closed by hand.

## #49 — why it is `needs work`

The four phases do real work: three new or hardened gates, roughly 1,300 lines,
all CI green, and a set of ADRs that argue their case carefully. The scope gate
genuinely catches the case it was built for.

But the program's own thesis is that **a gate must never report clean over
something it did not examine**, and each of the three gates this stack adds or
hardens still has at least one path that does exactly that — and, more seriously,
the ADRs and changelog assert several properties that do not hold. In a
repository whose entire value is that its claims match reality, the false claims
are the harder blocker than the code.

None of this is a regression: `main` today has no scope gate, no mutation gate,
and the same secret-scan hole. The objection is not that #49 makes anything
worse. It is that it ships documentation saying holes are closed that are not.

### Blocking, in priority order

1. **The secret-scan security gate still fails open, and now claims not to.**
   `tools/secret-scan-full-history.sh` enumerates objects with
   `git cat-file --batch-all-objects --batch-check`, then switches on the object
   type with branches for `blob` and `commit` **and no default branch**. When git
   cannot read an object it does not fail: it prints to stderr and emits the type
   `missing`. That falls through the `case` — never counted, never materialised,
   never an error — so the dominant corruption mode is silently skipped and the
   phase reports clean. `tree` and `tag` objects are skipped the same way, so an
   annotated tag's message is never scanned despite the header claiming "every
   object in the object database".

   The exit-2 guards that do exist are only reachable for an object git
   successfully classified and then failed to read. The hole is on `main` too —
   this PR changes only the exit codes, 1 to 2, not the enumeration — but ADR
   0008 and the `CHANGELOG` now list "an object it enumerated and could not read"
   as a state that exits 2. Fix is a `*)` default branch that exits 2, plus
   checking the enumeration's own status (the `while read` is fed by process
   substitution, which neither `set -e` nor `pipefail` covers).

2. **The mutation gate counts any non-zero pytest exit as a kill.**
   `tools/mutation_gate.py` decides a mutant died with `if _run(...) != 0:
   continue`, and reports a survivor only on `== 0`. pytest returns non-zero for
   collection errors (2), internal errors (3), usage errors (4) and
   no-tests-collected (5) as readily as for a failed assertion (1). Output is
   captured and discarded, so nothing surfaces. This is the same mechanism as the
   defect the branch's own commit "the mutation gate reported clean over a suite
   that was already failing" fixed: that commit fixed the trigger and left the
   mechanism.

   It is reachable today. `SCREENING_TESTS` is four hard-coded paths that nothing
   validates against the tree. Rename `tests/test_plan.py` and every stage-one run
   exits 4, every mutant is recorded killed, and the gate prints
   `mutants: clean - N mutant(s) ... every one killed by the suite` and exits 0
   over zero evidence. `make scope` does not cover this declaration, and nothing
   in `.github/workflows/` runs `make mutants`, so the drift window is indefinite.
   Fix: treat exit 1 as the only kill, refuse on 2-5, and check the screening
   paths exist before the loop.

3. **ADR 0009's evidence for working-tree safety does not exist.** The ADR says
   "a test asserts the tree is unchanged after a run" and the changelog repeats
   it. `test_the_gate_never_writes_to_the_working_tree` calls
   `gate.main(["--root", str(root)])` **without** monkeypatching
   `DECLARED_TARGETS`, `SCREENING_TESTS` and `PACKAGE_DIR`, unlike the test
   immediately above it. So it runs the real `src/contextsafe` targets against a
   fixture containing only `src/pkg`, refuses with exit 2 before the staging loop
   is ever entered, and then asserts a file is unchanged by a run that never
   staged anything. Its second assertion shells out to `git status -- src` in the
   **real repository**, which the run never touched and which would fail
   spuriously for any developer with uncommitted `src` changes.

   Verified by reading both tests side by side. The staging and mutation code is
   sound as far as I can tell; it is the proof that is missing.

4. **The a11y gate can still exit 0 having examined nothing, and exit 1 when it
   could not examine.** `run_axe` treats `payload.get("ok")` as proof the engine
   ran, so a harness returning `{"ok": true}` with no pages produces zero
   findings and exit 0. Separately, `--engines ''`, `--engines bogus`, the
   `coverage` rule and `undetermined-uncovered` all name a failure to run and all
   exit 1, because `UNAVAILABLE_RULES` lists only four ids. And `main` has no
   exception boundary, so `--locale zz` is an uncaught traceback at exit 1 — the
   same input class this very PR fixed to exit 2 in the i18n gate. Two gates, one
   PR, opposite answers.

5. **The scope gate breaks its own contract on an unreadable claim.** Its
   `hygiene_gate` import catches only `(OSError, SyntaxError)`, so a
   `ModuleNotFoundError`, `NameError` or `ValueError` escapes as a traceback and
   exit **1** — "examined and found something" for a gate that could not examine.
   It also dropped the `UnicodeDecodeError` guard its sibling `hygiene_gate.py`
   carries. And `_under` returns `True` for every path when a root is `""` or
   `"."`, so `MARKER_ROOTS = (".",)` reports clean over everything; the gate
   refuses a vacuous comparison when there are zero files but not when a root
   vacuously claims all of them.

6. **The claim-source integrity check is trivially defeated.** The scope gate's
   headline defence is that it refuses to run if a Makefile recipe passes an
   argument overriding the configured scope. In practice it scans for four string
   literals on the first line mentioning the tool, never joins backslash
   continuations, and never looks past that line. Nine of ten realistic spellings
   pass clean — `mypy --strict src/`, `mypy --strict "src"`,
   `mypy --strict $(SRC)`, a comment line before the real one, a continuation,
   `pytest --cov src` in the space form. The comment-line evasion is not
   hypothetical: this repository's own `sync` target already uses recipe comments.

### Tests that assert less than they appear to

Worth fixing because this stack's whole subject is evidence quality.

- Deleting phases 1 and 3 from `secret-scan-full-history.sh` entirely — so the
  gate no longer scans reachable history or the working tree — leaves **all**
  secret-scan tests passing. The fake gitleaks never records its argv, and
  nothing asserts three invocations or their `--source` arguments.
- `test_the_unavailable_rules_are_the_ones_that_name_a_failure_to_run` restates
  the `frozenset` literal from the source. It cannot detect the defect in item 4
  above, and it is green.
- Three scope-gate refusal tests are tautologies: their fixtures also lack a
  Makefile or a pyproject, so they refuse for a different reason than the one
  they name. Replacing `if not files:` with `if False:` leaves all 24 tests
  passing — the gate's most-argued property is unpinned.
- `test_every_declared_exception_is_printed_on_a_clean_run` builds its expected
  strings from the same tuple the code prints, and passes vacuously when the
  tuple is empty.
- `test_every_gate_program_is_covered_by_this_contract` does enumerate `tools/`
  at runtime and does fail on a new gate — verified. But it globs `*.py` only, so
  the one shell gate sits outside the contract exactly as it did before the PR,
  and `tools/_private.py` or `tools/sub/nested.py` escape it.

### Counts in the descriptions that are wrong

Small, but this stack's argument is made of measurements.

- #47 says "8 failed, 7 passed" against its parent. It is 8 failed, **8** passed
  (16 tests, not 15); against `main` it is 11 failed, 5 passed.
- ADR 0008 and the changelog say "all five Python gate programs"; the case list
  holds **six**.

### What is genuinely good, and verified

Stated so the rework does not throw it away.

- `tests/test_contracts.py` pins nine real, previously unasserted boundaries —
  exact `max_length`, all four corners of the surrogate block, the 256-byte path
  and 253-byte host bounds, the non-string and empty-string branches, and
  `frozen`/`slots` on both records with two independent assertions. Not filler.
- The mutation gate's baseline genuinely runs the **whole suite**, not the
  screening set, and refuses with exit 2 when it is red. The two-stage logic
  cannot manufacture a survivor. Mutant ordering is deterministic, column is part
  of mutant identity, `bool` is correctly excluded from the integer-bound case,
  and chained comparisons are correctly skipped.
- Every "the mutation did not take effect" failure mode manifests as a false
  *survivor* — loud, exit 1 — never as a false clean. That is the right direction.
- The scope gate's path matching is genuinely segment-based in both directions,
  with no separator bug; `srcery/` cannot be claimed by `src`.
- The i18n gate's changes are clean: no path examines zero catalogs and exits 0,
  and the unknown-locale traceback is now a proper exit 2.
- Six `# type: ignore` comments removed from `tools/` were suppressing nothing.
  Independently confirmed: `main` carries exactly seven, #49 removes six and
  keeps the one that is load-bearing.

### The path forward

The fixes are small and surgical — a `case` default branch, a pytest exit-code
check, three constants monkeypatched in one test, a widened `except`, a wider
`UNAVAILABLE_RULES`. Do them on `assurance/phase-6-blocked-and-recorded`, correct
the ADR and changelog sentences that overstate what is proved, rebase, and merge
one pull request.

## Dependabot pull requests

### #40 — python-dependencies group (4 updates)

`uv.lock` only: coverage 7.15.1→7.15.4, hypothesis 6.156.6→6.165.10, mypy
2.3.0→2.3.1, **ruff 0.15.21→0.16.4**. `CLEAN / MERGEABLE`, all nine checks green,
re-run 2026-08-28T01:51Z. Its base differs from current `main` only by #45, which
touched neither `uv.lock` nor `pyproject.toml`, so its green is current for the
files it changes. **Recommendation: `merge`.**

One thing to know: ruff 0.15 to 0.16 is a minor bump, and `[tool.ruff.lint]`
selects `RUF`, `B` and `SIM`, whose contents grow across minor versions. There is
no `required-version` pin. Merging #40 **before** #49 returns is the better
order — #49 has to be rebased and re-run anyway, and doing it against ruff 0.16.4
is how the new gate code gets checked under the new linter before it lands rather
than after.

### #39 — setup-uv 8.3.2 → 10.0.1

One SHA in five places across `ci.yml`, `release.yml` and `security.yml`.
Verified: `20cfd1bf...` is genuinely the commit tagged `v10.0.1` upstream, and
`.github/` has not changed on `main` since this PR's base, so its green is
current.

Two majors of breaking changes, both read and both benign here. v9.0.0 changes
`prune-cache` to default `false` — a cache-size and cost change, not a
correctness one. v10.0.0 disables caching on `pull_request_target`,
`workflow_run` and `release`, but only for `enable-cache: auto`; this repository
sets `enable-cache: true` explicitly everywhere and already disables the cache by
hand on the tag path in `release.yml`, for exactly the poisoning reason v10
addresses. Behaviour here is unchanged. **Recommendation: `merge`.**

### #26 — setup-node 6.0.0 → 7.0.0

One SHA in `ci.yml`, for the accessibility job's Node. SHA `820762786...`
verified as upstream `v7.0.0`; `.github/` unchanged on `main` since the base; all
nine checks green including the accessibility job, which is the one it affects.
**Recommendation: `merge`.**

### #25 — upload-artifact 4.6.2 → 7.0.1

One SHA in `ci.yml`, for the accessibility report upload. SHA `043fb46d1...`
verified as upstream `v7.0.1`; `.github/` unchanged since the base; green.
**Recommendation: `merge`.**

## Hazards checked and found absent

Recorded so a later reader knows the ground was covered.

- **A changelog hunk landing in an already-released section.** Not possible here.
  `CHANGELOG.md` has exactly one section heading, `## [Unreleased]`. No tag and no
  release exist, and `CITATION.cff` deliberately carries no version. The changelog
  conflict is a placement ambiguity, not a misfiled entry.
- **Colliding monotonic identifiers.** `main` carries ADR 0000-0006. The open PRs
  add 0007, 0008 and 0009, and because they are nested rather than parallel, no
  two claim the same number for different content. No renumbering needed. There
  are no migrations in this repository.
- **Two pull requests appending to the same file's end and merging into something
  broken.** The four assurance branches are nested, not parallel, so nothing
  interleaves. The four Dependabot branches touch only `.github/workflows/*.yml`
  and `uv.lock`, which no assurance branch touches.
- **Billing starvation.** None, verified by step count and job duration rather
  than by conclusion alone.
- **A workflow that never ran on a stacked pull request.** `ci.yml` and
  `security.yml` both trigger on `pull_request` with no branch filter, so the
  phase branches were scanned even while stacked. Confirmed against run history:
  every phase branch, `assurance/phase-2` included, has its own CI and security
  runs.

## Safe order of operations

1. **Merge #39, #26, #25** in any order. Each is one verified SHA bump in
   `.github/`, independent of the others and of everything else.
2. **Merge #40.** Doing it now means the eventual #49 rebase is checked under
   ruff 0.16.4 before it lands.
3. **Send #49 back for the six items above**, on its own branch. Correct the ADR
   0008, ADR 0009 and changelog sentences that overstate what is proved, and the
   two wrong counts.
4. **Rebase #49** onto current `main`. The two phase-2 commits will apply empty —
   skip them. Resolve the two conflicts exactly as tabled above and nothing else.
   Re-run `make verify`. **Merge #49.** No regeneration step, no changelog
   reposition, no identifier renumber is required.
5. **Close #48, #47 and #46 as superseded by #49.** They will not auto-close;
   after step 4 their diffs are empty but they stay open.
6. **Run `make mutants` by hand once** after step 4. It is deliberately outside
   `make verify` and no workflow invokes it, so merging #49 is the first moment it
   exists on `main` with nothing running it.

## Defects on `main` that no open pull request addresses

Separate from the triage. Fixed in the working tree, uncommitted. All three are
one defect class — a document asserting a gate that is not there — which is the
class `docs/18-ASSURANCE-PROGRAM.md` exists to track.

1. **`DEFINITION_OF_DONE.md` claimed a required check that does not exist.** It
   said "The required GitHub `verify` check runs exactly `make verify`". There are
   no required status checks on this repository. The `protect-main` ruleset
   carries exactly two rules, `deletion` and `non_fast_forward`; classic branch
   protection returns "Branch not protected". Nothing mechanically refuses a merge
   over a red or absent `verify`. The same gap makes `.github/CODEOWNERS`
   advisory, despite its comment that "Merge-gate and dependency changes require
   explicit owner review". Making `verify` required is a repository-settings
   change and the owner's to make; the document now says what is true and names
   the gap.

2. **`CONTRIBUTING.md` claimed GitHub Actions is unavailable on this account.**
   It is not: 93 of the last 100 workflow runs succeeded and every open pull
   request has nine green checks. This matters beyond tidiness — #47's description
   cites this sentence as its reason for not building the CI-side proof its own
   plan called for. The line now describes what runs, and names the real gap
   beside it: `ci.yml` carries `paths-ignore` for `**.md`, `docs/**` and
   `LICENSE`, so a documentation-only pull request gets no `verify` run at all.

3. **Two SHA-pinned actions are stale and nothing will re-raise them.** `main`
   pins `actions/checkout` at v7.0.0 (upstream v7.0.1) and `actions/setup-python`
   at v6.3.0 (upstream v7.0.0). Dependabot offered both, as #18 and #19, and both
   were closed on 2026-08-16 in the same minute as #20 and #21. Closing a
   Dependabot pull request tells it not to offer that version again, so those two
   pins are now frozen silently. `.github/dependabot.yml` says it in its own
   comment: "A pinned SHA is only safe while something bumps it." The README's
   Security and Supply-Chain row claimed the actions are "kept current by
   Dependabot"; it now records the two that are not.

   The pin bumps themselves are **not** made here. `actions/setup-python` v6 to
   v7 is a major version that has never run against this repository, and making an
   untested workflow change that only CI can validate would be the same unwatched
   green this triage argues against. The remedy is to let Dependabot re-raise them
   and review the result normally.

4. **Not fixed, recorded:** the secret-scan enumeration hole in item 1 of the #49
   list is present on `main` today, independent of any pull request. If #49 is
   reworked it should be fixed there; if #49 is abandoned it still needs fixing.
