# Operations and SRE

Status: proposed v1 operating model  
Owner: service/operations lead  
Deployment: customer-controlled local runner; no hosted production service

## 1. Reliability model

V1 has no public uptime SLO because it has no always-on server. Reliability is measured as successful, deterministic local execution; pack/update integrity; receipt verifiability; and timely human support.

Safety properties have zero error budget:

- no accepted PHI canary;
- no mandatory assertion passing without evidence;
- no unsigned clinical approval represented as approved;
- no verified receipt after tampering;
- no withdrawn assertion represented as current when revocation data are available.

A breach stops releases until corrected and reviewed.

## 2. Service-level objectives

| SLI | SLO | Window |
|---|---:|---|
| Valid-run completion on supported reference environment | at least 99.5% excluding invalid input | rolling release suite |
| Deterministic normalized receipt | 100% across 3 reruns/supported OSes | each release |
| Receipt verification | 100% valid accepted; 100% tampered rejected | each release |
| Critical support acknowledgement during business hours | 4 business hours | quarterly |
| Confirmed pack/assertion safety defect withdrawal | 1 business day | per incident |
| Standard support acknowledgement | 1 business day | monthly |
| Pack update notice before effective use | 10 business days for non-emergency change | per release |
| Core source/review currency check | 100% by due date | monthly dashboard |
| Pilot receipt delivery after complete evidence | 3 business days | per run |

Business hours: Monday–Friday, 09:00–17:00 Pacific, excluding published US holidays. V1 is not 24/7 clinical support.

## 3. Supported environments

- Windows 11 current supported release.
- macOS 14 and newer supported releases.
- Ubuntu 24.04 LTS.
- Python runtime bundled or locked so customers do not resolve dependencies from the internet during a run.
- x86_64 and arm64 where release tests pass.

The exact support matrix is pinned per release. Unsupported environments may be evaluated during discovery but cannot receive an unqualified v1 receipt.

## 4. Installation and update

- Signed release artifact, checksum, SBOM, version, and offline installation guide.
- Customer verifies signature/checksum before install.
- Pack approvers use `contextsafe pack sign` and verify the three-role threshold with `contextsafe pack verify`; engagement-plan approvers use `contextsafe plan sign` and verify the customer-sponsor/ContextSafe-delivery-owner threshold with `contextsafe plan verify` before evidence import.
- No automatic update.
- Pack and runner can update separately only within declared compatibility.
- Previous minor version remains available for receipt reproduction.
- Emergency revocation list is signed and can be imported offline.
- Rollback restores the prior runner/pack; it does not rewrite receipts.

## 5. Observability

### Local structured events

- timestamp, event name, severity, command, run/case/assertion IDs;
- runner, pack, schema, mapping versions;
- duration, counts by status, error class;
- no clinical value, name, pronoun, message fragment, credentials, or raw path.

### Health report

The diagnostics command reports:

- platform and supported-version status;
- file permissions and disk space;
- database integrity;
- pack/schema/signature validity;
- expected fixture smoke test;
- revocation-list age;
- locale catalog validity.

It emits a shareable redacted bundle. Raw evidence is never in the bundle.

### No telemetry

V1 sends no usage, crash, or analytics telemetry. Support metrics come from engagement logs and customer-approved redacted summaries.

## 6. Runbook: standard execution

1. Verify release signature and compatibility.
2. Confirm the dual-signed non-production plan, synthetic namespace, and owners.
3. Run diagnostics and plan validation.
4. Execute one dry-run case through cleanup.
5. Import observations and confirm preflight.
6. Run complete pack; inspect coverage before outcomes.
7. Review fail, blocked, and indeterminate results.
8. Assign dispositions; obtain both customer-clinical-owner and ContextSafe-clinical-chair review signatures for every accepted clinical residual risk; render/sign receipt.
9. Verify receipt on a second environment.
10. Cleanup synthetic records and temporary evidence.
11. Record closeout and next rerun.

Abort on production endpoint, namespace mismatch, suspected PHI, stale mandatory oracle, invalid signature, or synthetic-record downstream leakage.

Iteration-3 operating boundary: only `evidence preflight` is a supported CLI surface,
and it never persists the evidence source or any copy, index, or log of it. An
optional `--output` writes only the same non-sensitive result document (boundary
status, hashes, declared scope) the command would otherwise print to stdout; it
never writes evidence content. The internal evidence-store primitive is for synthetic
automated tests only. A complete new index is published atomically; existing indexes
are never repaired on open, and reads use SQLite read-only mode. Its write transaction
serializes writers, validates the exact index and all referenced objects before
removing abandoned staging and unindexed content objects, then performs the
same-descriptor second pass. A crash can leave a recoverable orphan but cannot create
an indexed pass. There is no
supported import, cleanup, backup, support-bundle, or pilot recovery workflow for these
internal records yet; do not preserve or transfer an iteration-3 workspace as customer
evidence.

