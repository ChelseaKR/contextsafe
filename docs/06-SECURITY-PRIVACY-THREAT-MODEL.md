# Security, privacy, and threat model

Status: pre-implementation threat model  
Owner: security/privacy lead  
Review cadence: before pilot, before v1, annually, and after any architecture or incident change

## 1. Security objective

ContextSafe must not turn a safety test for trans and nonbinary people into a new source of patient exposure, credentials, or sensitive organizational findings. V1's strongest control is architectural: synthetic records, non-production execution, local processing, minimal transfer, and no hosted raw-evidence service.

“No PHI” is a product boundary and operating discipline, not a magical property of synthetic data. Misconfigured staging environments and exports can contain real patient data. Detection is layered and fallible.

## 2. Assets

- A-SEC-01: customer staging credentials and network details.
- A-SEC-02: customer system map, versions, and vulnerabilities/findings.
- A-SEC-03: synthetic raw evidence and normalized observations.
- A-SEC-04: pack, clinical oracle, mappings, and approval signatures.
- A-SEC-05: receipts, reviewer identities, and dispositions.
- A-SEC-06: customer and trans-community reviewer relationships.
- A-SEC-07: signing keys and release artifacts.
- A-SEC-08: trust in the product's bounded claims.

## 3. Trust boundaries

TB-01 incoming customer evidence; TB-02 optional staging FHIR connection; TB-03 mapping profiles; TB-04 pack update; TB-05 local workspace and OS account; TB-06 reviewer identity/signing; TB-07 receipt transfer; TB-08 dependency/build chain; TB-09 support channel.

## 4. Threat actors and misuse

- Accidental operator exporting a real patient.
- Malicious insider tampering with evidence or a disposition.
- External attacker stealing credentials or customer findings.
- Compromised dependency or release artifact.
- Vendor or customer using a receipt as marketing certification.
- Actor using customer/reviewer relationships to identify trans people or organizations.
- Overconfident clinician treating a synthetic oracle as patient-specific guidance.
- Founder overriding governance to close a sale.

## 5. STRIDE threats and controls

| ID | Category | Threat | Prevent/detect/respond | Residual |
|---|---|---|---|---|
| T-01 | Spoofing | Reviewer identity is forged | root-signed purpose/role trust manifest, plan-enrolled customer keys, role roster, MFA for code host, hardware-backed signing preferred, detached signatures, callback for critical approvals | compromised endpoint or trust root |
| T-02 | Spoofing | Synthetic record collides with a real person | explicit namespace, local test flag, reserved contacts, customer suppression, dry run, cleanup | vendor behavior outside test |
| T-03 | Tampering | Evidence or result changed after review | content hashes, append-only review events, signed deterministic receipt, verification command | signer compromise |
| T-04 | Tampering | Mapping hides or changes unsupported value | mapping fixtures, code review, approval, ambiguity retention, mapping hash, absolute GI/RSG-to-SPCU substitution prohibition | subtle semantic error |
| T-05 | Repudiation | Customer denies release disposition | named signed review, dual customer-clinical/ContextSafe-clinical signatures for accepted clinical residual risk, timestamps, receipt hash, customer release system remains authoritative | key custody disputes |
| T-06 | Information disclosure | Real PHI included in export | no-PHI contract, training, field allowlist, namespace gate, free-text ban, canary scanner, pre-persistence fail, incident drill | heuristic miss |
| T-07 | Information disclosure | Logs expose names, pronouns, tokens, paths | structured allowlisted logs, redaction tests, no raw values, local-only default | platform crash dump |
| T-08 | Information disclosure | Customer/reviewer list exposes trans affiliation | confidential CRM, minimum access, no public attribution by default, no tracking | legal compulsion/insider |
| T-09 | Denial of service | Malformed or huge input exhausts runner | file/count/field limits, bounded streaming parser, timeouts, no entity expansion, reject without ContextSafe copy | local resource exhaustion |
| T-10 | Elevation | Parser or template executes content | treat input as data, no eval, sandbox recommendations, output escaping, dependency scanning | zero-day |
| T-11 | Supply chain | Compromised package/release | lockfile, hashes, SBOM, signed releases, pinned CI, SAST/SCA, reproducible build target | upstream compromise |
| T-12 | Integrity | Expired oracle still yields pass | validity gate, pack pin, revocation list, receipt warnings | disconnected customer misses recall |
| T-13 | Safety misuse | Receipt marketed as certification | claims policy, contract restriction, watermark, public correction/withdrawal right | screenshot stripped of context |
| T-14 | Network | Read-only adapter queries real patients | staging host allowlist, exact synthetic identifier query, least-scope credential, result cap, kill switch | endpoint misroutes |
| T-15 | Privacy | Support ticket receives raw evidence | portal warning, attachment block where possible, staff script, secure exception path, deletion | user bypass |

