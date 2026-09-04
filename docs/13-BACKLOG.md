# Implementation backlog

Status: estimated v1 baseline  
Estimation: core-team ideal days; specialist hours are shown separately  
Priority order: top to bottom within each phase  
Owners: F product/delivery pool (0.8-FTE founder plus the scheduled product/research delivery lead), E engineering pool (the scheduled senior implementation engineer), CL clinical chair, LAB laboratory lead, COM community co-chair, SEC security/privacy, A11Y accessibility/language, LEG counsel, DP design partner

An item is done only when its acceptance statement has objective evidence. Estimates include implementation and tests but not procurement delay.

### Core-team role allocation

Each pair below is `F/E` ideal days and accounts for every P0 item. The task table's owner is accountable; this ledger is the delivery-capacity split. Within `F`, the founder and delivery lead receive named task assignments before each stage; the delivery lead does not inherit any independent clinical, community, security, or legal approval authority.

| Items | Per-item F/E allocation | F subtotal | E subtotal |
|---|---|---:|---:|
| B-001–007 | 10/0; 3/0; 3/2; 5/0; 2/0; 2/1; 2/0 | 27 | 3 |
| B-008–014 | 2/3; 2/3; 7/1; 4/0; 4/0; 2/0; 1/4 | 22 | 11 |
| B-015–021 | 3/0; 3/1; 5/3; 2/3; 3/2; 1/3; 1/3 | 18 | 15 |
| B-022–031 | 2/1; 3/4; 3/5; 3/2; 3/2; 3/3; 2/3; 2/4; 2/4; 2/2 | 25 | 30 |
| B-032–038 | 3/2; 2/2; 2/4; 2/6; 2/3; 1/3; 3/0 | 15 | 20 |
| B-039–048 | 2/3; 2/0; 3/2; 2/0; 2/2; 2/0; 2/4; 2/3; 3/0; 0/6 | 20 | 20 |
| B-049–056 baseline | 3/2; 4/6; 1/4; 2/3; 1/2; 0/5; 1/1; 0/2 | 12 | 25 |
| **B-001–056 baseline** | — | **139** | **124** |
| B-057 conditional extension | 4/6 | 4 | 6 |
| **Maximum if invoked** | — | **143 / 252.5 available** | **130 / 170 available** |

Temporal capacity is a separate constraint:

| Gate | Work that must be complete | F capacity / assigned | E capacity / assigned |
|---|---|---:|---:|
| DG-01, end week 4 | B-001–B-007 | 31 / 27 | 20 / 3 |
| DG-04, end week 21 | B-001–B-048 | 146.5 / 127 | 105 / 99 |

The week-21 `E` reserve is six days. No additional pre-pilot engineering scope may consume it; a forecast beyond 99 assigned days requires added engineering capacity or a moved DG-04.

## Phase 0 — discovery and authority

| ID | Trace | Deliverable and acceptance | Owner | Dependency | Estimate |
|---|---|---|---|---|---:|
| B-001 | H-01..06, DG-01 | Recruit and complete 15–20 interviews; synthesis includes disconfirming evidence and buyer path | F | none | 10d |
| B-002 | P0-15, R-09 | Obtain design-partner LOI naming sponsor, technical/clinical/lab/privacy owners, pathway, and target release | F/DP | B-001 | 3d |
| B-003 | P0-15, R-06 | Map partner non-production topology, exports, synthetic suppression, and cleanup | F/DP | B-002 | 5d |
| B-004 | P0-10, R-01/R-05 | Recruit governance roster and sign charter/conflicts/compensation | F/CL/COM | none | 5d + 24h reviewers |
| B-005 | P0-11, R-07/R-11 | Counsel memo on FDA/CDS, UPL/UPM, HIPAA/BA, claims, contract, and insurance | LEG | B-002 | 2d + 20h counsel |
| B-006 | G-06 | Paper receipt comprehension test with five cross-role reviewers | F/A11Y | B-001 | 3d + 5h reviewers |
| B-007 | DG-01 | Discovery decision memo scores every continue/kill gate | F/CL/COM | B-001..006 | 2d |

## Phase 1 — governed pack and contracts

| ID | Trace | Deliverable and acceptance | Owner | Dependency | Estimate |
|---|---|---|---|---|---:|
| B-008 | P0-01 | Define pack/case/assertion/source/approval JSON Schemas with invalid examples | F | B-007 | 5d |
| B-009 | P0-02, CTP-001..012, R-25 | Author canonical case manifests with necessity and prohibited-inference fields | F/CL/COM | B-004/B-008, adopted [publication policy](17-PUBLICATION-POLICY.md) | 5d + 16h review |
| B-010 | A-001..A-036 | Author assertion predicates, applicability, states, evidence, and severity rubric | F/CL/LAB | B-008/B-009 | 8d + 40h review |
| B-011 | A-025..A-030 | Define INV/CTX/XFAIL reference fixtures and boundary values; label them non-clinical reference data | LAB/F | B-010 | 4d + 16h lab |
| B-012 | P0-01, R-03 | Implement approval, validity, withdrawal, and pack compatibility rules | F/CL/COM | B-008..011 | 4d |
| B-013 | P0-02, R-01 | Complete independent clinical and community pack review; unresolved content excluded/experimental | CL/COM/LAB | B-009..012 | 2d + 40h reviewers |
| B-014 | P0-01/P0-12 | Build deterministic pack compiler/validator and source manifest | F | B-008/B-012 | 5d |

Publication gate on this phase: B-009 and B-010 are the first artifacts that would
state which fields at which boundaries carry trans identity data, so the
[publication policy](17-PUBLICATION-POLICY.md) decision record must name a date
before B-009 authoring starts. The policy also requires a re-read of
already-public documents against its classification rule at that point. This is a
sequencing constraint rather than added work: deciding after the pack exists is
deciding under pressure, with the artifact already written.

## Phase 2 — execution plan and evidence core

