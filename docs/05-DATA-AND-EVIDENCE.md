# Data, test pack, and evidence

Status: proposed pack 0.1 specification  
Owners: clinical safety chair and community co-chair  
Laboratory oracle approver: laboratory medical director

## 1. Semantic rules

ContextSafe uses the HL7 Gender Harmony model and keeps these concepts distinct:

- GI: Gender Identity.
- SPCU: Sex Parameter for Clinical Use; contextual clinical guidance linked where possible to observable information.
- RSG: Recorded Sex or Gender, including an administrative or jurisdictional context.
- NtU: Name to Use; represented in FHIR with HumanName.use equal to usual.
- Pronouns: a person's specified pronouns.

No value is inferred from another. GI or RSG cannot become SPCU through a local mapping, customer approval, or disclosed deviation; such target behavior is observed and failed, not normalized into an allowed substitution. Absence, unknown, declined, unsupported, and not applicable are different. Sexual orientation is outside the v1 pack because it is not needed to test the initial pathway.

The pack does not encode “trans physiology.” It tests explicitly supplied synthetic clinical context and a partner-approved laboratory fixture. A person's GI never chooses a laboratory reference interval.

## 2. Synthetic identity convention

Every case uses:

- identifier system urn:contextsafe:synthetic;
- identifier value CSYN-CTP-NNN;
- family name ZZZTESTCONTEXTSAFE;
- given/name-to-use token beginning CSYN;
- email under example.invalid;
- telephone in the reserved 555-0100 through 555-0199 fictional range where a system requires one;
- explicit synthetic marker in the approved local test field;
- partner-approved test-patient flags and downstream suppression.

Dates of birth are fixed values chosen to exercise adult age bands, but are not evidence of a real person. Partners may translate display values to their approved test-patient convention while preserving the case ID. The tool rejects identifiers outside the approved synthetic namespace.

Free-text clinical notes are prohibited in v1 evidence. Fixed coded comments may be used only when the assertion specifies them.

## 3. Canonical twelve-patient pack

The traits below are test parameters, not claims about all people with a similar identity.

| Case | Synthetic scenario | Required concepts | Primary hazard |
|---|---|---|---|
| CTP-001 | Nonbinary adult; RSG X in government-ID context; NtU CSYN-Aster; they/them; no SPCU for identity-only workflow | GI, RSG, NtU, pronouns | X coercion; GI used as clinical proxy |
| CTP-002 | Trans woman; NtU CSYN-Mara differs from legal test name; she/her; order-scoped female-typical SPCU with approved supporting observation | GI, NtU, pronouns, SPCU, RSG | deadnaming; SPCU lost |
| CTP-003 | Trans man; NtU CSYN-Leo differs from legal test name; he/him; order-scoped male-typical SPCU with support | GI, NtU, pronouns, SPCU, RSG | GI/RSG conflation; range selection failure |
| CTP-004 | Nonbinary adult; they/them; order-scoped male-typical SPCU with effective period and source observation | GI, NtU, pronouns, SPCU | binary SPCU overwrites nonbinary GI |
| CTP-005 | Trans woman; she/her; two orders, only one has an SPCU | GI, NtU, pronouns, SPCU on one order | SPCU leaks outside its context |
| CTP-006 | Trans woman; she/her; organ-dependent synthetic order with a local, clinician-approved oracle | GI, NtU, pronouns, SPCU, supporting observation | GI suppresses relevant test or substitutes for context |
| CTP-007 | Adult explicitly declines GI and pronouns; RSG X in source context; NtU supplied | declined states, RSG, NtU | declined becomes unknown or invented value |
| CTP-008 | Adult with GI/pronouns not collected; RSG unknown; sex-invariant synthetic analyte | absent/unknown, NtU | null coerced to binary; unnecessary disclosure |
| CTP-009 | Adult with legal test name and a current NtU plus expired prior NtU | name periods and use | old name shown or current name lost |
| CTP-010 | Adult with two RSG records: X government-ID context and F payer context; nonbinary GI | GI, multiple RSG, source/context | one RSG overwrites another or GI |
| CTP-011 | Adult with an expired SPCU and a current order-specific SPCU tied to different contexts | SPCU periods, contexts, support | expired or wrong-context SPCU applied |
| CTP-012 | Reproduction of the published failure pattern: administrative X, configured out-of-range synthetic result, required range and flag | RSG X, lab oracle | silent LIS error, absent range, unflagged abnormal result |

CTP-006 cannot enter the core pack until the local organ-dependent oracle has independent clinical approval. If consensus is not reached, it remains experimental and its assertions are not counted in mandatory coverage.

## 4. Laboratory fixtures

V1 includes three classes of synthetic result:

1. INV: a sex-invariant fixture whose approved range and flag are the same across values used by the target.
2. CTX: a context-sensitive fixture where the order carries an explicit, approved SPCU and supporting observation.
3. XFAIL: a fixture configured so that RSG X historically or intentionally exercises a missing-range failure path.

