# ADR 0009 — Mutation evidence over a declared subset, and what it is not

Status: accepted
Date: 2026-08-27
Decision owners: technical owner

## Context

`make test` holds 90% branch coverage overall and 95% across the sixteen modules
named in the Makefile's `SAFETY_MODULES`. Those numbers say a line ran. They say
nothing about whether anything would have failed had the line been wrong.

That is the last place in this repository where a green mark still means less
than a reader would assume. ADRs 0005, 0007 and 0008 made every gate say what it
examined; none of them can say whether the suite behind the coverage number
would notice a change. A suite that imports every module and asserts almost
nothing reports the same 95%.

## Decision

Add `tools/mutation_gate.py`, run as `make mutants`. It changes one operator or
one constant in a declared safety module, runs the tests, and requires them to
fail.

**Declared scope, not implied scope.** `DECLARED_TARGETS` is two modules
(three since 2026-09-04; see "What this is not"),
`contract_validation.py` and `identifiers.py`, chosen because they are where the
accept-or-reject decisions live: the bounded-string and provenance grammars from
ADR 0006, and the PHI canary and direct-identifier detectors. That is a subset
of `SAFETY_MODULES`, and it is written down for the same reason `make scope`
writes its exceptions down.

**Mutants come only from lines the suite executes**, measured with `coverage` in
the same run rather than assumed. A mutant on a line nothing runs would survive
for a reason mutation testing was not asked about. The run prints the covered
line count, so the denominator is visible.

**Five operators**, each a real defect shape in validation code: a comparison
swapped with its neighbour (`>` for `>=`), a boolean operator flipped, a `not`
removed, a boolean constant flipped, a numeric bound moved by one. String
constants are deliberately never mutated: a mutated regular expression is a
different program, not a probe for a missing assertion.

**Two stages, and the claim is about the suite.** Every mutant runs first
against four fast test modules, and a mutant they do not kill then runs against
the whole suite before being reported. Answering with the subset alone would
report survivors the suite in fact catches. Survivors are the only mutants that
pay the full run, so the gate gets faster as they are fixed.

**Nothing is written into the working tree.** The package is copied to a
temporary directory, mutated there, and put ahead of the editable install with
`PYTHONPATH`. A crash or an interrupt cannot leave a mutated source file behind,
and a test asserts the tree is unchanged after a run: it records the module's
bytes at the moment each test run is launched and requires every one of those
observations to be the unmutated source, because the restore in `finally` means
a before-and-after comparison would pass for a gate that mutated in place. Its
companion replaces staging with one that hands back the working tree and
requires that watch to go red. Neither existed until 2026-08-31 -- the test this
sentence used to cite ran `main` without patching `DECLARED_TARGETS`,
`SCREENING_TESTS` and `PACKAGE_DIR`, so it refused at exit 2 before staging
anything and then found a file unchanged by a run that never touched it, and its
second assertion shelled out to `git status` in the real repository, which fails
for anyone with uncommitted work under `src`. The baseline run uses the
same `PYTHONPATH` mechanism, so the two runs cannot resolve to different files
and report a mutation that never took effect. `__pycache__` is excluded from the
copy, because a stale `.pyc` beside a mutated source would be imported instead
of it and every mutant would survive for a reason unrelated to the tests.

**Three states, like every other gate.** Exit 0 when every mutant died, 1 on a
survivor, 2 when the gate produced no evidence: the suite does not pass
unmutated, a declared target no test imports, or no mutant generated. A run of
zero mutants is not a suite that killed them all.

**The baseline is the suite, and that is load-bearing.** The kill decision in
the second stage belongs to the suite, so the baseline has to be the suite too.
It was not, at first. The baseline ran only the screening set, and while an
unrelated contract test was failing, every mutant's second stage returned
non-zero, every mutant was recorded as killed, and this gate printed `clean`
over 35 mutants it had proved nothing about. That is this program's own defect
class committed by the gate written to close it, and it was found by re-running
the measurement in isolation rather than by reading the code. One coverage run
over the suite now both checks it passes and produces the lines to mutate.

**Not in `make verify`,** for runtime alone. The declared set takes about two
minutes against roughly a second for everything else in `verify`, so it is its
own target the way `make secret-scan` and `make a11y-full` are. It needs no tool
a clean clone lacks.

Correction, 2026-09-05: "roughly a second for everything else in `verify`" was
written on 2026-08-27 and is no longer true of the tree. `make verify` was
measured at about four minutes on 2026-09-05, about 90% of it the pytest stage;
the figures and the method are in "What the gate costs, measured" in
[docs/18-ASSURANCE-PROGRAM.md](../18-ASSURANCE-PROGRAM.md). The comparison this
paragraph rests on is two minutes against about four, not two against one. The
decision recorded here is left as it was taken; what the corrected ratio implies
for it is open, and it belongs with the options that section prices.

## Consequences

