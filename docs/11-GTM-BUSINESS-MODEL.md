# Go-to-market and business model

Status: hypothesis to validate  
Owner: founder  
Commercial principle: sell patient-safety evidence, not fear or a “trans-safe” badge

## 1. Beachhead

US health systems with:

- an active EHR, registration, interface, or LIS change;
- a mature patient-safety or clinical-informatics function;
- a staging environment and synthetic-record policy;
- a laboratory medical director and interface team;
- executive willingness to own the finding;
- procurement capacity for a USD 75,000–125,000 pilot.

Best early triggers:

- adding X/nonbinary registration values;
- implementing Name to Use, pronouns, GI, RSG, or SPCU;
- EHR/LIS migration;
- interface-engine upgrade;
- laboratory reference-interval redesign;
- patient-safety review after an identity-related incident or near miss.

Do not target individual trans patients, small clinics without staging capacity, or unfunded DEI teams as buyers.

## 2. Buyer and users

Economic buyer order to test:

1. Chief quality/patient safety or chief medical information officer.
2. Enterprise clinical informatics/digital health leader.
3. Risk management or malpractice insurer-sponsored safety program.
4. Laboratory/pathology leadership for a focused engagement.

Champions: interface analyst, informatics nurse/physician, EHR release lead, LGBTQ+ clinical program. Procurement stakeholders: privacy/security, legal, vendor management, insurance, IT operations.

## 3. Positioning

For health systems changing patient identity or clinical-context workflows, ContextSafe is a clinically and community-governed release test that follows synthetic cases across registration, EHR, interface, and LIS and produces a traceable receipt. Unlike component certification or generic synthetic data, it tests the installed multi-vendor pathway and exposes where meaning changes.

Use “test,” “evidence,” “observed,” and “reviewed.” Avoid “certified,” “compliant,” “bias-free,” “guaranteed,” or “safe hospital.”

## 4. Market landscape

| Category | Examples | What it solves | ContextSafe boundary |
|---|---|---|---|
| Synthetic patient/data generation | Synthea, Synset | creates reusable synthetic records/scenarios | ContextSafe uses a small governed pack and cross-system oracle |
| FHIR conformance | Inferno | tests FHIR implementations/IG conformance | ContextSafe tests installed semantic behavior across non-FHIR boundaries |
| Standards | HL7 Gender Harmony, DICOM | defines representations and exchange guidance | ContextSafe observes whether a local workflow preserves intended concepts |
| EHR/LIS QA and consulting | vendors, implementation firms, internal teams | broad implementation and regression testing | potential competitor, partner, or substitute |
| Patient-safety benchmarking | Leapfrog and quality programs | organizational practices and transparency | ContextSafe produces release-specific evidence, not a facility grade |

The packaged vertical may be novel; the methods are not. Before every major sales claim, update the competitive scan and interview customers about internal substitutes.

## 5. Offers and pricing hypotheses

### Readiness assessment — USD 7,500–12,000

- 2-week workflow/buyer/data-boundary assessment.
- One dry-run case or simulator.
- Fit, risks, and fixed pilot proposal.
- Credit 50% toward pilot signed within 30 days.

### Design-partner pilot — USD 75,000–125,000

- 10–12 weeks.
- One pathway, one LIS, up to two mappings.
- Core pack baseline, finding review, one remediation rerun, receipts.
- Customer provides staging operators and clinical/lab owners.
- Discount only in exchange for structured feedback, not public endorsement.

### Annual assurance — USD 30,000–60,000

- Pack updates and validity notifications.
- One planned annual rerun.
- Receipt verifier/support.
- Quarterly release-planning review.
- Additional release run: USD 8,000–15,000.

### Later channel offer

License the governed pack and delivery method to an established testing platform, EHR/LIS integrator, insurer, or quality organization. Do not build a sales-heavy SaaS layer before repeat demand.

## 6. Unit economics

Pilot target:

- `F` product/delivery-pool delivery: no more than 80 hours; `E` engineering-pool delivery: no more than 120 hours; total core team: no more than 200 hours;
- optional evidence-only extension: separate USD 15,000–25,000 change order, no more than 32 additional `F`-pool hours, 48 `E`-pool hours and 8 paid reviewer hours; extension economics are reported separately and cannot hide remediation/product-development time;
- external clinical/community/lab/security/accessibility cost: USD 14,000–25,000;
- travel/secure tooling/insurance allocation: USD 2,000–5,000;
- contribution margin after external reviewers and paid `F/E` delivery cost: at least 40%;
- fully loaded gross margin target after three pilots: at least 35%.

