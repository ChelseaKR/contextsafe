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

### Corpus status, 2026-09-04

The part of B-048 that needs no external person is committed:
`tests/fixtures/seeded-faults/` and `tests/test_seeded_faults.py` hold, for
every published fault, one of three things, and the matrix in that test
module (`MATRIX`) says which. **Exercised** means a complete synthetic fixture
(case, rule set, and observation set with exactly one fault applied) and tests
proving the fault is reported as the assertion demands — `fail` with the
predicate's own reason, or `indeterminate` and `unobserved` where absence is
the fault — and located in the receipt's divergence section at the observed
checkpoint the fault touched and nowhere else. **Refused** means the faulted
input cannot reach evaluation: a fail-closed gate refuses it whole with a
named code at a structural path, pinned by a fixture under
`seeded-faults/refused/` or by a named test elsewhere; a refusal is detection
without a receipt and is counted separately from exercised, never as
localization. **Not yet exercisable** means nothing here can express or
decide the fault, and the row names the missing item from a closed
vocabulary. The mutation and detector columns are compared against the table
above verbatim, and this table is compared row for row against the test data,
so neither can drift from the other.

As of 2026-09-04: 12 of 36 exercised at receipt level, 7 refused before evaluation, and 17 not yet exercisable.

This is not the 41-fault evaluation B-048 defines. There is no hidden-fault
set; no independent fault author has reviewed the corpus and no independent
QA has run it; every fault here was written by the implementer of the
mechanism that detects it, so the counts are deterministic corpus coverage
over the published library and nothing more — no population-sensitivity claim
of any kind, and no evidence about faults this library does not contain. An
exercised row may still name a missing item: F-001 is reported at the EHR as
a value change, not at a patient-facing display (A-006), and F-035 proves the
run identity moves with the mapping version, not that a verifier would notice
a claimed one. Rows waiting on SPCU predicates wait on clinical review, not
only on code; rows waiting on laboratory results wait on the laboratory lead's
fixture (B-011) as well as the importer.

| Fault | Status | Evidence | Missing item |
|---|---|---|---|
| F-001 | exercised | `F-001.json`: A-I02 `value_not_present` at `ehr` | patient-facing display observation (E-DISPLAY, B-019) |
| F-002 | not yet exercisable | — | patient-facing display observation (E-DISPLAY, B-019); name contexts and periods in the observation contract (B-019) |
| F-003 | not yet exercisable | — | name contexts and periods in the observation contract (B-019) |
| F-004 | exercised | `F-004.json`: A-I02 `value_not_present` at `ehr` | — |
| F-005 | exercised | `F-005.json`: A-I01 `status_not_preserved` at `ehr` | — |
| F-006 | exercised | `F-006.json`: A-I05 `overwritten_by_other_concept` at `ehr` | — |
| F-007 | exercised | `F-007.json`: A-I06 `value_coerced` at `registration` | — |
| F-008 | exercised | `F-008.json`: A-I01 `value_coerced` at `registration` | — |
| F-009 | exercised | `F-009.json`: A-I02 `value_changed_across_checkpoints` at `ehr` | — |
| F-010 | exercised | `F-010.json`: A-I01 `record_count_changed` at `registration` | — |
| F-011 | not yet exercisable | — | SPCU predicates awaiting clinical review (B-029) |
| F-012 | not yet exercisable | — | SPCU predicates awaiting clinical review (B-029) |
| F-013 | not yet exercisable | — | SPCU predicates awaiting clinical review (B-029) |
| F-014 | not yet exercisable | — | SPCU predicates awaiting clinical review (B-029) |
| F-015 | refused | `refused/F-015.json`: `prohibited_spcu_mapping` at `$.observations[0].mapping` (declared form only; undeclared derivation needs A-020/A-021, B-029) | SPCU predicates awaiting clinical review (B-029) |
| F-016 | refused | `refused/F-016.json`: `prohibited_spcu_mapping` at `$.observations[0].mapping` (declared form only; undeclared derivation needs A-020/A-021, B-029) | SPCU predicates awaiting clinical review (B-029) |
| F-017 | not yet exercisable | — | laboratory results (B-011, B-025, B-030) |
| F-018 | not yet exercisable | — | laboratory results (B-011, B-025, B-030) |
| F-019 | not yet exercisable | — | laboratory results (B-011, B-025, B-030) |
| F-020 | not yet exercisable | — | laboratory results (B-011, B-025, B-030) |
| F-021 | not yet exercisable | — | laboratory results (B-011, B-025, B-030) |
| F-022 | not yet exercisable | — | laboratory results (B-011, B-025, B-030) |
| F-023 | exercised | `F-023.json`: A-I02 and A-I03 `missing_evidence`; `lis_return` unobserved | — |
| F-024 | refused | `refused/F-024.json`: `invalid_rsg_value` at `$.observations[0].value.value` | normalizer and adapters (B-022 to B-026) |
| F-025 | exercised | `F-025.json`: A-I02 `value_changed_across_checkpoints` at `interface`; `ehr` never named | — |
| F-026 | not yet exercisable | — | receipt verifier (B-036) |
| F-027 | not yet exercisable | — | evidence-minimized presentation (B-038); patient-facing display observation (E-DISPLAY, B-019) |
| F-028 | refused | `tests/test_pack.py::test_pack_rejects_inactive_expired_or_incompatible_content` | authored assertions with validity (B-010) |
| F-029 | refused | `refused/F-029.json`: `invalid_synthetic_identifier` at `$.synthetic_identifier`; `tests/test_preflight.py::test_field_namespace_free_text_and_canary_fail_closed` | — |
| F-030 | refused | `tests/test_receipt_schema.py::test_stripped_or_padded_limitations_fail_the_contract` | — |
| F-031 | exercised | `F-031.json`: A-I01 `status_not_preserved` at `ehr` | — |
| F-032 | refused | `refused/F-032.json`: `case_mismatch` at `$.observations` | authored assertions with validity (B-010) |
| F-033 | not yet exercisable | — | laboratory results (B-011, B-025, B-030) |
| F-034 | not yet exercisable | — | signatures and role thresholds (B-035) |
| F-035 | exercised | `F-035.json`: trace names mapping `0.2.0`; `payload_sha256` moves | receipt verifier (B-036) |
| F-036 | not yet exercisable | — | review and disposition state machine (B-032) |