- The first honest run reported **nine survivors of 35**, and all nine were real
  gaps in a pair of modules at 95% branch coverage: `frozen=True, slots=True`
  unasserted on both records the boundary layer is built from, the non-string
  and empty-string branch of `provenance_string`, a value of exactly
  `max_length` in `bounded_string`, the upper end of the surrogate block, the
  256-byte relative-path bound and the 253-byte host bound. Two of those are
  gaps introduced by ADR 0006's own change; five predate it.
  `tests/test_contracts.py` now pins each, which is the argument for this gate
  stated as concrete assertions rather than as a claim.
- With those pinned, measured in isolation: **35 mutants over 143 covered lines,
  every one killed by the suite**, exit 0. The same measurement showed 14 of the
  35 surviving the fast screening set, which is why the second stage exists.
- Because the gate is green here, the only way to know it can fail is a
  repository where it must. `tests/test_mutation_gate.py` builds one: the same
  three-line module, tested at its boundary and not, and the gate has to tell
  them apart. The weak fixture yields exactly two survivors, `Gt became GtE` and
  `10 became 11`, and both are real, because `over(50)` is true whether the
  operator is `>` or `>=` and whether the bound is 10 or 11. Branch coverage of
  that module is 100% in both fixtures.
- The fix a survivor asks for is a case at the edge, not more code. The strong
  fixture differs from the weak one by two assertions.
- There is **no survivor allowlist**. Nothing here is currently unkillable, and
  building the escape hatch before a mutant needs it is how a gate gets turned
  off one line at a time. When a genuinely equivalent mutant appears, the
  mechanism is added then, with a real entry and a reason.
- `make mutants` is not wired into CI in this change. It is a target a
  maintainer or a scheduled job runs, documented in `CONTRIBUTING.md` alongside
  `make secret-scan`. Adding a workflow nobody has watched execute is not
  evidence.

  (Wired in on 2026-09-04, closing #80: `.github/workflows/mutation.yml` is the
  scheduled job this sentence anticipated, weekly plus any pull request touching
  the package, the suite or the gate. It stays out of `make verify` for the
  runtime reason below. The caution above still holds and is not waived — this
  ADR's authors have not watched that workflow execute, and its first real run
  is the evidence, not its existence. What the tree can assert without one is
  asserted: `tests/test_ci_workflows.py` requires the workflow to exist, to run
  without being asked, to keep `mutants` out of `verify`, and to carry no
  `continue-on-error` or `|| true` that would turn any of the three exit codes
  into a pass.)

## What this is not

- **It is not B-048.** B-048 requires all 41 published and hidden faults to be
  detected and correctly localized before release, against an authored fault
  corpus with clinical meaning. This measures assertion strength against
  mechanically generated changes. It is a weaker signal about clinical
  correctness and a stronger one about whether the suite checks what it runs.
  Neither substitutes for the other, and passing this closes nothing in B-048.
- **It is not a proof of correctness.** R-14 is recorded as irreducible: a
  finite test pack cannot prove safety. A killed mutant says one specific wrong
  program would have been caught.
- **It does not cover fourteen of the sixteen safety modules.** That is the
  declared subset, visible in `DECLARED_TARGETS`, and widening it is a runtime
  decision rather than a design one. (Widened once, on 2026-09-04, when
  `review.py` joined both `SAFETY_MODULES` and `DECLARED_TARGETS` with B-032:
  thirteen of sixteen remain outside it.)

## Rejected alternatives

- **`mutmut` or `cosmic-ray`.** Either would be a new dependency in a repository
  whose gates are stdlib by policy, and neither is needed: the operator set here
  is five rules over `ast`, and the parts worth getting right — coverage
  restriction, not touching the tree, the two-stage claim — are the parts a
  general tool would have to be configured into anyway.
- **Mutating the source files in place and restoring afterwards.** One crash
  between the write and the restore leaves a mutated safety module in the
  working tree. The temporary copy makes that impossible rather than unlikely.
- **A random sample of mutants per run.** Faster, and nondeterministic. This
  repository requires the same inputs to produce the same output; a gate whose
  result depends on a seed cannot be one of its gates.
- **Reporting survivors from the fast screening set alone.** Two minutes becomes
  thirty seconds, and the gate reports survivors the suite already kills. A gate
  that cries wolf is turned off, and then it protects nothing.
- **Putting it in `make verify`.** Two minutes on every push, against one second
  today, for a signal that changes slowly. `make secret-scan` and
  `make a11y-full` already set the precedent for a gate that runs elsewhere.
  (Correction, 2026-09-05: "one second today" is the figure this ADR was written
  against. Measured nine days later, `make verify` is about four minutes, so
  this rejected option would add two minutes to four rather than to one.
  Whether the option is still rejected at that ratio is not decided here; see
  the correction above, and "What the gate costs, measured" in
  [docs/18-ASSURANCE-PROGRAM.md](../18-ASSURANCE-PROGRAM.md).)
