# Test and evaluation strategy

Status: v1 quality plan  
Owner: test lead  
Safety approvers: clinical safety chair, community co-chair, security lead

## 1. Quality claim

ContextSafe must demonstrate that it correctly evaluates approved assertions over controlled evidence, fails closed when evidence or governance is insufficient, preserves provenance, and communicates results accessibly. Passing software tests does not validate a clinical oracle; oracle validation is a separate human evidence process.

## 2. Test layers

| Layer | Scope | Target |
|---|---|---|
| Unit | schema predicates, canonical types, hashes, status algebra, locale helpers | at least 90% line and branch; 100% safety modules |
| Property | parser bounds, normalization idempotence, hash stability, no-pass-without-evidence | thousands of generated cases per CI/nightly budget |
| Contract | JSON schemas, CLI exit codes, adapter/mapping interfaces, receipt compatibility | all published examples and prior minor versions |
| Integration | import → normalize → evaluate → review → receipt | each format and status path |
| End-to-end | twelve-case reference workflow and seeded faults | all mandatory assertions |
| Clinical evaluation | oracle/source/reviewer sufficiency and disagreement | two independent reviewers; lab specialist where applicable |
| Security/privacy | malicious input, PHI canaries, secrets/logging, signature tamper | 100% high-risk cases fail safe |
| Accessibility/i18n | automated and manual EN/ES receipt use | [Accessibility targets](08-ACCESSIBILITY-I18N.md) |
| Operational | install, interrupted run, cleanup, recall, correction, incident drill | all supported OSes and runbooks |
| External pilot | real staging workflow and human comprehension | [Pilot success gate](02-USER-RESEARCH-AND-PILOT.md) |

## 3. Status algebra invariants

These are merge-blocking:

1. Missing evidence cannot produce pass.
2. A blocked/expired assertion cannot execute.
3. Not-applicable requires a pre-observation applicability rule.
4. Unsupported values cannot be coerced.
5. A clinical finding cannot be closed without named human disposition; an accepted clinical residual risk requires distinct customer-clinical-owner and ContextSafe-clinical-chair `review` signatures, and neither role can substitute for the other.
6. Aggregate “all passed” is false if any applicable mandatory outcome is fail, indeterminate, blocked, or unobserved.
7. HTML semantics equal the verified JSON semantics.
8. Changed evidence, mapping, plan, pack, assertion, oracle, review, or result invalidates the relevant prior signature; wrong-purpose or incomplete plan/pack/mapping/review/receipt thresholds fail closed.
9. GI, SPCU, RSG, NtU, and pronouns have distinct canonical types and cannot be assigned across types.
10. Re-running identical deterministic inputs yields identical deterministic payload.

## 4. Seeded fault library

The evaluator must detect every applicable injected defect and localize it no later than the first observed divergent boundary.

| Fault | Mutation | Expected detector |
|---|---|---|
| F-001 | drop current NtU | A-005/A-006 |
| F-002 | replace NtU with legal test name | A-006/A-007 |
| F-003 | show expired prior NtU | A-015 |
| F-004 | drop pronouns | A-008 |
| F-005 | convert declined GI/pronouns to unknown | A-009 |
| F-006 | overwrite GI with RSG | A-010/A-011 |
| F-007 | coerce X to F | A-014 |
| F-008 | coerce absent/unknown to M | A-014 |
| F-009 | drop RSG source/context | A-012 |
| F-010 | collapse two RSG records | A-013 |
| F-011 | drop SPCU | A-016 |
| F-012 | apply one SPCU to all orders | A-017/A-023 |
| F-013 | treat expired SPCU as current | A-018/A-022 |
| F-014 | detach supporting observation | A-019 |
| F-015 | derive SPCU from GI | A-020 |
| F-016 | derive or map SPCU from RSG under any declared or undeclared local mapping | A-021 |
| F-017 | attach order to wrong synthetic patient | A-025 |
| F-018 | alter analyte code/value/unit | A-026 |
| F-019 | omit required reference interval | A-027/A-029 |
| F-020 | return wrong interval bounds | A-027 |
| F-021 | omit abnormal flag above bound | A-028/A-030 |
| F-022 | report out-of-range result as normal | A-028/A-030 |
| F-023 | omit checkpoint but report pass | A-032 |
| F-024 | normalize unsupported value to closest code | A-033 |
| F-025 | infer first divergence across an unobserved boundary | A-034 |
| F-026 | mutate raw evidence after evaluation | A-035/receipt verifier |
| F-027 | include unnecessary legal-name/GI field in HTML | A-031/A-036 |
| F-028 | use expired assertion/oracle | pack validity gate |
| F-029 | ingest PHI canary/non-synthetic MRN | P0-11 privacy preflight |
| F-030 | strip limitations from report template | receipt schema/presentation gate |
| F-031 | convert explicitly declined identity data to absent | A-009/A-032 |
| F-032 | attach name/pronoun observation to the wrong synthetic case | A-001/A-005/A-008 |
| F-033 | preserve a numeric range with the wrong unit | A-027/A-028 |
| F-034 | remove one required receipt signer or substitute the wrong-purpose role | review/signature threshold verifier |
| F-035 | change mapping/terminology version without changing the run identity | A-035/P0-12 verifier |
| F-036 | omit the owner or disposition for a mandatory failed outcome | P0-10 finalization gate |

