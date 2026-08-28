# ADR 0005 — The gates are inside the trees they scan, and exemptions carry a reason

Status: accepted
Date: 2026-08-27
Decision owners: technical owner

## Context

`tools/hygiene_gate.py` replaced two shell lines that could not fail. It kept
their scope exactly: `MARKER_ROOTS = ("src", "tests")`, "kept identical to what
the ripgrep line searched, so this change fixes the gate's failure modes without
quietly widening or narrowing what it covers." That was the right call for a
change whose whole claim was that it changed nothing but the failure modes.

It leaves `tools/` outside every marker scan. `tools/` holds four gate
implementations and one shell script. Between them they decide whether anything
merges: `hygiene_gate.py`, `publication_sweep.py`, `i18n_gate.py`,
`a11y_gate.py`, and `secret-scan-full-history.sh`. So the programs that enforce
the repository's rules were the one tree exempt from them.

Two more measurements, taken while sizing this:

- `[tool.coverage.run]` had `source = ["contextsafe"]`, so the 90% branch floor
  never measured `tools/` either. Measured on 2026-08-27, `tools/` sat at 91%
  branch coverage overall but `publication_sweep.py` at 77%, with `main`,
  `history_sources` and `load_denylist` almost entirely unexercised. That is why
  the `SweepUnavailable` branch added the same week shipped with no test.
- `publication_sweep.py` skipped an oversized or non-UTF-8 source with a bare
  `continue` and still printed a clean line. Its denominator was the count of
  files it managed to read, which is the one number that cannot reveal a file it
  failed to read. Demonstrated on a scratch repository holding one readable file
  and one binary file: `publication-sweep: clean over 1 source(s)`, exit 0.

All three are the same defect: a check reporting a clean result over content it
did not examine. [`docs/18-ASSURANCE-PROGRAM.md`](../18-ASSURANCE-PROGRAM.md)
records the class and the program that follows from it.

Widening the marker scan to `tools/` is blocked by one thing. `hygiene_gate.py`
has to name the words it bans: once in the module docstring's transcription of
the shell line it replaced, once in the docstring's description of the rule, and
once in `MARKERS` itself. Those three lines are not promises with nobody's name
on them. They are the rule's own definition, and a scan that cannot tell the two
apart cannot be pointed at the file that defines it.

## Decision

**Scope.** `MARKER_ROOTS` becomes `("src", "tests", "tools")`.

**Exemption.** One mechanism, line-level and greppable, matching
`publication-sweep: allow`, which this repository already uses and already
defends: "there is no allowlist of files that quietly exempts a whole path —
including this file, whose own rule patterns are exempted line by line."

`hygiene: allow` on the same line as the marker, **followed by a reason**. A
line carrying the allow marker with nothing after it is a new
`unreasoned-exemption` finding rather than a silent pass.

The reason is required here and is not required by the publication sweep, and
the difference is deliberate. A sweep exemption sits on a line whose content the
reviewer can read and judge directly: the personal path or the internal hostname
is right there. A marker exemption asserts something invisible from the line —
that a promise-shaped word is not a promise — so the claim has to be written
down next to it. The Definition of Done already bans an *unowned* marker; this
is what owning one looks like.

**Visibility.** Every honored exemption is printed on every run, pass or fail,
with its file, line, marker and reason, and the count is part of the clean line.
An exemption is the one thing this gate deliberately does not report as a
finding, so it is the one thing that would otherwise be invisible in a green
run.

**Unexaminable sources.** In `publication_sweep.py`, a listed source that is not
a regular file, is over the scan bound, or is not valid UTF-8 becomes an
`unexaminable-source` finding in both tracked and `--history` mode. The clean
line prints sources read over sources listed. This matches the precedent the
hygiene gate already set with its `unreadable` rule: "a file the gate could not
read is not a file it can vouch for, so it is reported rather than skipped."

**Coverage.** `[tool.coverage.run]` and the `test` target measure `tools`
alongside `contextsafe`.

## Consequences

- The gate implementations are subject to the rule they enforce. A marker
  planted in `tools/` now fails `make verify`; before this change it did not.
- Three exemptions exist, all in `tools/hygiene_gate.py`, all reported on every
  run. `test_this_repository_s_exemptions_all_sit_in_the_gate_that_defines_them`
  pins that, so a fourth one anywhere else is a test failure that has to be
  argued for rather than a line somebody added.
- The mechanism can become the hole it replaced. It is countable specifically so
  that can be watched: if exemptions accumulate faster than they retire, the
  gate has been turned off one line at a time.
- `publication_sweep.py` gets stricter on inputs this repository does not have
  today. Measured on 2026-08-27: 117 tracked paths, all read; 2006 blobs in the
  object database, none over the bound and none non-UTF-8. So this does not turn
  a green run red now. It makes a future skip visible instead of silent, which
  is the only moment it could matter.
- The failure hint for an unexaminable source says the exemption marker does not
  apply, because there is no readable line to put it on. Suggesting a mechanism
  that cannot work is how a reviewer learns to distrust the message.
- The coverage floor now applies to code that was previously unmeasured, so a
  future gate change carries a test obligation it did not carry before. That is
  the point, and it is why `history_sources`, `main` and the denylist paths in
  the sweep gained tests in this change.
- `tools/secret-scan-full-history.sh` is shell, so it is inside the marker scan
  and outside the coverage measurement. It has no test at all. That gap is real
  and is phase 4 of the assurance program, not something this change closes.

## Rejected alternatives

- **Leave `tools/` out and say so in the README.** Documenting a hole is not
  closing it, and the hole is specifically in the code that decides whether the
  README's other claims get to merge.
- **Exempt `tools/hygiene_gate.py` as a whole file.** This is the allowlist the
  publication sweep already rejected for itself. It would also exempt a genuine
  future marker in the same file, which is exactly the file most likely to
  acquire one.
- **Move the three marker-bearing lines out of the file** — the historical shell
  transcription into the changelog, the rule description into this ADR. Both
  already carry the text, so this would work. Rejected because the gate exists
  to keep unowned promises out of the code, not to push a file's own
  documentation somewhere a reader of that file will not see it.
- **Detect markers only in comments, the way a conventional linter does.** This
  would dissolve the problem for `MARKERS` but not for the two docstring lines,
  since a docstring is not a comment. It would also change detection semantics
  and scope in the same change, which is how a widening quietly becomes a
  narrowing.
- **Allow an exemption with no reason, and judge it in review.** This is what
  `publication-sweep: allow` does, for the reason given above. Applied to a
  marker it produces a line that says "this is fine" and nothing else, which is
  indistinguishable from a marker somebody wanted to keep.
- **Make a dead exemption — the allow marker on a line with no marker — a
  finding too.** It has no teeth worth the cost: such a line suppresses nothing,
  and the rule would fire on this gate's own `ALLOW_MARKER` definition and on
  every line of documentation that shows the syntax. The rule inspects only
  lines that actually carry a marker, so the mechanism can be written about
  without being tripped over.
- **Make an unexaminable source a refusal (exit 2) rather than a finding.** The
  sweep knows exactly which file it is and can name it, so it can report a
  finding. Exit 2 is kept for the case where there is nothing to name: an empty
  listing, or an object git enumerated and then refused to output.
