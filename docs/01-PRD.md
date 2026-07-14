# Product requirements document

Status: proposed  
Target: ContextSafe v1.0  
Owner: founder/product lead  
Approvers: clinical safety chair, laboratory lead, community co-chair, design-partner technical owner

## 1. Problem

Transgender and nonbinary patient data can be recorded correctly in a registration system and then be lost, collapsed, exposed inappropriately, or used as a clinical proxy as it crosses EHR, interface, and laboratory boundaries. Component conformance does not show that the installed workflow returns a name, pronoun, identity, context-specific clinical parameter, reference range, and abnormal flag safely.

Clinical informatics and interface teams need a repeatable pre-release test that tells them what was observed, what an approved test expected, where the mismatch appeared, and what evidence supports that conclusion.

## 2. Personas

| ID | Persona | Need | Constraint |
|---|---|---|---|
| PER-01 | Clinical informatics lead | Know whether a release changes patient-safety behavior | Cannot accept a black-box safety score |
| PER-02 | Interface/LIS analyst | Find the exact boundary and field transformation | Vendor formats and staging access vary |
| PER-03 | Laboratory medical director | Approve reference-range and flag expectations | Evidence is context-specific and sometimes uncertain |
| PER-04 | Patient-safety/risk executive | Make and evidence a release decision | Needs concise findings and accountable owners |
| PER-05 | Trans/nonbinary patient reviewer | Prevent demeaning or unsafe test assumptions | Must have compensated decision power, not symbolic consultation |
| PER-06 | Release engineer | Rerun the same pack after changes | Needs deterministic local execution and CI-friendly output |
| PER-07 | Security/privacy officer | Keep the exercise outside PHI processing | Must inspect data flows and fail-closed controls |

## 3. Jobs to be done

- JTBD-01: When an identity or interface configuration changes, help PER-01 determine whether the end-to-end pathway still preserves meaning before approval.
- JTBD-02: When a test fails, help PER-02 locate the first divergent checkpoint and inspect the exact evidence.
- JTBD-03: When an expected clinical behavior is encoded, help PER-03 verify its source, context, validity period, and limitations.
- JTBD-04: When a release is reviewed, help PER-04 see unresolved risk without interpreting raw messages.
- JTBD-05: When a synthetic scenario represents trans people, give PER-05 approval and withdrawal power over harmful assumptions or language.
- JTBD-06: When software is rerun, help PER-06 reproduce and compare results without a hosted dependency.
- JTBD-07: When evidence enters the runner, help PER-07 prove that obvious PHI is rejected and retained data are minimal.

## 4. Goals

| ID | Outcome | V1 target |
|---|---|---|
| G-01 | Detect cross-system loss or coercion | Correctly detect and localize all 36 published regression faults and all five independently authored, implementation-hidden challenge faults (41/41); any detection or localization miss blocks release; report these as bounded corpus results, not unseen-population sensitivity |
| G-02 | Produce reproducible release evidence | Same inputs and versions produce identical normalized JSON in 3 runs |
| G-03 | Make findings actionable | 100% pilot findings have boundary, evidence, owner, severity, and disposition |
| G-04 | Preserve the no-PHI boundary | 100% PHI canaries rejected before persistence; zero confirmed PHI incidents |
| G-05 | Demonstrate buyer value | One external partner uses a receipt in a release decision and converts or documents a falsifiable objection |
| G-06 | Share understandable results | In each locale, at least 90% of scored comprehension answers are correct, every participant answers at least 4/5 correctly, at least 90% of participant-task attempts succeed independently, and WCAG 2.2 AA passes |

## 5. Non-goals

- NG-01: Diagnose, treat, recommend a reference range for a real patient, or replace clinician judgment.
- NG-02: Certify legal or regulatory compliance, award a hospital grade, or promise clinical safety.
- NG-03: Ingest production traffic or real patient records.
- NG-04: Automate writes into arbitrary EHR or LIS products.
- NG-05: Cover imaging, DICOM, pharmacy, billing, or live CDS in v1.
- NG-06: Generate large statistically representative synthetic populations; the pack is a controlled test set.
- NG-07: Infer gender identity, anatomy, hormone status, or clinical context from another field.
- NG-08: Use generative AI to create, classify, or explain a test result.