The partner's laboratory medical director supplies fixture analyte code, units, lower/upper bounds, inclusivity, age band, effective version, and expected flag for the synthetic result. ContextSafe ships a reference fixture solely for software tests; it is not a clinical range recommendation.

Required edge values per approved fixture:

- one value below lower bound;
- lower bound;
- one in-range value;
- upper bound;
- one above upper bound;
- one unsupported or missing-context condition.

The oracle records whether a blank range, dual range, safety range, or contact-the-lab behavior is locally approved. Disputed behavior is indeterminate, never normalized into a universal expectation.

## 5. Mandatory assertions

All applicable assertions are mandatory. “Applicable” is determined by the immutable case manifest and partner profile before observation.

### Pack and synthetic safety

| ID | Assertion |
|---|---|
| A-001 | Case ID, synthetic identifier system/value, and approved test flag remain associated at every observed checkpoint. |
| A-002 | No prohibited free text or non-synthetic identifier enters accepted evidence. |
| A-003 | The target prevents the case from billing, public-health reporting, patient communication, and production operational queues as required by the plan. |
| A-004 | Cleanup evidence accounts for each created synthetic record and downstream artifact. |

### Name, pronouns, and identity

| ID | Assertion |
|---|---|
| A-005 | Current NtU is preserved with its use and valid period. |
| A-006 | Patient-facing staging display uses the current NtU wherever the approved workflow says it should. |
| A-007 | A legal test name remains available only in approved administrative contexts and is not substituted for NtU in tested patient-facing output. |
| A-008 | Pronoun value and status are preserved at applicable checkpoints. |
| A-009 | Explicitly declined pronouns/GI remain declined rather than unknown, absent, or populated. |
| A-010 | GI value, code system, and status are preserved. |
| A-011 | GI is not overwritten by RSG, NtU, pronouns, or SPCU. |
| A-012 | RSG value, type, source, jurisdiction/organization, and valid period are preserved when represented. |
| A-013 | Multiple RSG records remain distinct and do not overwrite GI. |
| A-014 | X, unknown, and absent values are not coerced into M or F. |
| A-015 | Expired NtU is not displayed as current; history remains only where approved. |

### Clinical context

| ID | Assertion |
|---|---|
| A-016 | SPCU value and code are preserved only where explicitly supplied. |
| A-017 | SPCU scope identifies the applicable order, result, encounter, or other approved context. |
| A-018 | SPCU effective period is preserved and evaluated against the synthetic event time. |
| A-019 | SPCU provenance or link to approved supporting observation remains traceable. |
| A-020 | GI is never treated as an SPCU. |
| A-021 | RSG is never treated or mapped as an SPCU; any such substitution fails the assertion even when a local mapping is documented or customer-approved. |
| A-022 | An expired SPCU is not applied as current. |
| A-023 | An order-specific SPCU reaches the LIS with the intended order and does not attach to an unrelated order. |
| A-024 | Absence of SPCU remains absence; the receiving pathway fails or defaults only according to the approved local safety oracle. |

### Laboratory result integrity

| ID | Assertion |
|---|---|
| A-025 | Returned result is linked to the correct synthetic case, order, specimen, and analyte. |
| A-026 | Analyte code, numeric value, unit, and status survive the round trip. |
| A-027 | Where the oracle requires a reference interval, lower/upper values, unit, inclusivity, and effective oracle version are present. |
| A-028 | Expected abnormal flag matches the approved fixture at below, boundary, in-range, and above values. |
| A-029 | RSG X does not produce a silent blank reference interval or suppress a required abnormal flag. |
| A-030 | A configured out-of-range value is never returned as apparently normal solely because a range is absent. |
| A-031 | A result-facing name and pronoun display follows the approved NtU/pronoun rule without exposing unnecessary legal-name or GI data. |

### Evidence and receipt integrity

| ID | Assertion |
|---|---|
| A-032 | Missing, inaccessible, stale, or ambiguous evidence yields indeterminate or blocked, never pass. |
| A-033 | Unsupported source values remain explicit and are not silently normalized to the closest supported value. |
| A-034 | First divergence names only an observed boundary; an unobserved boundary is not blamed. |
| A-035 | Every outcome traces to source hash, source pointer, mapping, assertion, oracle, pack, and runner version. |
| A-036 | Receipt presentation excludes raw fields not needed to substantiate the outcome and verifies against its deterministic JSON. |

## 6. Case-to-assertion matrix

All cases run A-001–A-004 and A-032–A-036.

| Case | Additional mandatory assertions |
|---|---|
| CTP-001 | A-005–A-008, A-010–A-014, A-020, A-024 |
| CTP-002 | A-005–A-012, A-014, A-016–A-023, A-025–A-031 |
| CTP-003 | A-005–A-012, A-014, A-016–A-023, A-025–A-031 |
| CTP-004 | A-005, A-006, A-008, A-010, A-011, A-014, A-016–A-023, A-025–A-031 |
| CTP-005 | A-005, A-006, A-008, A-010, A-011, A-016–A-024, A-025–A-031 |
| CTP-006 | A-005, A-006, A-008, A-010, A-011, A-016–A-024, A-025–A-031; experimental until approved |
| CTP-007 | A-005–A-015, A-020, A-024 |
| CTP-008 | A-005, A-010–A-014, A-020, A-024, A-025–A-030 |
| CTP-009 | A-005–A-007, A-015, A-031 |
| CTP-010 | A-005, A-008, A-010–A-014, A-020, A-021 |
| CTP-011 | A-016–A-024, A-025–A-030 |
| CTP-012 | A-005, A-007, A-010–A-014, A-020, A-021, A-025–A-031 |

