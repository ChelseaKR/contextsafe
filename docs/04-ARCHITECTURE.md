# Architecture

Status: proposed v1 design  
Owner: technical lead  
Decision boundary: [ADR 0001](decisions/0001-v1-boundary.md)

## 1. Drivers

### Functional

- Validate a governed synthetic pack.
- Normalize observations from four workflow checkpoints.
- Evaluate versioned assertions without inference.
- Produce and verify a durable JSON/HTML receipt.
- Support human disposition and a remediation rerun.

### Non-functional

- Local and offline for core operation.
- No PHI by design and fail closed on boundary violations.
- Deterministic, inspectable, and reproducible.
- Maintainable by the funded small core team during the 40-week build and by one technical owner after v1 within the bounded local-runner scope.
- Accessible static output in EN and ES.
- Explicitly extensible to additional adapters without a plugin marketplace.

### Scale envelope

V1 supports one engagement workspace at a time, 12–50 synthetic cases, up to 2,000 evidence items, 500 assertions, and 100 MB of source evidence. Evaluation target is under 60 seconds on a supported laptop, excluding manual collection. This is not a big-data system.

## 2. Context

    Customer staging systems
    registration -> EHR -> interface -> LIS -> EHR result
          |           |          |        |
          +------ customer exports observations ------+
                                                     |
                                                     v
    +-------------------------------------------------------------+
    | Customer-controlled ContextSafe workspace                   |
    | privacy preflight -> normalize -> evaluate -> receipt       |
    +-------------------------------------------------------------+
                |                         |
                v                         v
       human clinical review      static JSON/HTML receipt
                |                         |
                +------ dispositions -----+

Core execution has no ContextSafe-hosted control plane. The customer may keep the entire workspace. If ContextSafe personnel need evidence, the SOW must authorize a minimal encrypted transfer; no transfer is the default.

## 3. Components

| Component | Responsibility | Does not do |
|---|---|---|
| Pack compiler | Validate manifest, cases, assertions, sources, approvals, locale catalogs, and pack-signature threshold | Generate clinical rules |
| Plan guard | Validate environment, namespace, hosts, checkpoints, operators, cleanup, key enrollment, and plan-signature threshold | Connect to production |
| Privacy preflight | Reject unapproved fields, identifiers, free text, and PHI canaries | Claim exhaustive PHI detection |
| Import adapters | Parse canonical JSON, FHIR R4 JSON, HL7 v2 text, LIS CSV/JSON | Repair or infer missing values |
| Normalizer | Map source evidence to canonical observations with provenance | Discard source hash/ambiguity or map GI/RSG into SPCU |
| Evaluator | Apply pure, versioned predicates to normalized observations | Make patient-specific recommendations |
| Finding registry | Store outcomes, severity proposal, review, owner, and disposition | Allow automation to close a finding |
| Receipt builder | Create deterministic payload plus accessible presentation | Hide gaps or unresolved results |
| Receipt verifier | Verify hashes, schema, pack, outcome graph, and signatures | Attest clinical safety |
| Delta engine | Compare two verified receipts | Compare incomparable profiles silently |

## 4. Recommended implementation

- Python 3.12.
- Typed domain models with dataclasses or Pydantic; publish JSON Schema for exchange.
- Typer or argparse CLI; prefer argparse if ergonomics remain acceptable to reduce dependencies.
- SQLite for the local evidence index and dispositions; raw evidence remains content-addressed files in the workspace.
- Jinja2 or a minimal template renderer for static HTML; no browser framework.
- Babel/gettext or ICU-compatible catalogs for EN/ES strings.
- hashlib SHA-256 for content IDs; Ed25519 signatures using a maintained library.
- defusedxml only if XML parsing is required; v1 HL7 input is ER7 text and FHIR JSON.
- pytest, Hypothesis, ruff, mypy strict, Bandit/Semgrep, pip-audit, and accessibility gates.

Avoid a web server, cloud database, event bus, container orchestrator, vector database, LLM, analytics SDK, and universal adapter framework.

