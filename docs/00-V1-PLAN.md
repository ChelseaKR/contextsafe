# ContextSafe v1.0 master plan

Status: proposed implementation baseline  
Planning horizon: 10 months / 40 weeks from funded start  
Delivery assumption: an `F` product/delivery pool staffed by one product/technical founder at 0.8 FTE for weeks 1–40 plus one product/research delivery lead at 0.75 FTE for weeks 1–8 and 0.5 FTE for weeks 9–33; an `E` engineering pool staffed by one senior implementation engineer at 1.0 FTE for weeks 1–28 and 0.5 FTE for weeks 29–40; and contracted clinical, laboratory, interoperability, accessibility, security, legal, and trans-community reviewers  
Decision owner: founder until a governing clinical safety group is constituted

## 1. Outcome

Ship a service-assisted, local release gate that a US health system can use in a non-production registration-to-LIS pathway. V1.0 must evaluate a clinically approved synthetic pack, preserve an auditable evidence chain, and generate an accessible receipt that release decision-makers can understand.

V1.0 is not complete because a CLI exists. It is complete only when one external design partner has run the pack end to end, reproduced the receipt, remediated or dispositioned every finding, obtained both mandated review signatures for every accepted clinical residual risk, and confirmed that the receipt was used in a real release decision.

## 2. Problem and thesis

Health systems can implement demographic fields correctly in one product and still lose, coerce, or misuse the information at an interface boundary. The first wedge is a small, clinically governed pack that exposes those integration failures and leaves a durable receipt.

The commercial thesis is service-first:

- customers buy an expert implementation and safety review;
- the local runner makes delivery consistent and repeatable;
- an annual subscription maintains the pack, reruns it after releases, and records deltas;
- productization follows repeated evidence, not speculative integration work.

The novelty claim is intentionally narrow. Synthetic patients, FHIR conformance tools, and quality-assurance frameworks already exist. The differentiated hypothesis is that no established offering packages transgender/nonbinary clinical-context assertions, cross-system execution, clinical/community adjudication, and release evidence into this focused workflow. Validate that claim continuously; do not publish “no competitors.”

## 3. V1 contract

### Included

- Four checkpoints: registration export, EHR representation, outbound HL7 v2 or FHIR representation, and LIS result returned to the EHR.
- Twelve canonical synthetic patients and at least 30 mandatory assertions defined in [Data and evidence](05-DATA-AND-EVIDENCE.md).
- File inputs: canonical JSON, FHIR R4 JSON, captured messages created only from the approved synthetic staging cases in HL7 v2 text, and a constrained LIS-result CSV/JSON mapping. Real records are never copied and redacted into fixtures.
- Local deterministic evaluation.
- JSON receipt and static WCAG 2.2 AA HTML report.
- English authoring and complete Spanish user-facing receipt strings.
- Named technical, clinical, laboratory, and community review.
- Customer-run staging execution with ContextSafe facilitation.

### Excluded

- Production traffic, real patient data, or continuous surveillance.
- Universal write adapters or robotic user-interface automation.
- RIS/DICOM, pharmacy, billing, and CDS execution.
- A hosted multi-tenant application.
- Clinical treatment recommendations or a universal reference-range policy.
- Regulatory certification or a hospital safety grade.
- Generative AI in any decision or evidence path.

The rationale and change rule are in [ADR 0001](decisions/0001-v1-boundary.md).

## 4. Workstreams and accountable outcomes

| Workstream | Accountable outcome | Primary document |
|---|---|---|
| Product | Approved problem, users, requirements, and metrics | [PRD](01-PRD.md) |
| Research | Evidence that teams will run and act on the test | [Research and pilot](02-USER-RESEARCH-AND-PILOT.md) |
| Service | Repeatable intake-to-remediation delivery | [Service design](03-SERVICE-DESIGN.md) |
| Engineering | Small local runner and stable schemas | [Architecture](04-ARCHITECTURE.md) |
| Clinical and evidence | Reviewed cases, assertions, and provenance | [Data and evidence](05-DATA-AND-EVIDENCE.md) |
| Trust | No-PHI enforcement and bounded claims | [Security](06-SECURITY-PRIVACY-THREAT-MODEL.md) and [Governance](07-GOVERNANCE-LEGAL-SAFETY.md) |
| Inclusion | WCAG 2.2 AA and viable EN/ES output | [Accessibility and i18n](08-ACCESSIBILITY-I18N.md) |
| Quality | Reproducibility and safety-property gates | [Test strategy](09-TEST-AND-EVALUATION.md) |
| Reliability | Supported local execution and incident handling | [Operations](10-OPERATIONS-SRE.md) |
| Business | Paid pilot, pricing, channel, and renewal hypothesis | [GTM](11-GTM-BUSINESS-MODEL.md) |

## 5. Stage plan

