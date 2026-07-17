# Security policy

ContextSafe's current code is an offline, deterministic validator and evaluator for
**synthetic** patient fixtures. It is designed to never touch real patient data —
so the most important security property here is that the fail-closed boundaries
(synthetic-only namespaces, non-production attestations, PHI canaries,
direct-identifier checks) actually hold. Security here is inseparable from patient
safety: a bypass of those boundaries is a first-class vulnerability even if it
"only" affects test data.

## Supported versions

This is a pre-1.0 implementation slice; there is no tagged release yet. Security
fixes land on `main` and, once one exists, the latest tagged release.

| Version | Supported |
| ------- | --------- |
| `main` / latest tag | ✅ |
| older tags | ❌ |

## Reporting a vulnerability

**Email ckellyreif@gmail.com** with `contextsafe security` in the subject — this is
the primary channel today: the repo is private, and GitHub's private vulnerability
reporting is not available on a private free-plan repo. Expect an acknowledgement
within a few days; this is a volunteer-scale project, so please be patient and do
not disclose publicly until a fix is available.

### Redaction-safe reporting (please read)

**Never include real patient data, real PHI, or real production system details in a
report.** Every fixture in this repository is synthetic by construction; reproduce
issues with the synthetic fixtures under `fixtures/` and `tests/`, or describe the
*shape* of the flaw ("the evidence preflight accepts a payload containing X")
without real values.

## What we consider a vulnerability

In addition to the usual (code execution, injection, path traversal, secret
exposure), the following are **first-class** security bugs in ContextSafe:

- **Any path by which the evidence boundary accepts non-synthetic or
  identifier-bearing content** it is specified to reject — PHI canaries,
  direct-identifier patterns, prohibited fields, namespace pins, the one-MiB limit,
  or the exact field allowlist (`schemas/contextsafe-evidence-source-v1.schema.json`).
- **Any path by which `evidence preflight` writes** anything beyond its documented
  safe success metadata — it is specified to create no workspace, copy, index, or
  log.
- **Any way to make a compiled pack claim more authority than it has** — e.g. an
  artifact that does not say `signature_status: not_verified` and
  `executable: false` (see `docs/adr/0002-unsigned-compilation-before-authorization.md`).
- **Any nondeterminism or hash-integrity break in receipts or the evidence store** —
  duplicate index states, unverified objects surviving recovery, or receipts whose
  input/rule-set/result hashes do not cover what they claim
  (see `docs/adr/0003-recoverable-evidence-commit.md`).
- **Any bypass of fail-closed behavior** — missing or ambiguous evidence evaluating
  to anything other than indeterminate.

See `docs/06-SECURITY-PRIVACY-THREAT-MODEL.md` for the full threat model.

## Our commitments

- Boundary-bypass and fail-closed regressions are fixed with the highest priority.
- We credit reporters who want credit, and respect those who want anonymity.
- The dependency surface is deliberately tiny (zero runtime dependencies; dev tools
  locked in `uv.lock`) and scanned: pip-audit runs inside `make verify` locally and
  in CI, gitleaks runs in pre-commit and CI, and Semgrep SAST runs in CI.
