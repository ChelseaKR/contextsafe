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

**Use GitHub's private vulnerability reporting**, on this repository's Security
tab, or directly at
<https://github.com/ChelseaKR/contextsafe/security/advisories/new>. The report
is visible only to the maintainer, it stays attached to the repository, and it
gives you a private thread to work in until there is a fix.

That is the whole channel, on purpose. This policy used to publish a personal
email address, because private vulnerability reporting is not offered on a
private repository and there had to be *some* way to reach a human. A published
address is a permanent invitation to every scraper on the internet, and it is
worse than that here: this is a trans-health project, and the maintainer is a
named individual. The channel should not be one that costs her anything to
leave open.

If the reporting form is unavailable to you for any reason, open a public issue
that says only that you have a security report and asks for a private channel —
**no details, no reproduction, no affected paths.** You will get a private
thread back. Do not put the finding itself in a public issue.

Expect an acknowledgement within a few days. This is a volunteer-scale project,
so please be patient, and please do not disclose publicly until a fix is
available.

### Redaction-safe reporting (please read)

**Never include real patient data, real PHI, or real production system details in a
report.** Every fixture in this repository is synthetic by construction; reproduce
issues with the synthetic fixtures under `src/contextsafe/fixtures/reference/` and
`tests/`, or describe the
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