## 7. Assertion contract

Each assertion contains:

- immutable ID and SemVer version;
- title and plain-language rationale;
- applicable cases, checkpoints, and partner-profile conditions;
- canonical fields read;
- pure predicate and allowed statuses;
- expected evidence, including proof of absence where relevant;
- linked clinical oracle, if any;
- default severity rubric, never automatic final severity;
- source IDs, quotations within licensing limits, and retrieval dates;
- technical, clinical, laboratory, and community approvals as applicable;
- valid-from, re-review date, supersession/withdrawal state;
- known limitations and counterexamples;
- locale strings.

An expired, withdrawn, or incompletely approved mandatory assertion blocks pack validation.

## 8. Evidence items

| Evidence type | Examples | Required metadata |
|---|---|---|
| E-REG | registration export or approved screenshot transcription | collector, time, system/version, case, field pointer, raw hash |
| E-EHR | FHIR Patient/Observation or constrained EHR export | resource pointer, server/version, query/method, raw hash |
| E-HL7 | captured HL7 v2 message | message control ID token, version, segment pointer, capture point, raw hash |
| E-LIS | order/result export | accession token, analyte, result pointer, LIS/version, raw hash |
| E-DISPLAY | structured observation of staging UI | view ID, role, locale, observer, approved fields only |
| E-PLAN | environment attestation and system map | approvers, date, plan hash |
| E-REVIEW | signed human judgment | role, reviewer, rationale, source outcome; accepted clinical residual risk carries distinct customer-clinical-owner and ContextSafe-clinical-chair signatures |
| E-CLEAN | cleanup and downstream-suppression evidence | system, record token, action, operator, time |

Screenshots are discouraged because they easily contain unrelated data. If needed, the customer creates a cropped, approved, synthetic-only artifact. OCR or AI extraction is not used in v1.

## 9. Provenance and integrity

Raw source bytes receive SHA-256 content IDs. Normalized observations reference the source hash and exact path/segment. Mappings are versioned and signed. Evaluation records the set of evidence IDs read. The deterministic receipt forms a Merkle-style manifest of:

- plan hash;
- pack and assertion hashes;
- mapping and terminology hashes;
- raw evidence hashes;
- normalized observation hashes;
- outcome hashes;
- review/disposition hashes.

The signed receipt can omit raw evidence while proving which bytes produced it. A hash proves integrity, not truth or clinical correctness.

## 10. Receipt claim taxonomy

| Claim ID | Permitted claim | Required support |
|---|---|---|
| CLM-001 | “This source value was observed at checkpoint X.” | evidence hash, pointer, collector, system/version |
| CLM-002 | “This value differed from the approved expected value.” | CLM-001 plus assertion and oracle versions |
| CLM-003 | “The first observed divergence was between X and Y.” | complete observations for adjacent checkpoints |
| CLM-004 | “Named reviewers confirmed severity/disposition.” | signed review with role and rationale; accepted clinical residual risk requires both mandated roles |
| CLM-005 | “A rerun no longer reproduced the finding.” | two verified comparable receipts |
| CLM-006 | “The pack passed all applicable assertions.” | zero fail/blocked/indeterminate mandatory outcomes and complete coverage |

Forbidden claims include “the hospital is safe,” “the system is compliant/certified,” “no trans patient can be harmed,” “the correct treatment is,” or “this reflects all transgender people.”

## 11. Data classification and retention

- Public: published schemas, empty/example pack structures, source bibliography.
- Internal: draft assertions, reviewer roster, product operations.
- Confidential: customer system map, mappings, receipts, findings, contracts.
- Prohibited: real patient data, production exports, credentials, unrelated free text.

Raw evidence remains at the customer by default. If transferred under exception, it is encrypted, access logged, and deleted no later than 30 days after final receipt. ContextSafe may retain a mutually approved redacted receipt for the contract term plus 90 days. Research notes follow [Research](02-USER-RESEARCH-AND-PILOT.md). Legal/financial records exclude evidence and follow counsel/accounting retention.

## 12. Pack change process

1. Open a change record with evidence and affected assertions.
2. Classify as editorial, technical, clinical, representation, or emergency safety.
3. Run source verification and counterexample review.
4. Obtain required clinical/community/lab approvals.
5. Execute the full reference fixture suite.
6. Publish SemVer, migration note, validity dates, dissent, and affected receipts.
7. Notify customers if any prior outcome may change.

A clinical oracle change is at least a minor pack release; changed expected outcome is major. A harmful or invalid assertion is withdrawn immediately and triggers the recall procedure in [Governance](07-GOVERNANCE-LEGAL-SAFETY.md).