## 6. PHI boundary controls

### Before engagement

- Contract states prohibited data and authorized evidence fields.
- Customer privacy owner signs the data-flow diagram.
- Technical owner demonstrates synthetic patient policy and downstream suppression.
- No BAA is assumed to solve poor scope; counsel determines status.

### Before persistence

- Accept only approved file types and size limits.
- Require plan ID, case ID, synthetic identifier system, and namespace match.
- Reject unapproved identifiers and free-text-bearing resources/segments.
- Check email domain, phone range, names, MRN pattern, account numbers, dates, URLs, and known canaries.
- Reject any unexpected FHIR resource type or HL7 segment/field.
- During the complete first pass, store nothing on rejection except at most a non-sensitive error class; do not create a workspace or retain source hash/prefix, filename/path, byte count, or rejected bytes.

### After acceptance

- Raw evidence stays customer-local.
- Use least-privilege filesystem permissions and full-disk encryption.
- Logs contain IDs and statuses only.
- HTML shows only claim-minimal fields.
- Cleanup command enumerates all retained artifacts.

The scanner must say “boundary check passed,” not “contains no PHI.” Human and system controls remain necessary.

Implementation note (2026-07-13): the first enabled boundary profile is a strict,
code-only canonical JSON envelope. It rejects unknown/prohibited fields, non-plan
case/checkpoint/namespace values, arbitrary prose, leading/trailing whitespace,
Unicode control/format characters, configured canaries, and bounded patterns for
email, SSN-like values, phone numbers, URLs, dates, MRN/account labels, and long
numeric identifiers. These patterns can miss identifiers and can produce false
positives. The result therefore says `boundary-check-is-not-proof-of-no-phi`; no
approved operating process may treat scanner success as privacy authorization.
Only after that complete first pass succeeds may the internal-test primitive write a
private second-pass staging file. A concurrent source mutation fails before promotion
or indexing. Staging cleanup is attempted, but filesystem denial can leave partial
second-pass bytes for permitted exclusive recovery or explicit operator remediation;
that residual is an incident condition, not a successful boundary result.

## 7. Data minimization by format

- FHIR: allowlist Patient identifiers/name/pronouns/GI/RSG/SPCU extensions as required, ServiceRequest, relevant Observation, DiagnosticReport, and Encounter references. Any narrative, contained resource, unrelated field/resource, or unapproved free text rejects the entire source before persistence. Never strip prohibited content and accept the remainder.
- HL7 v2: allowlist exact PID/GSP/OBX/OBR fields per profile. Reject NTE and other free-text fields.
- LIS: constrained columns only: synthetic case/order/accession tokens, analyte code, value, unit, range fields, flag, status, timestamps.
- UI observation: structured observer form; no screenshot by default.

An adapter performs only the bounded streaming parse needed to enforce format, namespace, and field allowlists against a caller-owned read-only source. No ContextSafe copy, temporary file, index row, or content-bearing log exists until the entire first-pass boundary check succeeds.

## 8. Identity, access, and secrets

V1 local operation uses the customer's OS identity and filesystem. ContextSafe does not implement user accounts.

