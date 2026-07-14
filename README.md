# ContextSafe

**A proposed clinically and community-governed release-gate plan for transgender and nonbinary patient safety across registration, EHR, HL7/FHIR, and laboratory systems.**

Status: product and delivery plan for v1.0; no executable product exists yet.

The planned ContextSafe service would run a fixed, versioned pack of synthetic patients through a health system's non-production workflow, evaluate whether identity and clinical-context data survive each boundary, and produce a signed evidence receipt. Its intended capability is to detect data loss, coercion, unsafe defaults, missing reference ranges, and patient-facing misidentification before a release reaches care; none of those capabilities is implemented or clinically approved yet.

The v1 product is deliberately a **service with a small local tool**, not a universal integration platform:

1. A clinically and community-reviewed synthetic test pack.
2. A customer-run, non-production test protocol.
3. File-based observations from registration, EHR, HL7 v2 or FHIR, and LIS.
4. A deterministic Python evaluator.
5. Static HTML and JSON receipts that distinguish facts, clinical judgments, gaps, and unresolved findings.

## Why this exists

HL7 Gender Harmony defines distinct concepts for Gender Identity, Sex Parameter for Clinical Use, Recorded Sex or Gender, Name to Use, and Pronouns. Those representations matter, but standards conformance does not prove that an installed, multi-vendor workflow preserves them. A published case report documents an X value passing from an EHR to an LIS that had no matching reference range, causing abnormal results to go unflagged.

ContextSafe is intended to test the installed workflow rather than assume that each component's configuration is sufficient.

## Product boundary

ContextSafe v1.0:

- uses only obviously synthetic records;
- runs only in customer-controlled non-production environments;
- performs no patient-specific clinical decision-making;
- makes no claim that a system is clinically safe, compliant, certified, or free of defects;
- does not prescribe a universal laboratory reference-range policy;
- requires named clinical and trans-community review before a test pack or clinical assertion is released;
- keeps raw customer observations local unless a separately approved transfer is necessary;
- reports observed behavior and reviewed expectations with provenance.

The packaged vertical workflow may be differentiated; **synthetic clinical data and health-IT conformance testing are established categories**. Synthea, Synset, and Inferno are adjacent prior art. ContextSafe's proposed wedge is the clinically governed, transgender/nonbinary, cross-system release receipt—not invention of synthetic QA.

## V1 user and outcome

The primary user is a health-system clinical informatics or interface team preparing a registration, EHR, interface-engine, or LIS change. The economic buyer is initially a patient-safety, quality, risk, or digital-health executive.

A successful v1 allows one design partner to:

- execute the canonical pack in a representative staging pathway;
- evaluate at least 30 approved assertions across four checkpoints;
- reproduce the same result from the same evidence;
- route every failed or indeterminate assertion to a named owner;
- attach a reviewable receipt to its release decision.

## Start here

- [V1 master plan](docs/00-V1-PLAN.md)
- [Product requirements](docs/01-PRD.md)
- [User research and design-partner pilot](docs/02-USER-RESEARCH-AND-PILOT.md)
- [Service design](docs/03-SERVICE-DESIGN.md)
- [Architecture](docs/04-ARCHITECTURE.md)
- [Data and evidence model](docs/05-DATA-AND-EVIDENCE.md)
- [Security, privacy, and threat model](docs/06-SECURITY-PRIVACY-THREAT-MODEL.md)
- [Clinical, community, legal, and safety governance](docs/07-GOVERNANCE-LEGAL-SAFETY.md)
- [Accessibility and internationalization](docs/08-ACCESSIBILITY-I18N.md)
- [Test and evaluation strategy](docs/09-TEST-AND-EVALUATION.md)
- [Operations and SRE](docs/10-OPERATIONS-SRE.md)
- [Go-to-market and business model](docs/11-GTM-BUSINESS-MODEL.md)
- [Roadmap](docs/12-ROADMAP.md)
- [Prioritized backlog](docs/13-BACKLOG.md)
- [Risk register](docs/14-RISK-REGISTER.md)
- [V1 release checklist](docs/15-V1-RELEASE-CHECKLIST.md)
- [Research sources](docs/16-RESEARCH-SOURCES.md)
- [ADR 0001: v1 boundary](docs/decisions/0001-v1-boundary.md)

## Working principles

1. A pass means only that listed assertions passed on a named system version and evidence set.
2. Missing evidence is indeterminate, never pass.
3. Identity, administrative, and clinical-context data are separate concepts.
4. The evaluator does not invent clinical rules.
5. A machine cannot approve a clinical expectation or speak for trans people.
6. A receipt includes failures, exclusions, deviations, and reviewer identities.
7. Patient safety defects are not converted into a single marketing score.

## Implementation posture

The recommended implementation is Python 3.12, typed schemas, a command-line runner, a local SQLite evidence index, and generated static HTML/JSON. V1 has no hosted database, multi-tenant control plane, universal EHR writer, production agent, real-patient ingestion, AI classifier, or automated clinical recommendation.

When implementation begins, this repository should inherit the portfolio standards in ../STANDARDS. The planning documents specify ContextSafe's project-specific values; they do not replace those standards.

Last reviewed: 2026-07-13. Re-review before implementation and at every material clinical, standards, or regulatory change.