## 7. Runbook: suspected PHI

1. Stop command and disconnect optional endpoint.
2. Do not forward, screenshot, or inspect beyond what is necessary.
3. Preserve only the non-sensitive error category if no accepted persistence occurred; retain no hash, hash prefix, filename, path, byte count, or rejected content. A FHIR narrative, contained resource, unrelated field/resource, or unapproved free text rejects the whole source; never strip and continue.
4. If content may have persisted, isolate workspace and notify customer security plus ContextSafe security within one hour.
5. Follow customer direction and counsel on preservation/deletion.
6. Rotate credentials if exposure is possible.
7. Invalidate affected run/receipt.
8. Conduct root-cause review and reauthorize the collection method before resuming.

## 8. Runbook: critical safety finding

1. Freeze the run and preserve integrity.
2. Notify customer technical and clinical safety owners; acknowledge within 4 business hours or immediately during an active session.
3. Confirm observation and applicability with a second qualified reviewer.
4. Do not access real patient records to estimate impact.
5. Customer activates its patient-safety/incident process and decides release/production response.
6. ContextSafe records finding, limitation, owners, and disposition.
7. Rerun only after remediation and scope confirmation.

## 9. Runbook: wrong evaluator result

1. Mark affected runner/pack version under investigation.
2. Reproduce with immutable evidence.
3. Determine whether predicate, mapping, evidence, oracle, or presentation failed.
4. Withdraw affected artifact/version if a false pass or clinically material error is possible.
5. Notify every affected customer within one business day.
6. Issue a new version and correction receipt; never overwrite.
7. Add fault fixture and postmortem.

## 10. Runbook: pack withdrawal

1. Clinical chair or community co-chair signs emergency hold.
2. Publish signed revocation entry with assertion/pack versions, reason category, date, and replacement status.
3. Verifier marks affected receipts as relying on withdrawn content.
4. Notify contracted contacts directly.
5. Block new evaluation with the version.
6. Review prior findings and offer rerun where results may change.

## 11. Runbook: signing-key compromise

1. Revoke key and stop receipt/pack release.
2. Publish signed revocation through an independent recovery key.
3. Inventory artifacts signed after earliest suspected compromise.
4. Notify affected customers and provide verification instructions.
5. Rotate hardware/device, credentials, and release policy.
6. Re-sign only after independently verifying original deterministic payload; do not alter timestamps or history.

## 12. Backup and recovery

- Source code, schemas, packs, and public fixtures: version control plus encrypted backup.
- Signing keys: hardware-backed primary and offline recovery key with tested access procedure.
- Customer workspace: customer responsibility; ContextSafe documents export/backup before evaluation.
- ContextSafe-held approved redacted receipts: encrypted backup, restore tested quarterly.
- RPO: 24 hours for product/release metadata; zero tolerance for losing a signed receipt already delivered because customer also retains it.
- RTO: 2 business days for local runner/release distribution; 1 business day for revocation verification.

Restore tests verify hashes and signatures, not merely file existence.

## 13. Change and maintenance cadence

- Dependency/security review weekly during build and monthly after v1.
- Clinical/standards watch monthly; governance review quarterly.
- Patch releases as needed for non-semantic fixes.
- Minor pack releases no more than monthly except safety updates.
- Major pack release when expected outcomes or public contracts change.
- Supported minor runner versions: current and previous for at least 12 months.
- Receipt schema major versions readable for at least 7 years or with a standalone verifier.

## 14. Capacity and cost guardrails

Per standard pilot:

- workspace under 100 MB;
- evaluation under 60 seconds;
- support under 20 `F`-pool hours after mapping;
- `F`-pool delivery under 80 hours and `E`-pool delivery under 120 hours;
- total core-team delivery under 200 hours, matching B-049–B-052;
- if B-057 is invoked, separately meter at most 32 `F`-pool hours, 48 `E`-pool hours and 8 paid reviewer hours against the extension change order; do not blend them into base-pilot delivery;
- external reviewer work planned, paid, and capped by SOW.

If three engagements exceed these, stop and redesign the service. Custom integration work is classified and reported separately, never absorbed into the standard delivery envelope.

## 15. Operations review

Monthly:

- SLOs and safety-property violations;
- install/update failures by platform;
- support categories and `F/E` pool hours;
- blocked/indeterminate causes;
- stale approvals/sources;
- incidents and near misses;
- customer/reviewer access roster;
- upcoming pack validity deadlines.

Quarterly governance receives the summary without customer-identifying or reviewer-sensitive data unless needed and authorized.
