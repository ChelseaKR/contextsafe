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
