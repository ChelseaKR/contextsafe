# ADR 0012 — A partial parse is a failure to examine, and the syntax that follows from it

Status: accepted
Date: 2026-09-05
Decision owners: technical owner

Extends [ADR 0004](0004-sast-gate-pragma-and-scan-invocation.md), which chose the
scan, and [ADR 0008](0008-one-exit-code-contract-for-every-gate.md), which chose
the exit-code contract and recorded that the SAST gate sat outside it. Neither is
superseded: ADR 0004's rule set, its full-scan-on-every-event posture and its "no
waiver, no `.semgrepignore`, no `# nosemgrep`" rule all stand. What changes is who
reads the scan's result.

## Context

The scanner had not been reading all of `src/contextsafe/validation.py`, and said
so in a line nobody was looking at:

```
[WARN] Syntax error at line src/contextsafe/validation.py:327:
  Partially analyzed due to parsing or internal Semgrep errors
```

Line 327 was `def _enum[T: StrEnum](...)` — PEP 695 type parameters on a generic
function. The parser stops there and reports the remainder of the module as
partially analyzed.

Three facts make this the repository's named defect class rather than a lint
annoyance:

- `validation.py` is a safety module. It is in the Makefile's `SAFETY_MODULES`,
  it carries the 95% branch-coverage floor, and it is where a fail-open would
  matter most. The SAST gate was reporting clean over the part of it the scanner
  had not finished reading.
- The scan still exits 0. A partial parse is reported at level `warn`, and
  `--strict` — chosen in ADR 0004 precisely so "a scan that cannot run can no
  longer report success" — did not convert it. On `main` the job was green for as
  long as the construct existed; it went red only on a branch whose larger file
  set pushed the same warning into exit 3. **A control whose verdict depends on
  how many files the run happened to include is not a gate.**
- ADR 0008 gives every gate three states — clean, finding, could-not-examine —
  and explicitly left semgrep outside them, on the grounds that whether the
  scanner distinguishes a finding from an analysis error is a property of a tool
  this repository cannot verify offline. That reasoning was right about the exit
  code and wrong about the gate: the scanner's `--json` report carries the parse
  errors and the list of files it actually scanned, and a report can be read
  offline by a stdlib program with tests.

The construct itself was fixed when #114 was filed, by writing `_enum` with a
`TypeVar` and ignoring ruff's `UP047` — the rule that asks for exactly the syntax
the scanner cannot parse — with the reason recorded beside the ignore. That fix
closed one instance. Nothing detected the next one, and the reason for the ruff
ignore lived only in a `pyproject.toml` comment, which is not where a constraint
on how this codebase may be written belongs.

## Decision

### 1. The scanner's exit code is no longer the verdict

`tools/sast_gate.py` runs the scan, writes its JSON, reads it, and answers in the
three states of ADR 0008:

- **0** — every source the gate claims was scanned, every scanned file parsed,
  no rule matched. The clean line names both counts.
- **1** — the scanner reported a match. Any match: this gate does not read the
  registry's blocking/non-blocking classification, which is ADR 0004's `--error`
  posture moved into the program unchanged.
- **2** — it could not examine what it claims to. That covers the scanner being
  absent, the scanner exiting in a way that says it did not complete, no report
  written, a report that cannot be read or is not JSON, a report in a shape the
  gate does not understand, a scan of zero files, **a file the parser could not
  finish**, and a tracked source under the declared trees that is missing from
  the scanner's own list of scanned files.

A partial parse is state 2 and not state 1 deliberately, and a run carrying both
a parse error and a real finding is state 2: the finding list gathered beside an
unread file is incomplete and nothing in it says so. ADR 0008 made the identical
call for an accessibility run with an absent engine.

The report is read fail-closed. A missing or wrongly typed `results`, `errors` or
`paths` key is a refusal, not an empty list — an empty list would be a clean
verdict derived from a document the gate did not understand.

**The scan runs with `--timeout 0`, and that is part of the decision rather than
a tuning detail.** By default a rule that runs long on a file is abandoned and
reported as a `warn`-level `Timeout` error. That rule did not examine that file,
which is the state this gate refuses to call clean; but whether it happens
depends on how loaded the machine is, so a gate that failed on it would be a
gate whose verdict tracks CPU contention — the same defect as one whose verdict
tracked the file count, one layer over. The alternative to excusing the state is
removing it: give every rule as long as it needs, and then any error at all
means something. Measured on 2026-09-05 against the registry `auto`
configuration over this repository: 16 timeout errors across 6 files with the
default limit, 0 with none, and the same wall time to the second, because the
run is dominated by fetching the rules. A rule that genuinely hangs is bounded
by the job's own `timeout-minutes`, which fails the job.

### 2. The gate declares the tree it holds the scan to

Every tracked `.py` file under `src` and `tools` must appear in the scanner's
`paths.scanned`. Those are the two trees `[tool.mypy] files` and
`[tool.coverage.run] source` already claim and `make scope` already holds to the
tree (ADR 0007), so a third tree of Python cannot appear without something
noticing.

`tests` is deliberately outside the claim, and stated rather than left to be
inferred from a passing run: the scanner's default ignore file drops test
directories before the gate sees anything, so claiming them would produce a gate
that fails every run for a reason that is not a defect.

### 3. It runs in CI, not in `make verify`