F-001–F-036 are reviewed by an independent fault author before the evaluation corpus is frozen. At least five additional hidden faults are authored by an independent reviewer and withheld from implementation until pre-release evaluation.

## 5. Positive and boundary fixtures

- Every case/assertion expected pass path.
- Every status: pass, fail, indeterminate, blocked, not applicable.
- FHIR R4 extension forms for GI, SPCU, RSG, pronouns, and HumanName usual.
- HL7 v2 partner profile fixtures, including unsupported pre-adoption behavior.
- Multiple/empty values, Unicode, differing code systems, validity periods, time zones, and daylight-saving boundaries.
- Laboratory below/lower/in-range/upper/above values and unit mismatches.
- Exact X failure pattern from CTP-012.
- EN, ES, pseudolocale, long reviewer names, long limitations, and right-to-left smoke rendering for future readiness.
- Receipt with zero findings and receipt with all findings; both must expose limitations.

Fixtures are authored from synthetic primitives. Never copy and redact a real patient record.

### Evidence-boundary safety matrix

The iteration-3 gate covers reference-shape schema/runtime agreement and separately
tests the documented runtime-only semantic constraints; unknown and prohibited fields;
plan, case, checkpoint, source/media-type, and namespace mismatch; direct-identifier
patterns; PHI canaries; prose, boundary whitespace, Unicode control/format characters,
invalid UTF-8/JSON, duplicate keys, excessive depth/size, final symlinks, directories,
descriptor mutation, and first/second-pass hash mismatch. A rejection test asserts that
no workspace exists and that structured errors do not echo content or a source path.

### Receipt contract matrix

The published receipt contract is validated against the reference document, the
`evaluate --output` artifact, and generated bundles from the property layer.
Negative cases cover an unknown field at every level of the document, envelope,
payload, hashes, scope, summary, and outcome; a relabelled `signature_status` or
`trusted_time`; timestamp, signature, reviewer, and run-environment fields added
to the payload; semantic or source values added to an outcome; stripped,
duplicated, empty, reworded, reordered, and padded limitations (F-030); a scope
that claims clinical approval or permitted patient data; a non-canonical payload
hash; a claimed time that is not whole-second UTC; every missing required field;
and an empty result set. The missing-field cases are parametrized from the
contract's own `required` lists and a companion test asserts that the
parametrization reaches every one of them, so a required field added later
cannot escape the gate. Enum parity is asserted against the runtime status,
reason, checkpoint, and concept types, and version constants against the runtime
schema versions, so a new value cannot enter a receipt without a contract
change. The mandated disclosure set is pinned in the contract itself — a closed,
ordered list, as in the compiled-plan and compiled-pack contracts — and the test
suite restates the same wording independently of both the runner and the schema,
so a stripped or reworded disclosure fails validation rather than a comparison
against itself. A final test records the boundary honestly: structural validity
is not tamper detection, because hash, approval, and signature verification are
separate work.

Store tests cover private modes, deterministic IDs, content deduplication, idempotency,
concurrent writers, append-only update/delete triggers, ordinary rollback, staged-copy
failure, orphan/staging recovery, missing/corrupt objects, read-only access, exact
schema/header/version enforcement, non-repair of missing tables/metadata/triggers,
canonical parity for every index column, record-count bounds, and unsafe filesystem
entries. The safety-module coverage manifest in the Makefile includes `evidence.py`,
`preflight.py`, and `evidence_store.py`; the combined safety gate remains at least 95%
branch coverage.

## 6. Clinical oracle evaluation

For each clinical assertion:

1. Evidence author drafts claim, applicability, counterexamples, and source map.
2. Two reviewers independently rate: supported, supported with limits, disputed, or unsupported.
3. Laboratory content requires a laboratory specialist.
4. Before review, freeze the clinical-oracle subset, category definitions, and exclusions. The unit is one assertion independently rated by each of the same two clinical reviewers as supported, supported-with-limits, disputed, or unsupported. Report the four-category confusion matrix, raw agreement, unweighted Cohen’s kappa, and a 95% bootstrap interval. The gate is raw agreement ≥90% and kappa point estimate ≥0.80. If either rater uses only one category so kappa is undefined, the predeclared fallback is Gwet’s AC1 point estimate ≥0.80 with raw agreement ≥90%; the reason and prevalence are disclosed rather than switching statistics post hoc.
5. Disagreement is discussed; unresolved assertions remain experimental or excluded.
6. Reviewer confirms predicate behavior against plain-language expectation.
7. Community reviewers perform separate representation/harm review.
8. Re-review date and withdrawal trigger are set.