| ID | Trace | Deliverable and acceptance | Owner | Dependency | Estimate |
|---|---|---|---|---|---:|
| B-015 | P0-03 | Define engagement/plan schemas and approved environment/namespace/cleanup contract | F/SEC | B-003/B-008 | 3d |
| B-016 | P0-03, T-PLAN | Implement plan validation that blocks production, unallowlisted host, missing owner, and namespace mismatch | F | B-015 | 4d |
| B-017 | P0-11, T-PRIVACY | Implement streaming size/type/field/namespace/free-text/canary preflight before persistence | F/SEC | B-015 | 8d |
| B-018 | P0-04 | Implement content-addressed raw evidence store and append-only SQLite index | F | B-017 | 5d |
| B-019 | P0-04/P0-12 | Define canonical observation/evidence models with source pointers and ambiguity | F | B-008/B-018 | 5d |
| B-020 | P0-14 | Implement CLI shell, stable JSON errors, exit codes, quiet/no-color modes | F/A11Y | B-014/B-016 | 4d |
| B-021 | P0-14, R-10 | Implement normalized deterministic payload and timestamp/signature envelope separation | F | B-019/B-020 | 4d |

Implementation note (2026-07-13): internal risk-reduction code now exercises B-017
for one strict canonical JSON envelope, B-018 through a non-executable local store, and
part of B-019 through published raw-evidence and ambiguity-preserving observation
contracts. These backlog items are not closed: authorized import still depends on
B-035; normalization and mapping/version binding remain B-019/B-021/B-026;
FHIR/HL7/LIS and canonical adapter acceptance remain B-022–B-026; governed cleanup is
B-046; and independent security, privacy, interoperability, clinical/community, and
pilot gates remain outstanding.

Implementation note (2026-07-17, B-020): the shipped commands now share `--quiet`
and `--no-color` modes, documented stable exit codes (0 success, 2 contract
rejection, 64 usage error), and an ANSI-free output regression test. B-020 is not
closed: most of the command surface in [Architecture §7](04-ARCHITECTURE.md)
(sign/verify, import, normalize, review, render, diff, cleanup) does not exist
yet, and independent accessibility review of operator-facing CLI conventions is
outstanding.

Implementation note (2026-08-15, B-021): the three-run reproducibility evidence
named in the note below now exists for the shipped commands.
`tests/test_determinism.py` runs each command three times in fresh interpreters
under different time zones, locales, hash seeds, UTF-8 modes, working
directories, and input directories, and requires byte-identical exit codes,
stdout, stderr, and `--output` artifacts plus a pinned reference-receipt digest;
a CI matrix reproduces the same digest on Ubuntu, macOS, and Windows. Command
output is now written as UTF-8 bytes rather than through a text stream, because
text-mode writes translate the terminal newline on Windows and would have given
the same receipt two different file digests. B-021 is not closed: observation
normalization and mapping/version binding remain with B-019/B-026, no signing
path exists (B-035), the matrix runs GitHub's server SKUs rather than the
Windows 11 and macOS desktop fresh installs RG-15 requires, and packaging and
fresh-install evidence remain B-045. The matrix also records a live platform
limitation: `pack validate`, `plan validate`, and `evidence preflight` depend on
descriptor-relative no-follow reads, which Windows cannot provide, so they fail
closed there with `input_path_unsupported` while
[Operations](10-OPERATIONS-SRE.md) still lists Windows 11 as a planned supported
platform. Closing that gap needs a decision, not a test.

Implementation note (2026-07-17): the payload/envelope-separation part of B-021 is
now exercised: `contextsafe evaluate` emits a receipt document whose deterministic
payload is hashed separately (`payload_sha256`) from an untrusted envelope carrying
caller-declared `claimed_generated_at`, `signature_status: not_signed`, and
`trusted_time: false` (P0-14, R-10). B-021 is not closed: observation normalization
and mapping/version binding remain with B-019/B-026, no signing path exists (B-035),
and cross-platform three-run reproducibility evidence remains outstanding.

## Phase 3 — adapters and evaluator

| ID | Trace | Deliverable and acceptance | Owner | Dependency | Estimate |
|---|---|---|---|---|---:|
| B-022 | P0-04 | Canonical JSON import with schema and property tests | F | B-017..021 | 3d |
| B-023 | P0-04 | FHIR R4 JSON parser for allowlisted resources/extensions; any narrative, contained resource, unrelated field/resource, or unapproved free text rejects the entire source before persistence—never strip and accept | F | B-017..021 | 7d + 8h interop |
| B-024 | P0-04 | HL7 v2 ER7 parser for approved PID/GSP/OBR/OBX profile with bounded input | F | B-017..021 | 8d + 12h interop |
| B-025 | P0-04/P0-07 | LIS CSV/JSON mapping and fixture importer | F/LAB | B-011/B-017..021 | 5d + 4h lab |
| B-026 | P0-04, R-08 | Versioned mapping profile with ambiguity retention and fixture approval | F | B-022..025 | 5d |
| B-027 | P0-08 | Implement status algebra and pure evaluator; all ten safety invariants property-tested | F | B-010/B-019/B-026 | 6d |
| B-028 | P0-05 | Implement identity/NtU/pronoun/RSG predicates A-005..A-015 | F | B-027 | 5d |
| B-029 | P0-06 | Implement SPCU context/provenance/period predicates A-016..A-024 | F/CL | B-027 | 6d + 8h review |
| B-030 | P0-07 | Implement result/range/flag predicates A-025..A-031 | F/LAB | B-025/B-027 | 6d + 8h lab |
| B-031 | P0-08/P0-12 | Implement first-observed-divergence and evidence trace A-032..A-035 | F | B-027..030 | 4d |

Implementation note (2026-07-17, B-027): the property-test layer from
[Test and evaluation §2](09-TEST-AND-EVALUATION.md) is now seeded with
Hypothesis suites covering the machine-checkable status-algebra invariants
(§3 items 1, 3, 4, 9, 10) against the iteration-1 evaluator and receipt.
B-027 is not closed: the governed status algebra over approved assertions
still depends on B-010/B-019/B-026, and invariants 2, 5, 6, 7, and 8 need
pack-lifecycle execution blocking, review signatures, HTML rendering, and
signature verification that do not exist yet.