## 6. Critical user stories

- As PER-01, I want one approved pack and execution plan so that a release is tested consistently.
- As PER-02, I want checkpoint-level diffs so that I can find where meaning changed.
- As PER-03, I want every clinical expectation tied to a dated source and reviewers so that uncertain guidance is visible.
- As PER-04, I want failures and indeterminate results separated from passes so that missing evidence cannot look reassuring.
- As PER-05, I want harmful language or scenarios blocked from release until resolved so that lived experience is not advisory theater.
- As PER-06, I want a signed, versioned receipt so that I can attach it to a change record and rerun it.
- As PER-07, I want the runner to reject PHI-like inputs before saving them so that a staging mistake does not silently expand scope.

## 7. Requirements

### P0: v1 cannot ship without these

#### P0-01 — Versioned pack validation

The runner content-validates pack metadata, cases, assertions, terminology, source references, reviewer approvals, validity dates, and schema versions, then verifies the three-role pack-signature threshold before execution.

Given a pack with a missing reviewer, expired clinical assertion, unknown field, or broken source reference, when `pack validate` runs, then canonicalization/signing is blocked and each defect is reported. Given missing or incomplete clinical/community/technical signatures, `pack verify` and execution stop and write no pass/fail receipt.

#### P0-02 — Canonical twelve-patient pack

Pack 1.0 contains CTP-001 through CTP-012 and the mandatory assertions in [Data and evidence](05-DATA-AND-EVIDENCE.md); cases explicitly separate GI, SPCU, RSG, name to use, and pronouns.

Given pack 1.0, when its manifest is listed, then all 12 immutable case IDs, current versions, approval states, and applicable assertions are visible and no field is inferred from another.

#### P0-03 — Non-production execution plan

The tool generates a customer-specific plan that names target environment, allowed hostnames, checkpoints, collection method, synthetic identifier namespace, responsible operators, reviewer/key enrollment, and cleanup. The customer sponsor and ContextSafe delivery owner sign the canonical plan with `contextsafe plan sign`; both signatures must verify before evidence import.

Given a target marked production, an unallowlisted host, an identifier outside the synthetic namespace, or an unsigned/partially signed plan, when a run is planned or evidence import is attempted, then the tool refuses execution and records the reason.

#### P0-04 — File-first observation ingestion

The runner accepts canonical JSON, FHIR R4 JSON, HL7 v2 text, and constrained LIS result mappings without requiring a hosted service.

Given valid or invalid fixture files, when imported, then valid content is normalized with source-byte hashes and invalid content is rejected with location-specific errors; source files are never silently repaired.

#### P0-05 — Identity fidelity evaluation

The evaluator checks name to use, pronouns, gender identity, and recorded sex/gender independently at each applicable checkpoint.

Given a case whose usual name or pronouns are dropped, overwritten by a legal name, or coerced, when evidence is evaluated, then the relevant assertion fails at the first observed divergence and shows expected and observed semantics without exposing unnecessary source fields.

#### P0-06 — Clinical-context fidelity evaluation

The evaluator checks SPCU value, context, period, provenance, and links to supporting observations without treating GI or RSG as substitutes. No customer approval, local mapping, or disclosed deviation can convert GI or RSG into SPCU for a core assertion.

Given a contextual SPCU that is absent, expired, detached from the order/result context, or derived/mapped from GI or RSG, when evaluated, then the assertion fails or is indeterminate according to the approved rule and never passes by field equivalence or local waiver.

#### P0-07 — LIS range and abnormal-flag evaluation

For approved synthetic analytes, the evaluator checks that a result includes expected unit, reference-range state, and abnormal flag behavior defined by the case's approved oracle.

