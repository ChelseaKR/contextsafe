# Definition of done

A ContextSafe change is done only when every applicable item below is evidenced
in its pull request. `N/A` requires a short reason; an unchecked item is not an
implicit waiver. This definition governs iteration work and does not by itself
assert clinical approval, production readiness, or V1 completion.

## Scope and traceability

- The change has one bounded outcome linked to a requirement, backlog item,
  issue, or accepted decision.
- Acceptance criteria cover both intended behavior and the fail-closed or
  indeterminate path.
- The pull request names the affected ISO/IEC 25010 quality characteristic(s),
  what remains outside scope, and any operational assumption.

## Automated merge gate

- The GitHub `verify` check runs exactly `make verify` on Python 3.12 with the
  frozen `uv.lock` dependency graph, and is green before merge. It is not a
  *required* status check: the `protect-main` ruleset carries only the deletion
  and non-fast-forward rules, so nothing mechanically refuses a merge over a red
  or absent `verify`. Until that setting exists, this item is enforced by review,
  and saying so is the point — a gate named in a definition of done and absent
  from the repository is the defect class `docs/18-ASSURANCE-PROGRAM.md` tracks.
- Formatting and lint pass with Ruff, strict typing passes with mypy, and all
  tests pass with at least 90% overall branch coverage and 95% coverage across
  the safety modules named by the Makefile.
- The dependency audit and repository-hygiene checks pass without a suppressed
  failure or an unowned `TODO`, `FIXME`, or `HACK` in product code or tests.
- New behavior includes happy-path, malformed-input, boundary, and applicable
  safety-negative tests; deterministic output vectors change only when the
  reviewed contract changes.

## Clinical and community safety

- Inputs remain obviously synthetic and confined to non-production workflows;
  no patient data, patient-specific recommendation, clinical certification, or
  universal reference-range policy is introduced or implied.
- Gender identity, recorded sex or gender, sex parameter for clinical use,
  name to use, and pronouns remain distinct; identity, anatomy, clinical state,
  or a clinical rule is never inferred from another field.
- Missing, ambiguous, conflicting, or out-of-scope evidence remains
  indeterminate rather than becoming a pass.
- A rule or assertion that carries clinical or community judgment has named,
  dated provenance and the required independent clinical and trans-community
  approval before it is represented as governed content.

## Security, privacy, and evidence integrity

- Inputs stay strictly parsed and size-bounded, and rejected values, patient
  data, credentials, or unrestricted evidence do not enter logs or receipts.
- Canonicalization and receipts remain deterministic, value-minimized, and
  bound to their case, observations, rule-set version, and result hashes.
- New data fields document classification, lineage, retention, deletion, and
  correction implications before collection or publication.
- Workflow changes retain least-privilege permissions, immutable action SHAs,
  disabled checkout credential persistence, and clean `actionlint` and zizmor
  results; workflow and dependency-boundary changes receive code-owner review.

## Documentation and release impact

- README, schemas, fixtures, ADRs, safety language, and operating instructions
  are updated wherever behavior, boundaries, or assumptions changed.
- Compatibility, migration, rollback, correction, and receipt implications are
  explicit and tested where they are machine-checkable.
- Required clinical, community, interoperability, privacy, security,
  accessibility, and legal review artifacts are committed before the stage
  that depends on them.
- V1 release additionally requires every applicable gate and named approval in
  [`docs/15-V1-RELEASE-CHECKLIST.md`](docs/15-V1-RELEASE-CHECKLIST.md); a green
  implementation check cannot substitute for pilot or governance evidence.

Last reviewed: 2026-07-13. Recheck quarterly and whenever the product boundary,
clinical governance model, evidence contract, or merge gate changes.
