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
the fixtures under [`fixtures/`](fixtures/) and [`tests/`](tests/); if a fixture you
need doesn't exist, add a synthetic one rather than reaching for anything real. A
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

A change merges when the full gate is green. Reproduce it locally with:

```sh
make verify
```

`make verify` runs sync + lint + format-check + typecheck + test/coverage + audit +
hygiene + publication sweep — the exact same target `ci.yml` invokes, on the same pinned
(`uv sync --locked`) toolchain, so green locally means green in CI.

| Gate | Command | What it checks |
| --- | --- | --- |
| Lint | `make lint` | `ruff check`: correctness, security (bandit rules), import hygiene, complexity ≤10 |
| Format | `make format` | `ruff format --check` |
| Types | `make typecheck` | `mypy --strict` over `src` |
| Tests + coverage | `make test` | pytest; branch coverage ≥90% overall, ≥95% on safety-critical modules |
| Dependency audit | `make audit` | `pip-audit` against the locked environment |
| Hygiene | `make hygiene` | no TODO/FIXME/HACK in tracked files under `src`/`tests`; no stray tool config within two path segments of the root. Exit 1 on a finding, exit 2 when it could not examine anything, and the clean line says how many files it read. |
| Publication sweep | `make publication-sweep` | nothing unpublishable in tracked files: no personal filesystem path, no internal hostname, no pointer to a repository a reader cannot open, no relative link escaping the repository. Add `publication-sweep: allow` to a line only with a reason in review. |

One gate sits outside `make verify`, because it needs a tool a clean clone does
not have and `make verify` must stay exactly what CI runs:

| Gate | Command | What it checks |
| --- | --- | --- |
| Full-history secret scan | `make secret-scan` | gitleaks over every ref, every object in the object database (including unreachable ones and every commit message), and the working tree. Needs gitleaks 8.30.1 on `PATH` (`brew install gitleaks`); CI and the release pipeline run this same target. |

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
- CI must be green (or, while GitHub Actions is unavailable on this account,
  attach the local `make verify` output to the PR).
