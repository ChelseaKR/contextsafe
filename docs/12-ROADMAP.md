# Roadmap to v1.0

Status: proposed 10-month / 40-week path  
Owner: founder  
Planning unit: elapsed weeks after funded start

## 1. Now, next, later

### Now — validate and bound, months 0–2

Outcomes:

- buyer, staging, and evidence-access hypotheses tested;
- design-partner LOI and funded readiness work;
- governance group established and paid;
- pack 0.1 and receipt prototype reviewed;
- intended-use and data-boundary legal memo;
- ADR 0001 accepted.

Do not build adapters before the discovery gate passes.

### Next — build and start pilot, months 2–7

Outcomes:

- deterministic local runner and schemas;
- twelve-case pack with governed core assertions;
- file import, normalization, evaluator, review, receipt, and verification;
- security, privacy, accessibility, EN/ES, and operations gates;
- gated external-pilot setup and the six-week baseline.

### Later — complete pilot, release, and learn, months 7–10

Outcomes:

- v1.0 hardening and signed release;
- annual-assurance conversion;
- second-partner transferability test;
- only then, P1 FHIR collection/delta/mapping improvements.

RIS/DICOM, pharmacy, CDS, hosted collaboration, and production canaries remain beyond v1 and require separate governance.

## 2. Milestones

| Milestone | Target | Outcome/exit |
|---|---:|---|
| M0 Discovery decision | week 4 | discovery continue gate passes |
| M1 Governance and pack alpha | week 8 | reviewers approve scope and pack 0.1 |
| M2 Deterministic vertical slice | week 12 | one case imports, evaluates, reviews, renders, verifies |
| M3 Full reference pathway | week 17 | 12 cases/36 assertions run on fixtures |
| M4 Trust beta | week 21 | security/a11y/i18n/ops gates and hidden faults pass |
| M5 External pilot baseline | week 27 | after six elapsed pilot weeks, at least 10 cases complete the partner pathway |
| M6 Remediation receipt | week 33 | after the full 12-week pilot, partner uses verified P0 delta and utility/control-value evidence in release decision |
| M7 v1.0 | week 40 | release checklist and commercial conversion gate pass |

## 3. Workstream sequence

| Weeks | Product/research | Governance/evidence | Engineering | Trust/operations | Commercial |
|---:|---|---|---|---|---|
| 1–4 | interviews, workflow, buyer | recruit reviewers | paper schemas only | initial threat/legal boundary | LOI/readiness offer |
| 3–8 | pilot design | pack 0.1, oracle protocol | architecture spikes | privacy/a11y plan | SOW/security packet |
| 7–12 | usability prototype | assertions reviewed | vertical slice | base CI/security | paid pilot close |
| 11–17 | operator tests | pack beta | all file adapters/evaluator | logs/signing | partner mapping |
| 16–21 | comprehension tests | hidden fault authors | hardening/P0 delta | a11y/EN-ES/runbooks | pilot prep |
| 20–21 | contracting and calendar preparation only; no measured pilot activity | final gate review | no partner execution | finish DG-04 evidence | sponsor scheduling |
| 22–27 | pilot phases A–C: safety setup, mapping, dry run, baseline | baseline adjudication | partner-local execution and adapter fixes only | incident/cleanup exercises | time-study baseline |
| 28–33 | pilot phases D–E: remediation, rerun, closeout | finding disposition | delta and compatibility evidence | closeout/cleanup evidence | renewal proposal |
| 33–37 | release feedback or frozen extension measures | pack 1.0 | unaffected hardening; B-057 only in weeks 34–37 if invoked | independent reviews continue | conversion or priced extension |
| 38–40 | final decision | pack 1.0 freeze | release candidate | independent dossier close | conversion/reference |

## 4. Decision gates