Annual assurance target:

- `F`-pool service time under 30 hours/customer/year;
- external review allocated across customers, not unpaid;
- fully loaded gross margin at least 65%.

If mappings remain bespoke or reviews cannot be amortized ethically, raise price, narrow the ICP, or remain a premium service. Do not underpay community reviewers to manufacture margin.

## 7. Sales process

1. Trigger-based outbound or trusted introduction.
2. 30-minute safety/problem qualification.
3. Technical and clinical feasibility call.
4. Paid readiness assessment or fixed pilot proposal.
5. Security/legal/procurement packet.
6. Design-partner execution.
7. Executive closeout with evidence and annual proposal.

Qualification score:

- target release within 6 months;
- executive buyer;
- staging and synthetic policy;
- four named customer owners;
- export feasibility;
- paid budget;
- willingness to remediate/rerun.

Require at least five of seven, including staging, owners, and budget.

## 8. Evidence to earn

Before broad selling:

- one external pilot satisfying objective gates;
- one reproducible finding/remediation story approved for at least private reference;
- measured comparison with prior test effort;
- receipt comprehension and accessibility results;
- counsel-approved claims sheet;
- security architecture and incident procedure;
- two independent buyers stating how they would procure/renew.

Never use synthetic seeded faults as customer success evidence without labeling them synthetic.

## 9. Acquisition channels

- Clinical informatics and laboratory medicine communities.
- Patient-safety/diagnostic-excellence networks.
- EHR/LIS implementation consultants who lack this pack.
- Malpractice insurers and risk collaboratives.
- Health-system LGBTQ+ clinical leaders as champions, not sole budget owners.
- Standards communities as research/credibility venues, without implying endorsement.
- Public open schema and one non-clinical example receipt to demonstrate method.

Avoid paid targeting based on gender identity or health interests.

## 10. Objections

| Objection | Evidence-based response |
|---|---|
| “Our EHR supports these fields.” | Component support does not show cross-system preservation; propose one dry-run case. |
| “Inferno already tests FHIR.” | Use Inferno for conformance; ContextSafe focuses on semantic, multi-boundary installed behavior. |
| “We test internally.” | Compare packs and receipts; partner or license if internal coverage is equivalent. |
| “Synthetic data are unrealistic.” | The pack is controlled boundary testing, not prevalence modeling; local fixture approval is explicit. |
| “This creates liability.” | The defect already exists or does not; scoped evidence and remediation can improve governance. Counsel decides. |
| “Federal requirements changed.” | The value proposition is patient safety and data integrity, not one certification mandate. |
| “No budget.” | Identify patient safety/risk/CMIO buyer; do not proceed as unpaid DEI work. |
| “We need production monitoring.” | Out of v1; decline or separately research with new safety/legal review. |

## 11. Partnerships

Desired:

- health system as design partner;
- trans-led healthcare organization for paid governance;
- laboratory medicine reviewer or society relationship;
- interoperability/testing platform for future distribution;
- insurer or quality organization for buyer/channel validation.

Partnership rules:

- no logo or endorsement without written approval;
- no exclusive claim over community knowledge;
- core safety pack governance remains independent of one customer;
- partner-specific mappings are confidential unless released by agreement;
- referral fees and conflicts are disclosed.

## 12. 90-day founder plan

Days 1–30:

- 15 interviews and competitor/substitute scan.
- Recruit compensated governance group.
- Obtain initial legal intended-use consult.
- Produce pack 0.1 paper prototype and sample receipt.

Days 31–60:

- Run two tabletop workflows with simulated exports.
- Secure design-partner LOI and paid readiness assessment.
- Finalize SOW/data-boundary/security packet.
- Test price and buyer path with five executives.

Days 61–90:

- Begin partner mapping/dry run.
- Close governance approvals needed for thin evaluator.
- Decide build, license-to-incumbent, advisory-only, or stop using discovery gates.

## 13. Commercial kill gates

Pause or pivot if:

- no paid design partner after 25 qualified conversations;
- buyer remains only an unfunded DEI role;
- security/procurement requires a hosted enterprise platform before pilot;
- expected service gross margin remains below 35% after two pilots;
- no customer will attach the receipt to a release decision;
- incumbent/internal substitute already satisfies the job at lower switching cost;
- selling requires overstating clinical or regulatory claims.

## 14. Ethical growth limits

No patient lead lists, identity-based ad targeting, facility “shame rankings,” pay-to-pass, undisclosed sponsored assertions, or customer control over core severity. Public-interest access can be funded through grants or cross-subsidy, but must include reviewer compensation and the same safety gates.
