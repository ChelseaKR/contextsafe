# ContextSafe

**A proposed clinically and community-governed release-gate plan for transgender and nonbinary patient safety across registration, EHR, HL7/FHIR, and laboratory systems.**

Status: product and delivery plan for v1.0 plus internal iteration-1 synthetic
evaluation, iteration-2 unsigned governance-contract tooling, and iteration-3
privacy/evidence-core risk reduction. No clinically governed, cryptographically
authorized, or externally validated product exists yet.

The planned ContextSafe service would run a fixed, versioned pack of synthetic patients through a health system's non-production workflow, evaluate whether identity and clinical-context data survive each boundary, and produce a signed evidence receipt. Its intended capability is to detect data loss, coercion, unsafe defaults, missing reference ranges, and patient-facing misidentification before a release reaches care. The current code proves only bounded offline fixture evaluation, unsigned contract compilation, a read-only code-envelope boundary check, and an internal-test evidence-store primitive; it is not clinically approved and does not establish those product capabilities.

## Internal implementation slice

Iteration 1 implements a deliberately narrow Python 3.12 path:

- strict, versioned [case](schemas/contextsafe-case-v0.1.schema.json) and
  [observation](schemas/contextsafe-observation-set-v0.1.schema.json) contracts;
- separately typed GI, RSG, SPCU, name-to-use, and pronoun values;
- fail-closed rejection of every cross-concept assignment, with an explicit
  GI/RSG-to-SPCU prohibition;
- a pure exact-match evaluator where missing or ambiguous evidence is indeterminate;
- a deterministic, value-minimized JSON receipt with input, rule-set, and result hashes;
- offline `validate` and `evaluate` commands plus a small synthetic
  [reference fixture](fixtures/reference/case.json).

Iteration 2 adds a machine-enforceable but deliberately unsigned control plane:

- a strict [pack envelope](schemas/contextsafe-pack-v1.schema.json), deterministic
  compiler, semantic component hashes, compatibility rules, lifecycle and withdrawal
  checks, descriptor-anchored no-follow component reads, declared-role completeness,
  a canonical source manifest, and separate source-pack and compiled-payload hashes;
- strict [engagement](schemas/contextsafe-engagement-v1.schema.json) and
  [execution-plan](schemas/contextsafe-plan-v1.schema.json) contracts;
- fail-closed non-production attestations, exact host allowlisting, fixed synthetic
  namespace, owner and cleanup matching, four-checkpoint scope, and
  engagement/compiled-pack hash pinning; the host guard rejects canonical and legacy
  numeric IP forms, and the cleanup deadline must remain current through the complete
  plan validity interval;
- canonical compiled artifacts that always say `signature_status: not_verified`,
  `executable: false`, and `valid_for_signing: true`.

Iteration 3 adds a deliberately non-executable evidence-core slice:

- a strict, code-only [canonical JSON boundary envelope](schemas/contextsafe-evidence-source-v1.schema.json)
  with a one MiB limit, exact field allowlist, plan/case/checkpoint namespace pins,
  Unicode controls, prohibited-field checks, direct-identifier patterns, and known
  PHI canaries;
- a read-only `evidence preflight` command that opens the caller-owned regular file
  once, retains its descriptor, hashes and checks the complete first pass, emits only
  safe success metadata, and creates no workspace, copy, index, or log;
- a two-pass internal-test persistence primitive that copies only from the same
  validated descriptor into a private SHA-256 object store, deduplicates content,
  and appends deterministic records to an update/delete-protected SQLite index;
- explicit rollback and next-transaction recovery for staging files and filesystem
  objects left by a process crash, with full verification of every indexed object;
- [accepted-evidence](schemas/contextsafe-evidence-v1.schema.json) and
  [ambiguity-preserving observation](schemas/contextsafe-observation-v1.schema.json)
  contracts. Ambiguous candidates retain every typed value and source pointer.

The durable primitive has no CLI import route. Every iteration-3 evidence record says
`authorization_status: not_verified_internal_test_only` and
`usable_for_execution: false`; a future signature-verification layer may not relabel
these records. The preflight scanner is a fallible boundary check, not proof that bytes
contain no PHI.

Declared approvals are not authenticated signatures and do not establish that a
real clinical or community review occurred. The committed
[reference pack](fixtures/reference/pack-draft.json) is intentionally `draft`, has
no approvals, and must fail compilation. Tests construct visibly test-only approval
declarations in memory solely to exercise the state machine.

These slices have no signatures, FHIR/HL7/LIS adapters, clinical oracle, HTML report,
network access, authorized evidence-import command, hosted service, or approved
patient-data pathway. Iteration 3 contains internal-test-only local persistence, but
none of its records can authorize execution or support a receipt.
Patient data is prohibited, but bounded checks cannot prove an input is synthetic.
Its fixture rules use invented tokens and are not medical guidance. It was built
ahead of the plan's discovery and governance gates as internal risk-reduction work,
so it cannot be represented as pack approval, pilot evidence, or V1 progress through
those gates.

With `uv` installed:

```bash
make verify
uv run contextsafe validate \
  --case fixtures/reference/case.json \
  --observations fixtures/reference/observations.json \
  --rules fixtures/reference/rules.json
uv run contextsafe evaluate \
  --case fixtures/reference/case.json \
  --observations fixtures/reference/observations.json \
  --rules fixtures/reference/rules.json \
  --output receipt.json

# Requires current approval declarations but still emits an unsigned artifact.
# The committed draft intentionally fails.
uv run contextsafe pack validate \
  --pack path/to/pack.json \
  --as-of 2026-07-13 \
  --output compiled-pack.json

# Revalidates the pack, then validates an unsigned plan without network access.
uv run contextsafe plan validate \
  --engagement path/to/engagement.json \
  --plan path/to/plan.json \
  --pack path/to/pack.json \
  --as-of 2026-07-13 \
  --output compiled-plan.json

# Read-only: validates an unsigned plan-shaped scope and never persists input.
uv run contextsafe evidence preflight \
  --source fixtures/reference/evidence-source.json \
  --plan path/to/plan.json \
  --case-token CSYN-CTP-I01 \
  --checkpoint ehr \
  --source-type canonical_json \
  --media-type application/vnd.contextsafe.evidence+json
```

`make verify` uses the frozen lockfile and gates lint, format, strict typing,
90% overall branch coverage, 95% safety-module branch coverage, dependency audit,
and repository hygiene.

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
- [ADR 0002: unsigned compilation before authorization](docs/decisions/0002-unsigned-compilation-before-authorization.md)
- [ADR 0003: recoverable evidence commit](docs/decisions/0003-recoverable-evidence-commit.md)

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