Why the not-yet-exercisable rows are not stretched: an SPCU that is absent at
a boundary is indistinguishable, under the observation contract, from a
boundary nobody observed, so F-011 can only be `indeterminate` today and a
`fail` needs an observed-absence form and the A-016/A-024 predicates; F-012
reads as `diverged` at the interface in the divergence section but no
predicate can name which order carried the wrong SPCU; F-013 needs an
effective period the contract does not carry; F-014's detached support is
refused as `invalid_support` before evaluation rather than reported, and a
relinked support is only a changed value, which says nothing about
traceability; F-002 and F-003 need a legal-name context and a name period, and
`legal_name` is a prohibited key by design; F-026 would be a hash comparison
the verifier has to make, and no verifier exists; F-027 needs a result-facing
display observation and the B-038 presentation pass; and the seven laboratory
rows have no analyte, interval, unit, or flag in any contract. Stretching any
of them into an exercised row would count a detection the mechanism does not
make.

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

### Privacy canary matrix

The rejection cases above establish that a direct identifier, control
character, or unapproved free-text value fails closed. The canary suite
(`tests/test_privacy_canaries.py`, B-039) establishes where that boundary
actually falls and what surfaces it can leak into. Near-miss cases run in both
directions: approved codes that resemble identifiers must not be false
positives, and values one character from acceptable must fail closed with a
named code. Three identifier-shaped values pass the pattern scan today — a date
outside the pattern's 19xx/20xx window, a date written with dots, and a
seven-digit local number — and are pinned as blind spots for the independent
security review rather than presented as approved behavior; the
synthetic-namespace grammar, not the scan, is what bounds them. The log canary
is structural: no module imports `logging`, no module prints, and no accepted
or rejected command emits a log record. The crash canary requires that an
unexpected failure after the boundary read carries neither evidence content nor
the caller's source path, and that a CLI rejection prints a structured error
rather than a traceback. The index canary draws the storage boundary
explicitly: raw bytes stay in the content-addressed object that `raw_sha256`
names, while the SQLite index a diagnostic or support bundle would read carries
hashes, tokens, and provenance only. A final matrix property asserts that no
rejection anywhere echoes the value that triggered it.

### Determinism matrix

Invariant 10 is tested in two forms. In process, the property layer permutes a
generated bundle's observations and rules and requires the same payload bytes.
Across processes, `tests/test_determinism.py` runs each shipped command three
times in fresh interpreters under different time zones, locales, hash seeds,
UTF-8 modes, working directories, and input directories, and requires
byte-identical exit codes, stdout, stderr, and `--output` artifacts. Every
artifact must be one canonical UTF-8 JSON line with one terminal newline and no
carriage return; the reference `evaluate` document has a pinned SHA-256 that a
CI matrix must reproduce on Ubuntu, macOS, and Windows; no absolute input path,
locale, or time-zone value may appear in an artifact; a caller-declared
`claimed_generated_at` must move the envelope without moving `payload_sha256`;
and a fail-closed rejection must emit the same stderr bytes and error code every
run. The matrix runs GitHub's server images, so it is byte-reproducibility
evidence and not the Windows 11 and macOS desktop fresh-install evidence RG-15
requires (B-045). Commands that read components beneath a root require
descriptor-relative no-follow open and fail closed with
`input_path_unsupported` where the platform cannot provide it; a monkeypatched
test pins that behavior on every platform rather than trusting a Windows-only
observation.

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
