# Risk register

Status: initial v1 register  
Scale: probability P and impact I from 1 low to 5 high; score P×I  
Review: biweekly during build, weekly during pilot, monthly after v1  
Risk acceptance: named owner plus relevant clinical/community/security/legal approver

| ID | Risk | P | I | Score | Owner | Mitigation / leading indicator | Contingency and residual risk |
|---|---|---:|---:|---:|---|---|---|
| R-01 | Pack encodes stereotypes or conflates GI/RSG/SPCU | 3 | 5 | 15 | COM/CL | distinct types; absolute GI/RSG-to-SPCU mapping prohibition; necessity review; dual community/clinical approval; dissent rate | withdraw case/assertion; residual: small reviewer group cannot represent everyone |
| R-02 | Laboratory oracle is clinically wrong/stale | 3 | 5 | 15 | LAB | two clinical reviewers; local policy/version; boundaries; monthly source review | mark indeterminate/withdraw/reissue receipts; residual clinical uncertainty stays visible |
| R-03 | Standard/terminology changes invalidate assertions | 4 | 4 | 16 | CL/interoperability | pin versions; monthly watch; validity dates; revocation | compatibility/major pack release; rerun affected receipts |
| R-04 | Receipt implies certainty or is tampered with | 3 | 5 | 15 | SEC/F | claim taxonomy, deterministic JSON, signatures, limitations, comprehension tests | revoke/correct and notify; screenshots can still strip context |
| R-05 | Founder/sales bypasses reviewers or severity | 2 | 5 | 10 | CL/COM | dual approvals, protected release, dual customer/ContextSafe signatures for accepted clinical residual risk, conflict log, append-only review | halt sale/release; independent audit; governance cannot remove all power imbalance |
| R-06 | Synthetic records leak into billing/reporting/patient contact | 3 | 5 | 15 | DP technical | namespace, flags, downstream suppression, one-case dry run, cleanup | stop, customer incident process, invalidate run; shared staging services remain risk |
| R-07 | Real PHI enters workspace | 3 | 5 | 15 | SEC/DP privacy | no-PHI contract, allowlists, pre-persistence checks, no free text, tabletop | isolate/notify/delete per counsel; detector cannot prove absence |
| R-08 | Vendor export/mapping hides a field or invents absence | 4 | 4 | 16 | F/DP technical | source pointers, ambiguity, mapping fixtures, proof-of-absence protocol | indeterminate or custom mapping; may limit transferability |
| R-09 | No budget owner; interest remains unfunded DEI | 4 | 4 | 16 | F | sell to quality/risk/CMIO; paid readiness; 25-conversation gate | license/open protocol or stop; mission value alone does not fund maintenance |
| R-10 | Local cross-platform execution is nondeterministic | 3 | 4 | 12 | F | locked runtime, normalized payload, three-OS repeat tests | narrow support matrix; reproducibility may impose tooling constraints |
| R-11 | Product crosses FDA/CDS or practice-of-medicine/law boundary | 2 | 5 | 10 | LEG/CL | synthetic QA intended use; no patient recommendations; counsel review; claims control | advisory-only/license pack/feature removal; regulators/courts may differ |
| R-12 | Receipt is inaccessible or Spanish meaning is unsafe | 3 | 4 | 12 | A11Y/COM | WCAG 2.2 AA, professional translation, manual EN/ES tests | block locale/release until fixed; language variation remains |
| R-13 | Parser/input exploit compromises endpoint or evidence | 2 | 5 | 10 | SEC/F | bounded parsers, no eval, fuzz/property tests, SAST/SCA, local isolation | revoke release and incident response; upstream zero-day residual |
| R-14 | Test passes but installed workflow still harms untested cases | 4 | 5 | 20 | CL/F | narrow scope, explicit coverage, no safety grade, pack updates, local extensions | communicate limitation and expand only with evidence; finite tests never prove absence |
| R-15 | Partner cannot provide representative staging pathway | 4 | 4 | 16 | DP sponsor | feasibility before build; exact owners; one-case dry run | stop pilot; simulator evidence cannot substitute for external validation |
| R-16 | Custom integration destroys service economics | 4 | 3 | 12 | F | file-first, two-mapping cap, 80-`F`-pool-hour delivery budget, classify custom work | raise price, partner with integrator, narrow ICP, or remain consulting |
| R-17 | Competitor/internal team already solves job | 3 | 3 | 9 | F | substitute interviews and live competitive scan; compare actual test packs | partner/license or pivot; packaged vertical novelty remains a hypothesis |
| R-18 | Community participation is extractive or exposes reviewers | 3 | 5 | 15 | COM/F | pay parity, decision rights, attribution choice, confidential roster, wellbeing review; the same attribution choice extends to every public contributor and pseudonymous contribution is accepted | pause governance/recruit with consent; cannot eliminate emotional burden; public authorship cannot be withdrawn from forks or archives |
| R-19 | Critical finding causes mishandled disclosure or liability | 3 | 5 | 15 | DP clinical/LEG | customer incident RACI, dual signatures for any accepted clinical residual risk, confidentiality, evidence freeze, counsel, insurance | activate customer safety process; ContextSafe does not investigate real patients |
| R-20 | Revocation does not reach offline customer | 3 | 4 | 12 | F/SEC | contract contacts, monthly signed list check, verifier age warning | direct outreach and reissue; fully disconnected copies may remain |
| R-21 | Signing key or build chain compromised | 2 | 5 | 10 | SEC | hardware keys, recovery key, signed artifacts/SBOM, protected release | revoke/rebuild/notify; historical trust investigation required |
| R-22 | Evidence hash is mistaken for evidence truth | 3 | 4 | 12 | F/CL | provenance language, reviewer training, receipt comprehension | correct claims; source may be faithfully wrong |
| R-23 | Political/certification changes weaken demand | 4 | 3 | 12 | F/LEG | patient-safety positioning; multiple buyer triggers; quarterly policy watch | focus risk/insurer/lab channels; mission remains but market may shrink |
| R-24 | Reviewer or `F`-pool capacity delays source/pack maintenance | 4 | 4 | 16 | F/CL/COM | funded calendar, expiry blocks, backup reviewers, narrow pack | pause release/renewal rather than run stale; service continuity depends on people |
| R-25 | This project's own published material becomes targeting or enforcement input: a loss map read as a retention map | 3 | 5 | 15 | COM/F/LEG | [publication policy](17-PUBLICATION-POLICY.md) three-class rule; locator material blocked while either governance chair seat is unfilled; no instance material about any real organization or person, ever; community co-chair may stop a publication alone; minimization by design — hashes, statuses, and counts rather than values; policy watch extended to enforcement activity and to how the project is cited; leading indicator: any citation of project material in an enforcement action, demand letter, or a fork whose evident purpose is targeting | stop publishing under policy §8, then decide takedown deliberately with counsel and the community co-chair rather than reflexively. Residual, stated plainly: publication cannot be undone; the underlying representations are published standards, so withholding buys curation friction and not secrecy; a fork adopts none of these controls; and classification is a human judgment made once per artifact |
| R-26 | Lawful process compels production of receipts, customer identities, reviewer identities, or pack content | 2 | 5 | 10 | LEG/SEC | minimization is the control: raw evidence stays customer-local, no hosted findings store, receipts carry no values, roster small and confidential; counsel-owned response; the customer's own posture is set in contract before the first paid pilot | produce the minimum responsive set under counsel and notify affected parties where permitted; residual: no technical control defeats valid process, and a public-institution customer may be subject to records law this project does not control |

