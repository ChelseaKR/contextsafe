# V1.0 release checklist

Status: objective gate template  
Release authority: founder/technical owner plus clinical safety chair, community co-chair, security lead, and counsel-approved claims  
Rule: unchecked or unevidenced means not released

Evidence links must point to immutable CI artifacts, signed review records, pilot receipts, or dated controlled documents. A statement that work was done is not evidence.

## RG-01 — discovery and market truth

- [ ] Fifteen or more completed interviews across at least three health systems and five roles.
- [ ] Design-partner LOI and paid SOW name executive, clinical, lab, technical, release, and privacy owners.
- [ ] Competitive/substitute scan is dated within 30 days and states that synthetic QA is established prior art.
- [ ] Buyer uses patient-safety/quality/risk budget rather than an unfunded DEI commitment.
- [ ] Discovery decision memo passes every continue gate in [V1 plan](00-V1-PLAN.md).

## RG-02 — pack validity

- [ ] Pack, case, assertion, source, terminology, and approval schemas validate.
- [ ] Every mandatory assertion is approved, in date, and not withdrawn.
- [ ] Schema/pack compatibility and invalid examples pass.
- [ ] Source manifest has version/retrieval/review dates and limitations.
- [ ] `contextsafe pack sign` produces role/purpose-bound detached signatures and `contextsafe pack verify` requires the clinical-chair, community-co-chair, and technical-release-owner threshold plus the complete approval graph.

## RG-03 — case and assertion governance

- [ ] CTP-001–CTP-012 exist; experimental CTP-006 cannot affect mandatory aggregate until approved.
- [ ] A-001–A-036 have immutable IDs, applicability, predicate, evidence, limitations, and reviewers.
- [ ] Two clinical reviewers and an appropriate lab reviewer approve clinical content.
- [ ] The frozen clinical-oracle subset achieves ≥90% raw agreement and unweighted Cohen’s kappa ≥0.80; if kappa is undefined because a rater uses one category, the predeclared Gwet AC1 fallback is ≥0.80 and the prevalence limitation is disclosed.
- [ ] Two compensated trans/nonbinary reviewers approve representation and necessity.
- [ ] Conflicts, compensation, dissent, and validity dates are recorded.

## RG-04 — safe execution plan

- [ ] Production, unallowlisted host, invalid namespace, missing owner, and missing cleanup each fail.
- [ ] `contextsafe plan sign` and `contextsafe plan verify` require distinct customer-sponsor and ContextSafe-delivery-owner signatures; unsigned or partially signed plans cannot import evidence.
- [ ] One-case dry run proves downstream suppression and cleanup at partner.
- [ ] Partner privacy/security and technical owners sign environment attestation.

## RG-05 — ingestion and normalization

- [ ] Canonical JSON, FHIR R4 JSON, approved HL7 v2 ER7, and LIS mapping fixtures pass.
- [ ] Invalid, ambiguous, oversized, unsupported, and malicious inputs fail safely.
- [ ] Any FHIR narrative, contained resource, unrelated field/resource, or unapproved free text rejects the entire source before persistence; no strip-and-accept path exists.
- [ ] Source bytes, pointers, mappings, and ambiguity remain traceable.
- [ ] No parser repairs or infers a missing clinical/identity value.

## RG-06 — identity fidelity

- [ ] All applicable A-005–A-015 positive fixtures pass.
- [ ] F-001–F-010 are detected and correctly localized.
- [ ] GI, RSG, SPCU, NtU, and pronouns are enforced as distinct types.

## RG-07 — clinical-context fidelity

- [ ] All applicable A-016–A-024 positive fixtures pass.
- [ ] F-011–F-016 are detected and correctly localized.
- [ ] Expired, missing, unsupported, and wrong-context SPCU cannot pass.
- [ ] GI or RSG cannot become SPCU through a documented, customer-approved, or otherwise local mapping; every such substitution fails.

## RG-08 — LIS safety behavior

- [ ] A-025–A-031 pass on approved INV/CTX/XFAIL fixtures.
- [ ] Below/lower/in-range/upper/above boundary values are tested.
- [ ] F-017–F-022 are detected.
- [ ] CTP-012 reproduces and detects blank-range/unflagged-result failure pattern.
- [ ] Receipt explicitly states that fixture ranges are not patient-specific recommendations.