Exactly as `make secret-scan` is wired. The scanner is not in `uv.lock`, a clean
clone does not have it, and `--config auto` is a network call, while `make verify`
must stay the byte-for-byte gate `ci.yml` runs on a clean checkout. `make sast` is
the maintainer's entry point and `.github/workflows/security.yml` runs the same
program — the scanner's argv lives in `SEMGREP_ARGV` in the gate and nowhere else,
so the job cannot pass while the gate a maintainer runs scans something different.
The three states are covered by `tests/test_sast_gate.py` with recorded report
shapes and a stand-in scanner, which run inside `make verify` on a machine with
no semgrep installed, and `tests/test_gate_exit_contract.py` now drives this gate
into state 2 along with the other ten.

### 4. While this scanner is the SAST gate, no function or class here carries PEP 695 type parameters

`def f[T](...)` and `class C[T]:` are banned in `src` and `tools`. `TypeVar` is
how a generic is written here. The PEP 695 `type` alias form is unaffected and is
still used in four modules.

This is a real constraint on the code, imposed by a tool, so it is recorded here
rather than only in the `pyproject.toml` comment beside the `UP047` ignore, and
`tests/test_sast_gate.py::test_no_source_uses_pep695_type_parameters_on_a_function_or_class`
asserts it over the tracked tree — offline, inside `make verify`, without the
scanner. `UP046`, the same rule for a generic class, is not in the ignore list
today because no class here is generic; a future one needs `UP046` ignored for
this same recorded reason rather than a new argument.

The constraint is bounded by its cause, which is a fact about one tool at one
version: measured on 2026-09-05, semgrep 1.175.0 parses `def _enum[T: StrEnum]`
without complaint, while the CI container is pinned to 1.168.0, which is the
version the warning above came from. So the ban is not "this syntax is bad"; it
is "the gate cannot read it, and a gate that cannot read a safety module is worse
than the syntax is good". It is reviewable the day the pinned scanner parses it,
and the gate — not the ban — is what makes the next unparsable construct visible.

## Consequences

- A file the SAST parser cannot finish fails the security workflow by design,
  with a message naming the file, rather than by whichever exit code `--strict`
  happens to produce for the size of that run. This is what #114 asked for.
- The gate's clean line states its denominator: how many files were scanned and
  how many declared sources were covered. A green SAST check now names what it
  read, which is the invariant `docs/18-ASSURANCE-PROGRAM.md` drives at.
- The finding verdict moves from `--error` into a program in this repository. It
  is the same rule — any match fails — but it is now this repository's code that
  applies it, and its tests are the evidence. The fail-closed report reading is
  what keeps that from being a weakening: a report the gate cannot parse is a
  refusal, not a pass.
- The scan now runs without `--error` and without `--strict`, because both would
  fail the step before the gate could speak. An analysis error still fails, one
  state further along and by name.
- The job gained a `git config --global --add safe.directory` step. The container
  runs as a different user than the one that checked the tree out, and both the
  scanner's target selection and the gate's `git ls-files` read the repository
  through git.
- **Two properties of the CI container are asserted by the first run and by
  nothing in a checkout: that it carries `python3` and `git`.** The scanner is
  written in Python and limits itself to git-tracked files, so both are strongly
  implied and neither is proved here. If either is absent the job fails loudly on
  its first execution rather than passing quietly, which is the right direction
  for a gate to be wrong in.
- **What this gate still cannot see**, measured rather than assumed: with a
  syntax error at the end of a file and nothing after it, semgrep 1.175.0
  reported no error at all and `~100.0%` parsed lines, while the same error with
  code following it produced the `PartialParsing` entry this gate reads. So the
  gate detects an unparsable construct that has code after it — the case in
  `validation.py`, and the case that matters, since the unread remainder is the
  exposure — and cannot detect one that silently truncates a file's tail. Stated
  because a gate that does not say what it misses is the thing this repository
  keeps finding.
- Three gates now sit outside `make verify` rather than two, and `CONTRIBUTING.md`
  states the count that `make claims` re-derives from its own table.

## Rejected alternatives

- **Keep `--strict` and treat exit 3 as the detector.** It is what produced the
  bug: the same tree, the same construct, green on `main` and red on a branch.
  Nothing in the flag's contract promises that a partial parse reaches it, and
  the run this repository actually depends on is the one where it did not.
- **`--max-target-bytes 0` / a `--verbose` parse-rate threshold.** Both are knobs
  on how much the scanner reports, not on whether anything reads the report. The
  defect was never the scanner's honesty; it was that nothing was listening.
- **A `.semgrepignore` entry or `# nosemgrep` on the generic function.** ADR 0004
  refused both for a real finding, and they are worse here: suppressing the
  warning would leave the module unscanned *and* silent.
- **Treat a rule timeout as an acceptable warning and pass over it.** It is a
  rule that did not read a file, reported as such, which is the exact thing this
  ADR is about. Excusing it would have been a rule for this gate and a different
  rule for everything else. `--timeout 0` removes the state instead, at no
  measured cost.
- **A ruff rule, or a grep, banning `def name[` and calling it done.** That bans
  the one construct already known to break the parser and detects nothing else —
  which is exactly the position #114 says is not good enough. The syntax ban is
  worth having as an offline, fast assertion of a known limit, so it is kept, but
  it is the second line and not the gate.
- **Put `make sast` inside `make verify`.** It needs semgrep and the network.
  `make verify` is the gate a clean clone can run and the one `ci.yml` runs
  byte for byte; adding a target that cannot run there would make the merge gate
  unrunnable offline for everyone in order to move one job.
- **Have the workflow keep its own semgrep command and pipe it into the gate.**
  Two copies of one invocation, which is the drift the pip-audit job was changed
  to avoid in the same file. The argv lives in the gate.
- **Have the gate parse the scanner's human-readable output.** Cheaper to write
  and unbounded to maintain: the banner text is not a contract, and a gate whose
  detection depends on a `[WARN]` string is the same fragility one layer over.