## Highest-priority treatment

Scores 15 or higher require a funded mitigation owner before implementation: R-01–04, R-06–09, R-14–15, R-18–19, R-24, and R-25. R-14 is irreducible: a finite test pack cannot prove safety. The primary treatment is bounded claims and visible coverage, not more confident scoring.

R-23 previously read “weaken demand **or increase harm**” and analyzed only demand; every mitigation on that row was a market mitigation. The harm half is now R-25, with its own owner, score, and treatment, and R-23 is scoped to demand alone. R-26 separates compelled disclosure, which is a legal event rather than a market or publication one.

## Triggers

- Any PHI or downstream synthetic leakage: invoke SEV-1 and stop all runs.
- Any false pass on a high-severity hidden fault: block release.
- Any clinical/community assertion hold: withdraw affected pack content.
- Evidence completeness below 75% after partner dry run: stop pilot and reassess.
- More than 120 `F`-pool integration hours projected: change order, partner, or stop.
- No paid partner after 25 qualified conversations: commercial pivot decision.
- Reviewer participation below quorum or unpaid work: pause pack release.
- Any sign that published material is being used to locate or pressure trans people or the organizations serving them: stop publishing under [publication policy](17-PUBLICATION-POLICY.md) §8 and convene the harm review before anything else.
- Any legal process naming this project or a customer's receipts: pause publication, preserve, and route to counsel.
- Pack authoring (B-009) reached without an adopted publication policy: stop and decide the policy first.

## Residual-risk acceptance

Acceptance records include risk/version, evidence, affected users, residual severity, compensating control, owner, expiry, and signatures. Founder alone cannot accept clinical, community, security, accessibility, or legal residual risk. Critical residual risk is not acceptable for v1.
