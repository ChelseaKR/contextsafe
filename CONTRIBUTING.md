# Contributing to ContextSafe

Thank you for considering a contribution. ContextSafe validates and evaluates
**synthetic** patient fixtures for transgender and nonbinary patient-safety release
gating, so contributing carries one obligation beyond the usual: **never let real
patient data, PHI, or production system details reach the repository** — not in a
fixture, a test, an issue, a commit message, or a screenshot.

If you have not yet, read [`README.md`](README.md) for what the project is and why,
and [`SECURITY.md`](SECURITY.md) for how to report a vulnerability.

## The synthetic-only rule (read this first)

Every fixture is synthetic by construction, and the code enforces this fail-closed
(synthetic namespaces, PHI canaries, direct-identifier checks). Reproduce bugs with
the fixtures under
[`src/contextsafe/fixtures/reference/`](src/contextsafe/fixtures/reference/) and
[`tests/`](tests/); if a fixture you need doesn't exist, add a synthetic one rather
than reaching for anything real. A
pull request that violates this rule will be closed and, if needed, the history
scrubbed.

## Getting set up

ContextSafe targets Python 3.12+ and uses [`uv`](https://docs.astral.sh/uv/) for a
reproducible, locked environment:

```sh
uv sync --locked
```

`--locked`, not `--frozen`: `--frozen` installs a lockfile that has drifted from
`pyproject.toml` and still exits 0, so it cannot gate drift. `--locked` exits 1 instead.

Optionally install the pre-commit hooks (they run the same ruff/mypy/gitleaks as CI):

```sh
uvx pre-commit install
```

## The merge gate

Every gate in this repository uses the same three exit codes, and they are
three because two is how a gate lies: **0** it examined what it claims to and
found nothing, **1** it examined and found something, **2** it did not examine,
so it has no answer. A gate that cannot run fails differently from a gate that
failed. See [ADR 0008](docs/adr/0008-one-exit-code-contract-for-every-gate.md).
Three states, not necessarily three codes: a program that takes arguments may
also refuse to start, and those exit **64** — the CLI's `EXIT_USAGE_ERROR` — for
a usage error. That is not a fourth answer about anything examined; it says the
run never began, which is why it is kept out of the three.

A change merges when the full gate is green. Reproduce it locally with:

```sh
make verify
```

`make verify` is the exact same target `ci.yml` invokes, on the same pinned
(`uv sync --locked`) toolchain, so green locally means green in CI. Its stages are the
rows of this table and nothing else — the sentence that used to list them separately
was removed rather than corrected, because two hand-maintained lists of the same set
drift apart, and both of them had. `make claims` re-derives this table's command column
from the `verify` target in the `Makefile` and fails when they disagree.

| Gate | Command | What it checks |
| --- | --- | --- |
| Locked sync | `make sync` | `uv sync --locked`, which exits 1 on lockfile drift where `--frozen` would install the stale lock and exit 0 |
| Lint | `make lint` | `ruff check`: correctness, security (bandit rules), import hygiene, complexity ≤10 |
| Format | `make format` | `ruff format --check` |
| Types | `make typecheck` | `mypy --strict` over `src` |
| Tests + coverage | `make test` | pytest; branch coverage ≥90% overall, ≥95% on safety-critical modules |
| Dependency audit | `make audit` | `pip-audit` against the locked environment, through `tools/audit_gate.py`, which separates the three states pip-audit's two exit codes ran together: exit 1 is an advisory the service reported, exit 2 is a service that did not answer, a report that could not be read, or a run that audited nothing. A transient failure is retried with backoff first. This stage still needs the network, so `make verify` is not runnable offline; what it no longer does is report an unreachable advisory service as the same failure as a vulnerability. See [ADR 0011](docs/adr/0011-dependency-audit-reachability-in-the-merge-gate.md) |
| Hygiene | `make hygiene` | no TODO/FIXME/HACK in tracked files under `src`/`tests`/`tools`; no stray tool config within two path segments of the root. Exit 1 on a finding, exit 2 when it could not examine anything, and the clean line says how many files it read and how many exemptions it honored. |
| Scope | `make scope` | every tracked Python file is inside the trees each analysis claims, read from `[tool.mypy] files`, `[tool.coverage.run] source`, and the marker scan's own `MARKER_ROOTS`. A file nobody claims, a claim with nothing under it, and a declared exception that excuses nothing are each a finding; exit 2 when a claim cannot be read. |
| Published patterns | `make patterns` | every `pattern` in every `.json` file under `schemas/`, at any depth, against the constants the runtime compiles: equal to one, derived from named ones by a function the gate recomputes, or declared as having none with the reason printed on every run. A published pattern in none of the three is a finding, and so is a derivation or declaration that matches nothing published. Exit 2 when it read no contract, and when a file sits under `schemas/` that it can neither read as a contract nor place as documentation, because a grammar gate that examined nothing — or that skipped a file by the shape of its name — is not a clean one. The clean line names how many contracts it read. |
| Publication sweep | `make publication-sweep` | nothing unpublishable in tracked files: no personal filesystem path, no internal hostname, no pointer to a repository a reader cannot open, no relative link escaping the repository, and no source it listed and then could not read. Add `publication-sweep: allow` to a line only with a reason in review. |
| Internationalization | `make i18n` | catalog parity, placeholder parity, message quality, and review consistency across the shipped locale catalogs; a machine-translated string may never reach a surface claiming human review; no hardcoded string on the pseudolocalized page, and the pseudolocale itself measured for expansion, diacritics, and placeholder parity. Fails rather than passing when it examined no catalog. |
| Accessibility | `make a11y` | renders the receipt page in every shipped locale and checks structural validity, WCAG 2.2 contrast computed from the stylesheet, no colour-only status encoding, print (nothing hidden, headers repeating, no finding orphaned from its reason), and evidence minimization (only catalog text and pointer-named receipt values on the page, against a payload hash it recomputes). Fails rather than passing when it examined no page. `make a11y-full` adds axe-core and is a separate CI job because it needs the node harness. |
| Claims | `make claims` | figures and lists the documents state, re-derived from the repository: this table against the `Makefile`, the ADR index against `docs/adr/`, the coverage floors against `make test`, the contract count against `schemas/`, and the standards table against the gates `verify` actually runs. Prints what it cannot see on every run. |

A marker the hygiene gate must not report — the rule naming the words it bans is
the case that exists — is exempted with `hygiene: allow` on the same line,
**followed by a reason**. An exemption without one is a finding, and every
honored exemption is printed on every run so the mechanism stays countable. See
[ADR 0005](docs/adr/0005-hygiene-marker-exemptions.md).

Three gates sit outside `make verify`. Two need a tool a clean clone does not
have, and `make verify` must stay exactly what CI runs; the third costs minutes
of its own on top of a merge gate that was measured at about four of them on
2026-09-05 (see "What the gate costs, measured" in
[docs/18-ASSURANCE-PROGRAM.md](docs/18-ASSURANCE-PROGRAM.md)):

| Gate | Command | What it checks |
| --- | --- | --- |
| SAST | `make sast` | Semgrep over the tree, with the verdict read from the scan's JSON rather than from its exit code. Exit 1 on any finding; exit 2 on a file the parser could not finish, on a tracked `.py` under `src` or `tools` that is absent from the scanner's own list of scanned files, and on every way of not getting a scan at all — scanner absent, scan incomplete, no report, or a report in a shape the gate does not understand. A partial parse used to be a warning the job stayed green over, which left a safety module scanned in part and reported clean. The scan runs with no per-rule timeout, so a rule that gave up on a file cannot be mistaken for one that read it, and the verdict does not track how loaded the machine is. Needs semgrep 1.168.0 on `PATH` and the network, since `--config auto` resolves the registry ruleset; `.github/workflows/security.yml` runs the same program, in a container pinned to that same version, on every pull request. The version is part of the gate: 1.168.0 is the parser that stops at a PEP 695 generic function and a later one does not, so a scan by any other version is exit 2 naming both, and `ALLOW_SEMGREP_VERSION_DRIFT=1` accepts one with a warning — the same pin, and the same escape hatch, as the secret scan below. Its states are covered by `tests/test_sast_gate.py`, which drives them with recorded report shapes and a stand-in scanner and therefore runs without semgrep installed. See [ADR 0012](docs/adr/0012-sast-partial-parse-and-the-syntax-it-forbids.md), which also records the one syntax this constraint forbids: no PEP 695 type parameters on a function or class while this scanner is the gate. |
| Mutation evidence | `make mutants` | changes one operator or constant in a declared safety module and requires the suite to fail. Branch coverage says a line ran; this says a change to it would be noticed. Stdlib only, writes nothing into the working tree, and takes about two minutes, which is why it is not in `verify`. Exit 1 on a survivor, exit 2 when it produced no evidence. `.github/workflows/mutation.yml` runs it weekly and on any pull request touching the package, the suite or the gate, so it is no longer evidence that exists only when somebody remembers to produce it. See [ADR 0009](docs/adr/0009-mutation-evidence-over-declared-safety-modules.md). |
| Full-history secret scan | `make secret-scan` | gitleaks over every ref, every object in the object database (including unreachable ones and every commit message), and the working tree. Needs gitleaks 8.30.1 on `PATH` (`brew install gitleaks`); CI and the release pipeline run this same target. Exit 1 on a finding; exit 2 when gitleaks is absent, is not the pinned version, cannot read an object it enumerated, or enumerated zero blobs. Its three states are covered by `tests/test_gate_exit_contract.py`, which drives it with a stand-in scanner and therefore runs without gitleaks installed. |

`make package` is not a gate: it builds the sdist and wheel, exports the
CycloneDX SBOM from the locked graph, and lists the wheel's contents. The
judgment over that output is `tools/fresh_install_gate.py`, which
`.github/workflows/package.yml` runs on Ubuntu, macOS and Windows and which a
maintainer runs with `uv run python tools/fresh_install_gate.py --dist dist`:
`pip install --no-index` into an empty venv, the README Quickstart from outside
the checkout, and the receipt document against the digest
`tests/test_determinism.py` pins. Exit 1 on a finding; exit 2 when the wheel was
not examined. `tests/test_wheel_quickstart.py` drives its real path on every
`make verify`.

## Design constraints that reviews enforce

- **Fail closed.** Missing or ambiguous evidence is indeterminate, never pass.
- **Determinism.** Same inputs, same rule set, same receipt — byte for byte.
- **Boundary honesty.** Compiled artifacts stay unsigned and non-executable until a
  real authorization chain exists; do not add code that pretends otherwise.
- **Consequential decisions get an ADR** in [`docs/adr/`](docs/adr/) (see
  ADR 0000 for the format).

## Commits and PRs

- Keep changes small and single-purpose; update `CHANGELOG.md` under
  `## [Unreleased]` for anything user-visible.
- Stage explicit paths (never `git add -A`).
- CI must be green. `ci.yml` and `security.yml` both run on every pull request,
  including a documentation-only one: `ci.yml` carried `paths-ignore` for
  `**.md`, `docs/**` and `LICENSE` until 2026-09-04, which meant the four
  `verify` stages that exist to catch documentation drift — `claims`,
  `publication-sweep`, `hygiene` and `i18n` — never saw a documentation change.
  `mutation.yml` runs on top of those when a pull request touches the package,
  the suite or the mutation gate. None of these is a *required* status check;
  see `DEFINITION_OF_DONE.md` for what that does and does not mean.
