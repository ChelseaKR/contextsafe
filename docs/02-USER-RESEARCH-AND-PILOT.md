# User research and design-partner pilot

Status: recruitment plan  
Owner: founder/research lead  
Safety approvers: community co-chair and clinical safety chair

## 1. Questions to answer

| Hypothesis | Evidence needed | Disconfirming evidence |
|---|---|---|
| H-01: cross-system gender-context defects are under-tested | Recent examples, test plans, incident or near-miss patterns across 3 systems | Existing end-to-end packs already cover the behavior reliably |
| H-02: a patient-safety or risk owner can fund this | Named budget, buying path, acceptable pilot price | Only unfunded DEI owners express interest |
| H-03: synthetic staging execution is feasible | Ability to create cases and export four checkpoints without PHI | Vendor or governance rules block synthetic staging records |
| H-04: a fixed core pack transfers across systems | At least 70% of mandatory assertions apply at two systems | Every system needs a fundamentally different clinical oracle |
| H-05: receipts improve release decisions | Sponsor attaches receipt to change record and acts on findings | Receipt is viewed as redundant paperwork |
| H-06: trans reviewers see net safety benefit | Reviewers approve scenarios, language, governance, and compensation | Reviewers find the model extractive or likely to increase surveillance |

## 2. Research cohorts

Complete 15–20 interviews before substantial implementation:

- 3 clinical informatics leaders.
- 3 interface-engine or EHR analysts.
- 2 laboratory medical directors or clinical chemists.
- 2 patient-safety, quality, malpractice-risk, or compliance buyers.
- 2 privacy/security leaders.
- 3 transgender or nonbinary patient advocates with healthcare-system experience.
- 2 EHR/LIS vendor or implementation specialists, where accessible.

Represent at least three health systems, including a safety-net or community setting. Do not recruit current patients through their care team. Pay community reviewers at the same expert hourly rate as other domain reviewers; budget USD 150–250 per interview or review session.

## 3. Interview protocol

### Workflow questions

1. Walk through the last registration, EHR, interface, or LIS release that changed demographic data.
2. Which systems and fields were checked end to end? Show the artifact if permitted.
3. Describe the last failure involving name, pronouns, gender identity, recorded sex/gender, reference ranges, or abnormal flags.
4. Where was the failure first visible? Who owned remediation?
5. How are X, unknown, declined, nonbinary, and null values represented?
6. What synthetic records can be created, and how are they prevented from reaching production operations?
7. What evidence is required to approve a release?
8. Who owns the risk, contract, and budget?
9. What would make an external test unsafe or impossible?
10. What would a useful receipt change in your decision?

### Community questions

1. Which scenarios feel representative, stereotyped, invasive, or missing?
2. Which data should never be present merely to make a test “complete”?
3. Where could a test itself cause outing, misgendering, or clinical harm?
4. What language should appear in staff-facing and patient-facing artifacts?
5. What decisions must community reviewers be able to block?
6. What compensation, attribution, confidentiality, and withdrawal terms are appropriate?

Do not ask participants to disclose their own medical history. Capture role and workflow, not identity-linked health data. Obtain explicit consent for recording; default to notes. Remove organizational attribution from synthesis unless authorized.

## 4. Synthesis and decision artifacts

- Current-state service blueprint.
- Boundary and field map per system.
- Buyer and procurement map.
- Problem frequency/severity evidence table.
- Assertion applicability matrix.
- Objection log.
- Harm and benefit analysis reviewed by community participants.
- Discovery decision memo against the gates in [V1 plan](00-V1-PLAN.md).

Raw notes are access-restricted, retained for 90 days after synthesis, and then deleted. De-identified insights retain participant ID, role category, date, consent scope, and analyst.

## 5. Design-partner profile

Select one partner with:

- an executive patient-safety or quality sponsor;
- a clinical informatics lead, laboratory lead, interface analyst, release owner, and privacy contact;
- a representative non-production registration → EHR → interface → LIS → EHR pathway;
- permission to create clearly synthetic records and export evidence;
- a material release within 12 weeks;
- willingness to remediate and rerun;
- a procurement path for a USD 75,000–125,000 pilot and USD 30,000–60,000 annual continuation;
- agreement that results remain confidential unless both parties approve publication.

Avoid a first partner whose only interest is publicity, a broad enterprise rollout, production monitoring, or a custom one-off interface.

## 6. Pilot phases

### Phase A — Contract and safety setup, weeks 1–2

- Sign SOW, data-boundary schedule, DPA or no-PHI addendum, confidentiality terms, incident duties, and publication terms.
- Name RACI participants and escalation contacts.
- Attest non-production environment and synthetic namespace.
- Complete a tabletop PHI exposure and rollback drill.
- Approve target release and success criteria.

Exit: clinical, technical, security, and executive owners sign the execution charter.

### Phase B — Workflow mapping, weeks 2–4