## RG-09 — status safety

- [ ] Ten status-algebra invariants pass as unit and property tests.
- [ ] Missing/ambiguous/stale evidence yields indeterminate/blocked.
- [ ] Unsupported values remain explicit.
- [ ] First divergence never blames an unobserved boundary.
- [ ] “All applicable passed” is impossible with any fail/blocked/indeterminate/unobserved mandatory outcome.

## RG-10 — receipt

- [ ] Deterministic JSON validates and contains scope, coverage, limitations, versions, findings, evidence graph, reviews, and dispositions.
- [ ] HTML is derived only from JSON and exposes every status/limitation.
- [ ] Claim-minimization review confirms unnecessary fields are absent.
- [ ] No single “trans-safe,” compliance, or facility score exists.

## RG-11 — human review and disposition

- [ ] Automation cannot approve an oracle, finalize severity, or close a finding.
- [ ] Review state transitions require correct named role and signature.
- [ ] Every failed/blocked/indeterminate mandatory pilot outcome has owner and disposition.
- [ ] Every accepted clinical residual risk has distinct customer-clinical-owner and ContextSafe-clinical-chair `review` signatures; the record states that the customer owns local operational risk/release and the ContextSafe chair confirms only expectation, severity, and bounded disposition.
- [ ] Disputes and dissent remain visible.

## RG-12 — privacy and security

- [ ] PHI canary and synthetic-namespace suite rejects 100% before persistence.
- [ ] Logs, crash output, diagnostics, and support bundle contain no prohibited fields.
- [ ] Threat model received independent review; no open critical/high finding.
- [ ] Dependency/SAST/secret/license scans pass; SBOM is generated.
- [ ] Customer and ContextSafe complete suspected-PHI tabletop.

## RG-13 — provenance and signing

- [ ] Plan, pack, assertion, oracle, schema, mapping, terminology, evidence, runner, review, and result versions are pinned.
- [ ] Any mutation invalidates verification.
- [ ] Valid signatures verify; wrong/revoked/unknown keys fail.
- [ ] Pinned trust root, signer-to-role/purpose binding, customer key enrollment, and the explicit plan/pack/mapping/review/receipt signature thresholds pass, including verification-time validity, untrusted `claimed_signed_at`, and rotation overlap; no historical-time claim is made without a trusted timestamp/witness.
- [ ] `plan sign/verify` and `pack sign/verify` pass valid cases and fail missing, duplicate-role, wrong-purpose, expired, revoked, stale-trust, noncanonical, and tampered cases.
- [ ] Stale revocation state cannot report fully valid; recovery key, root/key compromise, revocation distribution, and verifier replacement are exercised.
- [ ] Compatible receipt delta exposes every version/evidence/coverage/assertion/outcome/disposition change; incompatible profiles fail with reason.
- [ ] Prior minor receipts remain verifiable.

## RG-14 — accessibility and EN/ES

- [ ] Zero serious/critical automated WCAG 2.2 AA findings.
- [ ] NVDA/Firefox and VoiceOver/Safari task walkthroughs pass.
- [ ] Keyboard, 400% zoom, 320 CSS px, high contrast, text spacing, and print checks pass.
- [ ] EN and ES catalog/placeholder/pseudolocale gates pass.
- [ ] Spanish is professionally translated and independently community-reviewed.
- [ ] In each locale, ≥90% of scored answers are correct, every participant scores at least 4/5, ≥90% of participant-task attempts succeed, and the cohort/denominators meet the predeclared PER-01–PER-07 coverage rule.

## RG-15 — deterministic local runner

- [ ] Identical inputs produce identical deterministic JSON across three runs.
- [ ] Windows 11, supported macOS, and Ubuntu 24.04 fresh installs pass.
- [ ] Interrupted run resumes without a partial pass.
- [ ] Core commands need no network and expose stable exit codes/JSON errors.
- [ ] Performance stays under 60 seconds/100 MB at v1 scale or exception is documented.

## RG-16 — service and operations

