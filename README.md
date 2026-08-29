# ContextSafe

**A proposed clinically and community-governed release-gate plan for transgender and nonbinary patient safety across registration, EHR, HL7/FHIR, and laboratory systems.**

Status: product and delivery plan for v1.0 plus internal iteration-1 synthetic
evaluation, iteration-2 unsigned governance-contract tooling, iteration-3
privacy/evidence-core risk reduction, iteration-4 receipt payload/envelope
separation, and iteration-5 localized receipt rendering and operator surfaces.
No clinically governed, cryptographically authorized, or externally validated
product exists yet.

The planned ContextSafe service would run a fixed, versioned pack of synthetic patients through a health system's non-production workflow, evaluate whether identity and clinical-context data survive each boundary, and produce a signed evidence receipt. Its intended capability is to detect data loss, coercion, unsafe defaults, missing reference ranges, and patient-facing misidentification before a release reaches care. The current code proves only bounded offline fixture evaluation, unsigned contract compilation, a read-only code-envelope boundary check, and an internal-test evidence-store primitive; it is not clinically approved and does not establish those product capabilities.

## Dual use

A tool that reports where transgender and nonbinary identity data is lost is, in
the same breath, reporting where it is retained: a finding that the value was
absent at the laboratory also says it was present in the EHR. That is what the
tool is for, and it is why this repository carries a
[publication policy](docs/17-PUBLICATION-POLICY.md) that says what may be
published about a governed pack, what never is — no receipt, no customer, no
vendor, no version, no real deployment — and who approves. The threat model
treats publication as a trust boundary of its own, TB-10, with the reader of
public project material as a named actor
([threat model §1, §3, §4, T-16](docs/06-SECURITY-PRIVACY-THREAT-MODEL.md)).

What is here today describes no real system: every fixture is synthetic, no
governed pack or receipt exists yet, and the concept separation the code encodes
is published HL7 Gender Harmony material.

## Quickstart

