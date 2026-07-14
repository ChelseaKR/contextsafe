## Summary and bounded outcome

<!-- What changes, why is it needed, and which requirement, issue, backlog item, or accepted decision owns it? -->

## ContextSafe safety boundary

<!-- State what this PR does not claim or enable. ContextSafe's current implementation is an offline synthetic reference evaluator, not a clinically approved safety certification or patient-data pathway. -->

## Evidence, compatibility, and rollback

<!-- Describe contract, fixture, rule, evidence, receipt, migration, correction, or rollback effects. Write N/A with a reason when none apply. -->

## Verification

- [ ] `make verify` passes from the repository root.
- [ ] New behavior has happy-path, malformed-input, boundary, and relevant safety-negative tests.
- [ ] Deterministic receipt or canonical-output vectors were refreshed when applicable.
- [ ] Patient data, credentials, rejected input values, and unrestricted evidence do not enter logs or public receipts.
- [ ] Schema and public-contract compatibility are preserved or the version and migration path are documented.

## Review gates

- [ ] Acceptance criteria are linked above and the affected ISO/IEC 25010 characteristic(s) are named.
- [ ] Documentation, ADRs, operating instructions, and rollback guidance are updated where behavior changed.
- [ ] Workflow and dependency changes use least privilege, immutable action SHAs, and receive code-owner review.
- [ ] Clinical, trans-community, privacy, security, accessibility, legal, and interoperability review is requested where the change depends on that judgment.
- [ ] The root [definition of done](../DEFINITION_OF_DONE.md) is satisfied, or every unchecked item is explained below.

### Exceptions, N/A reasons, or bounded follow-up

<!-- An unchecked requirement is not silently waived. Explain N/A or link an owned follow-up with a clear boundary. -->