| Stage | Calendar | Deliverable | Exit gate |
|---|---:|---|---|
| 0. Discovery | Weeks 1–4 | 15 interviews, workflow map, buyer map, evidence-access assessment | At least 3 systems confirm the problem and 1 signs a design-partner LOI |
| 1. Clinical foundation | Weeks 3–8 | Case pack v0.1, assertion protocol, reviewer charter, terminology decisions | Two clinicians, one lab leader, and two compensated trans reviewers approve scope |
| 2. Thin evaluator | Weeks 7–12 | Schema validator, canonical observation import, deterministic evaluation, JSON receipt | Reference fixtures reproduce byte-equivalent normalized results |
| 3. Workflow adapters | Weeks 11–17 | FHIR R4 parser, HL7 v2 parser, LIS mapping template, static report | Twelve cases can be evaluated from fixture evidence at all four checkpoints |
| 4. Internal validation | Weeks 16–21 | Security review, accessibility review, red-team pack, operations runbooks | All P0 safety gates pass; no open critical/high issue |
| 5. Design-partner pilot | Weeks 22–33 | Twelve-week staging pilot from safety setup through release-decision observation, utility study, remediation rerun, and signed pilot receipt | Pilot success thresholds in section 7 pass or the one-time evidence extension is explicitly invoked |
| 6. V1 hardening | Weeks 33–40 | Versioned pack 1.0, migration notes, support package, pricing, release | Every item in [release checklist](15-V1-RELEASE-CHECKLIST.md) has evidence |

Stages overlap only when their prerequisites are satisfied. Weeks 20–21 may contain contracting, scheduling, and partner preparation, but no pilot dry run, evidence import, case execution, or measured pilot activity begins before DG-04 passes at the end of week 21. Non-pilot-dependent hardening may overlap the pilot closeout in week 33; release-dossier work that consumes pilot evidence cannot. A discovery failure pauses engineering. The founder must not compensate for missing clinical governance with more code.

## 6. Capacity and estimate

The detailed backlog contains **263 baseline core-team days**, a separately costed **10-day conditional evidence-extension reserve**, and **345 explicitly scheduled specialist/participant hours**. The funded model supplies **422.5 core-team days** (252.5 `F`-pool days plus 170 `E`-pool days) and budgets **380 specialist hours**. Base work leaves 159.5 core days; even if the one extension is invoked, 149.5 core days and 35 specialist hours remain. Every B-001–B-057 item has an explicit `F/E` split in the backlog. `F` tasks are assigned between the founder and delivery lead before each stage; that staffing split never grants the delivery lead a clinical, community, security, or legal approval right. At each decision gate, re-estimate remaining P0 work. A role above 90% of its elapsed checkpoint capacity freezes additional scope; any forecast above available capacity, or any erosion of the stated gate reserve, requires named capacity or a moved gate rather than compressed review.

| Capacity ledger | Available / assigned | Calculation or source |
|---|---:|---|
| `F` product/delivery pool | 252.5 days available | founder: 0.8 × 40 × 5 = 160; delivery lead: 0.75 × 8 × 5 + 0.5 × 25 × 5 = 92.5 |
| `E` engineering pool | 170 days available | 1.0 × 28 × 5 + 0.5 × 12 × 5 |
| Core team, baseline | 422.5 available / 263 assigned | B-001–B-056; 159.5-day reserve |
| Core team, maximum with extension | 422.5 available / 273 assigned | B-001–B-057; 149.5-day contingency |
| Specialists and participants | 380 hours budgeted / 345 maximum assigned | B-001–B-057; 35-hour contingency |

Temporal loading is independently gated; total-program slack cannot rescue a missed early milestone:

| Checkpoint | `F` capacity / assigned | `E` capacity / assigned | Rule |
|---|---:|---:|---|
| End of week 4 / DG-01 | 31 / 27 days | 20 / 3 days | 4 `F` days and 17 `E` days remain; all B-001–B-007 dependencies must be complete |
| End of week 21 / DG-04 | 146.5 / 127 days | 105 / 99 days | 19.5 `F` days and 6 `E` days remain; `E` is at 94.3%, so scope is frozen and any slip beyond six days adds capacity or moves the pilot |

Week-4 capacity is founder 16 days plus delivery lead 15; week-21 `F` capacity is founder 84 plus delivery lead 62.5. Week-21 assignments are B-001–B-048, which must finish before B-049. The ledger is a ceiling, not permission to pull post-gate work forward.

Planning cash envelope, excluding founder compensation but including the product/research delivery lead, engineering pool, and specialists: **USD 285,000–500,000**. This assumes 92.5 paid delivery-lead days, 170 paid engineering days, and up to 380 specialist/participant hours; contracting rates, reviewer mix, counsel, and interoperability support drive the range. A paid pilot should fund a material share of post-discovery delivery but is not assumed to finance the entire V1 build.

## 7. Objective gates

### Discovery continue gate

Continue into implementation only when all are true:

- 15 completed interviews across at least 3 health systems and 5 roles.
- At least 8 interviewees report a recent identity or clinical-context failure, a manual check, or an untested boundary.
- One design partner signs an LOI naming an executive sponsor, technical owner, clinical owner, staging pathway, and target release.
- The partner can create obviously synthetic records and export required observations without sending ContextSafe PHI.
- Preliminary legal review finds the intended-use language defensible.

