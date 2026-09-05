# The 2026-09 wave: where all fifty-seven backlog items stand

Dated 2026-09-04. One row per item in [the backlog](13-BACKLOG.md), B-001 to
B-057, in one of four states.

## What this wave does not establish

The wave landed file readers, mapping profiles, assertion predicates, the
divergence section, an unsigned review log, a receipt delta, packaging
evidence, and a committed answer for every published seeded fault. It
established **no governance, no pilot, no clinical approval, and no signing.**

- **No governance.** The governance roster (B-004) is unrecruited, so no
  clinical chair, community co-chair, or laboratory lead has approved
  anything. Every profile, rule set, mapping, severity label, rationale code,
  and vocabulary this wave added is reference-only and ungoverned, and says so
  in its own document.
- **No pilot.** There is no design partner (B-002), no engagement, and no run
  against any real system. Every fixture is synthetic by construction and
  every identifier is an invented `CSYN-` or `fixture-` token.
- **No clinical approval.** Nothing here is a clinical oracle, a clinical
  recommendation, or approved content. No clinical, laboratory, community,
  interoperability, security, legal, translation, or accessibility reviewer
  has examined any artifact this wave produced.
- **No signing.** [ADR 0010](adr/0010-signing-layer-dependency-and-trust-model.md)
  is *proposed*. No command signs or verifies, no key or trust manifest
  exists, and every artifact the tool emits still says `not_signed` or
  `not_verified`. Nothing in this wave may be read as relabeling one.

**"Shipped" on this page means a mechanism landed in this repository.** It does
not mean the backlog item is closed: every implementation note in
[the backlog](13-BACKLOG.md) ends with the sentence "B-xxx is not closed" and
what it is waiting on, and none of them has been retracted. The status column
of the backlog's own phase tables is re-derived from those notes by
`make claims`; this page is the wave's dated snapshot beside it.

## How each state was derived

From the implementation notes in [the backlog](13-BACKLOG.md) and the git log,
and nothing else. No state here is a judgment about quality, completeness, or
readiness.

| State | Rule |
|---|---|
| Shipped in this wave | a commit dated 2026-09-04, after `ab92013`, names the item or landed the mechanism its note describes; the commit is in the row |
| Previously shipped | a mechanism landed before that wave; the note date or the commit is in the row |
| Blocked | nobody can start or finish it without a named person or a maintainer decision; the row names who or what, and the open issue |
| Not started | no note, no commit, and no named blocker |

Two limits of the derivation are stated rather than smoothed over. Several
Phase 1 and Phase 2 rows (B-008, B-012, B-014, B-015, B-016) are marked
*previously shipped* on the strength of a commit subject — `54adbb1`, "V1 wave
2: compile unsigned governed plans" — that does not name the item; the mapping
from that subject to those rows is read from the subject and is the one place
this table infers rather than quotes. And **no row is "not started"**: every
item that has not begun has a named person or decision in front of it, which
is the shape of this project rather than an artifact of the table.

## Phase 0 — discovery and authority

