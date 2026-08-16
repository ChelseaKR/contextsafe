# Service design

Status: proposed v1 delivery model  
Owner: service lead/founder

## 1. Service promise

ContextSafe helps a health system test a named non-production release against a reviewed synthetic pack and leave with a traceable receipt. It promises disciplined observation and review, not certification or proof of safety.

## 2. Service blueprint

| Phase | Customer-facing action | ContextSafe action | Evidence | Fail-safe |
|---|---|---|---|---|
| Qualify | Describes pathway, release, owners, and environment | Screens fit, buyer, data boundary, and conflicts | qualification record | decline if no safety/technical owner |
| Contract | Approves SOW and no-PHI schedule | Defines intended use, incident duties, publication boundary | signed charter | no access before signatures |
| Map | Shows staging workflow and exports | Maps checkpoints and local codes | system/field map | unknown transformations stay gaps |
| Dry run | Creates CTP-001 and performs cleanup | Validates namespace and collection method | dry-run receipt | stop on PHI or downstream leakage |
| Execute | Runs cases and exports observations locally | Facilitates, hashes, validates, and evaluates | run evidence | invalid evidence cannot pass |
| Review | Technical and clinical owners inspect findings | Explains boundaries; convenes governance for disputed expectations | disposition log | machine cannot close findings |
| Remediate | Changes configuration or interface | Maintains test baseline; does not prescribe care | change references | scope changes require approval |
| Rerun | Repeats affected cases | Creates delta and final receipts | signed receipt | stale or partial rerun is labeled |
| Close | Makes release decision and confirms cleanup | Transfers artifacts, deletes temporary copies, runs retrospective | closeout attestation | unresolved risk remains visible |
| Maintain | Schedules release or annual reruns | Updates pack with governed change notes | renewal receipt | recalled assertions are blocked |

## 3. Roles

### Customer

- Executive sponsor: owns budget and release-risk decision.
- Clinical safety owner: accepts or blocks clinical residual risk.
- Laboratory owner: approves LIS behavior and local range policy.
- Technical owner: controls staging, mappings, exports, and cleanup.
- Release owner: integrates the receipt into the release process.
- Privacy/security owner: approves the boundary and responds to incidents.

### ContextSafe

- Engagement lead: accountable for scope, schedule, and customer communication.
- Product/research delivery lead: shares `F`-pool research, planning, service, and evidence-delivery work under a named assignment; has no inherited safety approval authority.
- Test engineer: validates mappings, evaluates evidence, and reproduces results.
- Clinical safety chair: approves clinical oracle and adjudicates uncertainty.
- Community co-chair: approves representation, language, and community harms.
- Laboratory reviewer: approves lab assertions.
- Security/privacy lead: approves access and handles incidents.
- Accessibility/language reviewer: validates EN/ES artifacts.

One person may hold multiple ContextSafe operational roles, but the founder may not self-approve clinical, community, security, and release work. Independence requirements are in [Governance](07-GOVERNANCE-LEGAL-SAFETY.md).

## 4. RACI

| Decision/activity | F product/delivery pool | Customer technical | Customer clinical | ContextSafe clinical | Community co-chair | Security | Executive sponsor |
|---|---|---|---|---|---|---|---|
| Engagement fit | R | C | C | C | C | C | A |
| Environment and namespace | C | R/A | I | I | I | C | I |
| Core pack approval | R | C | C | A | A | C | I |
| Local mapping | C | R/A | C | C | I | C | I |
| Clinical expected behavior | I | C | C | R/A | C | I | I |
| Representation/language | C | I | C | C | R/A | I | I |
| PHI boundary | C | R | I | I | I | A | I |
| Finding calculation | R/A | C | I | C | I | I | I |
| Finding disposition | C | R | A | A* | C | C | I |
| Release decision | I | C | R | C | I | C | A |
| Public claim/case study | R | C | C | C | C | C | A |