Kill or reposition if no funded owner emerges, staging access is impossible, or clinical reviewers cannot agree on a minimum safe assertion set.

### Pilot success gate

The pilot succeeds only if:

- at least 10 of 12 cases reach all four checkpoints;
- at least 95% of mandatory evidence fields are available;
- the evaluator yields zero unexplained nondeterministic outcomes in three repeated runs;
- every finding has an owner and disposition, and every accepted clinical residual risk has distinct customer-clinical-owner and ContextSafe-clinical-chair signatures with their non-substitutable responsibilities stated;
- the partner reruns after remediation and uses the receipt in a documented release decision;
- the predeclared utility study shows at least 20 net partner staff-hours avoided versus comparable prior evidence/release work, **or** the sponsor documents a named risk/control outcome and accepts a paid continuation at the tested price;
- the sponsor agrees to a paid annual continuation or gives a specific, falsifiable reason not to.

Naturally occurring partner defects are reported by CS-1–CS-4 severity and are never a success requirement or partner-selection criterion. Seeded-fault performance is the evaluator gate. If technical/safety gates pass but utility evidence is incomplete or falls between 10 and 19 net hours with a credible control-value signal, the release authority may authorize one bounded four-week evidence extension with a predeclared decision rule. Failure of a safety gate, non-use of the receipt, or less than 10 net hours with no priced continuation/control outcome after that extension is a stop or pivot.

### V1.0 release gate

V1.0 requires:

- 100% P0 requirement acceptance with committed evidence;
- 100% mandatory assertion traceability from source and reviewer through result;
- two independent clinical reviewers and two compensated trans-community reviewers approve pack 1.0;
- one independent laboratory-medicine reviewer approves LIS assertions;
- no critical or high security/safety risks remain unmitigated; accepted medium residual risks are named;
- WCAG 2.2 AA automated and manual gates pass in EN and ES;
- PHI canary tests fail closed;
- receipt verification detects any changed evidence, schema, pack, or result;
- all 41 published/hidden evaluation faults are detected and correctly localized; any miss blocks release;
- the external pilot success gate passes;
- legal counsel reviews claims, contract, intended use, FDA/CDS posture, UPL/UPM risk, HIPAA posture, and insurance;
- support, incident, withdrawal, and pack-recall procedures are exercised.

## 8. Kill and pivot rules

Stop or materially narrow the product if any occurs:

1. Two qualified clinical groups cannot reach a documented consensus on the core LIS assertions after two facilitated review rounds.
2. Three prospective partners refuse synthetic staging records or cannot extract observations without PHI.
3. A pilot fails a technical/safety gate, the sponsor does not use the receipt, or—after the single bounded extension—shows less than 10 net staff-hours saved and no paid continuation or named control-value outcome.
4. Legal review concludes the shipped evaluator is likely a regulated medical device or unlawfully practices medicine unless the scope changes.
5. Required vendor integration makes each engagement more than 120 `F`-pool hours before evaluation.
6. A general-purpose incumbent ships the same governed pack and workflow with stronger access and at least three reference customers.

Permitted pivots are: advisory-only test protocol; licensable case pack for an established test platform; insurer-sponsored assessment; or open standard with paid implementation.

## 9. Dependencies

| Dependency | Needed by | Owner | Fallback |
|---|---|---|---|
| Design-partner staging pathway | Stage 3 | partner technical owner | Use reference simulator; do not claim external validation |
| Clinical consensus on expected behavior | Stage 2 | clinical safety chair | Mark assertion indeterminate; never encode disputed guidance |
| HL7/FHIR and LIS mapping expertise | Stage 3 | interoperability reviewer | File mapping worksheet and manual review |
| Legal intended-use analysis | Before pilot | counsel | Advisory-only pilot; withhold product release |
| Trans-community governance | Before pack approval | community co-chair | Pause pack release |
| EN/ES translation and accessibility review | Stage 4 | language/accessibility leads | English-only private alpha, not v1 |

## 10. Traceability model

Identifiers are immutable once published:

- PER: persona
- JTBD: job to be done
- G: goal
- P0/P1/P2: requirement
- CTP: canonical test patient
- A: assertion
- E: evidence item
- CLM: receipt claim
- R: risk
- B: backlog item
- RG: release gate

The authoritative case/assertion catalog is [Data and evidence](05-DATA-AND-EVIDENCE.md). The requirement-to-test matrix is [Test and evaluation](09-TEST-AND-EVALUATION.md). Backlog estimates and dependencies are [Backlog](13-BACKLOG.md). Release evidence is [Release checklist](15-V1-RELEASE-CHECKLIST.md).

## 11. Decisions required before code

1. Approve the file-first, non-production-only boundary in ADR 0001.
2. Recruit and compensate the clinical and community governance group.
3. Choose whether HL7 v2 GSP segments are mandatory or a documented pre-adoption profile for the first partner.
4. Agree on how the first partner safely proves that a value is absent rather than merely unavailable in an export.
5. Obtain counsel's intended-use review and insurance recommendation.

No irreversible architecture decision is needed for a hosted product, production agent, or universal adapter in v1.
