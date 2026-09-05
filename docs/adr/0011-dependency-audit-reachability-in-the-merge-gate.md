# ADR 0011 — The dependency audit stays in the merge gate, and says when it could not reach the advisory service

Status: accepted
Date: 2026-09-04
Decision owners: technical owner

## Context

`make audit` was one line:

```make
audit:
	uv run pip-audit --skip-editable --cache-dir .cache/pip-audit
```

pip-audit answers with two exit codes. Everything that is not a clean audit is
exit 1: a real advisory, a bad argument, and a request to PyPI that never
completed. On pull request #61 (2026-09-05) the third of those failed the whole
merge gate on a change that had nothing to do with dependencies:

```
requests.exceptions.ConnectionError: ('Connection aborted.',
ConnectionResetError(104, 'Connection reset by peer'))
make: *** [Makefile:32: audit] Error 1
```

The same commit passed on a re-run. That is #74, and it is ADR 0008's subject
wearing a different hat: a gate with two states where it needs three cannot tell
"I looked and found nothing" from "I could not look", and every reader of a red
`audit` stage had to open the log and read a traceback to find out which failure
they had.

The second half of #74 is that `make verify` is not runnable offline, which sits
awkwardly beside every other stage: each of them needs nothing a clean clone
lacks, and the three gates that do need a tool (`secret-scan`, `a11y-full`,
`mutants`) are outside `verify` for exactly that reason.

## Decision

**The audit stays inside `make verify`, and it learns the third state.**

`make audit` runs `tools/audit_gate.py`, which runs the same pip-audit over the
same locked environment with the same `--skip-editable`, and classifies the
result:

- **0** — every non-editable distribution in the environment was audited and
  none carried an advisory;
- **1** — at least one did;
- **2** — the advisory service did not answer, the report was unreadable, or the
  run audited nothing. "Unreadable" reaches inside the report as well as at it:
  a dependency entry whose `vulns` field is not a list is a distribution whose
  advisory status was never established, and it refuses the whole report rather
  than counting as one more audited distribution with nothing against it. An
  empty `vulns` list is an answer and stays one.

**The report decides the state, not the exit code and not a string match on
stderr.** pip-audit writes its JSON report when the audit completes and writes
nothing when it does not; the observed ConnectionError path raises out of the
process leaving no report on disk, which was measured rather than assumed. So a
report that parses and names an advisory is exit 1 whatever the process exited
with, a parsed report with no advisory is exit 0 only if the process also exited
0, and everything else is exit 2. A non-zero exit over a clean-looking report is
an unexplained disagreement, and the fail-closed reading of a disagreement is
that nothing was established.

**A transient failure is retried before the gate answers 2** — three attempts,
doubling backoff. Retries apply only to the "did not examine" state: an advisory
is an answer, and asking the same service again is not a second opinion. The
pre-existing `--cache-dir .cache/pip-audit` is carried through unchanged, and
this ADR makes no claim about what a warm cache buys: the claim that would be
worth making — that a warm cache answers offline for the distributions already
audited — is unmeasured, and if it held it would be a path to exit 0 over
advisory data the gate did not re-fetch, which is the defect the pinned-snapshot
alternative is rejected for below.

**`security.yml` runs `make audit`** instead of its own copy of the pip-audit
command line. The two were identical strings in two files, which is the drift
shape this repository has a gate for; a CI job restating a gate's invocation can
pass while the gate a contributor runs does something else.

## Consequences

- **`make verify` is still not runnable offline, and this ADR does not claim
  otherwise.** An audit needs the advisory service. What changes is the failure:
  exit 2 and a sentence saying the service was not reached, instead of exit 1 and
  a traceback. The half of #74 that asked for an offline `verify` is refused
  here, because the only way to grant it is a stage that answers 0 without
  reaching the service, and a clean line over an unasked question is the exact
  defect this file exists to remove.
- **A sustained PyPI outage still fails a pull request.** It fails as "did not
  examine", which is what the state is. A single dropped connection — the
  observed #61 case — is now absorbed by the retry.
- `make audit` gains an exit code on the failure path: 2 where it was 1. No
  workflow branches on the specific value; `security.yml` and `release.yml` both
  fail on any non-zero. A caller chaining on `$?` will see it.
- The gate's three states are asserted in `tests/test_audit_gate.py` with a
  stand-in auditor, and its "did not examine" case joins the one contract in
  `tests/test_gate_exit_contract.py`. No test here touches the network: a test
  that reached PyPI would be the flake it is testing for.
- `tools/audit_gate.py` is a gate program with a `main(argv)`, so the derivation
  in `test_every_gate_program_is_covered_by_this_contract` requires it to be in
  the contract table rather than beside it.

## Rejected alternatives

- **Move `audit` out of `verify` into `security.yml`**, which is #74's own first
  preference and where a scheduled dependency audit already runs. Rejected
  because `make verify` is the merge gate a contributor reproduces locally, and
  a merge gate that cannot fail on a real advisory is not one. The dependency
  surface is this project's whole supply-chain claim (`dependencies = []`), and
  moving its check to a workflow makes "green locally" mean less than it says.
  The cost of keeping it is the offline case above, stated rather than hidden.
- **Cache the advisory database and audit against a pinned snapshot.** #74's
  third option, and the only one that would make `verify` genuinely offline.
  Rejected for now: a pinned snapshot is a second thing to keep fresh, and a
  stale one reports clean over an advisory published yesterday — a green mark
  over something nobody looked at recently, which is worse than a red one that
  says why. Revisit if the retry proves insufficient.
- **Classify by matching the auditor's stderr** for connection errors. Rejected:
  the set of strings a network stack can produce is not enumerable, and a gate
  whose correctness depends on an upstream library's error text is a gate that
  silently reclassifies on a dependency bump. The presence of a report is a fact
  about what the auditor did.
- **Retry forever, or retry an advisory.** The first turns an outage into a
  15-minute job timeout with no message; the second reports a vulnerability as
  a transient failure if the service happens to answer differently, which is
  fail-open in the direction that matters most.
