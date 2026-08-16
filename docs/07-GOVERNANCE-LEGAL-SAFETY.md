# Governance, legal, and safety

Status: proposed charter; counsel and reviewers must approve before pilot  
Owners: clinical safety chair and community co-chair

## 1. Governance purpose

ContextSafe turns reviewed expectations into executable assertions. That creates authority and risk. Governance exists to prevent technical convenience, sales pressure, or a single expert from becoming an unexamined clinical rule.

Clinical correctness and respectful representation are separate approval domains. Neither is reduced to the other.

## 2. Governing group

Minimum before pack 1.0:

- one independent clinical informaticist as clinical safety chair;
- one independent laboratory medical director or clinical chemist;
- one interoperability specialist;
- at least two compensated transgender/nonbinary reviewers, one serving as community co-chair;
- one privacy/security reviewer;
- one accessibility/language reviewer;
- founder/product and technical lead, without unilateral clinical approval;
- legal counsel as non-voting advisor.

Seek racial, disability, age, socioeconomic, nonbinary, and care-setting breadth. Do not claim that a small group represents all trans people.

## 3. Decision rights

| Artifact/decision | Required approval |
|---|---|
| Technical parser/mapping | technical lead plus interoperability reviewer |
| Clinical oracle or assertion | two clinicians, including relevant specialist; lab lead for LIS content |
| Representation, names, pronouns, scenario language | community co-chair plus one additional community reviewer |
| Privacy boundary | security/privacy lead |
| EN/ES release | accessibility lead, professional translator, community reviewer |
| Pack release | clinical safety chair and community co-chair; technical release owner |
| Accepted clinical residual-risk disposition | customer clinical owner owns local operational risk and release decision; ContextSafe clinical chair independently confirms the governed expectation, severity, and bounded disposition record; both sign and neither substitutes for the other |
| Intended-use/marketing claim | founder, clinical chair, community co-chair, and counsel |
| Assertion withdrawal | either clinical chair or community co-chair may impose immediate temporary hold |
| Publication of method and concept material (class 1 in [publication policy](17-PUBLICATION-POLICY.md) §2) | maintainer alone while the group is unseated, decision recorded; clinical chair and community co-chair once seated |
| Publication of locator material — pack payload, mapping profiles, field and boundary paths (class 2) | clinical chair **and** community co-chair, plus counsel where a customer, contract, or jurisdiction is involved and the security/privacy lead where system internals are described. **Not publishable at all while either chair seat is unfilled** |
| Publication of instance material — any real organization, deployment, receipt, or person (class 3) | no approval path exists; prohibited |
| Withdrawal of publication approval, or a halt on publishing | community co-chair may act alone, as with an assertion hold; before that role is filled, any compensated community reviewer may |
| Repository visibility change | maintainer, recorded, with the threat model reviewed first |

Silence is not approval. Approval includes name/pseudonym, role, date, version, conflicts, rationale, and signature. The ContextSafe chair's signature on an accepted clinical residual risk does not make the customer's release decision; it confirms only the clinical expectation, severity, and boundedness of the recorded disposition. Refusal by either required signer prevents the receipt from representing that risk as accepted.

## 4. Reviewer RACI

| Activity | Founder | Clinical chair | Lab lead | Community co-chair | Technical | Security | Counsel |
|---|---|---|---|---|---|---|---|
| Research priorities | A/R | C | C | C | C | C | I |
| Case content | R | A | C | A | C | C | I |
| Assertion predicate | C | A | A where lab | C | R | I | I |
| Source sufficiency | C | A | A where lab | C | R | I | I |
| Pack release | R | A | C | A | C | C | I |
| Security boundary | C | I | I | C | C | A | C |
| Legal claims | R | C | I | C | I | C | A |
| Emergency withdrawal | R | A | C | A | C | C | C |
| Publication of project material | R | A | I | A | C | C | C |

Dual accountabilities reflect independent safety domains; a release needs all named approvals. On publication the community co-chair's accountability includes a unilateral stop, described in section 14.

## 5. Evidence policy

Evidence priority:

1. Normative published standard or regulator source.
2. Peer-reviewed systematic guidance or professional-society consensus.
3. Peer-reviewed study or case report.
4. Documented local clinical policy approved by the partner.
5. Expert consensus recorded through the governance process.
6. Community testimony for experience, language, and harm—not as a substitute for clinical evidence.

Every source records stable URL/identifier, title, publisher, version/date, retrieval date, applicable claim, limitations, and re-review date. Continuous-build standards are labeled as such and pinned to a commit or dated package where possible.

A single case report can motivate a test hazard, but does not establish a universal treatment rule.

## 6. Clinical safety case

Top-level claim: **For the named non-production scope, ContextSafe produces a traceable and reviewable comparison between approved synthetic expectations and observed evidence without making patient-specific clinical decisions.**

Subclaims:

