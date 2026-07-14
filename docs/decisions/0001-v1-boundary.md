# ADR 0001: service-first, local, synthetic, non-production v1

Status: proposed for approval  
Date: 2026-07-13  
Deciders: founder, clinical safety chair, community co-chair, security/privacy lead, design-partner technical owner  
Review trigger: two completed pilots or any request for production, real-patient, hosted, imaging, pharmacy, or CDS operation

## Context

The product hypothesis spans multiple proprietary clinical systems and high-consequence semantics. A universal automated integration platform would require production credentials, vendor-specific write paths, PHI handling, hosting, and much broader regulatory/security operations before the core customer value is proven.

The core question is smaller: can a governed synthetic pack reveal meaningful cross-system defects and improve a release decision?

## Decision

ContextSafe v1 is:

- a professional service supported by a small open-inspectable local runner;
- limited to customer-controlled non-production environments;
- limited to obviously synthetic test records and approved evidence fields;
- file-first, with optional P1 read-only FHIR collection;
- scoped to registration, EHR, HL7 v2 or FHIR, LIS, and result return;
- deterministic, with no AI in evidence, evaluation, or explanation;
- based on a fixed governed pack and partner-approved local mappings;
- delivered as signed JSON plus accessible static HTML receipt;
- explicit that human clinical/community approval and customer disposition cannot be automated.

V1 will not include a hosted multi-tenant service, universal write adapters, production canaries, real patient data, continuous monitoring, RIS/DICOM, pharmacy, billing, CDS, or patient-specific recommendations.

## Why

- Minimizes risk of PHI and trans-sensitive data exposure.
- Separates validation of the product thesis from enterprise-platform work.
- Makes multi-vendor use possible through exports.
- Preserves source evidence and local control.
- Is feasible for the funded 40-week `F/E` core-team model: the founder plus scheduled product/research delivery lead, the scheduled engineering pool, and paid expert reviewers.
- Makes custom work visible as service cost.
- Allows later integration based on repeated demand.

## Consequences

### Positive

- Smaller attack and regulatory surface.
- Lower procurement burden than hosted PHI processing.
- Deterministic and reproducible receipts.
- Can work where write APIs are unavailable.
- Clinical governance is the product core rather than an afterthought.

### Negative

- Manual collection and mapping increase service hours.
- Customer staging quality may limit evidence.
- No real-time/production assurance.
- Local support across operating systems adds packaging work.
- Results may not transfer across partners without mappings.
- Buyer may perceive service as consulting rather than software.

### Risks accepted

- A finite synthetic pack cannot prove safety for untested people/workflows.
- PHI detection cannot prove an export is safe.
- File evidence may omit behavior visible only in a user interface.
- One design partner is validation, not market proof.

These risks must remain explicit in receipts and sales.

## Alternatives considered

### Hosted SaaS from day one

Rejected for v1: tenancy, authentication, PHI/BA posture, SOC 2 expectations, breach surface, and collaboration UI do not prove the evaluator's value.

### Production synthetic monitoring

Rejected: synthetic records could reach billing, reporting, care, analytics, or patient communications. This requires a separate safety architecture and vendor approval.

### Universal EHR/LIS write adapters

Rejected: expensive vendor-specific automation with high privileges and fragile UI/API behavior. Customer operators use approved creation mechanisms.

### Pack-only PDF/checklist

Not selected as the target because it lacks reproducible evidence/provenance, but it is the fallback if legal or access constraints block software.

### Build on Inferno

Deferred: Inferno is strong FHIR conformance prior art, but the first pathway includes non-FHIR files, LIS behavior, human dispositions, and a small core-team-maintained scope. ContextSafe may export or reuse Inferno evidence rather than compete with it.

### Generate a population with Synthea/Synset

Rejected as the core: v1 needs controlled edge cases and approved expected behavior, not statistical realism or volume. Those tools remain potential inputs/partners.

## Guardrails

1. Any endpoint marked production is rejected.
2. Any non-synthetic identifier or prohibited free text blocks persistence.
3. Missing evidence cannot pass.
4. GI, RSG, SPCU, NtU, and pronouns remain distinct types; no local mapping, customer approval, or disclosed deviation can convert GI/RSG into SPCU.
5. No clinical assertion runs without current named approvals.
6. No machine closes a clinical safety finding.
7. Receipt never claims compliance, certification, or general safety.
8. Partner-specific clinical policy is labeled local.
9. Raw customer evidence remains local by default.
10. Scope expansion requires a new ADR plus security, clinical, community, and legal review.

## Revisit criteria

Consider a read-only adapter after two partners repeat the same safe collection task. Consider hosted collaboration only after at least five annual customers request it and can fund dedicated security/operations. Consider a new clinical domain only with a separate governed pack and qualified specialist.

Reversal requires:

- validated customer/job evidence;
- architecture and threat model;
- privacy/HIPAA and FDA/CDS/UPL/UPM legal memo;
- clinical/community governance approval;
- staffing and insurance;
- new success and kill gates.

## Validation

This decision succeeds if one design partner runs at least 10 cases through all four checkpoints, obtains a reproducible receipt, detects and correctly localizes all 36 published faults plus all five hidden challenges, passes the no-PHI gates, reruns after remediation, uses the P0 delta receipt in a release decision, and demonstrates the predeclared time/control-value outcome within the 40-week plan. Naturally occurring partner defects are reported outcomes, never a quota.

It fails if file collection cannot show the necessary behavior, delivery exceeds 120 `F`-pool hours, no funded buyer exists, or legal/safety review requires production/patient-specific operation for value.