- Staging credentials are read-only, short-lived, and kept in OS keychain or process environment.
- Never accept credentials in YAML, CLI arguments, logs, receipt, or support messages.
- Signing keys are separate from code-signing and customer credentials.
- The verifier pins the offline trust-root fingerprint and consumes its signed key/purpose/role manifest plus monotonic revocations; unknown, wrong-purpose, expired, revoked, stale-trust, or insufficient-threshold states do not verify as valid.
- Pack release requires role-distinct clinical-safety, community-co-chair, and technical-release-owner signatures created and checked through `pack sign/verify`; the technical signature attests build integrity and cannot replace either semantic approval. An executable plan requires customer-sponsor and ContextSafe-delivery-owner signatures through `plan sign/verify`. A mapping requires the plan-enrolled customer technical owner plus a distinct ContextSafe interoperability reviewer. Each review requires a signer authorized for its exact role; accepted clinical residual risk requires both the customer clinical owner and ContextSafe clinical chair, with neither substituting for the other. A pilot receipt requires a plan-enrolled customer release owner and a distinct ContextSafe clinical/service approver. Laboratory approval remains separately required for laboratory assertions.
- Key enrollment, rotation overlap, verification-time validity, untrusted claimed signing time, offline revocation freshness, root/key compromise, and verifier replacement follow the architecture trust model and exercised runbook.
- Repository administrators cannot bypass protected release or safety gates.
- Offboarding revokes code, CRM, storage, and signing access within one business day.

## 9. Secure development and release

- Threat model and misuse cases reviewed at design changes.
- Strict typing and parser property tests.
- 90% line and 100% safety-property branch coverage target.
- Secret, SAST, dependency, license, and SBOM gates.
- Pinned CI actions and least-privilege tokens.
- Signed tags and artifacts; public checksums.
- No external pilot or release with an open critical/high vulnerability. A demonstrably unaffected report is formally reclassified with evidence and independent security-lead approval; critical/high status itself is never waived.
- Coordinated vulnerability disclosure policy before pilot.

## 10. Privacy impact

### People affected

Trans and nonbinary people are the intended beneficiaries but are not data subjects in the synthetic pack. Reviewers, customer staff, and organizational contacts are data subjects in operations.

### Risks

- Reviewer identity could reveal gender identity or advocacy involvement.
- Organization participation could reveal unremediated safety defects.
- Test scenarios could normalize excessive collection of sensitive fields.
- Published output could encourage surveillance or forced disclosure.

### Controls

- Reviewers choose public attribution, private attribution, or pseudonymity in external material.
- Do not collect a reviewer's gender identity unless they volunteer it for governance composition; store separately with explicit consent.
- Every case follows a necessity test: no field exists merely for completeness.
- The pack tests “declined” and “not collected” as legitimate states.
- No analytics, tracking pixels, third-party fonts, or external scripts in receipts.
- Do not publish customer scores or comparative rankings.

## 11. Incident response

### SEV-1

Suspected PHI persisted/transferred, credential theft, signing-key compromise, malicious receipt, or synthetic record reaching real patient/billing operations.

1. Stop processing and isolate workspace/network.
2. Do not inspect more content than needed.
3. Notify customer security and clinical contacts within 1 hour.
4. Preserve minimal forensic metadata under counsel/customer direction.
5. Revoke credentials/keys and invalidate affected receipts/packs.
6. Determine notification duties with the customer and counsel.
7. Publish no details without authorization.
8. Complete blameless postmortem and reauthorize service before resuming.

### SEV-2

Non-sensitive integrity failure, inaccessible receipt, serious false result, or pack defect without known patient exposure. Acknowledge within 4 business hours; issue withdrawal/correction within one business day when confirmed.

### SEV-3

Minor tool, documentation, or support defect. Acknowledge within one business day.

A suspected clinical emergency is handed to the customer's clinical safety process immediately; ContextSafe is not an emergency service.

## 12. Verification before pilot

- Independent security design review.
- Malicious FHIR/HL7/CSV parser tests.
- PHI canary suite including direct identifiers, free text, FHIR narrative/contained/unrelated content, near-miss synthetic values, Unicode tricks, oversized input, and proof that the whole source is rejected rather than stripped.
- Receipt tamper and signature rotation tests.
- Logging and crash-dump inspection.
- Workspace permission tests on supported OSes.
- Optional adapter credential and query-scope test.
- Support-channel social-engineering tabletop.
- SEV-1 exercise with customer.

## 13. Known residual risks

- No detector proves data are synthetic.
- A staging system may share downstream production services.
- A hash does not prove evidence is truthful.
- A clinically approved fixture may still be wrong or become stale.
- Local endpoint security is outside ContextSafe control.
- A recipient can strip limitations from a screenshot.

These risks must appear in the customer receipt and [risk register](14-RISK-REGISTER.md).