With [`uv`](https://docs.astral.sh/uv/) installed:

```sh
make verify                       # sync lint format typecheck test audit hygiene publication-sweep i18n a11y claims
uv run contextsafe evaluate \
  --case fixtures/reference/case.json \
  --observations fixtures/reference/observations.json \
  --rules fixtures/reference/rules.json \
  --output receipt.json           # offline synthetic fixtures; unsigned receipt
uv run contextsafe render \
  --receipt receipt.json \
  --output receipt.html           # script-free HTML page; --lang for a locale
```

Everything runs offline against the committed synthetic reference fixtures;
the full command walkthrough, including pack, plan, and evidence-preflight
validation, is under [Internal implementation slice](#internal-implementation-slice).

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

Iteration 4 separates the evaluation receipt into a deterministic payload and
an explicitly untrusted envelope and publishes its contract (the B-021
payload/envelope and B-033 receipt-schema slices):

- `contextsafe evaluate` emits a receipt document whose `payload_sha256` covers
  only the deterministic payload; the payload itself still contains hashes,
  statuses, and limitations rather than semantic values;
- the envelope carries an optional caller-declared `claimed_generated_at`
  (canonical whole-second UTC), `signature_status: not_signed`, and
  `trusted_time: false`; the runner never reads a clock, and no timestamp or
  signature can enter the payload or its hash;
- `claimed_generated_at` is unauthenticated metadata that proves nothing about
  when evaluation ran, and a future signing layer may not relabel these
  unsigned documents;
- the document has a published
  [receipt contract](schemas/contextsafe-receipt-v0.1.schema.json), the pre-1.0
  shape of the receipt schema in [Architecture §8](docs/04-ARCHITECTURE.md).
  Every object is closed, the unsigned envelope constants are pinned, the
  payload may carry only hashes, statuses, counts, and the mandated disclosure
  set — pinned wording, in order, with no room for extra free text — and status,
  reason, checkpoint, and concept are closed sets. A document that validates has
  proved shape and claim minimality only: not a signature, trusted time,
  clinical approval, or receipt verification, and not that the payload hash
  still matches its payload.

Every published contract is listed in
[`schemas/README.md`](schemas/README.md), which also records why each `$id`
is under a domain reserved never to resolve.

Iteration 5 gives the receipt a human surface (the B-034 renderer and B-041
string catalogs):

- `contextsafe render --receipt receipt.json --lang en-US --output page.html`
  produces one self-contained HTML page: no script, no event-handler attribute,
  no external stylesheet, font, or image, and no network reference of any kind.
  It is deterministic in the receipt document and the catalog, adds no
  timestamp, and reads nothing from the machine that rendered it;
- every status is carried by its word *and* a distinct symbol, so the page
  loses no information printed in black and white or read with any colour
  vision; `<main>` carries `data-cs-payload-sha256`, so a checker can prove
  which receipt it looked at;
- user-facing strings live in `src/contextsafe/locales/`. `en-US` is the source
  locale. **`es-US` is a machine translation that no qualified human translator
  or community reviewer has checked** (that is B-042, and it has not happened),
  so the page shows a notice in both languages, marks each unreviewed string,
  and renders every mandated safety disclosure beside its `en-US` original;
- `make i18n` fails on catalog or placeholder drift, on a review record nobody
  signed, on an unreviewed string reaching a surface that claims review, on a
  missing disclosure, and on any visible text the catalogs do not account for.
  It also fails rather than passing when it has examined no catalog at all.
  [`docs/I18N.md`](docs/I18N.md) records the whole split, including why receipt
  bytes stay in one language;
- `make a11y` audits the rendered page in every locale — structural validity,
  WCAG 2.2 contrast computed from the stylesheet, no colour-only status
  encoding, and print — and `make a11y-full` adds axe-core in a headless DOM.
  The gate checks each page against the receipt document it should have
  rendered before auditing it, counts what it examined, treats a requested
  engine that cannot run as a failure rather than a skip, and never counts a
  rule axe could not determine as a pass. pa11y is not wired in, and
  [Accessibility §11](docs/08-ACCESSIBILITY-I18N.md) says why.

The same iteration adds the operator surface (the B-046 slice):

- `contextsafe diagnostics` reports what an installation can do — interpreter,
  platform, whether descriptor-relative no-follow reads exist here, whether a
  workspace is present and how many records its index holds. Not what it has
  seen: no case, no token, no path;
- `contextsafe cleanup --workspace DIR` lists what the tool created there,
  classified as index, object, staging leftover, directory, or unclassifiable,
  and reported as shapes and sizes rather than names. Deleting takes
  `--remove --confirm`, never follows a symbolic link, never leaves the
  workspace, and never removes an entry it could not classify;
- `contextsafe support-bundle` assembles a bundle **redacted by construction**.
  Every field is a typed value — a count, a flag, a member of a closed set, a
  digest, a dotted numeric version, or the shape of a path — and there is no
  constructor that accepts free text, so a patient name in an export path has
  nowhere to go. A filter would have to recognise the name; this cannot contain
  it. The assembled bundle is scanned again before it is written, as a check on
  the construction rather than as the thing that makes it safe;
- every command accepts `--log-dir`, which appends one closed-vocabulary record
  (command, outcome, error code) to a local append-only log. Off unless asked,
  never enabled from the environment, no message field, and no clock reading.

The durable primitive has no CLI import route. Every iteration-3 evidence record says
`authorization_status: not_verified_internal_test_only` and
`usable_for_execution: false`; a future signature-verification layer may not relabel
these records. The preflight scanner is a fallible boundary check, not proof that bytes
contain no PHI. A near-miss suite pins where its boundary falls in both
directions, including three identifier-shaped values it does not catch; those
are recorded for the independent security review that B-039 requires, and the
synthetic-namespace grammar rather than the scan is what bounds them.

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
# Emits a receipt document: deterministic payload plus untrusted, unsigned
# envelope. --claimed-generated-at is optional caller-declared envelope-only
# metadata and never changes the payload or payload_sha256.
uv run contextsafe evaluate \
  --case fixtures/reference/case.json \
  --observations fixtures/reference/observations.json \
  --rules fixtures/reference/rules.json \
  --claimed-generated-at 2026-07-17T00:00:00Z \
  --output receipt.json
# evaluate exits 0 whenever it produces a receipt, even one whose payload
# records fail outcomes. To block a pipeline on findings instead, add
# --fail-on finding: the receipt is emitted byte-identically and the process
# then exits 1 if the payload contains at least one fail outcome.

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

# Read-only: validates an unsigned plan-shaped scope and never persists the
# evidence source. --output is optional and writes only the non-sensitive
# result document (boundary-check status, hashes, scope) that would otherwise
# print to stdout; it still never copies, indexes, or logs the source itself.
uv run contextsafe evidence preflight \
  --source fixtures/reference/evidence-source.json \
  --plan path/to/plan.json \
  --case-token CSYN-CTP-I01 \
  --checkpoint ehr \
  --source-type canonical_json \
  --media-type application/vnd.contextsafe.evidence+json \
  --output preflight-result.json
```

Command output is a hash-covered artifact rather than display text: every
success payload, `--output` file, and stderr error object is the same UTF-8 byte
sequence on every platform, with no line-ending or encoding translation. A
three-run suite re-runs each command in fresh interpreters under different time
zones, locales, hash seeds, UTF-8 modes, working directories, and input
directories and requires byte-identical results, and a CI matrix reproduces the
pinned reference-receipt digest on Ubuntu, macOS, and Windows. That is
byte-reproducibility evidence only; it is not packaging, fresh-install, or
release evidence. `pack validate`, `plan validate`, and `evidence preflight`
need descriptor-relative no-follow reads, so on a platform without them —
Windows included — they fail closed with `input_path_unsupported` rather than
run with a weaker guarantee.

Every command also accepts `--quiet`, which suppresses the stdout success
payload while leaving exit codes, `--output` files, and stderr JSON errors
unchanged, and `--no-color`, which pins the plain-output contract: contextsafe
output never contains ANSI escape sequences, with or without the flag. Exit
codes are stable and documented: `0` success (including `--help`), `2`
fail-closed contract rejection with one JSON error object on stderr, and `64`
command-line usage error.

`make verify` is the whole merge gate and the exact target `ci.yml` runs. It
installs from the locked lockfile with `uv sync --locked`, never `--frozen`,
which installs a lock that has drifted from `pyproject.toml` and still exits 0,
so it cannot gate drift. Its stages are the ones named beside `make verify` in
the quickstart above, and each has a row in
[the contributing guide's gate table](CONTRIBUTING.md#the-merge-gate); the
floors are 90% overall branch coverage and 95% safety-module branch coverage.
`make claims` is the newest of them: it re-derives the figures and lists this
README states, including that stage list, so a stage added to `verify` and left
undocumented fails the build instead of quietly misleading a reader.

The gate implementations in `tools/` are inside the trees those gates scan and
inside the coverage floor. They were not until 2026-08-27, which is the first
phase of [the assurance program](docs/18-ASSURANCE-PROGRAM.md): a check that
reports clean over content it did not examine is the defect class that document
exists to track.

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
- [Roadmap](docs/12-ROADMAP.md)
- [Prioritized backlog](docs/13-BACKLOG.md)
- [Risk register](docs/14-RISK-REGISTER.md)
- [V1 release checklist](docs/15-V1-RELEASE-CHECKLIST.md)
- [Research sources](docs/16-RESEARCH-SOURCES.md)
- [Publication policy](docs/17-PUBLICATION-POLICY.md)
- [Assurance program](docs/18-ASSURANCE-PROGRAM.md)
- [Publication readiness](docs/PUBLICATION-READINESS.md)
- [ADR 0000: record architecture decisions](docs/adr/0000-record-architecture-decisions.md)
- [ADR 0001: v1 boundary](docs/adr/0001-v1-boundary.md)
- [ADR 0002: unsigned compilation before authorization](docs/adr/0002-unsigned-compilation-before-authorization.md)
- [ADR 0003: recoverable evidence commit](docs/adr/0003-recoverable-evidence-commit.md)
- [ADR 0004: the SAST gate and a scan that cannot skip itself](docs/adr/0004-sast-gate-pragma-and-scan-invocation.md)
- [ADR 0005: the gates are inside the trees they scan, and exemptions carry a reason](docs/adr/0005-hygiene-marker-exemptions.md)
- [ADR 0006: provenance tokens get a grammar and a boundary scan](docs/adr/0006-provenance-token-grammar-and-boundary-scan.md)

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

When implementation begins, this repository inherits the author's portfolio-wide
engineering standards for code quality, security and supply chain, CI/CD,
observability, accessibility, internationalization, documentation, and release.
The planning documents specify ContextSafe's project-specific values; they do
not replace those standards.

## Standards Conformance

Status against those standards, with applicability judged per standard. The
current code is an offline CLI that validates and evaluates synthetic fixtures,
renders a localized HTML receipt from the result, and reports on its own
installation. The Performance, Accessibility and Internationalization rows all
turn on what that rendered page is and is not:

| Standard | State |
| --- | --- |
| Responsible-Tech Framework | Applies — governance, community accountability, and fail-closed safety posture documented in `docs/07-GOVERNANCE-LEGAL-SAFETY.md` |
| Code Quality | Applies — ruff (incl. bandit rules, complexity ≤10), mypy `--strict`, branch coverage ≥90% (≥95% on safety-critical modules) via `make verify` |
| Security & Supply-Chain | Applies — Semgrep SAST, gitleaks secret scan at three scopes (pre-commit diff, full-history CI gate over every ref, every object, and the working tree via `make secret-scan`, and that same scan again at a release tag), pip-audit dependency audit (`.github/workflows/security.yml` + `make audit`), pinned `uv.lock`, SHA-pinned actions bumped by Dependabot (`.github/dependabot.yml`, weekly, 7-day cooldown), `SECURITY.md`. Two of those pins are nonetheless behind upstream: `actions/checkout` sits at v7.0.0 against v7.0.1 and `actions/setup-python` at v6.3.0 against v7.0.0. Closing a Dependabot pull request tells it not to offer that version again, and #18 and #19 were closed on 2026-08-16, so neither bump will be re-raised on its own |
| CI/CD | Applies — `ci.yml` runs the identical `make verify` gate on every push and pull request that touches code; docs-only changes are skipped by design (`paths-ignore`), and the security workflow has no such skip |
| Observability | Applies — deterministic, hash-covered JSON receipts and evidence records are the audit/observability surface of this offline CLI |
| Performance | N/A — offline library/CLI with no hosted route and no served surface to budget. `contextsafe render` writes a self-contained local HTML file rather than serving one, so there is no latency, payload, or availability budget to set, and none is claimed |
| Accessibility | Applies — a human-facing surface exists: `contextsafe render` produces the HTML receipt. `make a11y` runs `tools/a11y_gate.py` inside `make verify` over every shipped locale, checking structural validity, WCAG 2.2 contrast computed from the stylesheet, no colour-only status encoding, and print; `make a11y-full` adds axe-core in a headless DOM as its own CI job. The gate checks each page against the receipt it should have rendered before auditing it, reports what each check examined, fails rather than passing when it examined no page, and never counts a rule axe could not determine as a pass. **AA conformance is not claimed:** the manual evaluation that would support it (B-044, NVDA, VoiceOver, keyboard, zoom and high contrast in both languages) has not happened, and pa11y is deliberately not wired in. [Accessibility §11](docs/08-ACCESSIBILITY-I18N.md) states both boundaries |
| Internationalization | Applies — the earlier English-only declaration was superseded when the rendered receipt gained a locale. `make i18n` runs `tools/i18n_gate.py` inside `make verify`: catalog parity, placeholder parity, message quality, review consistency, and the rule that a machine-translated string may never reach a surface claiming human review; it fails rather than passing when it examined no catalog. Machine artifacts stay in one fixed language by design, because a payload whose wording varied with a locale would hash differently. **`es-US` is a machine translation no qualified human translator or community reviewer has read** (B-042, not done), and every page says so in both languages. See [`docs/I18N.md`](docs/I18N.md) |
| AI Evaluation | N/A — deterministic fixture evaluator; no LLM/model component |
| Quality & Metrics | Applies — coverage floors enforced in `pyproject.toml` and `make test`, over `src/contextsafe` and the gate implementations in `tools/`; hygiene gate bans TODO/FIXME/HACK in `src`, `tests` and `tools`, with line-level exemptions that must carry a reason and are printed on every run |
| Documentation | Applies — the planning corpus in `docs/`, ADR log in `docs/adr/`, published contracts in `schemas/`, `CONTRIBUTING.md`, `CHANGELOG.md` |
| Release & Versioning | Applies — tag-triggered `release.yml` re-runs `make verify` at the tag and gates on a matching CHANGELOG section. No tag and no release exist yet, so it has never fired, and `CITATION.cff` deliberately carries no `version` or `date-released` |
| AI Development Measurement | Applies — no AI-development baseline is recorded in this repo yet. The merge-blocking gates that do exist are outcome-side, not activity counters: `make verify` runs branch-coverage floors, mypy `--strict`, and the hygiene gate on every change |
| Incident Response | Applies — the private vulnerability channel and acknowledgement expectation are in [SECURITY.md](SECURITY.md); the confirmed safety-defect withdrawal timeline is in `docs/10-OPERATIONS-SRE.md` and the recall procedure in `docs/07-GOVERNANCE-LEGAL-SAFETY.md`. No incident has been recorded, so there is no `docs/incidents/` directory yet |
| Data Governance | Applies — data classification, retention, and the prohibited-data boundary are set out in `docs/05-DATA-AND-EVIDENCE.md` section 11. Every fixture in this repo is synthetic by construction, and the synthetic-only namespaces, PHI canaries, and direct-identifier checks fail closed rather than warn. Operator-supplied provenance on an accepted evidence record is bounded by a published grammar and then scanned, per [ADR 0006](docs/adr/0006-provenance-token-grammar-and-boundary-scan.md) |

Licensed under [Apache-2.0](LICENSE). Cite via [CITATION.cff](CITATION.cff).

Re-review this table before implementation and at every material clinical, standards, or regulatory change. It deliberately carries no review date. The one it carried went stale while this file kept changing, and a date nothing re-derives decays silently; the CI checkout is shallow, so `git log` cannot re-derive it either. `make claims` gates what is checkable here instead.