Implementation note (2026-09-04, B-022): `contextsafe import --format
canonical-json` now exists as the read-only conversion step: it runs the
iteration-3 evidence boundary scan on one canonical JSON envelope and converts
it, whole or not at all, into the observation-set document `evaluate` accepts,
with the source digest and record pointer on every observation, the importer's
version as the mapping version, and the case token cross-checked against the
case document. `src/contextsafe/importers/` is the boundary the FHIR, HL7, and
LIS adapters (B-023–B-025) will register into: a shared `ImportResult`, a
closed warning vocabulary, an `import_*` rejection family, and a registry the
command line reads, so a new format is one module and one entry. Values are
carried as the source's own tokens, so evaluating an imported observation
against the reference rule set reports `semantic_mismatch` until a mapping
profile binds the token, and `profile_reviewed` is `false` on every result.
A gender-identity, name, or pronouns record whose value is a recorded-sex code
or a laboratory status (which the envelope admits for any field) rejects the
source rather than arriving as that concept's value under a foreign token;
`evidence preflight` accepts and rejects the same sources as before, with the
plan-scope check now run after the envelope parse. The property suites assert
value-free rejection structurally (whole error object in a closed set at the
expected path), not by substring, so the gate is the same colour for the same
tree on every Hypothesis draw.
B-022 is not closed: the field-code mapping is reference-only and no
interoperability, clinical, or community reviewer has approved it; the source's
`plan_id` is checked for shape and not against a plan, because the plan-bound,
persisting `evidence import` still depends on B-035; sex-parameter records
reject rather than convert, because the envelope cannot carry the
supporting-observation link and no profile (B-026) exists to bind one; the
result's counts and warnings stay in process because the observation-set
contract has no field for them; and the property suites cover the
machine-checkable invariants only, not adapter acceptance against a partner
export.

Implementation note (2026-09-04, B-023): `contextsafe import --format
fhir-r4-json` now reads one FHIR R4 JSON `Patient`, alone or as the only
entry of a `collection` or `searchset` `Bundle`, through the shared boundary
scan and an exact element allowlist, and converts the HL7 Gender Harmony
`individual-genderIdentity`, `individual-pronouns`, and
`individual-recordedSexOrGender` extensions and the `HumanName` with `use`
`usual` into the observation set `evaluate` accepts, with the source digest,
the profile version, and an RFC 6901 pointer on every observation. Any
narrative, contained resource, element outside the allowlist, unknown
extension or sub-extension, `display`, `comment`, reference, identifier
outside the synthetic namespace, coded value outside the synthetic alphabet,
name with no part, `data-absent-reason` coding on recorded sex or gender
(the canonical concept has no presence state, so that system's `unknown` is
never carried as the recorded value `unknown`), document over one MiB, or
Patient carrying none of the concepts rejects the whole source with a code
and a location; nothing outside the allowlist is dropped, a recorded-sex-or-gender
value outside the contract's closed alphabet and any coding token over the
contract's 96-character bound reject at their own location in the source
rather than in the converted document, and a fixture per rejection class is
committed and pinned. What the allowlist admits and the canonical model
cannot hold is validated and not carried, and the list is closed:
`Patient.id`, `Patient.active`, every `HumanName` whose `use` is not `usual`,
`family` on the usual name, the pronouns coding's system, and the
recorded-sex-or-gender value's system. Two carriers of one concept are
two observations, which the evaluator reports as ambiguous. The reader's
choices are one versioned profile constant with `reviewed` fixed to false, and
the accepted subset is published as a reference-only schema. B-023 is not
closed: no interoperability reviewer (the 8h the row budgets) has examined the
profile, and the elements chosen where the guide is uncertain (the `value`
sub-extension form, `type` as the RSG context, the three `data-absent-reason`
presence codes) are recorded as choices, not as conformance; sex parameter for
clinical use is recognised by its extension URL and always rejects, because
neither `Encounter` nor `ServiceRequest` is implemented as an order-context
carrier and no allowlisted resource can carry a supporting observation, so
SPCU acceptance is deferred with the B-026 profile work; name periods
(CTP-009), RSG jurisdiction and source document, and every other Gender
Harmony sub-extension are not carried; the reader takes a file and never a
FHIR endpoint (Architecture section 10 remains P1); the coding system of a
recorded-sex-or-gender `value` is checked only against the presence system
and the token bound and is otherwise not carried, because the canonical
model has no field for it, and which systems an RSG value may come from is a
profile choice left for the reviewer; the synthetic-data confirmation in
`docs/PUBLICATION-READINESS.md` section 4 was found describing the corpus as
it stood before this item (five packaged files, no `birthDate` anywhere, no
PII-shaped literal outside `tests/test_preflight.py`) and is corrected under a
dated update with two tests that derive its figures and literal list from the
tree; neither `diagnostics` nor the support bundle enumerates
the importer registry's formats; and the receipt's limitation line still
reads "does not ingest FHIR", a reviewed wording the maintainer decides.