## 5. Workspace

    engagement/
      engagement.yaml       approved scope; no secrets
      plan.json             validated execution plan
      pack/                 pinned pack or immutable reference
      mappings/             local mapping profiles
      evidence/
        raw/                content-addressed, customer controlled
        normalized/         canonical evidence items
      trust/                pinned trust manifest, plan-enrolled customer keys, revocations
      contextsafe.sqlite    index, outcomes, reviews
      receipts/
        run-id.json
        run-id.html
        run-id.sig
      logs/                 structured, redacted events
      cleanup.json          deletion/retention attestation

Default permissions are owner-only. The CLI refuses a world-readable workspace where the platform exposes POSIX permission information.

## 6. Data flows

### 6.1 Plan

1. Operator creates engagement metadata from the approved template.
2. Plan guard validates non-production attestation, synthetic namespace, allowed checkpoints, expected formats, key/reviewer enrollment, and cleanup owner.
3. Pack compiler verifies pack, source, reviewer, terminology versions, and the clinical/community/technical pack-signature threshold.
4. Tool emits a canonical unsigned run plan and plan hash.
5. The customer sponsor and ContextSafe delivery owner each invoke `contextsafe plan sign`; `contextsafe plan verify` must confirm both role-distinct `plan` signatures before the plan becomes executable.

No evidence may be imported against an invalid, unsigned, or partially signed plan.

### 6.2 Stream from a caller-owned source

1. The customer passes a read-only, seekable file descriptor outside the ContextSafe workspace. The runner opens a path at most once and retains that descriptor; it never reopens by pathname. Before reading, it records descriptor metadata needed to detect mutation. A non-seekable source is rejected before content read in V1 unless the caller supplies an immutable in-memory byte buffer within the configured maximum.
2. First pass over the same open descriptor validates format/parser limits, synthetic namespace, field allowlist, free-text prohibition and PHI canaries while computing hash H1 in memory. For FHIR, any narrative, contained resource, unrelated field/resource, or unapproved free text rejects the entire source; the adapter never strips prohibited content and accepts the remainder. The runner creates no inbox, quarantine copy, temporary file, index row or content-bearing log during this pass.
3. On any first-pass boundary failure, attempt to close the descriptor and persist at most the non-sensitive rejection category. Do not create a ContextSafe workspace or retain a hash, prefix, filename, path, byte count, or rejected content.
4. On first-pass success, seek the same still-open descriptor to the start, verify descriptor metadata is unchanged, and stream it to a private content-addressed staging object while computing H2. Promote/register it only if H2 equals H1 and end metadata remains unchanged. A mismatch fails before promotion or indexing and triggers staging cleanup. If the filesystem denies that cleanup, the structured mutation error remains primary and the private `.part` file may remain for the next permitted exclusive recovery or explicit operator remediation. No pathname reopen or accepted record can race the validated bytes.

The filesystem object and SQLite row cannot be committed by one portable atomic primitive. A new index is therefore initialized and verified in an owner-only temporary database, then published by no-overwrite hard link; an existing index is never created or repaired on open. V1 uses a recoverable protocol under `BEGIN IMMEDIATE`: first validate SQLite integrity, the exact schema/header, every denormalized row column, and every referenced object; only then remove abandoned staging/unindexed objects, create and `fsync` an owner-only staging file, hard-link it without overwrite to its SHA-256 address, append and revalidate the deterministic index row, and commit SQLite with full synchronous durability. Read APIs use SQLite read-only/query-only mode. An ordinary failure before the commit attempt rolls back the row and removes a newly promoted object. A process/power failure can leave an unindexed content object, never a passing/indexed result; the next exclusive transaction removes that orphan before proceeding. A commit whose outcome is uncertain leaves the object in place so recovery can retain it if the row committed or remove it if it did not. This is recoverable consistency, not a cross-resource atomicity claim.

Heuristic detection supplements—not replaces—the namespace and allowlist. A detector miss is possible, so operator training and staging controls remain mandatory.