Clinical “ground truth” is an approved test oracle with provenance, not a universal truth.

## 7. Evaluator performance measures

On the fault library:

- Published regression coverage: 36/36 independently authored published seeded faults detected and correctly localized. Because these faults are intentionally authored and used in development/CI, this is deterministic corpus coverage, not a binomial estimate of unseen-fault sensitivity.
- Hidden challenge coverage: 5/5 independently authored faults withheld from implementation detected and correctly localized; any detection or localization miss blocks release. The population/sampling frame is not probabilistic, so no confidence interval or general sensitivity claim is made.
- False-positive rate: under 5% on reviewed positive fixtures.
- Localization: 41/41 correct first observed divergent boundaries across the published and hidden fault corpus; never accuse an unobserved boundary. There is no lower release threshold.
- Determinism: 100% identical normalized outputs across three runs and supported OSes.
- Receipt traceability: 100% outcomes resolve to all required version/evidence IDs.

Do not collapse these into one score. Publish numerator, denominator, corpus-construction limitations, and adjudication process.

## 8. Requirement traceability

| Requirement | Primary tests | Assertion/risk | Release gate |
|---|---|---|---|
| P0-01 | T-PACK-001..012 validity/expiry/approval plus `pack sign/verify` role-threshold cases | R-03 | RG-02 |
| P0-02 | T-CASE-001 matrix and semantic type checks | A-001..A-036, R-01 | RG-03 |
| P0-03 | T-PLAN-001..010 environment/namespace/cleanup plus `plan sign/verify` dual-role cases | R-06 | RG-04 |
| P0-04 | T-IMPORT-FHIR/HL7/LIS/CANON suites | R-07/R-08 | RG-05 |
| P0-05 | F-001..010 and case matrix | A-005..A-015 | RG-06 |
| P0-06 | F-011..016 and temporal/context properties | A-016..A-024 | RG-07 |
| P0-07 | F-017..022 and range boundaries | A-025..A-031, R-02 | RG-08 |
| P0-08 | T-STATUS properties and F-023..025 | A-032..A-034 | RG-09 |
| P0-09 | T-RECEIPT schema/tamper/presentation | A-035/A-036, R-04 | RG-10 |
| P0-10 | T-REVIEW role/signature/state-machine, including dual accepted-clinical-risk signatures | R-05 | RG-11 |
| P0-11 | T-PRIVACY canary/malicious-input/log suites, including whole-source FHIR narrative/contained/unrelated rejection | R-07 | RG-12 |
| P0-12 | T-PROV mutation/version/signature/trust/delta suites, including plan/pack sign/verify command contracts | R-04/R-21 | RG-13 |
| P0-13 | T-A11Y/I18N automated/manual matrix | R-12 | RG-14 |
| P0-14 | T-DETERMINISM cross-platform/restart | R-10 | RG-15 |
| P0-15 | T-SERVICE dry run/tabletops/closeout | R-06/R-09 | RG-16 |

RG identifiers are defined in [Release checklist](15-V1-RELEASE-CHECKLIST.md). Detailed implementation tasks are in [Backlog](13-BACKLOG.md).

## 9. CI gates

On every change:

1. format/lint;
2. strict types;
3. unit/property/contract tests and coverage;
4. safety invariants;
5. seeded-fault suite;
6. schema compatibility;
7. secret/SAST/dependency/license scans;
8. receipt integrity and no-PHI/log checks;
9. EN/ES catalog and accessibility automation;
10. documentation links and traceability;
11. build/SBOM/signature smoke test, including successful and wrong-role `plan sign/verify` and `pack sign/verify` command paths.

Network-independent gates use pinned fixtures. Live external source checks are scheduled review inputs and never determine a test pass automatically.

## 10. Manual release evaluation

- Independent clinician and laboratory walkthrough.
- Community harm/representation walkthrough.
- Security threat-model delta and PHI incident tabletop.
- Full NVDA/VoiceOver/keyboard/zoom/EN/ES matrix.
- Fresh install on Windows 11, current macOS, and Ubuntu 24.04 LTS.
- Interrupted execution and cleanup recovery.
- Pack withdrawal and signature-key compromise exercises.
- Independent plan and pack sign/verify exercise with missing, duplicate-role, wrong-purpose, expired, revoked, and stale-trust cases.
- Hidden-fault evaluation.
- External pilot closeout.

Evidence is dated, named, and committed or stored in the controlled release dossier.

## 11. Defect policy

Critical/high safety, privacy, integrity, security, legal, or accessibility defects block external pilot and release and cannot be waived; an allegedly unaffected path must be independently evidenced and formally reclassified. A false pass is more severe than a false fail; both are defects. A medium/low test waiver requires owner, rationale, user impact, compensating control, expiry, and approvals from technical lead plus the relevant safety owner. No waiver can permit missing evidence to pass, PHI acceptance, unsigned clinical approval, or receipt tampering.