- [ ] Qualification, contract, mapping, execution, review, remediation, rerun, cleanup, and closeout checklists exercised.
- [ ] Critical support, wrong-result correction, pack withdrawal, key compromise, and PHI runbooks exercised.
- [ ] SLOs, contacts, supported versions, retention, backup/restore, and revocation update procedures are published.
- [ ] Customer confirms final cleanup.

## RG-17 — evaluator evaluation

- [ ] All 36 independently authored published seeded faults are detected and correctly localized.
- [ ] All five independently authored, implementation-hidden challenge faults are detected and correctly localized; any detection or localization miss blocks release.
- [ ] Results are described as bounded authored-corpus coverage, not a population-sensitivity estimate; no unsupported confidence interval is reported.
- [ ] False-positive rate under 5% on adjudicated positives.
- [ ] First-boundary localization is correct for 41/41 seeded/challenge faults and never accuses an unobserved boundary; no lower release threshold applies.
- [ ] Coverage numerators, denominators, corpus limitations, and adjudication are reported separately.

## RG-18 — external pilot

- [ ] At least 10/12 cases reach all four checkpoints.
- [ ] Mandatory evidence completeness at least 95%.
- [ ] Zero unexplained nondeterminism.
- [ ] Natural partner defects are reported by CS-1–CS-4 and excluded from seeded performance and partner-selection/success quotas.
- [ ] The predeclared comparable-release study shows ≥20 net partner hours saved, or the sponsor documents a named control outcome and accepts paid continuation at the tested price. If the single bounded extension was used, its frozen rule passed.
- [ ] If B-057 was invoked, the separate change order, 32-`F`-pool-hour/48-`E`-pool-hour/8-reviewer-hour caps, global weeks 34–37 window, margin report, and release-date impact are recorded.
- [ ] Partner reruns after remediation and uses receipt in a documented release decision.
- [ ] Sponsor accepts annual continuation or records a falsifiable rejection reason.

## RG-19 — legal, claims, and insurance

- [ ] Counsel reviews intended use against FDA’s January 2026 Clinical Decision Support Software guidance, plus UPL/UPM, HIPAA/BA, state privacy, contract, liability, and claims.
- [ ] Claims sheet permits only evidence-bounded language.
- [ ] Marketing does not imply HL7, ONC/ASTP, DICOM, FDA, Leapfrog, or government endorsement.
- [ ] Required E&O, cyber, and other advised insurance is active.
- [ ] Privacy/security and publication terms are signed.
- [ ] The [publication policy](17-PUBLICATION-POLICY.md) decision record names a date for every open decision, or records why one is deferred and who holds it.
- [ ] Every publicly released artifact carries a recorded class and approval under that policy, no class 3 material has been published, and the pre-pack re-review of already-public documents is complete.

## RG-20 — release and maintenance

- [ ] All P0 requirements link to passing acceptance evidence.
- [ ] No open critical/high product, clinical, security, privacy, accessibility, or legal risk.
- [ ] Medium residual risks have owner, approvers, controls, and expiry.
- [ ] Signed runner, pack, checksums, SBOM, changelog, migration/withdrawal notes, and offline verifier are ready.
- [ ] Maintenance reviewers, compensation, source-watch dates, and next pack review are funded/scheduled.
- [ ] Annual-assurance commercial decision is documented.
- [ ] All five release authorities sign the release dossier.

## Kill review before signature

Do not release v1 if any is true:

- no funded owner;
- staging path cannot be isolated or evidence cannot be collected without PHI;
- mandatory clinical consensus or community quorum is absent;
- legal analysis requires a materially different regulated/practice scope;
- a high-severity hidden fault is missed;
- partner does not use the receipt;
- product needs a hosted control plane or production access to provide initial value;
- maintenance/reviewer work is unfunded.

## Release statement template

“ContextSafe v1.0 evaluated the named synthetic cases and applicable assertions against the listed non-production systems, versions, evidence, mappings, and approved test oracles. The receipt reports observed results, gaps, limitations, and human dispositions. It is not a clinical recommendation, regulatory certification, facility safety grade, or proof that untested patients and workflows are free of defects.”