Implementation note (2026-09-04, B-024): `contextsafe import --format
hl7v2-er7` now exists, registered through the B-022 importer registry with no
change to the command line: a bounded (one MiB) read of one ER7 message
through the same no-follow, descriptor-retaining first pass as the other
boundary commands, a strict parse whose delimiters are exactly MSH-1 and
MSH-2, and a closed segment allowlist of MSH, PID, GSP, OBR, and OBX. Every
profile decision is a versioned constant (`HL7V2_ER7_PROFILE`, 0.1.0,
`profile_reviewed` false and unsettable): PID-3 must carry the synthetic
identifier system and the case's token; PID-5 name type `D` is the name to
use; GSP-4 is a closed concept-type table carrying GI, pronouns, SPCU, and RSG
each to its own concept; OBR and OBX are read only to locate SPCU context and
supporting-observation tokens and to reject free text. PID-8 reaches
`recorded_sex_or_gender` with context `administrative` and nothing else, by
the type of the one function that reads it rather than by any table, and a
property suite pins that over arbitrary values with a structural comparison
against a closed set of rejections. A Z-segment, a populated field outside
the profile, a repetition where one value is admitted, an unhandled escape,
free text, a non-synthetic identifier, or a value the observation contract
rejects fails the whole message with a code and a location. GSP-5.3, the
coding system of a GSP value, is read only as the code system of a specified
gender identity value and rejects everywhere else rather than being dropped,
so a pronouns or SPCU token asserted in a vendor coding system cannot convert
as the bare token and pass its rule; OBX-11 is required.
B-024 is not closed: the profile is reference-only and no interoperability,
clinical, or community reviewer has confirmed the `D` name-type code, the
LOINC concept-type codes, or the decision to read RSG and SPCU from GSP when
v2.9.1 also defines GSR and GSC for them (both reject as segments outside the
allowlist); the 12 hours of interoperability review the estimate names have
not happened; presence states are read from the literal tokens `declined`,
`unknown`, and `absent` rather than from HL7 null flavors, and table 0001
values other than the RSG contract's set (`U`, `O`, `A`, `N`) reject until a
mapping profile (B-026) binds them; the message cannot state a checkpoint, so
the requested one is applied and the result says so; MSH-7 is checked for
shape only and never carried; a gender identity presence state is emitted
with the unbound code system, the same as the canonical JSON importer, and
whether a presence state may name a coding system at all is a B-026
mapping-profile decision this importer settles by rejecting; the mutation
gate's declared targets (`tools/mutation_gate.py`, ADR 0009) do not include
the importer, so its accept and reject decisions have branch-coverage
evidence, which measures execution, and no mutation evidence, which would
measure detection; and the property suites cover the machine-checkable
invariants, not adapter acceptance against a partner's interface-engine
output.

Implementation note (2026-09-04, B-025): the identity half of the LIS
export reader exists as `contextsafe import --format lis-csv` and
`--format lis-json`, registered into the B-022 registry with no change to
`cli.py`. Each reads only the identity columns of a laboratory result export
(`patient_id`, cross-checked against the case; `name_to_use`; `pronouns`;
`sex`, mapped only to recorded sex or gender in the fixed context
`laboratory`) into observations at `lis_return`, one per distinct value per
column, so a result export that repeats the identity per row is not
ambiguous with itself and rows that disagree stay ambiguous. The result
columns (`analyte`, `value`, `unit`, `range`, `flag`, `order`, `specimen`)
are recognized, bounded, scanned, and counted and produce no observation;
the source gets the closed warning `result_columns_not_observed`. The column
set is the versioned profile constant `LIS_PROFILE` 0.1.0 with
`profile_reviewed` false and a type that refuses true. An unknown column or
key, a formula-leading cell, an empty identity cell, a non-synthetic
identifier anywhere, free text in any cell, a malformed record, or a bound
overrun rejects the whole file by position. CSV is an RFC 4180 subset read
by a strict reader of its own; JSON is the published
`contextsafe-lis-export-v0.1.schema.json`. Both read through
`preflight.read_source`, the boundary's bounded no-follow first pass, and
hold every cell to `preflight.scan_text`. The reference set gains
`lis-export.csv` and `lis-export.json`; both imports are pinned in the
determinism matrix; `lis.py` and `lis_csv.py` are safety modules; one
fixture per rule sits under `tests/fixtures/lis/`.
B-025 is not closed: the profile is reference-only and the 4h laboratory
review the row budgets has not happened, so no reviewer has said this is
the shape of any export; the laboratory half — result, range, flag, order,
and specimen observations — does not exist, because the observation contract
has no concept for them and A-025..A-030 wait on B-030 and the B-011
fixtures; values are carried as tokens with no mapping profile (B-026) to
bind them, so a pronoun token or a laboratory-context sex value reports
`semantic_mismatch` against the case manifest rather than pass or fail on
its merits; an empty identity cell rejects rather than reading as `absent`,
because deciding what an LIS's empty cell means is a profile decision; and
the result's counts and warnings stay in process.