Implementation slice as of 2026-07-13: only the strict code-only `canonical_json` boundary envelope is enabled, at one MiB per file. The first pass reads bounded chunks from the retained descriptor into an at-most-one-MiB immutable memory buffer, then performs the strict JSON/profile checks; this is not yet a general incremental FHIR/HL7/LIS parser. `contextsafe evidence preflight` is read-only and may inspect an unsigned plan-shaped contract because it cannot copy or index evidence. The content store exists only as an internal synthetic-test primitive; all records are permanently non-executable. FHIR, HL7, LIS, signatures, authorized import, cleanup, and incident-approved use remain gated work.

### 6.3 Normalize

1. Parse without source mutation.
2. Apply a versioned mapping profile. A mapping cannot assign GI or RSG into the SPCU canonical type; an observed source workflow that does so remains evidence of a failed A-020/A-021 assertion.
3. Emit a canonical observation per case, checkpoint, field, and context.
4. Preserve source path/segment pointer, raw hash, mapping version, parser warnings, and ambiguity.
5. Validate canonical schema.

If two source values map to one canonical field, both remain visible and the observation is ambiguous until reviewed.

### 6.4 Evaluate

1. Select applicable mandatory assertions by case and partner profile.
2. Load the approved oracle version.
3. Apply pure predicates.
4. Emit pass, fail, indeterminate, not-applicable, or blocked.
5. Compute first observed divergence without assuming unobserved checkpoints.
6. Propose severity from rubric; a named reviewer confirms it.

Evaluation never changes evidence or an oracle.

### 6.5 Review and receipt

1. Reviewer verifies source and normalized evidence.
2. Reviewer confirms or changes proposed severity with rationale.
3. Customer assigns owner and disposition. If the disposition accepts a clinical residual risk, the customer clinical owner signs ownership of the local operational risk and release decision, and the ContextSafe clinical chair separately signs confirmation of the governed expectation, severity, and bounded disposition. Neither signature substitutes for the other.
4. Receipt builder materializes deterministic JSON.
5. HTML is rendered from JSON; it is not an independent source of truth.
6. The customer release owner and a distinct ContextSafe clinical/service approver sign the JSON hash; neither signature alone finalizes a pilot receipt.
7. Verifier replays schema, integrity, signer-role, purpose, validity, threshold, and revocation checks.

### 6.6 Signature trust model

The runner embeds the fingerprint of one offline ContextSafe trust-root public key. A root-signed `trust-manifest-v1.json` binds each ContextSafe-authorized key ID to organization, human/role, permitted artifact purposes (`plan`, `pack`, `runner`, `mapping`, `review`, `receipt`, `revocation`), algorithm, validity interval, and status. Pack 1.0 requires three valid, role-distinct `pack` signatures: clinical safety chair, community co-chair, and technical release owner. The first two approve clinical/community semantics; the technical signature attests release/build integrity and cannot replace either semantic approval. Laboratory assertions additionally require the approved laboratory reviewer’s `review` signature in the pack approval graph.

A mapping profile becomes executable only with a `mapping` signature from the plan-enrolled customer technical owner and a second `mapping` signature from the trust-manifest-enrolled ContextSafe interoperability reviewer; the people and organizations must differ. A review event binds the outcome/finding ID, evidence and oracle hashes, decision, rationale, reviewer role, and engagement-plan version. It verifies only when the signer is authorized for `review` and that exact role either in the global trust manifest or in the engagement plan's signed reviewer registry. An accepted clinical residual-risk event has a threshold of two role-distinct `review` signatures: customer clinical owner and ContextSafe clinical safety chair. The first owns the customer's local operational risk/release decision; the second confirms only the governed expectation, severity, and bounded disposition. Missing either signature blocks accepted status. A partner receipt requires one plan-enrolled customer release-owner key and one valid ContextSafe clinical/service key authorized for `receipt`, with different people and organizations.

