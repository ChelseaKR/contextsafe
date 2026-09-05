# ContextSafe

**An offline, deterministic command-line tool that evaluates whether transgender
and nonbinary patients' identity and clinical-context data survives each system
boundary — registration, EHR, HL7/FHIR, laboratory — and emits a hash-covered
receipt that states its own limits. The clinically and community-governed
service that would run it against a real health system is a plan, not a
product.**

The tool is here now. Fifteen subcommands, no network access, committed
synthetic fixtures that ship inside the package. With
[`uv`](https://docs.astral.sh/uv/) installed, this returns a full receipt:

```sh
uv run contextsafe fixtures export   # the packaged synthetic inputs, into ./fixtures/reference
uv run contextsafe evaluate \
  --case fixtures/reference/case.json \
  --observations fixtures/reference/observations.json \
  --rules fixtures/reference/rules.json
```

It evaluates five checkpoints — gender identity at the EHR, recorded sex or
gender at registration, sex parameter for clinical use at the interface, name to
use and pronouns at the EHR — comparing an expected SHA-256 against what was
observed. Below is that command's real output, pretty-printed, with four of the
five result objects and four of the five divergence entries elided where
marked:

```jsonc
{
  "envelope": {
    "claimed_generated_at": null,
    "signature_status": "not_signed",
    "trusted_time": false
  },
  "payload": {
    "case_id": "CTP-I01",
    "divergence": {
      "concepts": [
        {
          "checkpoints": [
            { "checkpoint": "registration", "state": "unobserved", "value_sha256s": [] },
            {
              "checkpoint": "ehr",
              "state": "observed",
              "value_sha256s": [
                "4b586a13d46580ed0a2126fcd4aedf4bfa89d5956d6baad6aaf9e59455c88df8"
              ]
            },
            { "checkpoint": "interface", "state": "unobserved", "value_sha256s": [] },
            { "checkpoint": "lis_return", "state": "unobserved", "value_sha256s": [] }
          ],
          "concept": "gender_identity",
          "expected_sha256s": [
            "4b586a13d46580ed0a2126fcd4aedf4bfa89d5956d6baad6aaf9e59455c88df8"
          ],
          "from_expected": { "at": null, "status": "agreed_where_observed" },
          "from_previous": { "after": null, "at": null, "status": "unobserved" }
        }
        // four more entries elided: recorded_sex_or_gender, sex_parameter_for_clinical_use,
        // name_to_use, pronouns — each observed at one boundary and unobserved at the rest
      ],
      "pathway": ["registration", "ehr", "interface", "lis_return"]
    },
    "hashes": {
      "input_sha256": "d9db15f2b90278df25c15cddbc6464c0c410451e690b96b6e94ce29a823c0920",
      "result_sha256": "415c2718630845efc56493433368a7854d0d55268a4eda14b10b22980d6d55e2",
      "rule_set_sha256": "aa81475440694f69bf6a819e9119678bcae6e8ff25adf9b8f4f69a7efc8d5b12"
    },
    "limitations": [
      "Synthetic reference fixture only; not an approved clinical oracle.",
      "A passing result does not establish safety, compliance, or certification.",
      "Patient data is prohibited; bounded checks cannot prove an input is synthetic.",
      "This iteration does not ingest FHIR or sign artifacts."
    ],
    "results": [
      {
        "case_id": "CTP-I01",
        "checkpoint": "ehr",
        "concept": "gender_identity",
        "evidence_sha256s": [
          "1917d730c88ed0f6fd76487c7aeaf58635effb03dfd688d74d423fbcbd510b5a"
        ],
        "expected_sha256": "4b586a13d46580ed0a2126fcd4aedf4bfa89d5956d6baad6aaf9e59455c88df8",
        "observed_sha256s": [
          "4b586a13d46580ed0a2126fcd4aedf4bfa89d5956d6baad6aaf9e59455c88df8"
        ],
        "reason": "affirmative_evidence_match",
        "rule_id": "A-I01",
        "rule_version": "0.1.0",
        "status": "pass",
        "trace": {
          "mappings": [
            {
              "mapping_sha256": "6cc9116756a5ffc9f895697ddb1a41858c2a88a0af116013d2c834ef5cd61aed",
              "mapping_version": "0.1.0"
            }
          ],
          "sources": [
            {
              "source_pointer": "$.concepts.gender_identity",
              "source_sha256": "1917d730c88ed0f6fd76487c7aeaf58635effb03dfd688d74d423fbcbd510b5a"
            }
          ]
        }
      }
      // four more result objects elided: recorded_sex_or_gender at registration,
      // sex_parameter_for_clinical_use at interface, name_to_use and pronouns at ehr
    ],
    "runner_version": "0.1.0",
    "schema_version": "contextsafe.receipt/0.3.0",
    "scope": {
      "clinical_oracle_approved": false,
      "patient_data_allowed": false,
      "synthetic_fixture_only": true
    },
    "summary": {
      "blocked": 0,
      "fail": 0,
      "indeterminate": 0,
      "not_applicable": 0,
      "pass": 5
    }
  },
  "payload_sha256": "07de843716235b50f940400b07d47ff7733c980aa62f1d76a180d74ff123ecf5",
  "schema_version": "contextsafe.receipt-document/0.1.0"
}
```

The `scope` and `limitations` blocks are part of the result, not small print
around it. Every receipt says in its own payload that it is `not_signed`, that
no approved clinical oracle stands behind it, that patient data is not allowed,
and that the fixture is synthetic — and the payload carries hashes, statuses,
counts, and structural source pointers rather than the identity values
themselves. Those fields are pinned by
the published
[receipt contract](schemas/contextsafe-receipt-v0.3.schema.json): the disclosure
set is mandated wording in a fixed order, the unsigned envelope constants are
closed, and a future signing layer may not relabel these documents. A tool on
this subject that could not state its own boundaries would not be safe to run,
so the boundaries are machine-checked rather than promised.

## Status

Status: product and delivery plan for v1.0 plus internal iteration-1 synthetic
evaluation, iteration-2 unsigned governance-contract tooling, iteration-3
privacy/evidence-core risk reduction, iteration-4 receipt payload/envelope
separation, iteration-5 localized receipt rendering and operator surfaces, and
iteration-6 file readers, mapping profiles, assertion predicates, the
divergence section, the unsigned review log, and packaging evidence.
No clinically governed, cryptographically authorized, or externally validated
product exists yet. [The 2026-09 wave record](docs/ROADMAP-WAVE-2026-09.md)
states where each of the fifty-seven backlog items stands, and what the wave
did not establish.

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
make verify                       # sync lint format typecheck test audit hygiene scope patterns publication-sweep i18n a11y claims
uv run contextsafe fixtures export   # the packaged synthetic inputs, into ./fixtures/reference
uv run contextsafe evaluate \
  --case fixtures/reference/case.json \
  --observations fixtures/reference/observations.json \
  --rules fixtures/reference/rules.json \
  --output receipt.json           # offline synthetic fixtures; unsigned receipt
uv run contextsafe render \
  --receipt receipt.json \
  --output receipt.html           # script-free HTML page; --lang for a locale
```

Everything runs offline against the synthetic reference fixtures, which are
package data under
[`src/contextsafe/fixtures/reference/`](src/contextsafe/fixtures/reference/):
`fixtures export` copies them to `./fixtures/reference`, so the block above runs
unchanged from a clone and from an installed wheel, and
`tests/test_wheel_quickstart.py` runs it from a freshly built wheel outside the
repository on every `make verify`. The full command walkthrough, including pack,
plan, and evidence-preflight validation, is under
[Internal implementation slice](#internal-implementation-slice).

### From a source file to a receipt

The block above evaluates observations somebody already authored, which is the
one path that does not exercise a reader. This one starts where a real case
would start — a synthetic patient in a FHIR R4 JSON `Patient` — and runs it
through import, evaluate, and render. Every intermediate artifact is a file you
can open, which is the design: three commands, not one, so nothing is decided
where you cannot see it.

```sh
uv run contextsafe fixtures export   # the packaged synthetic inputs, into ./fixtures/reference
uv run contextsafe import \
  --format fhir-r4-json \
  --source fixtures/reference/fhir-patient.json \
  --case fixtures/reference/case.json \
  --checkpoint ehr \
  --mapping fixtures/reference/mapping-fhir-r4-json.json \
  --output observations-fhir.json   # read-only: never persisted, copied, indexed, or logged
uv run contextsafe evaluate \
  --case fixtures/reference/case.json \
  --observations observations-fhir.json \
  --rules fixtures/reference/rules.json \
  --output receipt-fhir.json        # offline synthetic source; unsigned receipt
uv run contextsafe render \
  --receipt receipt-fhir.json \
  --output receipt-fhir.html
```

`import` reads the Patient once through the evidence boundary — one descriptor,
no-follow, one MiB, an exact element allowlist — and writes four observations at
the EHR: gender identity, pronouns, recorded sex or gender, and name to use,
each carrying the digest of the source bytes, an RFC 6901 pointer to the
element it came from, and the version and digest of the reference mapping
profile that bound the source's tokens to the case's values. The receipt then
reports three passes at the EHR (gender identity, name to use, pronouns) and
two `indeterminate` outcomes with reason `missing_evidence`: the recorded sex
or gender the reference rules expect at registration, and the sex parameter for
clinical use they expect at the interface. This source is one boundary, the
recorded sex or gender it carried was observed at the EHR rather than at
registration, and a boundary nobody observed is never a pass. Drop `--mapping`
and the same import evaluates to `semantic_mismatch` where the source's token
is not the case's value, because nothing has told the tool that the two mean
the same thing.

`--format hl7v2-er7 --source fixtures/reference/hl7v2-er7-message.hl7 --mapping
fixtures/reference/mapping-hl7v2-er7.json` runs the same three steps from the
HL7 v2 message; `lis-csv` and `lis-json` read the identity columns of the
packaged laboratory export at `lis_return`. `tests/test_wheel_quickstart.py`
runs this walkthrough from the built wheel beside the block above.

The reference mapping profiles are synthetic bindings for the packaged
fixtures, not the mapping of any real system; every one says `not_reviewed`,
no interoperability, clinical, laboratory, or community reviewer has seen one,
and the receipt this produces is unsigned. `import` needs descriptor-relative
no-follow reads, so it fails closed with `input_path_unsupported` on Windows
([Operations §3.1](docs/10-OPERATIONS-SRE.md)).

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
  [reference fixture](src/contextsafe/fixtures/reference/case.json).

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
  [receipt contract](schemas/contextsafe-receipt-v0.3.schema.json), the pre-1.0
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
  (command, outcome, error code, and the closed warning codes the command
  carried) to a local append-only log. Off unless asked, never enabled from the
  environment, no message field, and no clock reading;
- `contextsafe events summarize --directory DIR` reads that log back, and is
  the supported way to do it — the log shipped without a reader, so the only
  way to ask how many runs failed closed and with which codes was to parse the
  file by hand. It prints the record count, the count of each command, of each
  outcome, and of each error code, and the SHA-256 of the bytes it read
  ([contract](schemas/contextsafe-event-log-summary-v0.1.schema.json)). It
  never writes to the log it reads, refuses an `--output` that names either
  that log or the one `--log-dir` writes to, and carries no timestamp, path,
  or free text — there is nothing in the record shape for one to have come
  from. A line that is not one canonical record refuses the whole summary,
  naming the line and the field and neither value: a count derived from the
  lines that happened to parse would understate exactly the runs an operator
  is counting. The log is opened `O_NOFOLLOW`, so the command fails closed
  with `input_path_unsupported` where the platform has no such open; that
  guards the log's own name, not the directory the operator hands it, which
  the pack readers guard with descriptor-relative opens and this one does not.
  What it cannot see is a record removed from the end of a log, which is why
  the digest is in the document, and a sequence number tells it how many
  records that writer had seen, never which run came first.

Iteration 6 adds the source readers, the assertion predicates, the divergence
section, the unsigned review log, and the packaging evidence (the B-022 to
B-026, B-028, B-031, B-032, B-035 to B-038, B-041, B-045, and B-048 slices).
Every bullet here has an implementation note behind it in
[the backlog](docs/13-BACKLOG.md), and
[the wave record](docs/ROADMAP-WAVE-2026-09.md) states where all fifty-seven
backlog items stand after it:

- **`contextsafe import` and the importer registry (B-022).** `--format
  canonical-json --source FILE --case CASE.json --checkpoint ehr --output
  observations.json` is the read-only conversion step between a boundary
  envelope and the evaluator. It opens the source once through the same
  evidence boundary scan as `evidence preflight`, emits the observation-set
  document `evaluate --observations` accepts — one observation per record,
  `evidence.source_sha256` the digest of the source bytes,
  `evidence.source_pointer` the record's own pointer,
  `mapping.mapping_version` the importer's version — cross-checks the case
  token and synthetic identifier against the case document, and never
  persists, copies, indexes, or logs the source.
  `src/contextsafe/importers/` is the boundary the readers register into: a
  shared result with a closed warning vocabulary and an `import_*` rejection
  family, and a registry `--format` reads, so a new format is one module and
  one entry. The conversion is whole or nothing, and nothing is normalized to
  the closest supported value (A-033): a field code outside the closed
  five-concept mapping, an untyped value, an identifier outside the synthetic
  namespace, a gender-identity, name, or pronouns record whose value is a
  recorded-sex code or a laboratory status rather than a presence state or a
  `CSYN-` token, or any value the observation contract rejects fails the
  source with a code and a location and produces nothing. Values are the
  source's own tokens, carried verbatim — `CSYN-PRONOUN-THEY-THEM` stays that
  string, not `they/them` — so an import evaluated without a mapping profile
  reports `semantic_mismatch` where the token differs and `missing_evidence`
  at the checkpoints it did not read, and every result records
  `profile_reviewed: false`. The source's `plan_id` is checked for shape and
  not against a plan, sex-parameter records reject rather than arrive without
  the supporting-observation link the concept needs, and the result's counts
  and warnings stay in process because the observation-set contract has no
  field for them;
- **the FHIR R4 JSON reader (B-023).** `--format fhir-r4-json` reads one FHIR
  R4 JSON `Patient` — alone, or as the only entry of a `collection` or
  `searchset` `Bundle` — through the same boundary scan and an exact element
  allowlist. The HL7 Gender Harmony extensions map to the canonical concepts
  by name: `individual-genderIdentity` to gender identity,
  `individual-pronouns` to pronouns, `individual-recordedSexOrGender` to
  recorded sex or gender with its `type` sub-extension as the context, and the
  `HumanName` whose `use` is `usual` to name to use. Every observation carries
  the source digest, the profile version, and an RFC 6901 JSON Pointer to the
  element it was read from; two gender-identity extensions, or two usual
  names, are two observations, which the evaluator reports as ambiguous. The
  packaged reference set carries
  [`fhir-patient.json`](src/contextsafe/fixtures/reference/fhir-patient.json),
  the accepting synthetic Patient for CTP-I01, and the accepted subset is
  published as the reference-only
  [FHIR R4 source profile](schemas/contextsafe-fhir-r4-source-v0.1.schema.json).
  Nothing outside the allowlist is dropped: a narrative, a contained resource,
  any element outside the allowlist (`gender`, `meta`, `telecom`, `address`,
  `birthDate` included), any extension or sub-extension outside the profile
  (`comment`, `period`), a `display`, a reference, an identifier outside
  `urn:contextsafe:synthetic` / `CSYN-`, a coded value or name part outside the
  synthetic alphabet, a name with no part, a `data-absent-reason` coding on
  recorded sex or gender (the canonical concept has no presence state, so that
  system's `unknown` is never read as the recorded value `unknown`), a
  document over one MiB, or a Patient carrying none of the concepts rejects
  the whole source with a code and a location, and a fixture per class is
  committed under `tests/fixtures/fhir-r4-json/`. A recorded-sex-or-gender code
  outside the observation contract's closed alphabet, and any coding system or
  code over the contract's 96-character token bound, reject at their own
  location in the FHIR document, so no rejection names a path in the converted
  document. What the allowlist admits and the canonical model cannot hold is
  validated and not carried, and that list is closed too: `Patient.id`,
  `Patient.active`, every `HumanName` whose `use` is not `usual`, `family` on
  the usual name, the pronouns coding's system, and the
  recorded-sex-or-gender value's system. Sex parameter for clinical use comes
  only from its own extension and this reader does not carry it: no
  allowlisted resource carries an order context or a supporting observation,
  so the extension rejects. The reader's choices where the implementation
  guide is uncertain are one versioned profile constant whose `reviewed` field
  is false and cannot be set; no interoperability, clinical, or community
  reviewer has examined it, it is not a FHIR conformance profile, and it reads
  a file, never an endpoint;
- **the HL7 v2 ER7 reader (B-024).** `--format hl7v2-er7` reads one ER7
  message of at most one MiB through the same bounded, no-follow,
  descriptor-retaining first pass as the other boundary commands and converts
  it, whole or not at all, into the same observation-set document. Delimiters
  are the five characters MSH-1 and MSH-2 declare, exactly; segments end with
  the carriage return the standard fixes; only the five delimiter escapes are
  handled. The segment allowlist is MSH, PID, GSP, OBR, and OBX, and a
  Z-segment, a populated field the profile does not name, a repetition where
  the profile admits one value, an unhandled escape, free text, a control
  character, a PHI canary, a direct-identifier pattern, a production
  processing ID, or a patient identifier outside the synthetic namespace
  rejects the message with a code and a `SEG[n]-field.rep.comp` location,
  never the content. PID-8 Administrative Sex is read by exactly one function
  whose return type is `RecordedSexOrGender`, and an observation's concept is
  a function of the type of its value, so PID-8 arrives as
  `recorded_sex_or_gender` with the context `administrative` and can reach
  neither gender identity nor sex parameter for clinical use on any input; a
  property suite pins it. The packaged `hl7v2-er7-message.hl7` is an accepting
  synthetic message for CTP-I01, and `tests/fixtures/hl7v2/` holds three
  rejection messages. Every decision is a constant in `HL7V2_ER7_PROFILE`,
  version 0.1.0, `profile_reviewed: false` and unsettable: the name-type code
  `D` for name to use, the LOINC concept-type codes GSP-4 may carry, and the
  reading of recorded sex or gender and sex parameter for clinical use from
  GSP (v2.9.1 also defines GSR and GSC for them, and both reject as segments
  outside the allowlist) are choices no interoperability, clinical, or
  community reviewer has confirmed. Values are carried verbatim: `U` in PID-8
  is not turned into `unknown`, it rejects, and presence states are read from
  the literal tokens `declined`, `unknown`, and `absent` rather than from HL7
  null flavors, which a mapping profile still cannot bind because the reader
  rejects them before emitting a token. A coding system in GSP-5.3 is read
  only as the `code_system` of a specified gender identity value; with
  pronouns, recorded sex or gender, sex parameter for clinical use, or a
  presence state it rejects the message rather than being dropped, so a token
  asserted in a vendor namespace is never carried as if it were the fixture's
  own. The message cannot state a checkpoint, so the requested one is applied
  to every observation and the in-process result says so;
- **the LIS export identity columns (B-025).** `--format lis-csv` over
  `fixtures/reference/lis-export.csv`, and `--format lis-json` over
  `lis-export.json`, read the identity columns of a laboratory result export —
  the name, pronouns, and recorded sex a result-facing display would show
  (A-031) — into name-to-use, pronoun, and recorded-sex-or-gender observations
  at `lis_return`, one per distinct value per column, pointed at the first row
  that carries it. The column set is a versioned, reference-only profile with
  `profile_reviewed: false`: `patient_id` cross-checked against the case;
  `name_to_use`, `pronouns`, and `sex`, where `sex` becomes recorded sex or
  gender in the fixed context `laboratory` and never gender identity or sex
  parameter for clinical use; and `analyte`, `value`, `unit`, `range`, `flag`,
  `order`, `specimen`, which are recognized, scanned, and counted and produce
  no observation, because the laboratory result observation family is a later
  item. CSV is a strict RFC 4180 subset; JSON is the published
  [LIS export contract](schemas/contextsafe-lis-export-v0.1.schema.json). Both
  come through the evidence boundary's own read path, and any other column, a
  cell beginning with `=`, `+`, `-`, or `@`, an empty identity cell, an
  identifier outside the synthetic namespace anywhere, or a cell the boundary
  scan refuses rejects the whole file with a code and a position, never a
  value. Rows that disagree stay ambiguous and never pass. No laboratory,
  interoperability, clinical, or community reviewer has seen the profile; it
  is not the shape of any real system's export, and no result observation
  exists yet;
- **the versioned mapping profile (B-026).** `contextsafe import ... --mapping
  fixtures/reference/mapping-fhir-r4-json.json` applies a mapping profile
  after the conversion, and `contextsafe mapping validate --profile P.json
  --output canonical.json` emits a profile's canonical unsigned form with its
  SHA-256. A profile is a closed, versioned table for one importer format,
  from a source token — the carrier it was read from (a field code, an
  extension URL or `Patient.name`, `PID-5`, `PID-8`, or `GSP-5`, a column) and
  the verbatim token — to the canonical concept and value the observation
  should carry, published as the
  [mapping profile contract](schemas/contextsafe-mapping-profile-v1.schema.json)
  with its [compiled form](schemas/contextsafe-compiled-mapping-profile-v1.schema.json).
  Every importer records the source token beside each observation, so a row
  matches on what the source said, not on the value the importer built, and
  every observation emitted with a profile applied carries the profile's
  digest and version in its `mapping` block, so `evaluate`'s input hash binds
  them. Without `--mapping`, importers keep emitting verbatim tokens, byte for
  byte. Five reference profiles ship as package data, one per importer,
  binding each reference fixture's tokens to the reference case's values: with
  them, import followed by evaluate passes every rule at the imported
  checkpoint and reports `missing_evidence`, never `semantic_mismatch`, for
  the rest. A profile's only admissible review status is `not_reviewed`, with
  no reviewer and no date, and any other declaration rejects it: a declared
  approval authorizes nothing, exactly as on a pack, and `contextsafe mapping
  sign` is not built. A row whose target is sex parameter for clinical use
  from a gender-identity or recorded-sex carrier rejects first and by name
  (`prohibited_spcu_mapping`, A-020 and A-021), any other cross-concept row
  rejects, two rows collapsing two source values into one target reject (both
  stay distinct observations, which evaluate as ambiguous), a target outside
  the synthetic grammar rejects, and a sex-parameter row binds the value token
  only — never an order context or a supporting observation. A token with no
  row stays verbatim and the result says so, and with `--log-dir` the event
  record says so too — one unbound token is enough to raise it, and a profile
  that binds nothing is the loudest case rather than the condition — so the
  profile is visible while it can still be fixed. The reference profiles are
  synthetic bindings for the reference fixtures, not the mapping of any real
  system; no interoperability, clinical, laboratory, or community reviewer has
  seen one; HL7 null flavors and an LIS's empty cell are still not bound to
  presence states; and the recording context a profile binds (a `PID-8` value
  to the `government-id` record, say) is a declaration the profile's author
  makes and nothing here has confirmed;
- **assertion predicates, so a rule can say what kind of claim it makes
  (B-028).** A rule set that declares `contextsafe.rule-set/0.2.0` may name one
  predicate from a closed set, published in
  [`schemas/contextsafe-rule-set-v0.2.schema.json`](schemas/contextsafe-rule-set-v0.2.schema.json):
  `exact` (the default, and the only thing a 0.1.0 rule set could say);
  `present`, the value has status `specified`; `status_preserved`, the
  observed status equals the expected status and the value is not consulted,
  so a declined gender identity or pronoun stays declined and never becomes
  unknown, absent, or a value; `not_coerced`, the observed value's presence
  status and scalar are those of none of a closed `forbidden` set the rule
  carries in fixture tokens, so an X or unknown recorded sex or gender
  rewritten to the M or F the set names is a coercion whether or not the
  boundary also stamped its own context or source on the record, and a
  declined, unknown, or absent gender identity or pronoun rewritten to a value
  is a coercion whatever code system came with it; `record_count`, exactly
  `expected_count` distinct records remain; `preserved_across`, the same value
  hash at `preserved_from` and at the rule's checkpoint; and
  `not_overwritten_by`, the observed gender identity is not the case's
  recorded sex or gender, name to use, pronouns, or SPCU value. Each is a pure
  function in `src/contextsafe/evaluator.py`, each has its own affirmative and
  failure reason in the receipt (the receipt contract moved to 0.2 for them),
  and under every one of them missing evidence
  is `indeterminate`, an ambiguous checkpoint is `indeterminate`, and nothing
  passes on zero observations. A second reference pair,
  `rules-predicates.json` against `observations-predicates.json`, exercises
  every predicate on the same case. The predicates are mechanism for A-005 and
  A-008 to A-015 in
  [Data and evidence §5](docs/05-DATA-AND-EVIDENCE.md), not approved
  assertions: no clinical, laboratory, or community review has looked at any
  rule that uses them, and the rule sets that do are labelled reference-only.
  `not_coerced` decides status and scalar and nothing else — the faithful X
  carried under a different context is not a coercion and passes it, and the
  `exact` rule the reference pair ships beside it (A-I09 beside A-I06) is what
  reports that the record is no longer the declared one, so a receipt says
  which claim turned. On the recorded-sex-or-gender concept the value set is
  F, M, X, and unknown, so "absent" in A-014 is only expressible through a
  status-bearing concept, which is how F-008 carries it. Every
  single-observation predicate reports `indeterminate` with
  `ambiguous_evidence` when a checkpoint carries two records of the concept,
  so a multi-record case such as CTP-I10 cannot be evaluated for A-014 at all
  until the observation contract can name which record a rule reads.
  `preserved_across` says a value did not change between two boundaries, not
  that it was right at either. A `not_overwritten_by` rule whose expected
  gender identity scalar the case manifest also declares under another concept
  could never pass, so `parse_bundle` refuses it
  (`overwritten_expectation_conflict`) rather than evaluating it. A-006,
  A-007, and A-015 need a patient-facing display observation and a name period
  that the observation contract does not carry, so they have no predicate. The
  pack contract still pins the exact-only rule-set shape, and a 0.2.0 rule set
  is refused as a pack component by name. The seeded faults this slice can
  detect — F-004, F-005, F-006, F-007, F-008, F-010, F-031 from
  [Test and evaluation §4](docs/09-TEST-AND-EVALUATION.md) — live as complete
  synthetic inputs under `tests/fixtures/seeded-faults/`, each proved to be
  reported as `fail` with its own reason and never as `pass`; of the other
  twenty-nine, F-023 and F-025 are the B-031 slice's below, and the remaining
  twenty-seven were not detectable by that slice; the B-048 bullet below
  carries the current count;
- **first observed divergence and the evidence trace (B-031).** A receipt now
  says where a value first went wrong, and only where it was seen going wrong.
  The payload's `divergence` section, computed by
  `src/contextsafe/divergence.py` from the case and the observations alone,
  walks the four checkpoints in pathway order for each of the five concepts
  and reports the state of every boundary (`observed`, `unobserved`, or
  `ambiguous`, with the value hashes seen there), the first observed boundary
  whose hashes depart from the manifest's (`from_expected`), and the first
  observed boundary whose hashes depart from the previous observed one
  (`from_previous`, which names both sides). An unobserved boundary is never a
  location: when the EHR was not observed and the interface differs from
  registration, the divergence is `at` the interface and `after` registration,
  and the closed contract has no field in which the EHR could be blamed
  (A-034). Absence is never agreement: `agreed_where_observed` speaks only for
  boundaries with evidence, a concept with none is `unobserved`, and a
  boundary that cannot be read as one state is `ambiguous` and the concept
  `indeterminate` from there (A-032). Every outcome also carries a `trace` —
  the source hash and structural source pointer of each observation the
  predicate read and the version and hash of each mapping they came through
  (A-035) — and `parse_observations` refuses a pointer with any segment
  outside a closed structural vocabulary, so a pointer can locate a field but
  cannot carry a name. F-023 and F-025 join the seeded-fault library, and
  property tests hold that reordering observations never changes the section
  and that deleting an observed checkpoint never names the deleted boundary,
  never moves the located boundary when the deleted one was neither side of it,
  and, when the located boundary itself is deleted, locates only a boundary
  that already differed from the observed boundary behind it. The rendered page
  shows the section in `en-US` and
  machine-translated `es-US`, with the sentence that says what is never blamed
  beside its original, and it holds every checkpoint, concept, reason, state,
  and status it reads from a receipt to the published set before the value can
  become a catalog key, so an unpublished value is refused by its structural
  pointer and never reaches the stderr error object. The section compares
  value hashes and does not say which value was right; it is a location, not a
  finding, and carries no severity. A record-list concept is compared as its
  whole list, so an observation set that captures only some of the declared
  recorded-sex-or-gender records at a boundary reads as diverged there, never
  as partial agreement. `expected_sha256s` is carried for all five concepts
  whether or not any rule names them and, like every hash in the payload,
  unsalted, so for a concept with a small value space such as pronouns the
  declared value's hash is recoverable by enumeration (the payload has always
  carried unsalted hashes; the section widens what is carried, not how). An
  outcome that stopped at an evidence gate traces only the side that decided
  it, so a preserved-across rule with its source observed and its target
  missing carries an empty trace; the trace names assertion, mapping, source,
  and runner but no oracle or pack, because none exists to name; A-033 rests
  on the existing fail-closed validators because no normalizer exists;
  `ambiguous` is decided by observation count and hash repetition, not by the
  iteration-3 ambiguity-preserving observation contract, which has no route
  into evaluation; and the pointer vocabulary is the canonical manifest and
  evidence envelope only, so FHIR and HL7 paths need it extended under review.
  The receipt contract moved to 0.3 for the section and the trace, and no
  clinical, laboratory, or community review has looked at any of it;
- **the append-only review log (B-032).** `contextsafe finding review --receipt
  R.json --event E.json --log LOG.jsonl` records one declared review decision
  about one finding, and `contextsafe finding list --log LOG.jsonl` derives the
  current disposition per outcome from it; both print the same derived state
  document and accept `--output`. An event binds the outcome and the receipt's
  payload and rule-set hashes to a decision from a closed set (`confirmed`,
  `rejected`, `severity_changed`, `owner_assigned`, `remediated`,
  `accepted_residual_risk`, `withdrawn`), a severity from a closed label set,
  an owner as a role plus the SHA-256 of an opaque handle, a rationale *code*,
  an optional external reference under the
  [ADR 0006](docs/adr/0006-provenance-token-grammar-and-boundary-scan.md)
  grammar, and declared signers as a role plus an organization label. **There
  is no free-text field, by construction**, as with the support bundle, and
  the residual is stated rather than implied: a name-shaped token still fits
  the ADR 0006 grammars (`Jordan.Rivera` is a well-formed provenance label,
  `JORDAN-RIVERA` a well-formed system label), only the configured canaries and
  direct-identifier shapes are scanned for, and a grammar cannot see ordinary
  letters. The closed shape removes the field a name would be typed into, not
  the possibility of typing one into a label. The state machine is data, the
  table and the per-decision rules are pinned as literals a change must
  confront, and every transition the table does not contain is tested as a
  refusal. The log is one canonical line per event, hash-chained; every read
  re-hashes and replays the whole file before anything is appended, a single
  changed byte anywhere in it is refused, no line is ever rewritten, and
  `--output` naming the log is refused as `output_path_unsafe`: by device and
  inode when the log exists (a symlink or a hard link to it, from anywhere),
  and by parent-directory inode plus case- and normalization-folded leaf name
  when it does not yet exist (`/tmp/x/log` against `/private/tmp/x/log`, a
  symlinked parent, `REVIEW.jsonl` against `review.jsonl`). The fold is applied
  on every filesystem rather than probing which kind the log is on, so on a
  case-sensitive one it over-refuses a name that is a different file; the check
  runs before the log is opened and, for `finding review`, again after the
  append. What the chain cannot see is a record removed from its end: a log cut
  back to an earlier line is a valid shorter log, and detecting that needs an
  external record of the state document's `log_head_sha256`, which is one
  reason the document carries it. Two operational edges are stated rather than
  closed: a `finding review` whose `--output` cannot be written after the
  append exits 2 with `output_io_error` having recorded the event, so the next
  attempt to record the same event is refused as `illegal_transition` and
  `finding list` is the way to get the state; and a first event that is refused
  at the transition after the receipt binding held leaves a new, empty log file
  behind, which replays to the empty state. **Signers are declared, not
  verified.** Every event and every signer says `signature_status:
  not_verified`, an accepted residual risk needs two declared signers with
  distinct roles and organizations or is refused, and **a declared signer
  authorizes nothing**. A `remediated` decision binds no rerun receipt, so its
  rationale code is a declaration the tool cannot check, exactly like a signer.
  The vocabularies are reference-only and ungoverned, not the approved rubric;
  dispositions are not bound into any receipt, and the receipt contract is
  unchanged. Contracts:
  [review event](schemas/contextsafe-review-event-v1.schema.json) and
  [review state](schemas/contextsafe-review-state-v1.schema.json);
- **the signing layer, designed and not built (B-035 and B-036).**
  [ADR 0010](docs/adr/0010-signing-layer-dependency-and-trust-model.md) writes
  the signing layer down before any of it exists, and stops at the decision
  only the maintainer can make: the standard library has no Ed25519, so the
  first `sign` command is the first runtime dependency of a project whose
  `dependencies = []` is a supply-chain claim. The record lays out
  `cryptography`, `PyNaCl`, an optional `contextsafe[signing]` extra whose
  commands fail closed with `signing_unavailable` when the backend is absent,
  and a pure-Python implementation that is rejected outright, with the
  `pip-audit`, per-platform wheel and Windows consequences of each as read on
  2026-09-04; it recommends the extra backed by `PyNaCl` and says why. It then
  fixes what B-035 and B-036 must implement under any option:
  detached-signature and trust-manifest shapes as draft fragments inside the
  ADR and not in `schemas/`, subject hashes as the signed thing, rotation with
  a bounded overlap, 31-day revocation freshness measured against a
  caller-declared `--as-of` and never a clock, compromise recovery, the
  per-purpose thresholds from Architecture §6.6, and what a verified result
  would and would not prove without RFC 3161 time. Its status is proposed.
  Nothing in the tool changes: no command signs or verifies, no schema is
  published, no key or dependency is added, no security review of the trust
  model has happened, and every artifact still says `not_signed` or
  `not_verified`, which the design commits to never relabeling;
- **the receipt delta (B-037).** `contextsafe receipt diff --before A.json
  --after B.json --output delta.json` compares two receipt documents rule by
  rule and emits a deterministic, envelope-free delta
  ([contract](schemas/contextsafe-receipt-delta-v0.1.schema.json)): per rule,
  the status and reason in each receipt, whether the outcome changed, whether
  the evidence hashes changed, and a closed change code; counts of regressed
  (pass to fail, indeterminate, or blocked), improved, unchanged, and
  changed_other; and the payload hash of each receipt. Compatibility is
  fail-closed — identical case, rule-set hash, schema versions, concept and
  checkpoint sets, and rule bindings, or exit 2 with an
  `incompatible_receipts` error that names the field class and never a value —
  and each receipt is first parsed strictly against the published shape, with
  its `payload_sha256` required to cover its payload. `render` stays a
  top-level command for now and may move under `receipt` later. Both receipts
  are unsigned and carry no trusted time, so `before` and `after` are the
  caller's labels and **a delta over unsigned receipts proves nothing about
  which run came first**; swapping the inputs mirrors the delta exactly.
  Payload-hash agreement is an internal-consistency check, not verification:
  no signature, approval, or evidence is verified. The contract is
  reference-only and ungoverned, and a regression it reports is a finding for
  a reviewer, not a verdict;
- **print, evidence-minimized presentation, and the pseudolocale (B-038 and
  B-041), audited on 2026-09-04 and completed where the audit found a gap.**
  Every table has a `<thead>` and the print rules declare it a repeating
  header group; a result row, a limitation with its source-locale original,
  and the translation notice are each kept on one page, and a heading or
  caption stays with what follows it. `make a11y` fails when any of those
  declarations is missing, when a table has no header group, when any print
  rule on any selector sets a break property or a `thead` display to anything
  else, or when any print rule but the skip link's hides by any technique the
  gate names: `display`, `visibility` (`hidden` or `collapse`), zero opacity, a
  font below a pixel, a clip, a collapsed box with its overflow cut off, a
  positioned box pushed off the sheet, `content-visibility`, a transform that
  scales to nothing or translates off the sheet, or a negative indent or
  margin past the edge. Every `@media` block whose query reaches the printer
  is read as print rules, a block the gate cannot classify is a finding,
  declarations are read the way CSS reads them (case-insensitively, with
  `!important` set aside), and lengths are measured in their unit; the gate
  does not try to know which selectors cover a disclosure, so hiding anything
  else is the finding. The renderer recomputes `payload_sha256` from the
  payload and refuses a document whose hash does not cover it, and refuses any
  object carrying a field the receipt contract does not publish rather than
  rendering around it (A-036). `make a11y` adds a `minimization` check: every
  visible run of text is catalog text or one of the receipt values the page
  may present, named by pointer, and a catalog message with a placeholder
  counts only when the placeholder holds one of those values, so no message is
  a prefix that free text can hide behind. A result's expected, observed, and
  evidence hashes stay in the JSON and off the page, and the hash the gate
  expects is recomputed, never read from the document: the negative control
  forges the field and a page that carries it, which a gate reading the field
  would audit and the recomputing gate refuses. `qps-ploc` expands every
  message by at least 35 percent, and `make i18n` measures that floor on the
  body without its brackets, that no accentable letter outside a placeholder is
  left plain, and placeholder parity on the generated catalog
  (`pseudolocale-fidelity`) instead of trusting the transform;
  `hardcoded-string` accepts source-locale wording only where the page marks
  it as a source-locale original. The print checks are computed from the
  stylesheet and the markup, not from a browser that printed the page, so the
  print-preview task in
  [Accessibility §7](docs/08-ACCESSIBILITY-I18N.md) remains B-044's. No locale
  was added; the pseudolocale is never shipped to a reader, and `es-US`
  remains an unreviewed machine translation (B-042);
- **packaging and fresh-install evidence (B-045).**
  `.github/workflows/package.yml` builds the sdist and wheel, exports a
  CycloneDX SBOM from the locked graph, and on Ubuntu, macOS and Windows
  installs that wheel with `pip install --no-index` into an empty virtual
  environment, runs the Quickstart above from a directory outside the
  checkout, and requires the receipt document to reproduce the digest
  `tests/test_determinism.py` pins. Build provenance is attested over the
  recorded checksums only after every platform passes. The gate is
  `tools/fresh_install_gate.py`; it reads the pin rather than restating it,
  exits 2 rather than 0 for anything it could not examine (including a working
  directory that existed before it ran, since a kept environment would report
  a wheel it never installed), and its report carries digests, counts and
  codes and no path. `make package` builds the same artifacts locally and
  lists the wheel. These are GitHub's server images, not the desktop fresh
  installs RG-15 names; the artifacts are unsigned, and provenance says which
  workflow produced them, not that anyone authorized them (B-035); the SBOM is
  derived from `uv.lock`, not read out of the wheel; and no tag exists, so it
  has not fired;
- **a committed answer for every published seeded fault (B-048).** Each of the
  36 published seeded faults in
  [Test and evaluation §4](docs/09-TEST-AND-EVALUATION.md) now has one.
  `tests/test_seeded_faults.py` carries a matrix that says, for each fault, one
  of four things, and a dated table under §4 restates it row for row with a
  test holding the two together. Twelve are *exercised*: a complete synthetic
  fixture under `tests/fixtures/seeded-faults/` with exactly one fault applied,
  proved to be reported with the assertion's own reason and located in the
  divergence section at the observed checkpoint the fault touched — the nine
  from B-028 and B-031, plus F-001 (name to use dropped at the EHR), F-009
  (recorded sex or gender reaching the EHR with the boundary's own context and
  source in place of the declared ones, reported as a changed record while the
  `not_coerced` rule beside it still passes, because the X survived), and F-035
  (the same value through another mapping version: the trace names it and the
  run identity moves, so two mapping versions can never share a receipt). Seven
  are *exercised outside the receipt*: the laboratory faults F-017 to F-022 and
  F-033, each a complete synthetic fixture under
  `tests/fixtures/laboratory/seeded-faults/` reported as `fail` by one of the
  laboratory result predicates with that predicate's own reason, beside a clean
  counterpart that passes every rule — a wrong patient's order, an altered
  value, a blank interval, wrong bounds, a missing flag above the bound, an
  out-of-range value flagged normal, and a range preserved in the wrong unit.
  They are counted apart from the twelve because a laboratory outcome reaches
  no receipt and no divergence section, so nothing localizes them, and because
  every analyte, unit, bound, and flag in them is a token invented for software
  tests: no laboratory medical director has supplied or approved any of them,
  and none of them is a reference range. Seven
  are *refused*: the faulted input never reaches evaluation because a
  fail-closed gate refuses it whole with a named code at a structural path — a
  declared GI-to-SPCU or RSG-to-SPCU mapping (F-015, F-016), an unsupported
  value that is refused rather than nearest-matched (F-024), an identifier
  outside the synthetic namespace (F-029), an observation naming another case
  (F-032), and the pack validity and receipt contract gates that already exist
  (F-028, F-030); a refusal is detection without a receipt, so it is counted
  separately and never as localization. Ten are *not yet exercisable*, and each
  row names what it waits on from a closed vocabulary: the SPCU predicates and
  their clinical review, name contexts and periods in the observation contract,
  the receipt verifier, signatures, the review state machine, and the
  presentation pass. This is not
  the 41-fault evaluation B-048 defines: there is no hidden-fault set, no
  independent fault author has reviewed the corpus, no independent QA has run
  it, and every fault here was written by the implementer of the mechanism
  that detects it. Twelve of 36 at receipt level, and nineteen decided in all,
  is deterministic corpus coverage over the
  published library — not a sensitivity estimate over faults the library does
  not contain, and not a population claim of any kind. Nothing here is
  governed content, and no clinical, laboratory, or community review has
  looked at any fixture.

The durable evidence store has no CLI import route; `contextsafe import` writes
only an observation-set document and never an evidence record. Every iteration-3 evidence record says
`authorization_status: not_verified_internal_test_only` and
`usable_for_execution: false`; a future signature-verification layer may not relabel
these records. The preflight scanner is a fallible boundary check, not proof that bytes
contain no PHI. A near-miss suite pins where its boundary falls in both
directions, including three identifier-shaped values it does not catch; those
are recorded for the independent security review that B-039 requires, and the
synthetic-namespace grammar rather than the scan is what bounds them.

Declared approvals are not authenticated signatures and do not establish that a
real clinical or community review occurred. The committed
[reference pack](src/contextsafe/fixtures/reference/pack-draft.json) is intentionally `draft`, has
no approvals, and must fail compilation. Tests construct visibly test-only approval
declarations in memory solely to exercise the state machine.

These slices have no signatures, clinical oracle, network access, authorized
evidence-import command, hosted service, or approved patient-data pathway.
Iteration 3 contains internal-test-only local persistence, but
none of its records can authorize execution or support a receipt. The FHIR R4,
HL7 v2 and LIS readers each convert one synthetic file and are adapters to no
system: they read a file, never an endpoint, under a profile no
interoperability, clinical, laboratory, or community reviewer has examined.
Patient data is prohibited, but bounded checks cannot prove an input is synthetic.
Its fixture rules use invented tokens and are not medical guidance. It was built
ahead of the plan's discovery and governance gates as internal risk-reduction work,
so it cannot be represented as pack approval, pilot evidence, or V1 progress through
those gates.

With `uv` installed:

```bash
make verify
uv run contextsafe fixtures export   # packaged synthetic inputs, into ./fixtures/reference
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

# The second reference pair exercises every 0.2.0 rule-set predicate on the
# same case. Both rule sets are reference-only and ungoverned.
uv run contextsafe evaluate \
  --case fixtures/reference/case.json \
  --observations fixtures/reference/observations-predicates.json \
  --rules fixtures/reference/rules-predicates.json

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
release evidence. `pack validate`, `plan validate`, `evidence preflight`,
`import`, and both `finding` commands need descriptor-relative no-follow reads,
so on a platform without them — Windows included — they fail closed rather than
run with a weaker guarantee: `input_path_unsupported` for the boundary reads and
the review log, and `component_path_escape` for a pack component, because the
pack compiler maps an unsupported platform onto the same code as an escaping
path.
[Operations §3.1](docs/10-OPERATIONS-SRE.md) has the command-by-command matrix
and says what an operator on Windows can still run.

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

The gate implementations in `tools/` are inside the trees those gates scan,
inside strict typing, and inside the coverage floor, and `make scope` fails if a
tree of Python ever exists that no analysis was pointed at. They were not until 2026-08-27, which is the first
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
- [The 2026-09 wave: where all fifty-seven backlog items stand](docs/ROADMAP-WAVE-2026-09.md)
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
- [ADR 0007: every analysis declares the tree it examines](docs/adr/0007-declared-analysis-scope.md)
- [ADR 0008: one exit-code contract for every gate](docs/adr/0008-one-exit-code-contract-for-every-gate.md)
- [ADR 0009: mutation evidence over the declared safety modules](docs/adr/0009-mutation-evidence-over-declared-safety-modules.md)
- [ADR 0010: the signing layer, its first dependency and its trust model (proposed, decision pending)](docs/adr/0010-signing-layer-dependency-and-trust-model.md)
- [ADR 0011: the dependency audit stays in the merge gate and says when it could not reach the advisory service](docs/adr/0011-dependency-audit-reachability-in-the-merge-gate.md)

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
| Security & Supply-Chain | Applies — Semgrep SAST, gitleaks secret scan at three scopes (pre-commit diff, full-history CI gate over every ref, every object, and the working tree via `make secret-scan`, and that same scan again at a release tag), pip-audit dependency audit (`make audit`, which `.github/workflows/security.yml` now runs as that same target rather than as its own copy of the command, and which reports an unreachable advisory service as exit 2 rather than as a clean audit or a vulnerability — [ADR 0011](docs/adr/0011-dependency-audit-reachability-in-the-merge-gate.md)), pinned `uv.lock`, SHA-pinned actions bumped by Dependabot (`.github/dependabot.yml`, weekly, 7-day cooldown), `SECURITY.md`. Two pins Dependabot had stopped offering — `actions/checkout` at v7.0.0 and `actions/setup-python` at v6.3.0, since closing a Dependabot pull request tells it not to raise that version again and #18 and #19 were closed on 2026-08-16 — were bumped by hand on 2026-09-04 to v7.0.1 and v7.0.0, each SHA read from the upstream tag rather than guessed. Freshness against upstream is the one supply-chain fact no gate here re-derives, because it needs a network call; `tests/test_ci_workflows.py` checks what a checkout can see instead — every action pinned to a full SHA, carrying the version it is, and pinned to the same SHA in every workflow |
| CI/CD | Applies — `ci.yml` runs the identical `make verify` gate on every push to `main` and every pull request, with no `paths-ignore`. It carried one for `**.md`, `docs/**` and `LICENSE` until 2026-09-04; four `verify` stages are documentation gates, so a documentation-only change could break `make claims` and merge green while the next code pull request inherited the failure. `mutation.yml` runs `make mutants` weekly and on any change to the package, the suite or the gate itself, and `security.yml` runs SAST, the full-history secret scan and the dependency audit on every pull request and weekly. **No status check is required on this repository**: making `verify` required is a repository-settings change, and nothing here mechanically refuses a merge over a red one |
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