Dual A on pack approval is intentional: clinical and community approvals are both required. `A*` applies only when a customer accepts a clinical residual risk: the customer clinical owner owns the local operational risk and the customer/executive release decision, while the ContextSafe clinical chair independently confirms the governed expectation, severity, and bounded disposition record. Both sign; neither can substitute for the other. For remediate, defer, or release-blocked dispositions, ContextSafe clinical is consulted unless another governance rule requires approval.

## 5. Intake checklist

- Named release and date.
- Systems, versions, interface engine, and LIS.
- Non-production topology.
- Synthetic-record policy and identifier namespace.
- Export formats and evidence custody.
- Local GI/SPCU/RSG/name/pronoun definitions.
- Laboratory range and abnormal-flag policy.
- Required vendors and approval windows.
- Accessibility and language needs.
- Security, procurement, insurance, DPA/BAA position.
- Conflict-of-interest and publication preference.

## 6. Standard engagement package

### Deliverables

- One workflow and field map.
- One dry-run assessment.
- One execution of core pack 1.x.
- Up to two mapping profiles.
- Baseline receipt and one remediation rerun.
- Joint finding review and executive readout.
- Ninety days of receipt correction support for tool defects.

### Explicit exclusions

- Production access.
- Vendor configuration work.
- Clinical policy creation.
- Legal/compliance certification.
- More than two interfaces or one LIS.
- Ongoing monitoring.
- Custom application development.

Changes use a written change request with hours, price, safety review, and schedule impact.

## 7. Customer journey and service levels

| Moment | Desired experience | Measure |
|---|---|---|
| Qualification | Clear yes/no within 5 business days | 90% on time |
| Kickoff to dry run | Controlled and understandable | median 10 business days |
| Evidence rejection | Specific, private, actionable | 100% location and recovery guidance |
| Finding review | No surprises or score theater | 100% findings shown with limitations |
| Critical safety finding | Fast human response | acknowledge in 4 business hours |
| Receipt correction | Versioned, never overwritten | correction issued in 2 business days after validation |
| Pack recall | Direct and explicit | notify affected customers in 1 business day |

Operational objectives and escalation are in [Operations](10-OPERATIONS-SRE.md).

## 8. Finding severity

- CS-1 Critical: credible pathway to unflagged critical result, wrong-patient action, patient exposure, or other imminent serious harm. Release recommendation: block; notify customer safety owner immediately.
- CS-2 High: likely clinical or identity harm with no reliable downstream recovery. Release recommendation: remediate or the customer clinical owner accepts documented residual risk with a separate ContextSafe-clinical-chair signature confirming the governed expectation, severity, and bounded record.
- CS-3 Moderate: localized harm or workflow defect with a reliable recovery. Release recommendation: owner/date required.
- CS-4 Low: usability, language, or evidence-quality defect without plausible immediate harm. Release recommendation: backlog with rationale.
- Indeterminate: insufficient or disputed evidence. It is not a lower severity and is never pass.

Severity is assigned by the approved rubric and confirmed by a human. ContextSafe advises; the customer owns its release.

## 9. Disputed findings

1. Freeze the outcome as disputed; do not change it to pass.
2. Separate technical observation from clinical interpretation.
3. Obtain source and local policy from both views.
4. Clinical disputes go to two independent clinical reviewers; representation disputes go to the community co-chair plus another reviewer.
5. Record majority and dissent; no anonymous override.
6. If unresolved by the release date, report indeterminate with the potential severity.

## 10. Support boundaries

Supported: pack validation, mapping interpretation, runner defects, receipt verification, evidence custody, and the agreed test protocol.

Unsupported: treatment advice, real-patient troubleshooting, emergency clinical response, production system administration, interpreting law, or making the customer's release decision.

Clinical emergencies use the customer's established channels, not ContextSafe support.

## 11. Service improvement

After each engagement, measure `F/E` pool hours by activity, custom mappings, blocked steps, support volume, false findings, customer comprehension, and renewal objection. Update the standard service only when the change preserves [ADR 0001](adr/0001-v1-boundary.md) and is approved through governance.