Customer and engagement-specific reviewer public keys are enrolled in the immutable engagement plan with organization, human/role, permitted purposes, validity interval, and status; that enrollment is signed by the customer sponsor and a ContextSafe delivery-owner key authorized for `plan`. They are not promoted into the global trust manifest. Rotation supports an overlap interval. V1 envelope field `claimed_signed_at` is explicitly untrusted metadata outside the deterministic payload; without an RFC 3161 timestamp or independently witnessed append-only release log, the verifier makes only a verification-time key-validity/revocation decision and never claims cryptographic proof of historical signing time. Revocation statements are root-signed, monotonic, and bundled with releases. Unknown, wrong-purpose, expired/revoked at verification, duplicate-role, insufficient-threshold, stale-trust, or tampered signatures fail. When the current revocation set is older than 31 days, an offline verifier reports `trust_status=stale` and does not report the artifact as fully valid until an updated signed set is supplied. The compromise runbook covers root/key isolation, replacement manifest, partner notification, historical scope review, and independently distributed verifier update. Trusted historical time is P1 and requires a new trust ADR.

## 7. CLI surface

| Command | Input | Output/exit behavior |
|---|---|---|
| contextsafe pack validate | pack path | canonical unsigned pack/hash plus report; nonzero on any invalid or expired mandatory content |
| contextsafe pack sign | canonical validated pack and authorized signer key | detached `pack` role/purpose signature; refuses noncanonical or invalid pack |
| contextsafe pack verify | canonical pack, detached signatures, trust state | verification report; nonzero unless clinical-chair, community-co-chair, and technical-release-owner threshold plus approval graph pass |
| contextsafe plan validate | engagement and verified pack | canonical unsigned plan/hash; nonzero for production/namespace/scope/enrollment failure |
| contextsafe plan sign | canonical validated plan and authorized customer-sponsor or ContextSafe-delivery-owner key | detached `plan` role/purpose signature; refuses noncanonical or invalid plan |
| contextsafe plan verify | canonical plan, detached signatures, trust state | verification report; nonzero unless both required plan roles and the referenced verified pack pass |
| contextsafe evidence preflight | unsigned plan-shaped contract, one canonical JSON source, case/checkpoint/type | read-only boundary result; never copies, indexes, logs, or authorizes execution |
| contextsafe evidence import | plan, checkpoint, caller-owned files | evidence IDs; fail before any ContextSafe copy/index/log on boundary violation |
| contextsafe normalize | evidence IDs, mapping | canonical evidence; never overwrites |
| contextsafe mapping sign | canonical mapping profile and authorized signer key | detached role/purpose signature |
| contextsafe evaluate | plan and normalized evidence | immutable run outcomes |
| contextsafe finding review | run, finding, reviewer, decision | canonical unsigned append-only review event and hash |
| contextsafe review sign | canonical review event and authorized reviewer key | detached role/purpose signature |
| contextsafe receipt render | reviewed run | JSON, HTML, unsigned hash |
| contextsafe receipt sign | JSON and signer key | detached signature |
| contextsafe receipt verify | JSON, signatures, pack | verification report; nonzero on mismatch |
| contextsafe receipt diff | two verified receipts | semantic delta or incomparable error |
| contextsafe cleanup | plan and retention policy | cleanup checklist and attestation |

Each command supports JSON error output, documented stable exit codes, quiet mode, and a no-color mode.

## 8. Contract schemas

Publish versioned schemas:

- contextsafe-pack-v1.schema.json
- contextsafe-case-v1.schema.json
- contextsafe-assertion-v1.schema.json
- contextsafe-plan-v1.schema.json
- contextsafe-evidence-source-v1.schema.json
- contextsafe-evidence-v1.schema.json
- contextsafe-observation-v1.schema.json
- contextsafe-review-v1.schema.json
- contextsafe-receipt-v1.schema.json

Schema changes follow SemVer. Unknown required fields fail closed. Readers may preserve unknown optional extension fields but cannot evaluate them without a declared extension.

## 9. Core data model