Implementation note (2026-09-04, B-026): the versioned mapping profile
exists as `schemas/contextsafe-mapping-profile-v1.schema.json`, a closed
document naming the importer format it applies to, a SemVer version, a
review record whose only admissible status is `not_reviewed` (no reviewer,
no date; anything else rejects), and a table from source token — the
carrier the importer read it from and the verbatim token — to the canonical
concept and value the observation should carry. `contextsafe mapping
validate --profile P.json --output canonical.json` emits the canonical
unsigned profile and its SHA-256 as
`contextsafe-compiled-mapping-profile-v1` (`signature_status:
not_verified`, `executable: false`); `contextsafe mapping sign` from
Architecture section 7 is not built. `contextsafe import ... --mapping
PROFILE.json` validates the profile, requires it to be for the same format,
converts as before, and applies the profile after parsing; without
`--mapping` every importer keeps emitting verbatim tokens, byte-identical.
Every importer now records a `SourceToken` (concept, carrier, token) beside
each observation, and the registry's carrier table (`Importer.carriers`) is
what a profile is validated against, so `PID-8` can be read only as
recorded sex or gender and the FHIR sex-parameter URL is not a carrier at
all. Validation rejects a row whose target is SPCU from a GI or RSG carrier
first and by name (`prohibited_spcu_mapping`, A-020, A-021), any other
cross-concept row, two rows collapsing two source values into one target
(both are retained as distinct observations, which the evaluator reports
ambiguous), a duplicate source, a target outside the synthetic grammar
(`CSYN-`/`fixture-` tokens, `urn:contextsafe:` systems, the RSG alphabet, a
closed set of recording contexts, a lowercase pronoun-set shape), and a
sex-parameter target with any field but `value`, so a profile cannot bind an
order context or a supporting observation. Every observation an import
emits with a profile applied carries `profile_sha256` and `profile_version`
in its mapping block — the observation-set contract is widened for the pair,
required together, without a version bump, the way B-023 widened it — so
`evaluate`'s input hash binds the profile. Five reference profiles ship as
package data (`mapping-<format>.json`, exported by `fixtures export`), one
per registered importer, binding the reference fixtures' tokens to the
reference case's values so that import then evaluate passes every rule at
the imported checkpoint and reports `missing_evidence`, never
`semantic_mismatch`, for the rest; seventeen negative profiles, one per
prohibited row class and more, sit under `tests/fixtures/mapping/`, each
pinned to its code and location and to the layer that refuses it.
`mapping_profile.py` and `importers/mapping.py` are safety modules;
`import --mapping` per format and `mapping validate` are in the
determinism matrix with pinned digests; the reference-receipt digest and the
verbatim import digests are unchanged.
B-026 is not closed: the "fixture approval" in the row's deliverable has
not happened and cannot happen here — no interoperability reviewer has
examined any profile, and the schema admits no status by which one could say
so, deliberately; the reference profiles are synthetic bindings for the
reference fixtures and not the mapping of any real system, and the
recording context a row binds (the HL7 `PID-8` value to the case's
`government-id` record) is a declaration the profile makes that nothing has
confirmed; HL7 null flavors, the FHIR `data-absent-reason` codes beyond the
three the reader already admits, and an LIS's empty cell are still not
bound to presence states, because a profile row names a token the importer
emitted and those sources reject before emitting one; a token with no row
passes through verbatim with a closed warning rather than rejecting the
source, a fail-closed alternative the maintainer may prefer; the synthetic
target grammar (in particular the pronoun-set shape, admitted because the
reference case's own value is `they/them`) is a reference-only choice no
community reviewer has confirmed; the `mapping sign` command, a signer key,
a trust manifest, and the enrolled ContextSafe interoperability reviewer it
needs all wait on B-035; and the sibling `contextsafe-observation-v1`
contract, which no runtime parser reads, carries no profile binding.
Implementation note (2026-09-04, B-028): the identity, name-to-use, pronoun,
and recorded-sex-or-gender predicates of A-005 and A-008 to A-015 exist as
mechanism. A rule set declaring `contextsafe.rule-set/0.2.0` may name one of a
closed set — `exact` (the default), `present`, `status_preserved`,
`not_coerced`, `record_count`, `preserved_across`, `not_overwritten_by` — each
a pure function in `src/contextsafe/evaluator.py` with one affirmative and one
failure reason in the receipt contract, which moved to 0.2 for those reasons.
Missing or ambiguous evidence stays indeterminate under every predicate; a rule
that would be vacuous for its concept, or that the case manifest contradicts,
is refused; and the 0.1.0 rule-set shape, the reference `rules.json`, and the
pack contract that pins it are untouched. A second ungoverned reference pair
(`rules-predicates.json`, `observations-predicates.json`) exercises every
predicate against CTP-I01, and `tests/fixtures/seeded-faults/` carries F-004,
F-005, F-006, F-007, F-008, F-010, and F-031 with tests proving each is
reported as fail with its own reason and never as pass. B-028 is not closed:
the predicates are reference-only and ungoverned, because B-010 — the authored
assertions with applicability, evidence, severity rubric, and clinical,
laboratory, and community approval — has not happened, and no predicate here
is an approved assertion; A-006, A-007, and A-015 (patient-facing display,
legal-name contexts, expired name history) need a display observation and a
name period the observation contract does not carry; `not_coerced` decides
presence status and scalar only, so the faithful X under a rewritten context
passes it and is the `exact` rule's to report, and a checkpoint carrying two
records of one concept is `ambiguous_evidence` under it, so a multi-record
case cannot be evaluated for A-014; `preserved_across` states preservation,
not correctness; and a 0.2.0 rule set is refused as a pack component
(`incompatible_component`) until the pack contract's `rule_set_schema` pin is
revisited, which is a contract decision for the maintainer. The receipt
contract file the B-033 note below (Phase 4) names is now
`schemas/contextsafe-receipt-v0.2.schema.json`. Review fixes of the same day:
`not_coerced` first compared whole typed values, so X rewritten to F was
reported as `pass`/`value_not_coerced` whenever the boundary also stamped its
own context or source on the record, a false affirmative on the fault (F-007)
the predicate exists to detect; it now compares the presence status and the
scalar (`coercion_key` in `models.py`), the validator applies the same
projection to the forbidden set's uniqueness, its conflict with the expected
value, and its conflict with the case manifest, and tests hold that M or F
under a rewritten context, source, or both is `fail`/`value_coerced` in the
reference pair and in F-007 and F-008 while the faithful X under another
context is not a coercion; the reference pair ships A-I09, the `exact` rule
beside A-I06, so a receipt says which of the two claims turned; the property
generator reaches pass and fail under every predicate by design (one
observation at every checkpoint a predicate reads, values drawn from the
faithful, forbidden, restamped-forbidden, status-moved, and other-concept
cases) with a derandomized guard test that fails when a branch stops being
reached; run against the earlier generator, that guard does not reach
`preserved_across` pass or fail, `not_coerced` fail, or `not_overwritten_by`
fail within its bound, so the invariants over those branches were asserting
nothing; `parse_bundle` refuses a `not_overwritten_by` rule whose expected
scalar the manifest also declares under another concept
(`overwritten_expectation_conflict`), since a faithful observation could never
pass it, and a `record_count` rule over a manifest that declares one record
twice (`indistinct_declared_records`), since the predicate counts distinct
hashes and a faithful copy could only be reported as a changed count. The
case contract itself still admits the repeated record; refusing it there is a
0.1 case-contract decision this pass did not take. `make mutants` still
declares only `contract_validation.py` and
`identifiers.py`; extending that declaration to `evaluator.py` and
`validation.py` is an ADR 0009 decision the maintainer has not taken.

Implementation note (2026-09-04, B-031): the first observed divergence and
the evidence trace of A-032 to A-035 exist as mechanism. `contextsafe.divergence`
walks the checkpoints in pathway order (registration, EHR, interface,
laboratory return) for every concept the manifest declares and reports, from
the case and the observations alone, the first observed checkpoint whose value
hashes depart from the manifest's and, separately, from the previous observed
checkpoint. A checkpoint with no observation is `unobserved` and is never
named as a location: a divergence found across an unobserved gap is located
between the two observed sides, and the receipt shape has no field in which
the gap could be blamed (A-034). Absence is never agreement: the section says
`agreed_where_observed` only about boundaries that had evidence, marks every
other boundary `unobserved`, and reports a boundary that cannot be read as one
state (two observations of a single-valued concept, or one record captured
twice) as `ambiguous` and the concept `indeterminate` from there (A-032).
Every outcome now carries a `trace`: the source hash and structural pointer of
each observation the predicate read and the version and hash of each mapping
they came through (A-035); the validator refuses any observation whose pointer
carries a segment outside a closed structural vocabulary
(`non_structural_pointer`), and a property test holds that nothing but those
words and integers can reach a receipt. The receipt contract moved to 0.3 for
the section and the trace; the HTML page renders the section in `en-US` and
machine-translated `es-US` with the explainer beside its original; and
`tests/fixtures/seeded-faults/` carries F-023 (an omitted checkpoint reported
as indeterminate and unobserved, never pass) and F-025 (a divergence across an
unobserved EHR located at the interface and never at the EHR), with property
tests that reordering observations never changes the section and that
deleting an observed checkpoint never names the deleted boundary, never moves
the located boundary when the deleted one was neither side, and never blames
a boundary that agreed with its observed predecessor. B-031 is not closed:
`unsupported source values remain explicit` (A-033) is enforced today only by
the fail-closed validators of the one source profile that exists, and there is
no normalizer that could normalize anything until B-022 to B-026 exist; the
trace names assertion, mapping, source, and runner but no oracle or pack,
because no governed oracle or pack exists to name (B-010, B-029, B-030);
`ambiguous` is decided by observation count and hash repetition, not by the
ambiguity-preserving observation contract of iteration 3, which has no route
into evaluation yet; the section is not a finding and carries no severity,
which is B-032; and the structural pointer vocabulary is the canonical
manifest and evidence-envelope field names only, so a FHIR or HL7 source path
needs the vocabulary extended under review when those importers arrive. The
receipt contract file the B-028 note above and the B-033 note below name is
now `schemas/contextsafe-receipt-v0.3.schema.json`; the 0.2 file is not kept
beside it.

## Phase 4 — review and receipts

| ID | Trace | Deliverable and acceptance | Owner | Dependency | Estimate |
|---|---|---|---|---|---:|
| B-032 | P0-10, R-05 | Append-only review/finding/disposition state machine with role and signature checks; accepted clinical residual risk requires distinct customer-clinical-owner and ContextSafe-clinical-chair review signatures | F/CL | B-027 | 5d |
| B-033 | P0-09 | Define receipt JSON Schema and claim-minimal deterministic payload | F/SEC | B-031/B-032 | 4d |
| B-034 | P0-09/P0-13 | Build script-free semantic HTML renderer from JSON | F/A11Y | B-033 | 6d |
| B-035 | P0-12 | Implement pinned root trust, role/purpose manifest, plan-enrolled customer keys, explicit plan/pack/mapping/review/receipt thresholds, `plan sign/verify` and `pack sign/verify` plus other Ed25519 signing paths, rotation, detached signatures, revocation freshness, and compromise recovery | E/F/SEC | B-033 | 8d |
| B-036 | P0-09/P0-12 | Implement verification of schema, graph, hashes, approvals, signatures, and withdrawal | F | B-035 | 5d |
| B-037 | P0-12 | Implement deterministic receipt delta for compatible partner profiles; incompatible profiles fail with reason | E | B-036 | 4d |
| B-038 | P0-13 | Implement print stylesheet and evidence-minimized presentation A-036 | F/A11Y | B-034 | 3d |

Implementation note (2026-08-04, B-033): the receipt schema named in
[Architecture §8](04-ARCHITECTURE.md) is now published as
`schemas/contextsafe-receipt-v0.1.schema.json`, the pre-1.0 shape of the planned
`contextsafe-receipt-v1.schema.json`. It closes every object, pins the unsigned
envelope constants and the mandated disclosure set, bounds the payload to
hashes/statuses/counts/limitations with no unbounded free-text field, and
publishes closed status, reason, checkpoint, and concept enums; the
schema/runtime agreement, claim-minimality, mandated-limitation (F-030), and
enum-parity gates are in `tests/test_receipt_schema.py` plus a generated-bundle
property check. B-033 is not closed: the payload is still the iteration-1
fixture result, not a reviewed run, so receipt_id, coverage, findings,
dispositions, reviewer identities, and signature envelopes from
[Architecture §9](04-ARCHITECTURE.md) are absent pending B-031/B-032/B-035, no
independent security review of the receipt contract has happened, and structural
validity is not verification — hash, approval, and signature checking remain
B-036.

## Phase 5 — trust and operations

| ID | Trace | Deliverable and acceptance | Owner | Dependency | Estimate |
|---|---|---|---|---|---:|
| B-039 | P0-11, F-029 | Build direct-identifier, Unicode, free-text, near-miss, log, and crash-dump canary suite | SEC/F | B-017 | 5d + 8h review |
| B-040 | R-07/R-13 | Independent threat-model/security design review; all critical/high findings closed | SEC | B-023..036 | 2d + 20h review |
| B-041 | P0-13 | Externalize all strings; add en-US/es-US catalogs, parity, and pseudolocale gates | F/A11Y | B-034 | 5d |
| B-042 | P0-13 | Professional Spanish translation and independent community review | A11Y/COM | B-041 | 2d + 24h translation/review |
| B-043 | P0-13, RG-14 | Automated axe/pa11y/HTML/contrast/no-color/print tests | F/A11Y | B-034/B-041 | 4d |
| B-044 | P0-13, RG-14 | Manual NVDA/VoiceOver/keyboard/zoom/high-contrast EN/ES evaluation | A11Y | B-042/B-043 | 2d + 20h review |
| B-045 | P0-14 | Package and fresh-install test Windows/macOS/Ubuntu artifacts with SBOM/signatures | F/SEC | B-020..036 | 6d |
| B-046 | P0-15 | Implement diagnostics, cleanup enumerator, redacted support bundle, and local logs | F/SEC | B-018/B-020 | 5d |
| B-047 | P0-15 | Exercise PHI, critical finding, wrong result, pack withdrawal, key compromise runbooks | F/SEC/CL/DP | B-035/B-040/B-046 | 3d + 12h participants |
| B-048 | G-01, F-001..036 | Full 36-published-regression-fault and five-hidden-challenge-fault evaluation; all 41/41 must be detected and correctly localized, with any miss blocking release; corpus-bounded result makes no population-sensitivity claim | E/independent QA | B-028..046 | 6d + 16h QA |

Implementation note (2026-08-15, B-039): the canary suite is seeded in
`tests/test_privacy_canaries.py` for the one source profile that exists. It
pins the boundary in both directions — approved codes that resemble
identifiers and must not be false positives, values one character from
acceptable that must fail closed and with which code, and three documented
blind spots where an identifier-shaped value passes the pattern scan and only
the synthetic-namespace grammar bounds it — plus a structural log canary (no
module imports `logging`, no command emits a record), a crash canary (an
unexpected failure after the boundary read carries neither evidence content nor
the caller's source path), an index canary (raw bytes stay in the
content-addressed object; the queryable SQLite index carries hashes, tokens,
and provenance only), and a matrix property that no rejection ever echoes the
value that triggered it. B-039 is not closed: tuning the direct-identifier
patterns is a security-owned decision and the independent review has not
happened, the blind spots above are recorded for that review rather than
accepted, FHIR/HL7/LIS sources do not exist yet (B-023–B-025), and the
diagnostics, redacted support bundle, and local logs RG-12 also covers are
B-046.

Implementation note (2026-08-15, B-034 and B-041): B-041 depends on B-034, and
B-034 did not exist — `render_receipt` produced canonical JSON, and the package
had no human-facing surface at all, which is also why the previous i18n
declaration could truthfully say "N/A". So B-034 landed first as the enabling
slice: `src/contextsafe/html_receipt.py` and `contextsafe render` produce one
self-contained, script-free, network-free HTML page from a receipt document,
deterministic in the document and the catalog and nothing else, with every
status carried by a word and a symbol rather than by colour, a print
stylesheet, and `data-cs-payload-sha256` on `<main>` so a gate can prove which
receipt it audited.

B-041 then externalized the strings. Catalogs are
`src/contextsafe/locales/*.json`; `src/contextsafe/i18n.py` returns a `Message`
carrying text *and* review status, never a bare string, and a `Surface`
declares what it claims about the text it shows. A surface claiming
`human_reviewed` refuses an unreviewed string by construction. Because B-042
has not happened, the shipped `es-US` catalog is machine translated and marked
`machine` on every entry: the page carries a notice in both languages, marks
each string with `data-cs-review`, and renders every mandated safety
disclosure next to its `en-US` original. `make i18n` runs seven rules plus a
refusal to pass on an empty catalog set; `docs/I18N.md` records the whole
split, including why hash-covered artifacts stay in one language.

Neither item is closed. B-034 covers the receipt page only — the review,
finding, disposition, and delta surfaces in
[Architecture §7](04-ARCHITECTURE.md) do not exist, the print stylesheet has
had no B-038 evidence-minimization pass, and no independent accessibility
review has happened (B-043 automates part of that; B-044 is the human half).
B-041 is not closed while its Spanish is unreviewed: B-042 is a person, and
until that person exists the honest state of this locale is "usable with a
warning", not "translated". Locale-aware number, date, and list formatting and
right-to-left layout are unwritten.

Implementation note (2026-08-15, B-043): `tools/a11y_gate.py` audits the
rendered page in every shipped locale. `make a11y` runs the stdlib checks in
`make verify`; `make a11y-full` adds axe-core in a headless DOM and runs as its
own CI job, because the node harness is not something a clean clone carries.

The design point is refusing a pass the gate did not earn. It renders its own
subjects and validates each page against the receipt document — payload hash,
case id, mandated limitations — before auditing, so an error page or a page from
a different receipt is `wrong-subject` and is not counted as audited. An empty
page set is `no-pages`; a check that examined nothing is
`check-examined-nothing`; a requested engine that cannot run is
`engine-unavailable` rather than a skip; an engine that executed no rules is
`engine-examined-nothing`. Rules axe cannot decide without layout
(`color-contrast`, `landmark-one-main`, `page-has-heading-one`) are listed by
name, never counted as passes, and each must map to a built-in check that does
decide it. Every one of those failures has a negative control in
`tests/test_a11y_gate.py` that was watched to fail.

Running it found one real defect: `role="note"` on the machine-translation
notice overrode the implicit `complementary` landmark of `<aside>`, putting the
notice outside every landmark on the page — skippable by exactly the readers it
is addressed to. axe's `region` rule caught it; the notice is now named by its
heading instead.

B-043 is not closed. pa11y is not wired in: HTML_CodeSniffer loads its rulesets
by script injection and does not complete in a headless DOM without a browser,
so it is absent rather than present-and-skipped, and the rules it would add over
axe are the ones the built-in checks compute. Only the receipt page exists to
audit, so coverage of the surfaces in
[Accessibility §2](08-ACCESSIBILITY-I18N.md) is one row of six. No automated
gate is a substitute for B-044, and the Spanish page is auditable but its
wording is still unreviewed (B-042).

Implementation note (2026-08-15, B-046): `contextsafe diagnostics`, `contextsafe
cleanup`, `contextsafe support-bundle`, and an opt-in local event log
(`--log-dir` on every command). B-018 and B-020, the dependencies, are both in
place, so nothing here is forced.

The support bundle is the part that had to be right, because a bundle from this
tool could carry exactly the identity data the product exists to protect. It is
redacted by construction rather than by filter: every field is a `SafeValue`
from `src/contextsafe/safe_value.py`, there is no constructor that accepts free
text, and the serializer raises on anything that is not one. A caller holding a
string with a patient name in it has nowhere to put it. The assembled bundle is
then scanned with the boundary detectors before it is written and refuses to
emit if anything fires — belt and braces, documented as such, because trusting
that scan would be trusting the denylist again.

`tests/test_diagnostics.py` carries the hostile fixture that motivates the
design: a workspace path with a synthetic patient name in a *directory*
component, a name spelled with a Cyrillic homoglyph, and a record number
written with spaces between its digits. One test runs the repository's own
detectors over those strings and asserts they come back clean, so the claim
"a filter would have shipped these" is checked rather than asserted. A second
control replaced `path_shape` with a regex scrubber and watched the suite fail.
Writing that property test also found a real weakness: the version constructor
accepted `exports-Jordan-Rivera-1987` as a version string, and now requires a
dotted numeric form.

The cleanup enumerator classifies every entry under a workspace — index,
object, staging, directory, and anything it cannot classify — and reports
shapes, counts, and sizes rather than names. Removal is a separate act
requiring `--remove --confirm`, never follows a symlink, never leaves the
workspace, and never deletes an entry it could not classify; a directory still
holding a retained entry is retained with it.

The local log is deliberately minimal. It is off unless `--log-dir` is passed
and is never enabled from the environment, because output that varies with the
environment is what `tests/test_determinism.py` exists to prevent. A record is
a closed vocabulary — command, outcome, error code — with no message field, so
there is nowhere for an exception string or a path to land. It carries no
clock reading: the runner does not read a clock anywhere else and a log is not
a good reason to start, so records carry a per-file sequence number instead.
That is a real limitation and correlating these records with anything external
needs a timestamp captured outside the tool. Nothing imports `logging`, so the
structural log canary in `tests/test_privacy_canaries.py` still holds, and a
logging failure never changes the exit code of the command it logged.

B-046 is not closed. RG-12 also expects governed cleanup at a design partner
(B-047, B-049), and this cleanup enumerates a local workspace, not a partner's
non-production environment. The bundle covers the surfaces that exist; a signing
path (B-035), HL7/LIS adapters (B-024, B-025), and a review surface
(B-032) would each add sections, and each would need the same constructive
treatment; the FHIR reader (B-023) and the canonical importer (B-022) exist
and add none, because neither the diagnostics nor the bundle enumerates the
importer registry's formats. No independent security review of the bundle contents has happened
(B-040).

## Phase 6 — pilot and v1

| ID | Trace | Deliverable and acceptance | Owner | Dependency | Estimate |
|---|---|---|---|---|---:|
| B-049 | P0-15 | After DG-04 passes, complete contract/charter activation, comparable-release time-study baseline, dry run, and one-case cleanup at the design partner; preparatory contracting before DG-04 cannot authorize execution | F/E/DP | B-002..005/B-047/B-048 | 5d (3 F + 2 E) |
| B-050 | G-01..06 | Execute 12-case baseline and issue reviewed receipt | F/E/DP/CL/LAB | B-048/B-049 | 10d (4 F + 6 E) + 16h review |
| B-051 | G-03/G-05 | Support finding dispositions and partner remediation without configuring care; natural defects reported but not quota-gated | F/E/DP | B-050 | 8d elapsed, 5d effort (1 F + 4 E) |
| B-052 | G-02/G-05 | Rerun affected/full pack; partner uses P0 delta receipt and utility/control-value evidence in release decision | F/E/DP | B-051 | 5d (2 F + 3 E) |
| B-053 | G-06 | EN/ES cross-role comprehension study meets 90% target or blocks release | A11Y/F | B-050 | 3d + 20h participants |
| B-054 | RG-01..20 | Assemble independent release dossier and close all P0/risks/checklist evidence | F/all | B-048/B-052/B-053; B-057 if invoked | 5d |
| B-055 | G-05 | Annual-assurance proposal and conversion/objection decision | F | B-052 | 2d |
| B-056 | v1.0 | Sign and publish private/public artifacts consistent with claims policy | F/CL/COM/SEC/LEG | B-054/B-055 | 2d |
| B-057 | G-05 | Conditional one-time evidence extension in global weeks 34–37 with frozen measures and separate change order; no new scope or safety remediation | F/E/DP | B-052; only joint-authority invocation | 10d (4 F-pool + 6 E-pool) + 8h paid review |

## P1 parking lot

| ID | Trace | Trigger | Estimate |
|---|---|---|---:|
| B-101 | P1-01 | Two partners need repeated read-only FHIR collection and security approves | 10–15d |
| B-102 | P1-02 | Release engineers require JUnit/SARIF for renewal | 4d |
| B-103 | P1-03 | Multi-receipt exploration or approved cross-profile mapping exceeds 2 hours despite the P0 delta | 4–7d |
| B-104 | P1-04 | Mapping exceeds 30% of two deliveries | 10d |
| B-105 | P1-05 | Spanish-preferring operators validate demand | 5d + translation |
| B-106 | P1-06 | Two partners need governed local assertions | 8d + governance |

## Critical path

B-001 → B-002/B-004/B-005 → B-007 → B-008–014 → B-017–021 → B-022–031 → B-032–036 → B-039–048 → B-049–056, with B-057 inserted between B-052 and B-054 only if the predeclared extension rule is invoked.

The critical path is dominated by external access and governance, not code. A missed reviewer or partner milestone changes the release date; it does not justify bypassing the gate.