- DG-01 week 4: build only with design partner, owners, evidence access, and legal path.
- DG-02 week 8: encode only dual-approved assertions; experimental content cannot influence mandatory pass.
- DG-03 week 12: continue custom engineering only if vertical slice is understandable to all core personas.
- DG-04 week 21: start the 12-week pilot in week 22 only after safety properties, PHI canaries, and accessibility critical paths pass; pre-gate contracting and scheduling do not authorize a dry run or case execution.
- DG-05 week 27: continue after the baseline only if evidence completeness is at least 75% and no boundary incident remains unresolved.
- DG-06 week 33: release candidate only if the full 12-week pilot's technical/safety gates and predeclared utility/control-value gate pass, or B-057's single bounded, separately funded extension is formally invoked. The extension may run in weeks 34–37 only; if it consumes release-critical hardening capacity, DG-07 moves.
- DG-07 week 40: release v1 only with external use, legal approval, and funded maintenance.

## 5. Capacity checkpoint

- `F` product/delivery pool: 252.5 available days; 139 baseline assigned, 143 maximum with B-057.
- `E` engineering pool: 170 available days; 124 baseline assigned, 130 maximum with B-057.
- Specialists/participants: 380 budgeted hours; 345 maximum assigned.
- Base B-001–B-056: 263 core days. Maximum with B-057: 273 of 422.5, leaving 149.5 days.
- DG-01 temporal checkpoint: `F` 31 available / 27 assigned; `E` 20 / 3.
- DG-04 temporal checkpoint: `F` 146.5 available / 127 assigned; `E` 105 / 99. The `E` pool is 94.3% loaded at this gate, so no added scope is permitted and a forecast consuming the six-day reserve adds capacity or moves DG-04.

No role exceeds total funded capacity, including the extension. Temporal gate capacity, not total-program slack, controls entry to the pilot. A scope change must remove equivalent work, add named capacity, or move the date.

## 6. P1 fast follows

Prioritize using observed pilot time:

1. Advanced multi-receipt/cross-profile comparison if the mandatory P0 delta still leaves more than 2 hours of analysis per rerun.
2. Mapping workbench if mapping exceeds 30% of delivery time.
3. Read-only FHIR adapter if repeated collection is safe and broadly reusable.
4. JUnit/SARIF if release-engineering integration drives renewal.
5. Full Spanish execution guidance if operator demand is validated.
6. Customer-local extension namespace if two partners need the same extension mechanism.

No P1 begins before v1 P0 evidence is complete unless it removes a pilot blocker without expanding safety scope.

## 6. Later exploration

### RIS/DICOM

Requires DICOM Supplement 233 implementation research, imaging informatics lead, radiologist, modality/vendor staging access, and a distinct safety pack.

### Pharmacy

Requires pharmacist governance, e-prescribing/label workflow mapping, patient communication risk analysis, and no assumption that EHR behavior transfers.

### CDS

Requires fresh FDA/device analysis, clinical-specialty oracles, automation-bias evaluation, and strict separation from patient-specific advice.

### Hosted control plane

Requires five annual customers or equivalent demand, security staffing, tenancy architecture, BA/HIPAA analysis, SOC 2 procurement evidence, and a separate ADR.

### Production synthetic canaries

Requires proof they cannot affect billing, reporting, care, patient contact, inventory, or analytics; new legal, privacy, vendor, and patient-safety approval. This is a new product, not a configuration toggle.

## 7. Resourcing changes

Add a part-time interoperability engineer when partner mapping exceeds 20 `F`-pool hours/week. Add an operations/customer-success owner at five active annual customers. Add a dedicated clinical safety officer before any patient-specific, production, CDS, imaging, or pharmacy expansion. Governance/community review remains paid and independent at every scale.

## 8. Roadmap anti-goals

- Do not count repositories, adapters, or assertions as success.
- Do not broaden beyond four checkpoints to rescue weak buyer demand.
- Do not build hosted collaboration for one procurement request.
- Do not claim external validation from reference fixtures.
- Do not turn indeterminate clinical questions into configurable passes.
- Do not ship a “trans-safe score.”