- Map systems, versions, interfaces, fields, transformations, and checkpoints.
- Select HL7 v2 or FHIR observation path.
- Map local codes without altering core assertions.
- Dry-run CTP-001 and prove cleanup.

Exit: one case reaches every checkpoint; evidence can be collected locally.

### Phase C — Baseline execution, weeks 4–6

- Run all 12 cases.
- Collect and hash evidence.
- Evaluate mandatory assertions.
- Jointly review failed, blocked, and indeterminate outcomes.

Exit: at least 10 cases have complete pathways; all gaps are named.

### Phase D — Remediation, weeks 6–9

- Partner prioritizes defects.
- ContextSafe provides boundary/evidence analysis, not clinical treatment advice.
- Any changed expectation returns to governance.
- Partner implements configuration or interface changes. Any accepted clinical residual-risk disposition is signed separately by the customer clinical owner and ContextSafe clinical safety chair; neither signature substitutes for the other, and the customer retains its release decision.

Exit: every finding has disposition, owner, and target date.

### Phase E — Rerun and closeout, weeks 9–12

- Re-execute affected and regression cases.
- Generate signed baseline/delta receipt.
- Observe the release decision meeting.
- Measure time, defects, comprehension, and perceived value.
- Conduct buyer renewal interview.

Exit: pilot decision memo and conversion proposal.

## 7. Pilot measures

| Measure | Collection | Success | Stop threshold |
|---|---|---:|---:|
| Cases completing 4 checkpoints | receipt | at least 10/12 | fewer than 8 |
| Mandatory evidence completeness | evaluator | at least 95% | below 75% |
| Seeded-fault evaluator performance | independent evaluation before partner run | all 41/41 faults (36 published and 5 independently authored hidden challenges) detected and correctly localized | any detection or localization miss; results are bounded to the authored corpus and make no unseen-fault sensitivity claim |
| Natural partner defects | CS-1–CS-4 disposition log, excluding seeded faults | report count/severity; no success quota | mishandling, concealment, or selection for defect richness |
| Net partner time/control value | predeclared comparable-release time study and priced renewal decision | at least 20 net hours saved, or named control outcome plus paid continuation | after one bounded extension: under 10 hours and no priced/control outcome |
| False positive rate | expert adjudication | under 5% | above 15% |
| Finding localization | analyst task timing | median under 30 minutes | above 2 hours |
| Receipt comprehension | 5-question task test | at least 90% | below 70% |
| Remediation verification | rerun | 100% of closed findings | below 80% |
| Sponsor use | observation/attestation | used in release decision | never reviewed |
| Commercial signal | proposal | annual conversion or specific objection | no buyer/next step |

Before execution, the partner selects at least three recent comparable release-assurance tasks and records the roles, artifacts, scope, and staff time used. Pilot time uses the same role/task boundaries. **Net hours saved** equals comparable baseline hours minus partner hours spent producing equivalent evidence and release decisions; training, ContextSafe product development, seeded-fault authoring, and remediation work outside the comparison are reported separately. Natural defects are outcomes, not product-success requirements. The measured pilot begins only after DG-04 at the start of global week 22; its relative weeks 1–12 map to global weeks 22–33. If all safety/technical gates pass but utility evidence is incomplete or between 10 and 19 hours with a credible control-value signal, the joint release authority may approve one four-week, evidence-only extension with frozen measures; there is no second extension. B-057 reserves at most 32 `F`-pool hours, 48 `E`-pool hours and 8 paid reviewer hours, funded by a USD 15,000–25,000 change order. The extension occupies global weeks 34–37 while unaffected hardening continues; if it consumes a release-critical owner or reduces remaining hardening below its gate, the week-40 release moves.

## 8. Research and pilot safety

- Use participant aliases in working material.
- Never recruit through coercive employer or care relationships.
- Provide a content note before reviewing misgendering or outing scenarios.
- Allow community reviewers to pause, remove, or rewrite a case without defending personal experience.
- Separate community approval from clinical approval; neither can overrule the other's domain.
- Never publish a partner's defects, screenshots, system names, or reviewer identities without written permission.
- Do not send raw messages or exports by email or consumer file-sharing.
- Stop immediately on suspected PHI and invoke [the incident procedure](10-OPERATIONS-SRE.md).

## 9. Pilot deliverables

1. Approved execution charter.
2. Partner profile and field mapping.
3. Environment attestation and cleanup evidence.
4. Baseline receipt.
5. Finding register with accountable dispositions.
6. Remediation delta receipt.
7. Accessibility-reviewed executive summary.
8. Pilot evaluation against success and kill gates.
9. Annual rerun proposal.

## 10. Learning review

At closeout, classify every customization:

- core: broadly reusable and eligible for governed pack inclusion;
- adapter: reusable technical mapping;
- local: partner-only requirement;
- service: process improvement;
- out of scope: should not be productized.

Two partners must independently need a customization before it enters the product roadmap, unless it closes a critical safety defect.
