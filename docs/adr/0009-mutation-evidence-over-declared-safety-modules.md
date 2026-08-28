# ADR 0009 — Mutation evidence over a declared subset, and what it is not

Status: accepted
Date: 2026-08-27
Decision owners: technical owner

## Context

`make test` holds 90% branch coverage overall and 95% across the fifteen modules
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

**Declared scope, not implied scope.** `DECLARED_TARGETS` is two modules,
`contract_validation.py` and `identifiers.py`, chosen because they are where the
accept-or-reject decisions live: the bounded-string and provenance grammars from
ADR 0006, and the PHI canary and direct-identifier detectors. That is a subset
of `SAFETY_MODULES`, and it is written down for the same reason `make scope`
writes its exceptions down.

**Mutants come only from lines the tests execute**, measured with `coverage` in
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
and a test asserts the tree is unchanged after a run. The baseline run uses the
same `PYTHONPATH` mechanism, so the two runs cannot resolve to different files
and report a mutation that never took effect. `__pycache__` is excluded from the
copy, because a stale `.pyc` beside a mutated source would be imported instead
of it and every mutant would survive for a reason unrelated to the tests.

**Three states, like every other gate.** Exit 0 when every mutant died, 1 on a
survivor, 2 when the gate produced no evidence: the tests do not pass unmutated,
a declared target no test imports, or no mutant generated. A run of zero mutants
is not a suite that killed them all.

**Not in `make verify`,** for runtime alone. The declared set takes about two
minutes against roughly a second for everything else in `verify`, so it is its
own target the way `make secret-scan` and `make a11y-full` are. It needs no tool
a clean clone lacks.

## Consequences

- Measured on this repository: **35 mutants over 124 covered lines, every one
  killed by the suite**, in 2 minutes 12 seconds. That is a real result and not
  a vacuous one; the same measurement showed 14 of those 35 surviving the fast
  screening set, which is why the second stage exists.
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
- **It does not cover thirteen of the fifteen safety modules.** That is the
  declared subset, visible in `DECLARED_TARGETS`, and widening it is a runtime
  decision rather than a design one.

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
