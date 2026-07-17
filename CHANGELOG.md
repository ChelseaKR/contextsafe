# Changelog

All notable changes to ContextSafe are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project has no tagged
release yet, so everything to date lives under Unreleased.

## [Unreleased]

### Added

- V1 planning corpus (`docs/00`–`16`): PRD, service design, architecture, data and
  evidence model, security/privacy threat model, governance, test strategy,
  operations, GTM, roadmap, backlog, risk register, and release checklist.
- Iteration 1: strict versioned case and observation-set schemas; separately typed
  GI, RSG, SPCU, name-to-use, and pronoun values; fail-closed cross-concept
  rejection; pure exact-match evaluator (missing/ambiguous evidence is
  indeterminate); deterministic value-minimized JSON receipts; offline `validate`
  and `evaluate` CLI commands with a synthetic reference fixture.
- Iteration 2: strict pack envelope, deterministic unsigned compiler with semantic
  component hashes and lifecycle/withdrawal checks; strict engagement and
  execution-plan contracts with fail-closed non-production attestations, host
  allowlisting, and hash pinning.
- Iteration 3: canonical JSON evidence boundary envelope with field allowlist,
  namespace pins, PHI canaries, and direct-identifier checks; read-only
  `evidence preflight`; recoverable two-pass persistence into a SHA-256 object
  store with an update/delete-protected SQLite index.
- Standards-conformance baseline (2026-07-16 sweep): LICENSE (Apache-2.0),
  SECURITY.md, CONTRIBUTING.md, CITATION.cff, CHANGELOG, pre-commit config,
  Semgrep/gitleaks/pip-audit security workflow, tag-triggered release workflow,
  ADR log seed (existing ADRs relocated from `docs/decisions/` to `docs/adr/`),
  docs/I18N.md declaration, and a README Standards Conformance table.
