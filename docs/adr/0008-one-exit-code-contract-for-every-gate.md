# ADR 0008 — One exit-code contract, and the gates that depend on an absent tool obey it

Status: accepted
Date: 2026-08-27
Decision owners: technical owner

## Context

Three states, and they are three because two is how a gate lies:

- **0** the gate examined what it claims to and found nothing;
- **1** it examined and found something;
- **2** it did not examine, so it has no answer.

`make hygiene`, `make publication-sweep` and `make scope` were built that way,
the first two on 2026-08-27 after `! rg ...` was found mapping "ripgrep is not
installed" onto "ripgrep found nothing".

The three gates that depend on a tool a clean clone does not have were not built
that way, and those are exactly the three where the distinction matters most.
An absent scanner is the failure most easily mistaken for a clean one. Measured
before this change:

| Gate | "did not examine" | exit |
| --- | --- | --- |
| `tools/secret-scan-full-history.sh` | gitleaks not installed | 127 |
| `tools/secret-scan-full-history.sh` | gitleaks at an unpinned version | 1 |
| `tools/secret-scan-full-history.sh` | an enumerated object it could not read | 1 |
| `tools/secret-scan-full-history.sh` | zero blobs enumerated | 1 |
| `tools/a11y_gate.py` | `--engines axe` with no node harness | 1 |
| `tools/a11y_gate.py` | a check that examined no pages | 1 |
| `tools/i18n_gate.py` | no catalog examined | 1 |

So a damaged object database and a leaked credential were the same exit code. A
missing node harness and a contrast failure were the same exit code. Every one
of those is a failure, which is better than the alternative; none of them was
distinguishable from the failure the reader would assume.

`tools/secret-scan-full-history.sh` also had no test of any kind. It is the one
gate here written in shell, and the one whose external dependency is not in
`uv.lock`, so nothing exercised any of its states.

## Decision

**The contract is 0 / 1 / 2, for every gate, and it is documented in
`CONTRIBUTING.md` rather than inferred from each program.**

- `tools/i18n_gate.py` raises `GateUnavailable` where it used to append a
  `no-catalogs` finding, and returns 2. A requested locale with no published
  catalog is the same state and the same code.
- `tools/a11y_gate.py` gains `UNAVAILABLE_RULES` and `exit_code()`. Four rules
  name a failure to run rather than an accessibility defect:
  `engine-unavailable`, `engine-not-executed`, `engine-examined-nothing`,
  `check-examined-nothing`. Any of them is exit 2. **A run that also has real
  findings is still exit 2**, because those findings were gathered without every
  requested engine and a reader cannot tell from them what is missing.
- `tools/secret-scan-full-history.sh` returns 2 for an absent gitleaks (was
  127), an unpinned version, an object it enumerated and could not read, and
  zero blobs enumerated. A gitleaks finding stays 1, which is gitleaks' own
  `--exit-code 1`.

**The contract is asserted, not described.** `tests/test_gate_exit_contract.py`
drives all five Python gate programs into a state where they examined nothing
and requires exit 2 from each. `test_every_gate_program_is_covered_by_this_contract`
compares the case list against `tools/*.py`, so a gate added later that is not
in the table fails the suite rather than quietly sitting outside the contract.

**The shell script is tested through a stand-in gitleaks.** The real binary is
not in `uv.lock` and a clean clone does not carry it, which is why the gate sits
outside `make verify` in the first place. A fixture writes a small executable
that answers `version` and returns a chosen code from `detect`, which gives all
three states on a machine with no gitleaks installed:
`test_the_secret_scan_never_maps_an_absent_scanner_onto_a_finding` asserts the
three codes are three distinct values. Those tests run inside `make verify`,
so CI exercises the script's failure modes on every push even though CI's real
gitleaks run happens in a different workflow.

## Consequences

- **`make secret-scan` exits 2 instead of 127 when gitleaks is not installed,
  and 2 instead of 1 for every other failure to scan.** This is a deliberate
  exit-code change on failure paths. No workflow branches on the specific value;
  `security.yml` and `release.yml` both run the target and fail on any non-zero.
  A caller chaining on `$?` will see it.
- `make a11y-full` exits 2 rather than 1 when the node harness is missing. The
  `accessibility` CI job installs the harness first and fails either way, so its
  behaviour is unchanged; what changes is that a person reading the exit code
  can now tell which failure they have.
- The i18n gate loses its `no-catalogs` rule id. Nothing consumed it but the
  test that asserted it, which now asserts the refusal.
- The secret scan has tests. It had none, and the three-state proof runs without
  the tool it gates on.
- Semgrep is out of this contract's reach. ADR 0004 chose
  `semgrep scan --config auto --error --strict` precisely so that a finding and
  an analysis error both fail rather than either being swallowed, and
  `security.yml` fails on any non-zero. Whether semgrep distinguishes the two by
  exit code is a property of an external tool this repository cannot verify
  offline, since semgrep is not in `uv.lock`, so no claim is made about it here.
- Four gate programs now agree on 2, and one shell script does. That is a
  convention held by tests rather than by a shared library, because the shell
  script cannot import a Python constant and three integers are not worth a
  package boundary. The test is what makes it real.

## Rejected alternatives

- **A shared `tools/gate_exit.py` with the three constants.** The gate programs
  are standalone scripts run as `uv run python tools/x.py`, so importing a
  sibling means path manipulation in five files, and the shell script could not
  use it at all. The behavioural test covers every one of them, including the
  script.
- **Leave exit 127 for an absent gitleaks.** It is the shell convention for
  "command not found" and it is distinctive. Rejected because a reader of this
  repository learns one contract, not one contract and an exception, and 127 is
  indistinguishable from the shell's own 127 for a mistyped invocation.
- **Exit 1 when a11y has both real findings and an absent engine**, on the
  grounds that a genuine defect is the more actionable news. Rejected: the
  finding list is incomplete and nothing in it says so, which is the same defect
  as a clean line over content nobody read.
- **A CI job that removes the tool and asserts the job fails.** That is the
  obvious proof and it needs a GitHub Actions run to observe. The stand-in
  gitleaks gives the same evidence inside `make verify`, which CI already runs,
  and does not add a workflow nobody has watched execute.