- SC-01: the pack semantics distinguish identity, administrative records, and clinical context;
- SC-02: assertions have sufficient reviewed evidence and validity controls;
- SC-03: evidence and results are reproducible and tamper evident;
- SC-04: missing evidence cannot produce pass;
- SC-05: clinical and community review cannot be bypassed by automation or sales;
- SC-06: output communicates limitations and unresolved risk;
- SC-07: synthetic execution is isolated and cleaned up;
- SC-08: invalid packs and prior receipts can be withdrawn.

Release evidence for these subclaims is enumerated in [Release checklist](15-V1-RELEASE-CHECKLIST.md).

## 7. Hazard controls

| Hazard | Control | Release evidence |
|---|---|---|
| HAZ-01: GI used as clinical proxy | distinct schema, A-020, negative fixtures | test report |
| HAZ-02: missing LIS range looks normal | A-027–A-030, XFAIL fixture | seeded-fault evaluation |
| HAZ-03: deadname exposed | context-specific display assertions and minimization | accessibility/manual review |
| HAZ-04: uncertain expectation encoded as truth | oracle status, dual review, indeterminate outcome | approval ledger |
| HAZ-05: synthetic record affects operations | namespace, suppression, dry run, cleanup | pilot attestation |
| HAZ-06: real PHI ingested | no-PHI boundary and fail-closed preflight | canary test/tabletop |
| HAZ-07: receipt treated as certification | bounded claims, watermark, contract, comprehension test | counsel/claims review |
| HAZ-08: community consultation is extractive | pay parity, decision rights, withdrawal, conflict policy | compensation and approval records |
| HAZ-09: published project material helps someone locate trans patients or pressure the organizations serving them | [publication policy](17-PUBLICATION-POLICY.md) three-class rule, named approvers with a community co-chair veto, no instance material ever, re-review of already-public material before a governed pack lands | recorded publication decisions, the pre-B-009 re-review record, and TB-10/T-16 in the reviewed threat model |
| HAZ-10: public contribution outs a contributor or reviewer | attribution choice offered before first contribution, pseudonymity accepted, no roster or acknowledgement without individual written consent | consent records and the absence of any published roster |

## 8. Legal and regulatory posture

This section is planning guidance, not legal advice. US healthcare and state rules change; licensed counsel must review the actual product, contracts, claims, customers, and jurisdictions.

### FDA and clinical decision support

Intended v1 use is quality assurance in a synthetic, non-production environment. It compares staged system behavior with a pre-approved test oracle. It does not analyze a real patient's data, recommend diagnosis/treatment, control a device, select a patient-specific reference interval, or provide an alert used in care.

That intended use may reduce—but does not eliminate—FDA device-software risk. Before pilot and each new clinical function, counsel must analyze the shipped function and claims against FDA's January 2026 *Clinical Decision Support Software* guidance and document whether the function is a device, non-device CDS, enforcement-discretion function, or another category. Marketing and actual use must match. RIS/DICOM, live CDS evaluation, production canaries, automated clinical recommendations, or patient-specific inputs trigger a fresh analysis.

### Unauthorized practice of medicine and law

ContextSafe does not practice medicine: it does not create local clinical policy, diagnose, prescribe, select treatment, or tell a clinician how to manage a real patient. A licensed customer clinical owner approves local or disputed clinical expectations.

ContextSafe does not practice law: it does not declare compliance, interpret regulations for a customer's facts, or provide legal conclusions. Counsel reviews claims and contracts. “UPL” and unauthorized/unlicensed practice of medicine risks must be evaluated per state; labels alone are insufficient if conduct crosses the boundary.

### HIPAA and health privacy

V1 contractually and technically excludes PHI. Synthetic data are not automatically de-identified data, and a customer mistake can introduce PHI. Counsel determines whether ContextSafe is a business associate for each delivery model; do not claim “HIPAA does not apply” categorically. If PHI is suspected, stop and follow [incident response](06-SECURITY-PRIVACY-THREAT-MODEL.md).

Also review applicable state health-data, biometric, breach, employment, and consumer-protection laws. The safest posture is not to collect the data.

### Certification and interoperability

HL7, FHIR, DICOM, and ASTP/ONC materials inform the test. ContextSafe is not an HL7 or government certification unless formally authorized. Avoid official logos or wording that implies endorsement. Certification test methods can be inputs; ContextSafe's installed-workflow receipt is a different claim.

### Civil rights and nondiscrimination

Federal and state nondiscrimination requirements are legally and politically volatile. ContextSafe should sell consistent patient safety and data integrity, not promise that a receipt proves compliance with any current civil-rights regime. Counsel owns legal updates; governance owns patient-safety continuity even when certification requirements change.

### Contracts and insurance

Before paid pilot, obtain:

- master services and scoped SOW;
- no-PHI/data-boundary schedule;
- customer responsibility for staging isolation, local clinical policy, release decision, and cleanup;
- confidentiality and security incident duties;
- intellectual-property terms for core pack, local mappings, and feedback;
- limitation-of-liability and indemnity review;
- no-third-party-beneficiary and no-certification language where appropriate;
- publication/case-study consent;
- technology E&O, cyber, and any counsel-recommended professional/medical coverage.