Given an X or nonbinary administrative value that causes the LIS to omit a range or abnormal flag, when the result returns, then the assertion fails and identifies the LIS-return boundary; the tool does not select a replacement patient-specific range.

#### P0-08 — Safe unknown and missing-evidence behavior

Pass, fail, indeterminate, not-applicable, and blocked are distinct states; only affirmative evidence can produce pass.

Given missing, ambiguous, stale, or inaccessible evidence, when an assertion evaluates, then it is indeterminate or blocked, the missing evidence is named, and aggregate output cannot count it as pass.

#### P0-09 — Evidence receipt

Each run produces normalized JSON and accessible static HTML containing scope, versions, environment label, checkpoint coverage, assertion outcomes, evidence hashes, limitations, reviewer approvals, deviations, and signatures.

Given a completed run, when the receipt is rendered, then a reviewer can trace every outcome to the assertion version and evidence item; changing any evidence or result invalidates verification.

#### P0-10 — Human disposition workflow

Clinical expectations and pilot findings require named human approval; technical automation may calculate an outcome but cannot close a safety finding.

Given a failed, blocked, or indeterminate mandatory assertion, when a release receipt is finalized, then it includes a named owner and disposition of remediate, accepted residual risk, defer with date, or release blocked. An accepted clinical residual risk requires two distinct `review` signatures: the customer clinical owner owns the local operational risk and release decision, and the ContextSafe clinical safety chair confirms the governed clinical expectation, severity, and bounded disposition. Neither signature substitutes for the other; without both, the receipt cannot represent the risk as accepted.

#### P0-11 — Synthetic-only and PHI rejection

Inputs pass explicit synthetic-namespace validation plus deterministic PHI canary checks as a read-only stream from a caller-owned source before ContextSafe copies, indexes, or logs source bytes.

Given a file containing a non-synthetic identifier, realistic customer MRN, unapproved free text, known PHI canary, direct identifier pattern, or FHIR narrative/contained/unrelated content, when ingestion begins, then the entire input fails before any ContextSafe-controlled persistence; the runner never strips prohibited content and accepts the remainder. Logs contain only the rejection class, and the incident procedure is offered. The detector is a boundary check, not proof that accepted bytes contain no PHI.

#### P0-12 — Provenance and version pinning

The receipt pins runner, pack, assertion, schema, terminology, adapter, configuration, and source-evidence versions.

Given two verified receipts for the same partner profile, when the mandatory local delta command compares them, then every version, evidence, coverage, assertion, outcome, and disposition difference is explicit in deterministic JSON; incompatible profiles fail with a reason, and a result from changed inputs cannot be represented as the same run.

#### P0-13 — Accessible EN/ES static receipt

All user-facing receipt strings are externalized and available in English and Spanish; the HTML meets WCAG 2.2 AA and remains meaningful without color or scripts.

Given either locale and a keyboard or supported screen reader, when a reviewer navigates a receipt, then headings, tables, status text, evidence links, errors, and print output remain operable and understandable at 400% zoom.

#### P0-14 — Deterministic local CLI

All core validation, plan/pack signing and verification, evaluation, rendering, and receipt verification run locally with documented exit codes and no network dependency.

Given identical input bytes, configuration, pack, and runner version, when evaluation runs three times on supported platforms, then normalized JSON and semantic outcomes are identical; timestamps and signatures live outside the deterministic payload.

#### P0-15 — Service delivery controls

Every engagement follows approved intake, environment attestation, operator training, evidence transfer, review, remediation, cleanup, and closeout steps.

Given a prospective engagement, when any safety prerequisite in [Service design](03-SERVICE-DESIGN.md) is unmet, then execution does not begin and the blocked condition has an owner and deadline.

### P1: target after core pilot; may enter v1 only without delaying P0

#### P1-01 — Read-only FHIR adapter

Given a customer staging FHIR R4 endpoint with scoped credentials, when collection runs, then only allowlisted synthetic resources are read, credentials remain in memory, and the same normalized evidence is produced as file import.