| Entity | Key fields |
|---|---|
| Pack | id, version, schema_version, cases, assertions, sources, terminology, approvals, valid_from/to; detached signature envelopes are stored alongside and excluded from the canonical payload |
| Case | case_id, synthetic_namespace, traits, contexts, prohibited_inferences, applicable_assertions |
| Assertion | assertion_id, version, predicate, applicability, oracle, severity rubric, sources, approvals |
| Plan | plan_id, partner_profile, environment, allowed_hosts, checkpoints, operators, reviewer/key enrollment, cleanup, pack hash; detached signature envelopes are stored alongside and excluded from the canonical payload |
| Evidence | evidence_id, case_id, checkpoint, source_type, raw_hash, captured_at, collector, mapping_version |
| Observation | observation_id, canonical_path, typed_value, context, source_pointer, ambiguity, evidence_id |
| Outcome | run_id, assertion_id, case_id, status, expected, observed_refs, first_divergence, reason |
| Review | review_id, outcome_id, role, reviewer, decision, rationale, timestamp, signature |
| Finding | finding_id, outcomes, severity, owner, disposition, due_date, residual_risk |
| Receipt | receipt_id, deterministic payload, coverage, findings, limitations, versions, signatures |

Full field semantics are in [Data and evidence](05-DATA-AND-EVIDENCE.md).

## 10. Optional read-only FHIR adapter

P1 may read allowlisted Patient, Observation, ServiceRequest, DiagnosticReport, and Encounter resources from a staging FHIR R4 endpoint.

Controls:

- OAuth client credentials scoped read-only and staging-only.
- Host allowlist and TLS verification.
- Query by exact approved synthetic identifiers; no broad search.
- Maximum result and page limits.
- Credentials only in OS keychain or environment, never config or receipt.
- Resources pass the same privacy preflight as files.
- Any narrative, contained resource, unrelated field/resource, or unapproved free text rejects the entire response before persistence; the adapter never strips and accepts.
- No create, update, patch, delete, subscriptions, or bulk export.

FHIR conformance may be delegated to Inferno; ContextSafe should consume validation evidence rather than recreate a full FHIR conformance platform.

## 11. Error and recovery model

- Parser error: reject source; identify byte/segment/path where safe.
- Privacy boundary error: stop import and persist nothing from the rejected source; start the incident checklist if the caller-owned source was placed in a ContextSafe-controlled path or any persistence may have occurred.
- Missing checkpoint: mark applicable assertions indeterminate.
- Ambiguous mapping: retain alternatives; block affected assertions. A GI/RSG-to-SPCU mapping is prohibited rather than approvable and fails the applicable assertion.
- Expired oracle or approval: block evaluation.
- Receipt integrity failure: invalidate receipt; never auto-repair.
- Reviewer disagreement: keep disputed status and both opinions.
- Interrupted execution: append-only operations resume by content IDs; no partial pass.

## 12. Security boundaries

Trust boundaries are incoming evidence, mapping profiles, pack updates, reviewer identity/signing, optional staging network, and receipt transfer. Controls and threats are in [Security and privacy](06-SECURITY-PRIVACY-THREAT-MODEL.md).

## 13. Observability

Structured local events include command, run ID, case ID, assertion ID, status, duration, tool version, and error class. They exclude names, pronouns, field values, raw message fragments, URLs with credentials, tokens, and source paths that may contain identifiers.

The local runner exports an operations summary rather than telemetry. No product analytics leaves the customer environment in v1.

## 14. Trade-offs

| Decision | Benefit | Cost | Revisit trigger |
|---|---|---|---|
| File-first | Works across vendors; lowest trust burden | More manual collection | Three pilots show repeated API collection work |
| Local runner | No hosted evidence store | Harder support and updates | Five annual customers request team workflows |
| Fixed pack | Governable and comparable | Limited scenario breadth | Stable governance and two repeated extension requests |
| Static report | Accessible, durable, low attack surface | No collaboration UI | Disposition coordination dominates engagement time |
| SQLite | Transactional and simple | Single-workspace concurrency | Multi-user hosted product approved |
| No AI | Deterministic, explainable | More authoring labor | No v1 trigger; any change requires new safety/legal review |

## 15. What grows later

Adapters, not the evaluator core, should expand. DICOM, pharmacy, and CDS each require a separate governed pack and subject-matter reviewers. A hosted product requires a new architecture decision, threat model, HIPAA/BA analysis, tenancy design, and operating model. Nothing in v1 authorizes it.