Do not use disclaimers to excuse negligent methods or known defects.

## 9. Claims policy

Allowed with evidence:

- “evaluated 36 governed assertions across four named checkpoints”;
- “detected a mismatch between these observed fields”;
- “the partner rerun no longer reproduced finding F”;
- “the receipt passed integrity verification.”

Disallowed:

- “certifies trans-safe care”;
- “proves compliance”;
- “eliminates bias”;
- “covers every transgender patient”;
- “clinically correct reference ranges for trans people”;
- “FDA-approved,” “ONC-certified,” or “HL7-certified” without actual authorization;
- “no real competitor” as a fact.

Every external artifact shows scope, date, pack version, system versions, exclusions, indeterminate count, and the statement that results are not patient-specific medical advice or certification.

## 10. Conflicts, compensation, and independence

- Reviewers disclose relevant vendor, employer, research, advocacy, and financial relationships.
- A source author may advise but does not solely approve an assertion relying on their work.
- Community and clinical reviewers receive comparable expert compensation for comparable work.
- Customer-funded local assertions are labeled local and cannot enter core solely because the customer paid.
- Sales targets never determine pack content, severity, or finding closure.
- Reviewer dissent is preserved in decision records.

## 11. Change, appeal, and withdrawal

### Normal change

Proposal → evidence review → clinical/community review → fixture evaluation → release note → customer notification.

### Appeal

A customer may appeal applicability, technical observation, or clinical expectation. The original evidence is frozen. An independent reviewer not involved in the original decision evaluates the appeal. The receipt retains the original and appeal outcomes.

### Emergency withdrawal

If an assertion may cause harm or materially wrong results:

1. Clinical chair or community co-chair places it on hold.
2. Pack registry marks affected versions withdrawn within one business day.
3. Customers with affected receipts are notified directly.
4. Receipt verifier reports the withdrawal.
5. Governance determines correction, replacement, or retirement.
6. Prior receipts remain immutable but visibly invalidated for reliance on that assertion.

## 12. Regulatory and evidence watch

Review quarterly and before each pack release:

- HL7 Gender Harmony published and continuous builds;
- FHIR extension packages and US Core/USCDI changes;
- HL7 v2 Gender Harmony adoption;
- DICOM Supplement 233;
- ASTP/ONC certification/test-method changes;
- FDA CDS and device-software guidance;
- peer-reviewed laboratory guidance and safety reports;
- applicable federal/state privacy and practice rules.

Automated change detection may alert; a named qualified human determines relevance.

## 13. Governance launch gates

Before pilot:

- charter signed;
- reviewer roster and compensation approved;
- conflict disclosures complete;
- core case necessity review complete;
- intended-use/legal memo complete;
- [publication policy](17-PUBLICATION-POLICY.md) adopted or amended, and its class-2 posture decided;
- at least pack 0.1 dual-approved;
- dispute, withdrawal, and incident table-tops complete.

Before v1:

- pack 1.0 approvals and dissent published in the private release ledger;
- all high hazards have evidence;
- one external pilot reviewed by the group;
- reviewer workload and wellbeing retrospective complete;
- next review dates funded and scheduled.

## 14. Publication of project material

**A tool that reports where transgender and nonbinary identity data is lost is, in
the same breath, reporting where it is retained.** Governance therefore owns not
only what this project asserts but what it says in public, because a governed
pack is a list of where to look and a finding about loss is a statement about
retention. [Security §1 and T-16](06-SECURITY-PRIVACY-THREAT-MODEL.md) carry the
threat; the [publication policy](17-PUBLICATION-POLICY.md) carries the rule.

Four points belong here because they are governance decisions rather than
security controls:

- **Approval has an owner.** The decision-rights table in section 3 now assigns
  it. Method and concept material is open. Locator material — the pack payload,
  mapping profiles, and anything that names a field at a boundary — requires the
  clinical safety chair and the community co-chair, and **cannot be published at
  all while either chair seat is unfilled.** The unrecruited
  governance group is the gate on that class, not an excuse for skipping it.
- **The community co-chair may stop a publication alone**, on the same footing as
  an emergency assertion hold in section 11, and before that role is filled any
  compensated community reviewer may. The people whose exposure is the subject
  get a stop, not a vote.
- **Publication is irreversible in the way that matters.** A repository can be
  made private again; it cannot be made unread. Removal is a forward-looking
  signal, not an undo, and this project's own audit shows a deleted document
  remaining one command away in history.
- **Some publication is required, not merely permitted.** Withdrawn assertions,
  corrections, and limitations are published under sections 9 and 11. Nothing in
  this section may be used to suppress a finding that a customer or the public
  needs; the classes restrict where identity data lives, not whether this project
  admits when it was wrong.

The policy is a proposed decision document with open options and a recommendation
for each. Until its decision record names a date, this project's operative
posture is the interim rule above.