#### P1-02 — CI outputs

Given a completed local evaluation, when CI export is requested, then JUnit and SARIF summarize assertion IDs and statuses without embedding clinical source data or identifiers.

#### P1-03 — Advanced receipt comparison experience

Given multiple verified receipts or receipts with an approved profile migration, when a reviewer explores history, then filters, visual summaries, trend views, and mapped cross-profile differences reduce analysis time without replacing the deterministic P0-12 delta artifact.

#### P1-04 — Adapter mapping workbench

Given an unknown vendor export, when an analyst creates a mapping, then sample values can be previewed against the canonical schema and no mapping becomes approved without fixture tests and a named reviewer.

#### P1-05 — Spanish execution guidance

Given a Spanish-preferring operator, when the execution guide and errors are opened, then complete human-translated Spanish content is available with terminology reviewed by a healthcare translator and community reviewer.

#### P1-06 — Customer-pack extensions

Given an approved local assertion, when added in a customer namespace, then it cannot masquerade as a ContextSafe core assertion and its local sources and reviewers appear in the receipt.

### P2: explicitly later

#### P2-01 — RIS/DICOM pack

Given a future approved imaging pack, when executed, then DICOM Supplement 233 concepts and legacy Patient Sex behavior can be evaluated without changing v1 receipt semantics.

#### P2-02 — Pharmacy and e-prescribing

Given a future pharmacy adapter, when identity or clinical context crosses the boundary, then patient-facing labeling and decision logic can be evaluated with a pharmacy safety oracle.

#### P2-03 — CDS test extension

Given approved synthetic clinical scenarios, when a CDS rule is exercised, then its inputs and observed output can be recorded; ContextSafe still does not recommend care.

#### P2-04 — Hosted team control plane

Given validated multi-customer demand and security investment, when a hosted service exists, then tenants, receipts, access, deletion, and audit data remain isolated and raw evidence is optional.

#### P2-05 — Production-safe canary monitoring

Given separate clinical, privacy, vendor, and legal approval, when synthetic canaries run in production, then they cannot enter billing, reporting, treatment, or patient communication; this is not implied by v1.

## 8. Metrics

### Leading

- Interview completion and LOI conversion.
- Percentage of test cases reaching each checkpoint.
- Evidence completeness and time from kickoff to first receipt.
- Seeded-fault sensitivity and false-positive count.
- Median analyst time to localize a finding.
- Percentage of findings with owner within two business days.
- Receipt comprehension score by role and locale.

### Lagging

- Pilot-to-annual conversion.
- Reruns per partner and releases covered.
- Remediation verification rate.
- Number and severity of defects caught pre-release.
- Renewal, gross margin, implementation hours, and support hours.
- Pack change lead time and reviewer participation/retention.

Metrics may not rank individual clinicians, staff, or trans patients. Defects are system findings.

## 9. Open questions

| ID | Question | Owner | Blocking |
|---|---|---|---|
| OQ-01 | Which first-partner HL7 v2 version/profile carries Gender Harmony concepts? | interoperability lead | Yes, before adapter acceptance |
| OQ-02 | Which analytes and reference-range expectations are sufficiently settled for core status? | lab lead | Yes, before pack approval |
| OQ-03 | How will absence be evidenced in each vendor export? | partner technical owner | Yes, before pilot |
| OQ-04 | Does intended use remain outside FDA device oversight and state practice restrictions? | counsel | Yes, before paid pilot |
| OQ-05 | Will the partner permit an independently verifiable receipt outside its network? | security and contracts | No; private receipt is acceptable |
| OQ-06 | Which Spanish terminology best distinguishes GI, SPCU, and RSG? | translator and community co-chair | Yes, before v1 |

## 10. Scope-change rule

Any proposed P0 addition must remove another P0, extend the timeline, or receive explicit approval from the product owner, clinical safety chair, and community co-chair. A partner-specific integration may not silently become a core product requirement.