| Item | Deliverable | State | Evidence or blocker |
|---|---|---|---|
| B-001 | 15–20 discovery interviews with disconfirming evidence | Blocked | interview participants; discovery has not started ([#86](https://github.com/ChelseaKR/contextsafe/issues/86)) |
| B-002 | design-partner LOI naming sponsor and owners | Blocked | a design partner ([#87](https://github.com/ChelseaKR/contextsafe/issues/87)) |
| B-003 | map the partner's non-production topology | Blocked | the same design partner, through B-002 ([#87](https://github.com/ChelseaKR/contextsafe/issues/87)) |
| B-004 | governance roster and signed charter | Blocked | a clinical chair, a community co-chair, and a laboratory lead ([#88](https://github.com/ChelseaKR/contextsafe/issues/88)) |
| B-005 | counsel memo on FDA/CDS, HIPAA, claims, insurance | Blocked | counsel ([#89](https://github.com/ChelseaKR/contextsafe/issues/89)) |
| B-006 | paper receipt comprehension test, five reviewers | Blocked | five cross-role reviewers; nobody outside the project has read a rendered receipt ([#99](https://github.com/ChelseaKR/contextsafe/issues/99)) |
| B-007 | discovery decision memo scoring every gate | Blocked | B-001 to B-006, all of them people ([#86](https://github.com/ChelseaKR/contextsafe/issues/86)) |

## Phase 1 — governed pack and contracts

| Item | Deliverable | State | Evidence or blocker |
|---|---|---|---|
| B-008 | pack/case/assertion/source/approval schemas | Previously shipped | `54adbb1` (2026-07-13), inferred from the commit subject; no note names B-008 |
| B-009 | canonical case manifests with prohibited-inference fields | Blocked | the governance roster, and the publication-policy date the phase gate requires ([#88](https://github.com/ChelseaKR/contextsafe/issues/88)) |
| B-010 | authored assertions, applicability, and severity rubric | Blocked | clinical, laboratory, and community approval; the predicates that exist are mechanism, not assertions ([#88](https://github.com/ChelseaKR/contextsafe/issues/88)) |
| B-011 | INV/CTX/XFAIL laboratory reference fixtures | Blocked | the laboratory lead, and the 16 review hours the row budgets ([#76](https://github.com/ChelseaKR/contextsafe/issues/76)) |
| B-012 | approval, validity, withdrawal, compatibility rules | Previously shipped | `54adbb1` (2026-07-13), inferred from the commit subject |
| B-013 | independent clinical and community pack review | Blocked | the reviewers B-004 would recruit ([#88](https://github.com/ChelseaKR/contextsafe/issues/88)) |
| B-014 | deterministic pack compiler and source manifest | Previously shipped | `54adbb1` (2026-07-13), inferred from the commit subject |

## Phase 2 — execution plan and evidence core

| Item | Deliverable | State | Evidence or blocker |
|---|---|---|---|
| B-015 | engagement/plan schemas and environment contract | Previously shipped | `54adbb1` (2026-07-13), inferred from the commit subject |
| B-016 | plan validation blocking production and mismatch | Previously shipped | `54adbb1` (2026-07-13), inferred from the commit subject |
| B-017 | streaming preflight before persistence | Previously shipped | note 2026-07-13; `aa77c85` |
| B-018 | content-addressed store and append-only index | Previously shipped | note 2026-07-13; `aa77c85` |
| B-019 | canonical observation/evidence models | Previously shipped | note 2026-07-13, which says "part of B-019" |
| B-020 | CLI shell, stable errors, exit codes, quiet/no-color | Previously shipped | note 2026-07-17; `4f15434` |
| B-021 | deterministic payload and untrusted envelope | Previously shipped | notes 2026-07-17 and 2026-08-15; `69f65ba`, `243780a` |

## Phase 3 — adapters and evaluator

| Item | Deliverable | State | Evidence or blocker |
|---|---|---|---|
| B-022 | canonical JSON import and the importer registry | Shipped in this wave | `9f566f6` |
| B-023 | FHIR R4 JSON reader | Shipped in this wave | `9f566f6` |
| B-024 | HL7 v2 ER7 reader | Shipped in this wave | `9f566f6` |
| B-025 | LIS CSV/JSON import | Shipped in this wave | `9f566f6`, the identity columns only; the result, range, and flag half is B-030 |
| B-026 | versioned mapping profile | Shipped in this wave | `9f566f6` |
| B-027 | status algebra and pure evaluator | Previously shipped | note 2026-07-17; `7111af4` |
| B-028 | identity, NtU, pronoun, RSG predicates A-005..A-015 | Shipped in this wave | `78fa81b`, then `da0890d` and `af058c0` |
| B-029 | SPCU context/provenance/period predicates A-016..A-024 | Blocked | the clinical review the row budgets; deliberately unimplemented ([#90](https://github.com/ChelseaKR/contextsafe/issues/90)) |
| B-030 | result/range/flag predicates A-025..A-031 | Blocked | the laboratory lead and the B-011 fixtures ([#76](https://github.com/ChelseaKR/contextsafe/issues/76)) |
| B-031 | first observed divergence and evidence trace | Shipped in this wave | `3ddc0b3`, then `9b9d088` and `a118379` |

## Phase 4 — review and receipts

| Item | Deliverable | State | Evidence or blocker |
|---|---|---|---|
| B-032 | append-only review/finding/disposition state machine | Shipped in this wave | `9a908bf`, then `c6ded57`, `01b313f`, `821812d`, `4d5ba30`; the signature half is B-035 |
| B-033 | receipt schema and claim-minimal payload | Previously shipped | note 2026-08-04; `0ef1cb4` |
| B-034 | script-free semantic HTML renderer | Previously shipped | note 2026-08-15; `3b557c3` |
| B-035 | trust manifest, signing paths, rotation, revocation | Blocked | a maintainer decision on the first runtime dependency, recorded as proposed in ADR 0010 ([#81](https://github.com/ChelseaKR/contextsafe/issues/81)); design shipped this wave in `e3c3ba8` |
| B-036 | verification of schema, graph, hashes, signatures | Blocked | B-035, and the same decision ([#81](https://github.com/ChelseaKR/contextsafe/issues/81)) |
| B-037 | deterministic receipt delta | Shipped in this wave | `3f01b84`, then `6f18d46`, `b71b433`, `1209ad6` |
| B-038 | print stylesheet and evidence-minimized presentation | Shipped in this wave | `f041a6f`, then `3ea05da`; the print-preview half is B-044's |

## Phase 5 — trust and operations

| Item | Deliverable | State | Evidence or blocker |
|---|---|---|---|
| B-039 | direct-identifier, Unicode, canary, log, crash suite | Previously shipped | note 2026-08-15; `5e36efe` |
| B-040 | independent threat-model and security design review | Blocked | an independent security reviewer ([#84](https://github.com/ChelseaKR/contextsafe/issues/84)) |
| B-041 | externalized strings, catalogs, parity, pseudolocale | Previously shipped | note 2026-08-15 (`3b557c3`), extended this wave by `f041a6f` |
| B-042 | professional Spanish translation and community review | Blocked | a qualified human translator and a community reviewer; `es-US` is machine translated ([#82](https://github.com/ChelseaKR/contextsafe/issues/82)) |
| B-043 | automated axe/pa11y/HTML/contrast/print tests | Previously shipped | note 2026-08-19; `3b557c3`. pa11y is deliberately absent ([#94](https://github.com/ChelseaKR/contextsafe/issues/94)) |
| B-044 | manual NVDA/VoiceOver/keyboard/zoom EN/ES evaluation | Blocked | a person with the assistive technology ([#83](https://github.com/ChelseaKR/contextsafe/issues/83)) |
| B-045 | package and fresh-install Windows/macOS/Ubuntu with SBOM | Shipped in this wave | `8638e78`, then `80cc3e5`; the desktop fresh installs RG-15 names need a person with those machines, and the signatures need B-035 |
| B-046 | diagnostics, cleanup, redacted support bundle, local logs | Previously shipped | note 2026-08-21; `25c8813` |
| B-047 | exercise the PHI, finding, wrong-result, withdrawal runbooks | Blocked | a design partner and the security and clinical participants the row budgets ([#87](https://github.com/ChelseaKR/contextsafe/issues/87), [#88](https://github.com/ChelseaKR/contextsafe/issues/88)) |
| B-048 | 36 regression plus 5 hidden faults, all 41 detected | Shipped in this wave | `75e4566`, then `f36b6f9`, for the part needing no external person: 12 exercised, 7 refused, 17 not yet exercisable, and no hidden-fault set ([#78](https://github.com/ChelseaKR/contextsafe/issues/78)) |

## Phase 6 — pilot and v1

| Item | Deliverable | State | Evidence or blocker |
|---|---|---|---|
| B-049 | partner contract activation, dry run, one-case cleanup | Blocked | a design partner, and DG-04 ([#87](https://github.com/ChelseaKR/contextsafe/issues/87)) |
| B-050 | execute the 12-case baseline and issue a reviewed receipt | Blocked | the partner and the reviewers ([#87](https://github.com/ChelseaKR/contextsafe/issues/87), [#88](https://github.com/ChelseaKR/contextsafe/issues/88)) |
| B-051 | support finding dispositions and partner remediation | Blocked | the partner ([#87](https://github.com/ChelseaKR/contextsafe/issues/87)) |
| B-052 | rerun the pack and use the delta in a release decision | Blocked | the partner ([#87](https://github.com/ChelseaKR/contextsafe/issues/87)) |
| B-053 | EN/ES cross-role comprehension study | Blocked | study participants, and B-042's translator ([#82](https://github.com/ChelseaKR/contextsafe/issues/82), [#99](https://github.com/ChelseaKR/contextsafe/issues/99)) |
| B-054 | independent release dossier closing every P0 and risk | Blocked | everything above it, and the independent reviewers ([#88](https://github.com/ChelseaKR/contextsafe/issues/88)) |
| B-055 | annual-assurance proposal and conversion decision | Blocked | the partner ([#87](https://github.com/ChelseaKR/contextsafe/issues/87)) |
| B-056 | sign and publish the v1.0 artifacts | Blocked | B-035's signing decision and the governance roster ([#81](https://github.com/ChelseaKR/contextsafe/issues/81), [#88](https://github.com/ChelseaKR/contextsafe/issues/88)) |
| B-057 | conditional one-time evidence extension, weeks 34–37 | Blocked | a joint-authority invocation that has not been made, and B-052 before it ([#87](https://github.com/ChelseaKR/contextsafe/issues/87)) |

## The count

| State | Items |
|---:|---|
| 12 | shipped in this wave: B-022, B-023, B-024, B-025, B-026, B-028, B-031, B-032, B-037, B-038, B-045, B-048. ADR 0010 also landed in this wave, under B-035, which stays blocked |
| 17 | previously shipped: B-008, B-012, B-014, B-015, B-016, B-017, B-018, B-019, B-020, B-021, B-027, B-033, B-034, B-039, B-041, B-043, B-046 |
| 28 | blocked on a person or a maintainer decision |
| 0 | not started |

Twelve of the fifty-seven items had a mechanism land in this wave, and none of
them closed. Twenty-eight are waiting on somebody who does not exist yet: a
design partner, a governance roster, counsel, a translator, an accessibility
evaluator, an independent security reviewer, an independent QA, or the
maintainer's decision on the signing dependency. The critical path in
[the backlog](13-BACKLOG.md) says the same thing in one sentence — it "is
dominated by external access and governance, not code" — and this wave did not
change that. It made the code half larger.
