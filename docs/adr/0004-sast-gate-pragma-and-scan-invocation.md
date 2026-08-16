# ADR 0004 — The SAST gate: PRAGMA header statements, and a scan that cannot skip itself

Status: accepted
Date: 2026-08-15
Decision owners: technical owner

## Context

SEC-07 of the vendored security standard makes Semgrep an AUTO-GATE: zero unwaived
HIGH/CRITICAL findings at merge. The gate is `.github/workflows/security.yml`, job
`semgrep`. It has never once been green. All fourteen `main` runs of that workflow
failed, from `29565667759` on 2026-07-17 through the scheduled run `31301838938` on
2026-08-09. There is no first green run to regress from.

Two separate defects were behind that, and they point in opposite directions.

### Defect 1 — four blocking findings on the evidence index header

Reproduced locally against the same registry config (1074 rules, 72 targets, matching
the CI summary): four blocking findings, two rules firing on each of two adjacent
lines in `src/contextsafe/evidence_store.py`.

- `python.lang.security.audit.formatted-sql-query.formatted-sql-query`
- `python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query`

Both lines set the evidence index's format identity as the store is created:
`PRAGMA application_id` and `PRAGMA user_version`, each interpolating a module-level
integer constant into an f-string passed straight to `execute`.

Assessing the four on their merits:

- Neither interpolated value is reachable from caller input. `_INDEX_APPLICATION_ID`
  and `_INDEX_USER_VERSION` are module constants, never reassigned, never derived from
  an argument, environment variable, or file. There is no injection here.
- The `formatted-sql-query` findings are nonetheless true positives *on shape*. A
  string built at the point of execution is the construct the rule exists to find, and
  the rule cannot know the operand's provenance.
- The two `sqlalchemy-execute-raw-query` findings are additionally misattributed.
  SQLAlchemy is not a dependency of this project — it appears nowhere in
  `pyproject.toml` or `uv.lock`. The rule matched on the method name `execute` alone,
  and its remediation advice (TextualSQL, the ORM) is inapplicable.

The obvious remediation is unavailable: SQLite does not accept bound parameters in a
PRAGMA statement. `PRAGMA user_version = ?` is a syntax error, which
`test_pragma_header_sql_is_a_fixed_integer_assignment` now asserts directly so the
constraint is recorded in the suite rather than in a comment.

An inline coercion does not help either. `execute(f"... {int(value)}")` was measured
against both rules and still fires: these are shape matchers, not taint analysis.

### Defect 2 — the same gate passed every pull request without scanning anything

While confirming defect 1, the `semgrep` job was found to be green on all three open
pull requests. It was not finding the code clean. It was not reading it.

`semgrep ci` resolves a diff baseline on a `pull_request` event and shells out to
`git fetch origin --force --depth=1 <head-sha>`. This repository is private and the
checkout sets `persist-credentials: false`, so that fetch failed with
`fatal: could not read Username for 'https://github.com'`. Semgrep aborted before
scanning, and its default `--suppress-errors` converted the aborted run into exit 0:
"There were errors during analysis but Semgrep will succeed because there were no
blocking findings."

The job log for run `31872289010` contains a scan environment banner and then the
fetch failure. It has no scan summary at all — no rule count, no target count, no
findings line. Nothing was inspected.

So the control failed in both directions at once. On `main` it was permanently red for
a reason that was not a vulnerability, which trains a reader to ignore it. On every
pull request — the only place the gate can actually block a merge — it reported a
green SAST check over zero files. A genuine HIGH finding introduced by a pull request
would have passed.

## Decision

**Defect 1.** Render both header statements once, at module scope, next to the
constants they encode and alongside the other `_*_SQL` statements this module already
executes:

- `_SET_APPLICATION_ID_SQL` and `_SET_USER_VERSION_SQL` are built with the `:d`
  conversion, which accepts only an integer and can emit only digits and an optional
  sign. No string can reach the statement even if a future edit made the constants
  configurable.
- `_publish_new_database` executes those constants. No string is constructed at the
  call site.
- `test_pragma_header_sql_is_a_fixed_integer_assignment` pins the exact rendered text
  of both statements, asserts each matches `PRAGMA [a-z_]+ = -?\d+`, and asserts that
  SQLite rejects the parameterized form. Drift in either direction fails the suite.

No waiver was filed, no `.semgrepignore` was added, and no `# nosemgrep` was written.
There is nothing left to suppress: the registry auto config now reports 0 findings.

Be precise about why the rules stop firing. The code was already safe; the interpolated
values were never caller-controlled. What changed is that the dynamic construction no
longer sits on the `execute` call, and that the integer-only rendering and the exact
statement text are now enforced by a test instead of by inspection. The rules stop
matching because the shape they match is gone.

**Defect 2.** Replace `semgrep ci --config auto` with
`semgrep scan --config auto --error --strict`.

- `semgrep scan` needs no diff baseline and no git credential, so `push`,
  `pull_request`, and the weekly schedule all run the identical full scan.
- `--error` exits non-zero on findings.
- `--strict` exits non-zero on an analysis error. A scan that cannot run can no longer
  report success — the specific failure mode that produced defect 2.

Verified locally against the pre-fix tree: the replacement invocation exits 1 and
reports "Findings: 4 (4 blocking)", so it is at least as strict as the invocation it
replaces. Against the fixed tree it exits 0 with 0 findings over 72 targets.

## Consequences

- SEC-07 has a gate that inspects the whole tree on every event and blocks a merge.
  For the first time in this repository, a green SAST check means something was read.
- Full-scan-on-pull-request is slower than a diff scan and will surface a pre-existing
  finding on an unrelated pull request. That is the intended trade for this repository:
  it is small (72 targets, 28 seconds), and a gate that only ever examines the diff
  cannot notice that `main` is already carrying a finding.
- `--strict` will fail the job on an upstream registry or parse error, not only on a
  vulnerability. This is deliberate. The alternative is the behaviour being replaced.
- Semgrep's registry classification of blocking versus non-blocking findings no longer
  applies; `--error` treats any finding as a failure. The tree is at 0 findings today,
  so this costs nothing now and can be revisited with `--severity` if it becomes noisy.
- A genuine Lob-style detector false positive in future should be handled the way
  SEC-10 requires — a dated `.semgrep-waivers.yml` entry with a reason and an expiry —
  rather than by loosening these flags.

## Rejected alternatives

- **Parameterize the PRAGMA.** Not available. SQLite rejects bound parameters there,
  and the suite now asserts it.
- **Wrap the value in `int()` at the call site.** Measured; both rules still fire. It
  would also have left the misleading impression that a cast satisfied the linter.
- **Waive the four findings.** Available under SEC-10, and legitimate for the two
  SQLAlchemy findings, which are pattern noise from a framework this project does not
  use. Rejected because the `formatted-sql-query` pair is a fair reading of the code as
  written, and a fix that removes the construct is better than an expiring exception
  that a reader has to look up.
- **`# nosemgrep` at the two lines.** Same objection, with less visibility: an inline
  comment carries no expiry and no reviewer.
- **Keep `semgrep ci` and add `fetch-depth: 0`.** Might restore the baseline, might
  not — semgrep may run the fetch unconditionally, and the outcome cannot be verified
  outside GitHub Actions. `semgrep scan` removes the baseline machinery instead of
  betting on it.
- **Keep `semgrep ci` and add `--no-suppress-errors` alone.** Turns the silent pass
  into a loud failure, which is better, but leaves pull requests permanently red for a
  credential problem rather than scanning them.
