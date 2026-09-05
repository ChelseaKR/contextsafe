# Changelog

All notable changes to ContextSafe are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Everything up to the
first release is collected under 0.1.0: `.github/workflows/release.yml` fires on
a `vX.Y.Z` tag and refuses to build unless this file already carries a matching
`## [X.Y.Z]` heading, so the section is written and dated before the tag exists
rather than after it.

## [Unreleased]

### Fixed

- **The full-history secret scan has been red on `main` since B-026 landed, on
  four false positives.** gitleaks' `generic-api-key` rule reads
  `SOURCE_TOKEN_PATTERN, max_length=96` as a credential because the assignment
  follows a constant whose name contains TOKEN, and reads
  `{"token": "CSYN-9876543210"}` as one too -- that being the value in
  `tests/test_mapping_profile.py` whose whole purpose is to prove such a value
  is refused. A repository about synthetic identity tokens was always going to
  meet this rule.

  There is now a `.gitleaks.toml`: the default ruleset, extended, plus the
  narrowest allowlist that makes it usable. Three entries, each a false
  positive verified by hand, each carrying its reason. Two of them are this
  project's own published synthetic-token grammar, which is the namespace that
  exists so a real identifier cannot be mistaken for a fixture one.

  The config is passed to all three phases explicitly rather than discovered.
  gitleaks looks for a config beside its `--source`, and phase 2's source is a
  temporary directory of materialized object blobs, so discovery would have
  applied the allowlist to two phases out of three and silently not to the one
  that exists to read what the other two cannot see. A missing config is now
  exit 2, "I did not examine", alongside an absent scanner and an unpinned one.

  An allowlist is a hole in a gate, so its boundary is pinned rather than
  asserted in a comment: `tests/test_secret_scan_allowlist.py` checks that each
  entry admits the shape it exists for and that no credential shape passes,
  including a credential sitting beside an allowed token, which is what an
  unanchored allowlist would have swallowed. Those credential shapes are joined
  at run time from parts, because written whole they are real findings for the
  scanner under test -- they were, on this file's first run -- and a literal
  would be folded into the `.pyc` as well.

### Fixed

- **A mapping profile could write a name into an observation.** Every target
  value is held to the synthetic grammar except the one field whose purpose is
  to carry a person's name: `_target_problem` returned `None` for a name to use
  on the reasoning that the observation contract already requires a `CSYN-`
  prefix. A prefix is not a grammar. `CSYN-Jordan Rivera 555-01-0199` carries
  it, and the published contract refused that document while the runtime
  accepted it and emitted the value into an observation set at exit 0. The
  contract was the stricter of the two only by accident: `nameToUseTarget`
  inlined its own pattern instead of referencing the `syntheticToken` the file
  already defines, so no test compared them. It references it now, a name
  target is held to the same grammar as every other target, and the two are
  pinned equal. Separately, every target string now goes through the same
  boundary scan the source token already went through, which closes the
  asymmetry that made `CSYN-9876543210` a `direct_identifier_detected`
  rejection as a source token and an accepted value as a target. Found by
  adversarial review of this branch, not by a gate.

### Removed

- **Gate 0 of `docs/PUBLICATION-READINESS.md`, withdrawn from the public record
  on 2026-09-04.** The section is replaced by a dated stub that keeps the gate
  number, and every sentence elsewhere that described it — in the audit's own
  header, verdict, summary tables and closing paragraph, in this changelog's
  0.1.0 entries for the audit, and in `docs/17-PUBLICATION-POLICY.md` — was
  reduced to the gate's name. Nothing it said is restated. The audit's technical
  findings and Gate 1 are unchanged. This closes the default view of the
  repository; it does not rewrite history.

### Added

- **The versioned mapping profile, `contextsafe import --mapping`, and
  `contextsafe mapping validate` (B-026).** A mapping profile is the
  document that says what a source's tokens mean: a closed, versioned table
  for one registered importer format, from a source token (the carrier it was
  read from — a field code, an extension URL or `Patient.name`, a segment-field
  such as `PID-8` or `GSP-5`, a column — and the verbatim token) to the
  canonical concept and value the observation should carry. It is published
  as [`contextsafe-mapping-profile-v1`](schemas/contextsafe-mapping-profile-v1.schema.json),
  and `contextsafe mapping validate --profile P.json --output canonical.json`
  emits its canonical unsigned form (rows sorted by source, review fixed)
  with its SHA-256, published as
  [`contextsafe-compiled-mapping-profile-v1`](schemas/contextsafe-compiled-mapping-profile-v1.schema.json),
  saying `signature_status: not_verified`, `executable: false`, and three
  pinned limitations. The only review status a profile may declare is
  `not_reviewed`, with no reviewer and no date; any other status, or a named
  reviewer, rejects the profile — a declared approval authorizes nothing,
  exactly as one on a pack does. `contextsafe mapping sign` (Architecture
  section 7) is not built, and the compiled document says so.

  Validation is whole and by name. A row whose target is sex parameter for
  clinical use while its source concept is gender identity or recorded sex
  or gender rejects first and as `prohibited_spcu_mapping` (A-020, A-021),
  before any other check on the row; any other cross-concept row rejects as
  `concept_type_mismatch`; two rows with different sources naming one target
  value reject as `mapping_profile_target_collapses_sources` (ambiguity
  retention: two source values never become one); a duplicate source, a
  carrier the format's importer does not read, a carrier read as a concept
  the importer never emits it as (`PID-8` is recorded sex or gender and
  nothing else), a format no importer is registered under, and a token that
  is not a bounded code or that trips the boundary scan each reject with
  their own code and a location, never a token. Every target value must be
  in the synthetic namespace: a `CSYN-` or `fixture-` token, a
  `urn:contextsafe:` code system or source, the observation contract's
  closed recorded-sex alphabet, a closed reference set of recording contexts
  (`administrative`, `government-id`, `jurisdictional`, `laboratory`,
  `payer`), or a lowercase pronoun-set shape such as `they/them`, which is
  admitted because the reference case's own pronouns value has that shape
  and is a shape, not a list. A sex-parameter row binds the value token and
  nothing else: its target has one field, and the order context and
  supporting observations stay the source's, so a profile cannot put an
  SPCU on an order the source did not carry it on. The carrier table the
  validator checks against is the importer registry's own declaration
  (`Importer.carriers`, one per format), so a profile can name nothing an
  importer does not read. One negative profile per prohibited row class is
  committed under `tests/fixtures/mapping/` and pinned to its code and
  location, and `tests/test_mapping_profile_schema.py` records which layer
  — the schema or the runtime — refuses each.

  `contextsafe import ... --mapping PROFILE.json` validates the profile
  first, requires it to be for the same format, runs the conversion exactly
  as before, and applies the profile to what it produced: every importer now
  records, beside each observation, the source token it was read from, and a
  row matches on that — on what the source said, not on the value the
  importer built — so the token `CSYN-PRONOUN-THEY-THEM` read from the
  canonical envelope's `pronouns` field binds to the case's `they/them`. A
  token with no row stays verbatim and the in-process result carries the
  closed warning `mapping_profile_row_unmatched`; nothing is dropped,
  chosen between, or normalized, no observation changes concept or
  disappears, and two observations that carried two tokens are two
  observations after binding, which the evaluator reports as ambiguous.
  Without `--mapping`, importers keep emitting verbatim tokens and the
  document is byte-identical to what it was. Every observation an import
  emits with a profile applied carries the profile's SHA-256 and version in
  its `mapping` block (`profile_sha256`, `profile_version`, always
  together), so `evaluate`'s input hash binds the profile that produced what
  it evaluated. Five reference profiles ship as package data — one per
  registered importer, `mapping-<format>.json` under
  `src/contextsafe/fixtures/reference/`, exported by `fixtures export` —
  binding each reference fixture's tokens to the reference case's values, so
  that `import --mapping` followed by `evaluate` passes every rule at the
  imported checkpoint (gender identity, name to use, and pronouns at `ehr`
  for the FHIR and HL7 fixtures; pronouns for the canonical envelope;
  recorded sex or gender at `registration` and sex parameter for clinical
  use at `interface` when the HL7 message is imported there) and reports
  `missing_evidence`, never `semantic_mismatch`, for the rest. The LIS
  profiles bind the laboratory export's tokens in the `laboratory` context
  and the reference rule set has no rule at `lis_return`, so those imports
  evaluate to missing evidence only.

  One published contract widened, the way B-023 widened it: the
  observation-set v0.1 `mapping` block, and the runtime rule behind it, now
  admit the optional `profile_sha256` and `profile_version` pair, required
  together (`dependentRequired` in the schema,
  `mapping_profile_binding_incomplete` at runtime). Every previously valid
  document is still valid, an observation no profile touched is
  byte-identical to before, no schema version moved, and the pinned
  reference-receipt digest and the five verbatim import digests are
  unchanged; a dated `$comment` on the block says so, because a consumer
  holding the earlier copy of the file rejects every observation set an
  import produced with `--mapping`. Five new pinned digests cover
  `import --mapping` per format and one covers `mapping validate`.
  `mapping` joins the event log's closed command vocabulary;
  `src/contextsafe/mapping_profile.py` and
  `src/contextsafe/importers/mapping.py` are declared safety modules; the
  packaged reference set is fourteen files and the audit's synthetic-data
  section is re-derived accordingly; `schemas/README.md` lists fifteen
  contracts. No new runtime dependency. What this does not claim: no
  interoperability, clinical, laboratory, or community reviewer has seen any
  profile, the reference profiles are synthetic bindings for the reference
  fixtures and not the mapping of any real system, `profile_reviewed` stays
  `false` on every result, HL7 null flavors and an LIS's empty cell are
  still not bound to presence states, nothing here signs, persists, or
  authorizes anything, and a profile that a customer declares is exactly as
  ungoverned as one this repository ships.

- **`contextsafe import`, the read-only conversion step, and the importer
  registry the adapters that follow will share (B-022).**
  `contextsafe import --format canonical-json --source FILE --case CASE.json
  --checkpoint ehr --output observations.json` opens one caller-owned
  canonical JSON boundary envelope through the same evidence boundary scan as
  `evidence preflight` (one descriptor, no-follow, one MiB, prohibited fields,
  Unicode controls, PHI canaries, direct-identifier patterns) and converts it
  into the observation-set document `evaluate --observations` accepts: one
  observation per record, `evidence.source_sha256` the digest of the source
  bytes, `evidence.source_pointer` the record's own pointer,
  `mapping.mapping_version` the importer's version, the case token and
  synthetic identifier cross-checked against the case document, and the
  emitted document re-validated by the observation contract before it is
  written. It persists, copies, indexes, and logs nothing; the plan-bound
  `evidence import` in Architecture §7 is a different command and still does
  not exist. The source's `plan_id` is checked for shape only, and the
  in-process result says so with a closed-vocabulary warning.

  The conversion is whole or nothing. A `field_code` outside the closed
  five-concept mapping (the envelope's laboratory codes included), a record
  with no value, a record that says `specified` and carries no value, a
  recorded-sex-or-gender record without a context, an identifier outside the
  synthetic namespace, a checkpoint other than the one requested, or any
  value the observation contract rejects (a non-synthetic name, an
  unsupported RSG value, an over-long context) rejects the source with a code
  and a location and produces nothing. Nothing is dropped, and nothing is
  normalized to the closest supported value (A-033). A sex-parameter record
  rejects too: the envelope cannot carry the supporting-observation link the
  concept needs in one record, and an SPCU observation without it is not
  emitted. A gender-identity, name, or pronouns record whose value code is
  from another concept's vocabulary (an RSG sex code such as `F`, or a
  laboratory status such as `abnormal`, both of which the envelope admits for
  any field) rejects the source with `import_concept_not_convertible` at the
  record's `value_code`: a presence-bearing concept carries a presence state
  or a `CSYN-` token and nothing else, so a sex code cannot arrive as a gender
  identity under a foreign token. This rule is part of mapping version
  `0.1.0` from its first release; no earlier version of the mapping shipped.

  Values are the source's own tokens, verbatim. `CSYN-PRONOUN-THEY-THEM` is
  carried as that string, not as `they/them`; gender identity's `code_system`
  and RSG's `source`, which the envelope does not carry, are filled with a
  fixed `urn:contextsafe:unbound-...` token rather than a value guessed from
  the case or the checkpoint, and name to use's `use` is `usual` because the
  observation contract admits nothing else, fixed by the contract and not
  read from the source. So evaluating the reference source against the
  reference `rules.json` reports `semantic_mismatch` for the pronouns rule
  and `missing_evidence` for the other four, and that is the correct result:
  the tool has not been told the token and the expected value are the same,
  because the mapping profile that would say so (B-026) does not exist. Every
  result carries `profile_reviewed: false`, and the result type refuses to be
  constructed otherwise. The field-code mapping is an identity over concept
  names, so no importer path can derive one concept from another.

  The module boundary is `src/contextsafe/importers/`: `base.py` holds the
  shared `ImportResult`, the closed `ImportWarningCode` vocabulary, the
  `import_*` rejection family, and the `Importer` protocol;
  `canonical_json.py` is the one registered format; `__init__.py` is the
  registry `--format` reads its choices from, so adding a format is one new
  module and one registry entry with no change to `cli.py`. All three are
  declared safety modules. `preflight.scan_source` and
  `evidence.parse_evidence_envelope` are the plan-free halves of the existing
  preflight, factored out so the importer runs the same scan the preflight
  runs. `evidence preflight` accepts and rejects exactly the sources it did,
  but its error precedence moved: the plan-scope equality check now runs on
  the parsed envelope, after the record and namespace checks, so a source
  with a wrong checkpoint or plan ID and a record-level or namespace defect
  reports the record or namespace code where it previously reported
  `evidence_scope_mismatch`. The Hypothesis suites assert that a rejection is
  value-free structurally, by comparing the whole error object against a
  closed set of fixed sentences at the expected path, not by testing that the
  drawn value is absent from the message. `import` honours `--quiet`,
  `--no-color`, `--output`, and `--log-dir` (the log's closed command
  vocabulary now includes `import`), is in the three-run determinism matrix
  with a pinned artifact digest, and fails closed with
  `input_path_unsupported` where descriptor-relative no-follow reads do not
  exist, as the other boundary commands do. Hypothesis suites pin that import
  followed by evaluate is deterministic and that any unknown field code or
  non-synthetic identifier rejects the whole source. No published contract
  changed, no schema version moved, and the pinned reference-receipt digest is
  unchanged. The mapping is reference-only and ungoverned: no clinical,
  laboratory, interoperability, or community reviewer has approved it, and
  nothing it emits can authorize execution or relabel an unsigned artifact.

- **`contextsafe import --format fhir-r4-json`, a read-only FHIR R4 JSON
  reader for one synthetic Patient (B-023).** The second format registered
  through the B-022 importer registry, with no change to `cli.py`. It opens
  one FHIR R4 JSON document -- a `Patient`, or a `Bundle` of type
  `collection` or `searchset` whose only entry is a `Patient` -- through the
  same evidence boundary scan as every other format (one descriptor,
  no-follow, one MiB, prohibited fields, Unicode controls, PHI canaries,
  direct-identifier patterns), reads it against an exact element allowlist,
  and emits the observation-set document `evaluate --observations` accepts.
  The HL7 Gender Harmony extensions map to the canonical concepts by an
  identity over concept names: `individual-genderIdentity` to gender
  identity, `individual-pronouns` to pronouns,
  `individual-recordedSexOrGender` to recorded sex or gender (its `type`
  sub-extension is the canonical context), and the `HumanName` with `use`
  equal to `usual` to name to use. Every observation carries the source
  digest, the profile version as `mapping.mapping_version`, and an RFC 6901
  JSON Pointer to the element it was read from (`/extension/0`,
  `/entry/0/resource/name/0`). Values are the coding's own code and system,
  verbatim. Two gender-identity extensions or two usual names become two
  observations, which the evaluator already reports as `ambiguous_evidence`.
  The packaged reference set gains `fhir-patient.json`, the accepting
  synthetic Patient for CTP-I01 with CSYN tokens only; `fixtures export`
  carries it, and the three-run determinism matrix pins its import digest.

  Rejections are whole-source, with a code and a location and never the
  content, and nothing outside the allowlist is dropped. Before the reader runs, the boundary
  scan rejects any narrative (`text`, with its `div`), any `contained`
  resource, any `note`, `comment`, `telecom`, `address`, or `birthDate`
  key, and any URL that is not one of the five published constants (the
  four Gender Harmony extension URLs and the `data-absent-reason` code
  system), which are exempt from the URL detector by exact equality only.
  The reader then rejects any element outside its allowlist (`gender`,
  `meta`, `photo`, and the rest of `Patient` included), any extension or
  sub-extension outside the profile (`comment`, `period`), any `display` on
  a coding, more than one coding on a value, any identifier or resource id
  outside `urn:contextsafe:synthetic` / `CSYN-`, a Patient that does not
  carry the case document's token, any `managingOrganization`,
  `generalPractitioner`, or `link` reference (no other resource can be in
  the document for it to resolve to), any resource type other than
  `Patient`, more or fewer than one Patient, a name without a declared
  `use`, a name with no `given` or `family` part, a usual name with other
  than one `given` token, a name part or coded value outside the synthetic
  alphabet, a `Bundle.total` that is not the integer one, and a Patient
  carrying none of the concepts. A recorded-sex-or-gender code outside the
  contract's closed alphabet (`F`, `M`, `X`, `unknown`, imported from the
  contract rather than restated) rejects at the extension's own location
  with `import_value_unsupported`, never normalized to the closest value
  (A-033), and every coding's system and code is bounded at the
  contract's 96-character token length where it sits in the source; the
  contract's re-validation of the converted document stays as a second
  check, and no rejection the reader produces names a path in the
  converted document. What the allowlist admits and the canonical model
  cannot hold is validated and not carried, and the list is closed:
  `Patient.id`, `Patient.active`, every `HumanName` whose `use` is not
  `usual`, `family` on the usual name, the pronouns coding's system, and
  the recorded-sex-or-gender value's system; each is a bounded token, a
  boolean, or a synthetic name part, and an emitted observation set is the
  five concepts, not the whole Patient. Recorded sex or gender carries no presence state: the canonical
  concept has a value and a context and no status, so a `value` or `type`
  coding in the `data-absent-reason` system rejects with
  `import_concept_not_convertible` rather than arriving as a recorded value;
  in particular that system's `unknown` ("not recorded") never becomes the
  contract's `unknown` ("recorded as unknown"), which a rule expecting a
  recorded value would otherwise match. One
  fixture per rejection class is committed under
  `tests/fixtures/fhir-r4-json/`, and a test requires every committed
  fixture to be pinned to its code and location.

  Sex parameter for clinical use comes only from the
  `patient-sexParameterForClinicalUse` extension, and this iteration does
  not carry it: the canonical concept needs an order context and a
  supporting-observation link, neither `Encounter` nor `ServiceRequest` is
  implemented as a carrier, and the extension rejects with
  `import_concept_not_convertible` rather than arriving without them.
  Nothing derives SPCU from any other concept.

  The reader's choices are one versioned constant, `FHIR_R4_PROFILE`
  (0.1.0), whose docstring names each choice the implementation guide left
  uncertain -- the `value` sub-extension form, `type` as the RSG context,
  the three `data-absent-reason` presence codes, one `given` as the name to
  use -- and whose `reviewed` field is `False` and cannot be set. The
  accepted subset is published as
  `schemas/contextsafe-fhir-r4-source-v0.1.schema.json`, a closed,
  reference-only contract that is not a FHIR conformance profile; a test
  holds the schema and the runtime to the same verdict on every committed
  fixture and lists the four rejections only the runtime can see (a
  canary, a direct-identifier pattern, the case-token cross-check, and the
  count over concepts); which coding shape each sub-extension admits is
  written into the schema per extension, so a presence code where the
  concept has no state, an alphabet code where a synthetic token is
  required, and a recorded-sex-or-gender value outside the closed alphabet
  fail the schema and the runtime alike. The
  boundary scan now takes a `BoundaryProfile`, a format's declared delta
  from the canonical scan (`name` permitted, FHIR element names as safe
  location keys, the five constants); the canonical profile permits nothing
  and `evidence preflight` is unchanged. `src/contextsafe/importers/fhir_r4_json.py`
  is a declared safety module.

  One published contract widened: the observation-set v0.1
  `evidence.source_pointer` pattern, and the runtime rule behind it, now
  admit an RFC 6901 JSON Pointer with unescaped alphanumeric reference
  tokens alongside the `$`-rooted path. Every previously valid document is
  still valid, no schema version moved, and the pinned reference-receipt
  digest is unchanged; a `$comment` on the property names the date and the
  item, because a consumer holding the earlier copy of the file rejects
  every `fhir-r4-json` output. The two Hypothesis suites that draw an
  element name or an identifier for the reader assert value-free rejection
  the way the B-022 suites do: the whole error object is a member of a
  closed set of fixed sentences at a location built only from the profile's
  own element names, and the short draws a substring check would fail on
  are pinned as explicit examples. The import-side warning vocabulary gains
  `checkpoint_asserted_by_caller`, because a FHIR document names no
  checkpoint and the one recorded is the caller's claim. What this does
  not claim: no interoperability, clinical, laboratory, or community
  reviewer has approved the profile; nothing here reads a FHIR server,
  persists, indexes, or logs a source, or authorizes execution; the
  receipt's own limitation text is unchanged and still says this iteration
  does not ingest FHIR, which remains true of evidence import and is a
  wording the maintainer, not this change, decides.

  The sibling `contextsafe-observation-v1` contract's
  `candidates[*].source_pointer` is widened the same way, with the same
  dated `$comment`, so a candidate read from a `fhir-r4-json` observation
  set can carry its pointer; no runtime parser reads that contract, and a
  test now holds the two contracts to one grammar. The synthetic-data
  confirmation in `docs/PUBLICATION-READINESS.md` section 4 is corrected
  under a dated update: the packaged set is six files (9,796 bytes) with
  `fhir-patient.json` in its table, and the rejection fixtures under
  `tests/fixtures/fhir-r4-json/` carry deliberately PII-shaped literals
  (`1980-01-02`, `555-0100`, `CSYN-1234567890`, the `ALICE` canary) that
  the section now names, each pinned to its rejection and guarded by the
  never-echoed assertion; two tests derive the section's figures and its
  literal list from the tree, because the claims gate does not read prose.

- **`contextsafe import --format hl7v2-er7`, an HL7 v2 ER7 reader registered
  through the importer registry (B-024).** It reads one ER7 message of at
  most one MiB through the same bounded, no-follow, descriptor-retaining
  first pass the other boundary commands use (`preflight.read_source`, the
  format-independent half of `scan_source`, factored out for it) and converts
  it, whole or not at all, into the observation-set document `evaluate
  --observations` accepts, with no change to `cli.py`: the registry gained
  one entry. Delimiters are the five characters MSH-1 and MSH-2 declare,
  exactly; the segment terminator is the carriage return the standard fixes;
  the only escape sequences handled are the five that encode a delimiter,
  and any other rejects. The segment allowlist is MSH, PID, GSP, OBR, and
  OBX. A segment outside it (every Z-segment included), a populated field
  the profile does not name, a repetition where the profile admits one
  value, a value that is not a bounded code token, a control character, a
  PHI canary, a direct-identifier pattern, a production processing ID, a
  version other than 2.9.1, or a patient identifier outside the synthetic
  namespace rejects the message with a code and a `SEG[n]-field.rep.comp`
  location under the message root, never the content. `source_pointer` on
  every observation has that same form.

  Every decision is a constant in `HL7V2_ER7_PROFILE`, version 0.1.0, with
  `profile_reviewed = False` and a type that refuses to be constructed
  otherwise: PID-3 must carry the synthetic identifier system and the case's
  token; PID-5 repetitions are typed by table 0200, `D` (Customary Name, the
  code the Gender Harmony guidance assigns to name to use) becomes the name
  to use and `L` is admitted as the synthetic legal test name and never
  emitted; GSP-4 is a closed (code, coding system) table of four LOINC
  concept types, each to its own concept; OBR and OBX are read only to locate
  the `ORDER-CSYN-` context and `SUP-CSYN-` supporting-observation tokens a
  sex parameter for clinical use needs, and an OBX of type TX, FT, or ST
  rejects as free text. PID-8 Administrative Sex is read by exactly one
  function whose return type is `RecordedSexOrGender`, and the concept an
  observation is labelled with is a function of the Python type of its value,
  so PID-8 reaches `recorded_sex_or_gender` with the context
  `administrative` and cannot reach gender identity or sex parameter for
  clinical use by any input; Hypothesis pins that over arbitrary PID-8
  values, comparing each rejection structurally against a closed set of
  fixed error objects, and pins that every delimiter set drawn from the 27
  printable characters a token cannot contain converts the reference message
  to the same observations (a delimiter that is also a token character is
  covered by the escape round-trip tests, not by that property). Values are
  the source's own tokens, verbatim: `U` in PID-8 is not turned into
  `unknown`, it rejects (A-033). GSP-5.3, the coding system of a GSP value,
  is read for exactly one thing, the `code_system` of a specified gender
  identity value; populated with pronouns, recorded sex or gender, sex
  parameter for clinical use, or a presence state under any concept it
  rejects with `import_field_not_in_profile` at `GSP[n]-5.1.3` rather than
  being dropped, so a token asserted in a vendor namespace is never carried
  as if it were the fixture's own, and a test runs `evaluate` on the
  accepting and rejecting pair so that pass cannot appear. OBX-11
  Observation Result Status is required and must be `F`; OBR-25 is optional.
  These rules are part of mapping version 0.1.0 from its first release; no
  earlier version of the conversion shipped.

  Fixtures are synthetic with invented tokens: the packaged reference set
  gains `hl7v2-er7-message.hl7`, an accepting message for CTP-I01 that
  evaluates against the reference rules to three passes at `ehr` and two
  indeterminates at the checkpoints it did not observe, and
  `tests/fixtures/hl7v2/` holds three rejection messages (a Z-segment, a
  free-text OBX, a non-synthetic MRN). `.gitattributes` marks `*.hl7` as
  `-text` so no platform's end-of-line handling touches the bare carriage
  returns. The importer is a declared safety module, is in the three-run
  determinism matrix with a pinned artifact digest, honours `--quiet`,
  `--no-color`, `--output`, and `--log-dir`, and fails closed with
  `input_path_unsupported` where descriptor-relative no-follow reads do not
  exist. `ImportErrorCode` gains five closed codes
  (`import_identifier_not_synthetic`, `import_repetition_not_allowed`,
  `import_segment_not_allowed`, `import_field_not_in_profile`,
  `import_value_not_in_profile`) and `ImportWarningCode` gains
  `checkpoint_not_in_source`, because an ER7 message cannot state its
  checkpoint and the requested one is applied. No published contract
  changed, no schema version moved, and the pinned reference-receipt digest
  is unchanged. The profile is reference-only and ungoverned: no
  interoperability, clinical, laboratory, or community reviewer has approved
  the name-type code, the concept-type table, or the placement of recorded
  sex or gender and sex parameter for clinical use in GSP rather than the
  GSR and GSC segments v2.9.1 also defines, and nothing it emits can
  authorize execution or relabel an unsigned artifact.

- **`contextsafe import --format lis-csv` and `--format lis-json`: the
  identity half of the LIS export reader (B-025).** A laboratory result
  export carries the patient's identity beside the results, and that identity
  is what a result-facing display shows (A-031). Two importers register into
  the B-022 registry, with no change to `cli.py`, and read *only* the identity
  columns of such an export into name-to-use, pronoun, and
  recorded-sex-or-gender observations at `lis_return`. The column set is a
  versioned profile constant, `LIS_PROFILE` 0.1.0, whose `profile_reviewed`
  is `false` and whose type refuses `true`: `patient_id` on every row,
  cross-checked against the case document; `name_to_use`, `pronouns`, and
  `sex`, which are read, with `sex` mapping only to recorded sex or gender in
  the fixed context `laboratory` and never to gender identity or sex
  parameter for clinical use; and `analyte`, `value`, `unit`, `range`,
  `flag`, `order`, and `specimen`, which are recognized, bounded, scanned,
  and counted and produce no observation, because the laboratory result
  observation family is a later item (B-030) and the observation contract
  has no concept for a result. A source that carries them gets the new closed
  warning `result_columns_not_observed` and `ImportResult` gains
  `unobserved_cell_count`, the number of cells read and not claimed.

  The conversion is whole or nothing. A column or key outside the allowlist
  (a `gender_identity` or `sex_parameter_for_clinical_use` column included),
  a duplicate column, a missing `patient_id`, a table with no identity
  column, a row count outside 1 to 2,000, a cell over 128 characters, a cell
  beginning with `=`, `+`, `-`, or `@`, an empty identity cell, a cell that
  says `specified` without a value, a name or pronoun cell that is neither a
  presence state nor a `CSYN-` token, a `sex` value the observation contract
  does not admit (`f` is not read as `F`), an `order` or `specimen` cell
  outside the synthetic namespace, a result cell with whitespace in it, a
  `patient_id` that is not a synthetic case token or names another case, and
  any cell the evidence boundary scan refuses (boundary whitespace, a control
  or format character, a PHI canary, a direct-identifier pattern) each reject
  the whole file with a code and a position — a header index, a row and
  column name from the profile, or a record and field index — and never a
  cell or a key. Seven codes join the `import_*` family for this:
  `import_source_malformed`, `import_bound_exceeded`,
  `import_column_unknown`, `import_column_duplicate`,
  `import_column_missing`, `import_formula_cell`,
  `import_identifier_not_synthetic`, and `import_cell_free_text`. Any
  checkpoint but `lis_return` rejects before the file is opened.

  CSV is an RFC 4180 subset read by a strict reader of its own in
  `importers/lis_csv.py` (UTF-8, no byte-order mark, CRLF or LF, a header
  row, quoted fields with doubled quotes, no embedded line break, no bare
  CR, no bare quote, every record the header's width), because the standard
  `csv` module carries a line break inside a quoted field and a boundary
  reader must mean one thing. JSON is the new published contract
  `schemas/contextsafe-lis-export-v0.1.schema.json`, an input shape whose
  rows are objects over the same allowlist and must all carry the same key
  set; `tests/test_lis_export_schema.py` keeps it in agreement with the
  runtime's allowlist and grammars and records which rejections the schema
  alone catches. Both formats come through the evidence boundary's own open
  path: `preflight.read_source` is the bounded, no-follow, one MiB,
  metadata-unchanged first pass stopped before the JSON parse, and
  `preflight.scan_text` is the per-string half of the boundary scan made
  public so a CSV cell is held to exactly the rule an envelope string is;
  the LIS column names join the closed set of keys a rejection path may
  name. A result export repeats the identity on every row, so one
  observation is emitted per distinct value per identity column, pointed at
  the first row that carries it; rows that disagree produce one observation
  each and evaluate as ambiguous rather than pass. Nothing is chosen between
  them, and an empty identity cell is not read as `absent`.

  The packaged reference set gains `lis-export.csv` and `lis-export.json`
  (invented tokens; not the shape of any real system's export), so
  `fixtures export` now writes seven files. Both LIS imports are in the
  three-run determinism matrix with pinned artifact digests, and `lis.py`
  and `lis_csv.py` are declared safety modules. One fixture per rule sits
  under `tests/fixtures/lis/`, accepting and rejecting, and Hypothesis
  suites pin that both readers agree on any table, that any unknown column
  or foreign case identifier rejects the whole table with a fixed error
  object, and that a formula prefix in any cell does the same.

  What it does not claim. The profile is reference-only and ungoverned: no
  laboratory, interoperability, clinical, or community reviewer has approved
  it as the shape of any export, and the 4h laboratory review the backlog
  row budgets has not happened. Values are carried as tokens with no mapping
  profile to bind them, so evaluating the reference export against a
  `lis_return` rule passes the name (the same `CSYN-ASTER` on both sides)
  and reports `semantic_mismatch` for the pronoun token and the
  laboratory-context sex value, and against the shipped `rules.json`, which
  names no `lis_return` checkpoint, everything stays `missing_evidence`. No
  laboratory result observation exists yet; the result columns are counted
  and nothing more. `ImportResult.to_dict` gains a key, but that report has
  no schema and no command emits it. No existing contract version moved, the
  pinned reference-receipt and canonical-import digests are unchanged, and
  no runtime dependency was added.

- **B-048, the part that needs no external person: a committed answer for
  every published seeded fault.** `tests/test_seeded_faults.py` carries a
  36-row matrix over F-001 to F-036 from `docs/09-TEST-AND-EVALUATION.md`
  section 4, and a dated status table under that section restates it row for
  row; a test compares the two in both directions and another compares the
  matrix's mutation and detector columns to the library table verbatim, so
  neither document can drift from the other. Three new faults are exercised
  as complete synthetic fixtures under `tests/fixtures/seeded-faults/`: F-001
  (the name to use survives registration and reaches the EHR with status
  `absent`: `value_not_present` and `value_changed_across_checkpoints`,
  located at `ehr` after `registration`; removed entirely it is
  `missing_evidence`, never pass), F-009 (the recorded sex or gender reaches
  the EHR as X but with the boundary's own context and source in place of
  the declared ones: `value_changed_across_checkpoints` and
  `semantic_mismatch` at `ehr`, while the `not_coerced` rule beside them
  passes because the value survived, so a receipt says which claim turned
  and never reports a lost context as a rewritten value; the contract has no
  way to carry a dropped descriptor and refuses one as `missing_field`), and
  F-035 (the same faithful value through mapping version 0.2.0: both forms
  pass, the trace names the version and mapping hash, and `input_sha256`,
  `result_sha256`, and `payload_sha256` all move while `rule_set_sha256`
  stays, so two mapping versions can never share a run identity). Every
  exercised fault, the nine from B-028 and B-031 included, now has a
  restated localization: the divergence section's `from_expected` and
  `from_previous` for the fault's concept, a check that the detecting rule
  reads the checkpoint the section locates, and a library-wide check that no
  located boundary is ever an unobserved one. Five faults are refused before
  evaluation and pinned under `seeded-faults/refused/` with their code and
  structural path, in process and through the CLI (exit 2, no receipt
  written, no value in the error object): F-015 and F-016 as a declared
  GI-to-SPCU or RSG-to-SPCU mapping (`prohibited_spcu_mapping`), F-024 as an
  unsupported recorded-sex-or-gender token (`invalid_rsg_value`) and, in a
  variant, an unsupported status (`invalid_enum`), neither ever
  nearest-matched, F-029 as a case identifier outside the synthetic
  namespace (`invalid_synthetic_identifier`) and, in a variant, an
  identifying field on the case or an observation (`prohibited_field`), and
  F-032 as an observation naming another case (`case_mismatch`, reassigned
  to neither case). F-028 and F-030 are refused by the pack validity and
  receipt contract tests that already existed, and the matrix's pointers to
  those tests are checked to resolve. `tests/test_receipt_schema.py` no
  longer evaluates the `refused/` directory, since no receipt exists for a
  refused input. What this does not do: it is not the 41-fault evaluation
  B-048 defines. There is no hidden-fault set, no independent fault author
  has reviewed the corpus, no independent QA has run it, and every fault was
  written by the implementer of the mechanism that detects it, so 12 of 36
  exercised, 7 refused, and 17 not yet exercisable is deterministic corpus
  coverage and no population-sensitivity claim. The seventeen name what they
  wait on from a closed vocabulary — laboratory results (B-011, B-025,
  B-030), SPCU predicates awaiting clinical review (B-029), name contexts
  and periods in the observation contract (B-019), the receipt verifier
  (B-036), signatures (B-035), the review state machine (B-032), and the
  presentation pass (B-038) — and none was stretched into an exercised row:
  an absent SPCU is indistinguishable from an unobserved boundary under the
  contract, a relinked support is only a changed value, and F-012 reads as
  diverged in the divergence section without any predicate able to name the
  order. No contract version moves, no enum widens, no source module
  changes, and no pinned digest changes. After review: the README's B-028
  subsection, which counted twenty-seven faults as undetectable when it was
  written, now dates that count to its own slice and defers to the B-048
  subsection, and a test holds the README to one current count (the
  matrix's); the F-015 and F-016 evidence cells in the matrix and the docs/09
  table say the refusal covers the declared mapping form only, not the
  undeclared derivation the library's F-016 also names; the F-023 and F-035
  evidence prose is built from the same constants their tests read; and the
  CLI refusal test checks the stderr bytes, not only the error object, for
  the refused fixtures' identity-shaped tokens.
- **B-031 slice: the first observed divergence and the evidence trace
  (A-032 to A-035), as mechanism and nothing more.** The receipt payload has a
  `divergence` section, computed by the new `contextsafe.divergence` module
  from the case and the observations alone: for each of the five concepts,
  the state of every checkpoint in pathway order (`observed`, `unobserved`,
  or `ambiguous`, with the sorted value hashes seen there), the first observed
  checkpoint whose hashes depart from the manifest's (`from_expected`), and
  the first observed checkpoint whose hashes depart from the previous observed
  one (`from_previous`, which names both sides). An unobserved checkpoint is
  never a location: a divergence found across an unobserved gap is located
  between the two observed sides, and the closed shape has no field in which
  the gap could be blamed. `agreed_where_observed` says only that every
  boundary with evidence agreed; a concept with no evidence is `unobserved`;
  a boundary that cannot be read as one state (two observations of a
  single-valued concept, or one record captured twice) is `ambiguous` and the
  concept is `indeterminate` from there, never agreed. Every outcome carries a
  `trace`: the distinct source hash and source pointer of each observation
  the predicate read, and the distinct version and hash of each mapping they
  came through, both sorted so observation order cannot reach the payload.
  A source pointer is now a structural path and nothing else: `parse_observations`
  refuses an observation whose pointer has any segment outside the closed
  vocabulary in `contextsafe.validation.STRUCTURAL_POINTER_SEGMENTS`
  (`non_structural_pointer`), the receipt contract publishes the same
  vocabulary as a pattern, and a property test holds that a pointer drawn
  from the pointer alphabet at random is either refused or made only of those
  words and integers. The rendered page has a "First observed divergence"
  section in `en-US` and machine-translated `es-US`, with the sentence that
  says what is never blamed rendered beside its `en-US` original.
  `tests/fixtures/seeded-faults/` gains F-023 (a checkpoint omitted: both
  rules that read it are `indeterminate` with `missing_evidence`, the boundary
  is `unobserved`, and nothing passes there) and F-025 (name to use faithful
  at registration, unobserved at the EHR, changed after: located at the
  interface and between registration and the interface, and the EHR is named
  nowhere). Property tests hold that reordering observations never changes
  the section and that deleting every observation at one checkpoint never
  names the deleted boundary, never moves the located boundary when the
  deleted one was neither side of it, and, when the located boundary itself
  is deleted, locates only a boundary that already differed from the observed
  boundary behind it: the location can move forward across the gap the
  deletion opened, never onto a boundary that agreed with the boundary
  observed before it. The receipt contract enforces the pairings its comments
  stated: a `diverged` or `indeterminate` entry must name `at`, a `diverged`
  `from_previous` must name both sides, an `agreed_where_observed` or
  `unobserved` entry names nothing, and an `unobserved` checkpoint state
  carries no hashes while every other state carries at least one, so a
  hand-edited document fails the contract rather than surfacing in a
  renderer. The rendered page holds every checkpoint, concept, reason,
  state, and status it reads from a receipt to the published set before the
  value can become a catalog key: an unpublished value is refused as
  `invalid_receipt_document` at its structural pointer, and the value never
  reaches the stderr error object (the catalog's own unknown-key rejection
  names the key it was asked for, which is why it must never be reached with
  receipt content). What this does not do: it decides divergence of value
  hashes, not which value was right; a record-list concept is compared as
  its whole list, so partial capture of the declared records at a boundary
  reads as diverged there; `expected_sha256s` is carried for all five
  concepts whether or not a rule names them and, like every payload hash,
  unsalted, so a small-value-space concept such as pronouns is recoverable
  by enumeration; an outcome that stopped at an evidence gate traces only
  the side that decided it; it is not a finding and carries no severity
  (B-032); the trace names no oracle or pack because none exists to name;
  A-033 is enforced only by the existing fail-closed validators, because no
  normalizer exists yet; and no clinical, laboratory, or community review
  has looked at any of it.
- **B-028 slice: assertion predicates for identity, name to use, pronouns,
  and recorded sex or gender (A-005, A-008 to A-015), as mechanism and
  nothing more.** A rule used to be one expected value plus `required`, with
  the single observed hash compared to the expected hash. A rule set that
  declares `contextsafe.rule-set/0.2.0` may now name one predicate from a
  closed set, each a pure function in `contextsafe.evaluator`: `exact` (the
  default, unchanged); `present`, the value has status `specified` (A-008);
  `status_preserved`, the observed status equals the expected status and the
  value is not consulted, so declined stays declined and never becomes
  unknown, absent, or populated (A-009); `not_coerced`, the observed value's
  presence status and scalar are those of none of a closed `forbidden` set the
  rule carries in fixture tokens, so X or unknown rewritten to M or F is a
  coercion whether or not the boundary also stamped its own context or source
  on the record (A-014);
  `record_count`, exactly `expected_count` distinct records remain (A-013);
  `preserved_across`, the same value hash at `preserved_from` and at the
  rule's checkpoint (A-005, A-010, A-012); and `not_overwritten_by`, the
  observed gender identity is not another concept's declared value (A-011).
  Missing evidence is `indeterminate`, an ambiguous checkpoint is
  `indeterminate`, and no predicate can pass on zero observations.
  Every predicate has one affirmative and one failure reason, twelve new codes
  in the closed `OutcomeReason` set and the receipt contract, so a receipt says
  which claim was decided. The field a predicate reads is required for it and
  an unknown field for every other; a predicate that would be vacuous for a
  concept (`present` on recorded sex or gender, `not_overwritten_by` on
  anything but gender identity) is refused; a forbidden set that repeats a
  status and scalar under another context, or names the expected one, is
  refused; and `parse_bundle` refuses a rule the case manifest contradicts (a
  forbidden status and scalar the manifest declares under any context, a
  `present` rule on a declined value, an `expected_count` the manifest does
  not carry or that it carries as a repeated record, which the predicate's
  distinct-hash count could never meet: `indistinct_declared_records`, a
  `not_overwritten_by` expectation the manifest also declares under another
  concept: `overwritten_expectation_conflict`). The contract is
  `schemas/contextsafe-rule-set-v0.2.schema.json`,
  the first published schema for the rule set, with
  `tests/test_rule_set_schema.py` holding it to the runtime. Fixtures: a
  second ungoverned reference pair, `rules-predicates.json` and
  `observations-predicates.json`, exercises every predicate against CTP-I01,
  ships the `exact` rule beside its `not_coerced` rule on the same field
  (A-I09 beside A-I06) so a receipt says which of the two claims turned, and
  is pinned in the three-run determinism matrix; and
  `tests/fixtures/seeded-faults/` carries F-004, F-005, F-006, F-007, F-008,
  F-010, and F-031 from `docs/09-TEST-AND-EVALUATION.md` section 4 as complete
  synthetic inputs, each proved to be reported as `fail` with its own reason
  and never as `pass`, and F-007 and F-008 additionally with the boundary's
  own context, source, or both stamped on the coerced record. The property
  layer generates every predicate, reaches `pass` and `fail` under each one
  by design (one observation at every checkpoint a predicate reads, values
  drawn from the faithful, forbidden, restamped-forbidden, status-moved, and
  other-concept cases), holds the status algebra over all of them, and
  carries a derandomized guard test that fails when the generator stops
  reaching a branch. What this does not do: no clinical, laboratory, or
  community review has approved any rule or predicate here; `not_coerced`
  decides status and scalar only, so the faithful X under a rewritten context
  passes it and is the `exact` rule's to report; on the recorded-sex-or-gender
  concept only X and unknown are expressible, so "absent" in A-014 is
  reachable only through a status-bearing concept; a checkpoint carrying two
  records of one concept is `ambiguous_evidence` under every
  single-observation predicate, `not_coerced` included, so a multi-record
  case cannot be evaluated for A-014; `preserved_across` is a preservation
  claim, not a correctness claim; and the pack contract still pins the
  exact-only rule-set shape, so a 0.2.0 rule set is refused as a pack
  component by name (`incompatible_component`) until that contract moves.

### Changed

- **The receipt contract is 0.3: `contextsafe.receipt/0.3.0`,
  `schemas/contextsafe-receipt-v0.3.schema.json`.** The payload gains the
  required `divergence` section and every outcome gains a required `trace`;
  the closed `evidence_state` and `divergence_status` sets, the pinned
  `pathway`, and the structural-pointer pattern are new definitions; nothing
  0.2 carried changed. The 0.2 file is not kept beside it. Because the outcome
  list now carries a trace, `result_sha256` moved for every receipt, and both
  pinned reference digests in `tests/test_determinism.py` moved with it —
  once, and only for that reason: `input_sha256` and `rule_set_sha256` are
  byte-identical to 0.2, and no fixture changed. The README example receipt
  was refreshed for the same fields. The `receipt-document` version is
  unchanged: the envelope shape did not move.
- **A receipt now carries source pointers, so the old rule that it carries
  none is replaced by a stronger one.** Two tests used to assert that the
  string `source_pointer` never appears in a receipt; since A-035 requires
  the trace, they now assert that every pointer a receipt carries is a path
  of closed structural segments, and `test_divergence.py` holds the same over
  generated pointers. The value-minimisation claim is unchanged in substance:
  a pointer is a location in a source, and no word that is not a canonical
  field name can be in one.
- **`parse_observations` is stricter.** A source pointer whose segments are
  not all in the closed structural vocabulary is refused
  (`non_structural_pointer`) where the pattern check alone used to accept any
  word of the pointer alphabet. Every packaged fixture, seeded fault, and
  property generator already used structural pointers, so nothing shipped
  changed; an observation set that named a field outside the canonical
  manifest or evidence envelope is now refused rather than carried.
- Seventeen strings were added to both locale catalogs for the divergence
  section. The `es-US` entries are machine translations marked `machine`,
  like every other entry in that catalog: B-042 has not happened, and nothing
  here claims it has.
- **The receipt contract is 0.2: `contextsafe.receipt/0.2.0`,
  `schemas/contextsafe-receipt-v0.2.schema.json`.** The closed outcome-reason
  enum widened by the twelve predicate reasons, a `$comment` on
  `observed_sha256s` says what it carries under `preserved_across` and
  `record_count`, and nothing else changed; the
  0.1 file is not kept beside it, so a consumer pinned to the 0.1 `$id`
  rejects a 0.2 receipt on its `schema_version` rather than accepting a reason
  it has never seen. Because the payload carries its own `schema_version`,
  every receipt's `payload_sha256` moved, and the pinned reference-receipt
  digest in `tests/test_determinism.py` moved with it — once, and only for
  that reason: the reference `input_sha256`, `result_sha256`, and
  `rule_set_sha256` are byte-identical to 0.1.0, and `rules.json` and
  `observations.json` are unchanged. The README example receipt was refreshed
  for the same two fields. The `receipt-document` version is unchanged: the
  envelope shape did not move.
- **The rule-set contract is accepted at two versions.** `0.1.0` is untouched:
  no predicate field is allowed there, every existing `rules.json` parses
  unchanged, and its canonical form and hash are what they were. `0.2.0`
  admits the predicate fields, and its canonical form omits `exact` and every
  field the predicate does not read, so an exact rule hashes the same under
  either version. `contextsafe fixtures export` now writes seven files rather
  than five.
- Twelve `reason.*` strings were added to both locale catalogs. The `es-US`
  entries are machine translations marked `machine`, like every other entry in
  that catalog: B-042 has not happened, and nothing here claims it has.

- **ADR 0010 proposes the signing layer and stops at the decision only the
  maintainer can make.** The standard library has no Ed25519, so the first
  `sign` command is also the first runtime dependency of a project whose
  `dependencies = []` is a supply-chain claim. The record lays out four options
  — `cryptography`, `PyNaCl`, an optional `contextsafe[signing]` extra whose
  commands fail closed with `signing_unavailable` when the backend is absent,
  and a pure-Python implementation rejected outright because the interpreter's
  arithmetic is not constant-time and nobody here can review an RFC 8032
  verifier — with the `pip-audit` surface, per-platform wheels and Windows
  consequences of each as read from PyPI and OSV on 2026-09-04 and dated in the
  text, and recommends the extra backed by `PyNaCl`: the smaller surface that
  contains the one primitive this tool needs, a verifier that rejects the
  non-canonical inputs a cross-platform verifier must agree about, and on that
  date a wheel for every platform B-045 names. It then fixes what B-035 and
  B-036 must implement under any option: a detached-signature document and a
  trust manifest as draft schema fragments held inside the ADR and not
  committed to `schemas/`, subject hashes rather than files as the signed
  thing behind a domain-separation prefix, rotation with a 90-day overlap
  bound and the honest consequence that without trusted time a signature is
  as durable as its key's validity interval, root-signed monotonic revocation
  with the 31-day freshness rule from Architecture §6.6 measured against a
  caller-declared `--as-of` and never a clock, compromise recovery for a key
  and for the root, the per-purpose thresholds with distinctness by holder and
  organization, a closed error-category set for the `sign` and `verify`
  commands, and what a verified result does not prove without RFC 3161 time.
  Four points depart from §6.6's wording and are flagged for the maintainer,
  the first being that the manifest carries opaque holder and organization
  tokens rather than names, because a producible roster of trans-health
  reviewers is what T-08, T-17 and T-18 exist to keep small. Status is
  proposed. No module, command, schema, fixture, key, test or dependency is
  added; the shipped tool is byte-identical, no security review of the trust
  model has happened, and every artifact still says `not_signed` or
  `not_verified`. See
  [ADR 0010](docs/adr/0010-signing-layer-dependency-and-trust-model.md).

- **Packaging and fresh-install evidence, the part of B-045 that CI can
  produce.** `.github/workflows/package.yml` fires on a `vX.Y.Z` tag (the
  shape `release.yml` listens for; the two run independently, and an
  attestation's existence says nothing about whether the release gate passed)
  and on request. One job builds the sdist and wheel with `uv build`, exports a
  CycloneDX 1.5 SBOM from the locked graph with `uv export` (the pinned `uv`
  already in every workflow; no action, no new dependency of any kind), and
  records a `SHA256SUMS`. A matrix on `ubuntu-24.04`, `macos-15` and
  `windows-2025` then installs that wheel with `pip install --no-index` into an
  empty `python -m venv`, changes to a directory outside the checkout, runs
  `contextsafe fixtures export` and the README Quickstart, and requires the
  receipt document to reproduce the digest `tests/test_determinism.py` pins.
  `--no-index` is the `dependencies = []` claim enforced: a wheel that needs
  anything from an index fails to install. Only after every platform passes is
  build provenance attested with `actions/attest-build-provenance` (pinned by
  SHA, `id-token` and `attestations` write scoped to that one job) over the
  recorded checksums, and the artifacts, the per-platform reports and the
  provenance bundle are uploaded. Least-privilege permissions, immutable action
  SHAs with version comments and `persist-credentials: false` throughout;
  actionlint 1.7.12 and zizmor 1.16.3 (pedantic persona) report nothing.

  The gate is `tools/fresh_install_gate.py`, stdlib only, with the three exit
  codes every gate here has: 0 installed, ran and matched; 1 examined and
  wrong; 2 not examined -- no wheel, two wheels, no pip, no pin, a Quickstart
  line it cannot run, a working directory inside the checkout or one that
  already exists -- which is never a pass. The pre-existence refusal closes a
  fail-open shape found in review before merge: `python -m venv` over a kept
  environment and `pip install --no-index` of an already-installed version
  both exit 0, so a `--workdir` whose `outside/` had been removed but whose
  `venv/` remained would have run the Quickstart from the stale install and
  printed the clean line with the new wheel's name and digest. The gate now
  refuses any working directory that exists before it runs (the default path
  creates a private parent and works in a child of it), passes `--clear` to
  `venv` and `--force-reinstall` to `pip` as second guards under that first,
  and treats a bare `uv run contextsafe` Quickstart line as not examined
  rather than as a traceback. It reads the pinned digest from `tests/test_determinism.py` with
  `ast`, so there is one copy of the constant and the gate cannot agree with a
  stale one; the Quickstart parser that used to live in
  `tests/test_wheel_quickstart.py` moved into the gate, and that test now
  builds the wheel and drives the gate's real subprocess path on every
  `make verify`. Its report carries digests, counts, closed-vocabulary codes
  and a platform name and no path; a failed command is reduced to its exit
  code and, where stderr is the tool's own JSON error object, the error code.
  `tests/test_fresh_install_gate.py` drives all three states with a stand-in
  runner and pins that no path reaches the report. `make package` builds the
  same artifacts locally and lists the wheel's contents, so a reviewer can see
  what shipped; the reference fixtures were missing from it until 2026-09-02
  and nothing showed that.

  What this is not. These are GitHub's server images, not the Windows 11 and
  macOS desktop fresh installs RG-15 names: it is packaging evidence, and B-045
  stays open for the desktop half. The artifacts are unsigned. Build provenance
  states which workflow at which commit produced these bytes and nothing about
  whether anyone authorized them; it is not the B-035 signing path, and it does
  not make the release artifacts "signed" in the sense `docs/10-OPERATIONS-SRE.md`
  §4 uses. The SBOM is derived from `uv.lock` rather than read back out of the
  wheel, and `uv export`'s CycloneDX output carries a fresh serial number and
  timestamp on every run, so two exports of the same commit are not
  byte-identical; the provenance statement, not the SBOM, is what binds the
  artifact digests. `release.yml` is untouched: it still owns the full-history
  secret scan, `make verify` at the tag and the CHANGELOG heading, and there is
  still no publish step. Nothing here has fired: no tag exists.

- **B-038 and B-041, audited on 2026-09-04 and completed where they fell
  short.** The audit found the pseudolocale expanding text by 30 percent
  against the 35 the accessibility document requires, with nothing measuring
  it; `hardcoded-string` and `undisclosed-machine-translation` with no negative
  control despite `docs/I18N.md` saying every rule had one; a print block with
  no repeated-header or keep-together rule and a gate that checked only
  `display: none`; a renderer that trusted the document's own `payload_sha256`
  and rendered around any field it did not know; and nothing proving the page
  carries only what it needs (A-036, F-027). Now:
  - `qps-ploc` grows every message by at least `PSEUDO_MINIMUM_EXPANSION`
    (35 percent), and `make i18n` gains `pseudolocale-fidelity`: the floor,
    no accentable letter outside a placeholder left plain, and placeholder
    parity, measured on the generated catalog rather than assumed of the
    transform. A Hypothesis property pins the same three facts for arbitrary
    source text, and a negative control accents one letter per message, the
    transform that "some diacritic somewhere" could not tell from a real one.
    The floor is measured on the body with the two brackets set aside, the
    measure the transform pads to and the property uses: counted, the
    brackets alone were 40 percent of a four-letter status word, so a
    transform that stopped padding passed on exactly the short labels where
    expansion matters, and a control now names every label of five
    characters or fewer under that transform. An empty source message is
    `message-quality`'s finding and is no longer divided by. The pseudolocale
    is still never shipped to a reader. `hardcoded-string`'s parser pops the
    language stack by tag name, so a stray end tag can no longer shift the
    runs after it into the accepting source-locale bucket.
  - `hardcoded-string` now judges each visible run under the `lang` in force
    for it: source-locale wording is accepted only where the page marks it as
    a source-locale original, so an unmarked copy of a catalog sentence is a
    finding, reported by position and length rather than quoted. Both it and
    `undisclosed-machine-translation` have negative controls that were watched
    to fail.
  - The print stylesheet declares `thead` a repeating header group, keeps a
    result row, a limitation with its source original, the translation notice
    and a source-text block on one page, and keeps headings and captions with
    what follows them. `make a11y`'s `print` check fails when any of those
    declarations is absent, when a table has no `<thead>`, when any print
    rule on any selector sets a break property (`break-inside`,
    `page-break-inside`, `break-after`, `page-break-after`) or a `thead`
    display to anything else, or when any print rule but the skip link's
    hides by any of the techniques `HIDING_TECHNIQUES` names: `display`,
    `visibility: hidden` or `collapse`, zero opacity, a font below a pixel, a
    clip, a collapsed box with its overflow cut off, a positioned box pushed
    off the sheet, `content-visibility: hidden`, a transform that scales to
    nothing or translates off the sheet, or a negative indent or margin past
    the edge, each with a negative control. The hiding rule is an allowlist
    of what may be hidden rather than a list of selectors to protect, because
    a protected list let `li { display: none; }` through, and that hides
    every limitation. Review of the first form of this check found three
    more ways past it, each now a control: it read one block spelled exactly
    `@media print {` and filed a second print block, `print{`, `print and
    (...)` or `screen, print` under screen, where nothing looked (every
    `@media` block whose query reaches the printer is print now, brace-
    balanced, and a block the gate cannot classify is a finding); it
    compared declarations verbatim, so `DISPLAY: NONE`, `display: none
    !important` and `visibility: HIDDEN` produced nothing (names and values
    are lower-cased and `!important` set aside now); and it counted only an
    `absolute` or `fixed` box as positioned and compared `-50em` as the
    number 50 against 100 pixels (any `position` but `static` counts, and
    lengths are measured in their unit). `position: relative; left:
    -9999px`, which the first form's accepting test pinned as hiding
    nothing, is a catching row.
  - `render_receipt_page` recomputes the payload hash and refuses a document
    whose `payload_sha256` does not cover its payload
    (`receipt_payload_hash_mismatch`), and refuses any object carrying a field
    the receipt contract does not publish (`invalid_receipt_document`, naming
    the location and never the field or its value). A result's expected,
    observed and evidence hashes and its rule version stay in the JSON and off
    the page, and a test pins that against the schema's closed objects.
  - `make a11y` gains `minimization`: every visible run of text, the text of
    a `title`, `aria-label` or `alt` attribute included, is catalog text
    or one of the receipt values the page is allowed to present, named by
    pointer; a catalog message with a placeholder counts only when the
    placeholder holds one of those values or a locale tag, so no message is a
    prefix that free text can hide behind. Anything else is a finding that
    reports position and length, never content. The gate derives the hash
    each page must carry from the payload rather than reading the document's
    field, so a tampered document cannot be audited by agreeing with itself;
    the negative control forges the field and a page that carries it, so it
    fails under a gate that reads the field and passes only under one that
    recomputes. `src/contextsafe/html_receipt.py` joins the Makefile's
    `SAFETY_MODULES` now that it validates a document rather than only
    rendering one.

  Existing tests that edit a payload after it is built now re-seal it first.
  Neither item is closed: the print checks are computed from the stylesheet
  and the markup, not from a browser that printed the page, so the
  print-preview task in Accessibility §7 stays with B-044; no locale was
  added and es-US remains an unreviewed machine translation (B-042). No
  contract version moved and the pinned reference-receipt digest is unchanged.

- **`contextsafe receipt diff --before A.json --after B.json`, the deterministic
  receipt delta (B-037), under a new `receipt` command group.** It reads two
  receipt documents through the same bounded loader `render` uses, parses each
  strictly against the published receipt shape -- every object closed, every
  enum the published one, the envelope pinned to `not_signed` and untrusted
  time, the mandated limitation set exact, the summary required to count the
  results, and the declared `payload_sha256` required to cover the payload --
  and rejects the pair unless both carry the same `case_id`, the same
  `rule_set_sha256`, the same receipt schema versions, the same concept and
  checkpoint sets, the same rule identifiers, and each rule bound the same way.
  A mismatch is exit 2 with one `incompatible_receipts` error object whose path
  and message name the field class that differed and never its value. The delta
  (`schemas/contextsafe-receipt-delta-v0.1.schema.json`, the twelfth published
  contract) lists per `rule_id` the status and reason in each receipt, a
  `changed` flag, an `evidence_sha256s_changed` flag, and a closed change code;
  counts of `regressed` (pass to fail, indeterminate, or blocked), `improved`
  (the mirror), `unchanged`, and `changed_other` (any other difference, so the
  counts partition the rules); the recomputed payload hash of each receipt; a
  `runner_version_changed` flag; and a pinned three-slug limitation set. It is
  envelope-free, ordered by `rule_id`, and carries no expected, observed, or
  evidence hash and no semantic value. Property tests pin that `diff(A, A)` is
  all-unchanged, that the delta is invariant under any reordering of either
  receipt's results, and that swapping the inputs mirrors it exactly. The
  command honours `--quiet`, `--no-color`, `--output`, and `--log-dir` (the
  event log's closed command vocabulary gains `receipt`), and its artifact and
  its rejection are in the three-run determinism matrix with a pinned digest.
  `render` stays where it is and may move under `receipt` later.

  What this does not claim: both receipts are unsigned and carry no trusted
  time, so `before` and `after` are the caller's labels and the delta proves
  nothing about which run came first -- the document says so in its own
  limitations. Payload-hash agreement is an internal-consistency check, not
  verification; no signature, approval, or evidence is verified (B-036). The
  contract is reference-only and ungoverned: no clinical, community,
  laboratory, legal, security, or accessibility review of it has happened.
  `src/contextsafe/receipt_delta.py` is a new safety module in the Makefile's
  95% coverage set. `MANDATED_LIMITATIONS` in `contextsafe.receipt` is now
  public so the parser can require the exact set rather than restate it; the
  reference receipt bytes and their pinned digest are unchanged.

## [0.1.0] - 2026-09-02

### Fixed

- **The documented quickstart could not run from an installed wheel.** The five
  synthetic reference inputs lived under `fixtures/reference/` at the repository
  root, which is not package data: `uv build` shipped `src/contextsafe` and its
  locale catalogs and nothing else, so `contextsafe --help` worked from a
  `pip install` and the README's own `evaluate --case fixtures/reference/case.json`
  failed closed with `input_io_error` from anywhere but a clone. No test could see
  it, because every test runs from the checkout, where an editable install finds
  a file in the tree whether or not the wheel carries it -- the defect class
  `docs/18-ASSURANCE-PROGRAM.md` exists to name. The fixtures are now package
  data under `src/contextsafe/fixtures/reference/` (a rename; the bytes are
  unchanged), and a tenth subcommand, `fixtures export`, copies them to
  `./fixtures/reference` -- byte-exact, leaving a byte-identical file alone,
  refusing one that differs, and refusing the whole export if the install is
  missing one -- so the documented commands run verbatim from a clone or from a
  wheel. The unobserved path is now observed: `tests/test_wheel_quickstart.py`
  builds the wheel, installs it into a fresh virtual environment, and runs the
  README's Quickstart block, parsed from the README itself, from a directory that
  is not the repository, then checks the wheel's receipt against one produced in
  process from the checkout. It fails rather than skips when it cannot do that,
  so a missing build tool is a red mark and not a green one.

- **A support bundle's field *names* were never checked, in the one module whose
  whole argument is that nothing in a bundle is checked -- it is constructed.**
  `contextsafe.safe_value.to_json` refuses any value that is not a `SafeValue`,
  and there is deliberately no constructor that accepts free text, so "a caller
  holding a string with a patient name in it has nowhere to put it". It had
  somewhere: the key. `to_json` sorted the keys and wrote them out untouched, at
  any depth, so `{"MRN 1 2 3 4 5 6 7 for Jordan Rivera": count(1)}` serialized
  cleanly. The belt-and-braces detector scan in `contextsafe.diagnostics` would
  not have caught it either, and `test_the_hostile_fixture_defeats_a_filter` is
  the standing proof of that: the fixture exists because no filter sees a name
  spelled with a Cyrillic homoglyph or a record number spaced past a digit
  pattern. Nothing in this repository builds a bundle key from data, so no
  bundle ever carried one -- this was a claim about the module that was true of
  the values and stated about the structure. A key is now a published field
  name: lower-case ASCII snake_case, letter-led, at most 64 characters, which a
  name, a path component and a spaced-out record number are all outside.

- **Six gates that could still report clean over something they did not
  examine.** Found by reading the gates this branch adds and hardens against the
  rule they were written to enforce, and every one of them is the program's own
  defect class committed by the program itself.

  `tools/secret-scan-full-history.sh` switched on object type with branches for
  `blob` and `commit` and no default. `git cat-file --batch-check` reports an
  object it cannot read as type `missing`, so the dominant object-database
  corruption mode fell through: never counted, never materialised, never an
  error, and the phase reported clean over it. `tree` and `tag` fell through the
  same way, so an annotated tag's message was never scanned despite the line
  above claiming every object in the database. All four types are materialised
  now, anything else is exit 2, and the enumeration is written to a file whose
  exit status is checked -- it was fed through process substitution, which
  neither `set -e` nor `pipefail` covers, so a `git cat-file` that died halfway
  through simply ended the loop.

  `tools/mutation_gate.py` decided a mutant died on any non-zero pytest exit.
  pytest returns 2, 3, 4 and 5 for an interrupted run, an internal error, a
  usage error and no tests collected as readily as it returns 1 for a failed
  assertion, and the output is captured and discarded. It was reachable without
  corrupting anything: `SCREENING_TESTS` is four hard-coded paths that nothing
  compared against the tree, so renaming one test module made every screening
  run exit 4, every mutant "killed", and the gate print `clean` over zero
  evidence. Exit 1 is the only kill now, 2 to 5 are a refusal that names the
  code, and a declared path that is not in the tree is a refusal before the
  loop.

  `tools/a11y_gate.py` had four rules that name a failure to run sitting outside
  `UNAVAILABLE_RULES` and answering 1: `--engines ''`, an engine that does not
  exist, a page declared and not audited, and a rule axe returned as undetermined
  that no check here decides. `--locale zz` was an unhandled traceback, which the
  shell also reads as 1 -- the same input class this branch fixed to exit 2 in
  the i18n gate, answered differently by two gates in one repository. And
  `run_axe` treated the harness's `ok` as proof it had looked, so a harness
  returning no pages produced no finding and recorded axe as executed; every
  subject handed over must come back now.

  `tools/scope_gate.py` caught `(OSError, SyntaxError)` around the import that
  reads `MARKER_ROOTS`, so a `ModuleNotFoundError`, a `NameError` or a
  `UnicodeDecodeError` escaped as a traceback and exit 1 -- "examined and found
  something" from a gate that never read the claim. A claimed root of `""` or
  `"."` names no path segment, so it was true of every file and no file could
  ever fall outside it; the gate refuses a comparison with no files on exactly
  that reasoning and now refuses this too. And its headline defence, the check
  that a Makefile recipe passes no argument overriding the configured scope,
  compared four string literals to whole tokens on the *first* line mentioning
  the tool: `mypy --strict src/`, `mypy --strict "src"`, `mypy --strict $(SRC)`,
  `pytest --cov src`, an argument on a continuation line and a comment line above
  the real one all went through clean. It is a rule about argument shape now,
  over every line that invokes the tool, with continuations joined and recipe
  comments dropped, and an argument the gate cannot resolve is exit 2 rather
  than a guess.

- **Five tests that asserted less than they appeared to.** Deleting phases 1 and
  3 from the secret scan -- so it no longer scanned reachable history or the
  working tree -- left every one of its tests green; the stand-in scanner records
  its argv now and one test pins three invocations and what each is pointed at.
  The unavailable-rule test restated the frozenset it was checking, so it could
  not have detected the four missing ids above; the rules are read from the
  gate's own syntax tree and each refusal is driven rather than restated. Three
  scope-gate refusal tests used a fixture with no Makefile and no
  `pyproject.toml` either, so each passed on whichever refusal came first --
  replacing `if not files:` with `if False:` left all of them green. The
  exception-printing test built its expected strings from the tuple the code
  prints and passed vacuously over an empty one. And the gate-coverage test
  globbed `tools/*.py` with a leading-underscore exclusion, so the one shell gate
  sat outside the contract exactly as it had before.

- **`make claims` read a correctly documented gate as an undocumented stage.**
  Its list of gates outside `make verify` was a literal set holding one name.
  `make mutants` moved out of `verify` and the literal did not follow. The
  exclusion is read from the sentence `CONTRIBUTING.md` already writes, the
  sentence's own count is checked against the table under it, and a row that
  names a target the Makefile does not have, or one that `verify` does run, is a
  finding.

### Added

- **The metadata a first tag needs, written before the tag rather than after
  it.** `.github/workflows/release.yml` fires on `vX.Y.Z`, re-runs `make verify`
  at the tagged commit, and refuses to build unless this file already carries a
  matching `## [X.Y.Z]` heading — so everything the release asserts has to be
  true in the commit the tag points at. This section is that heading.
  `CITATION.cff` carries the `version` and `date-released` it had deliberately
  withheld while nothing was released. `pyproject.toml` declares the
  `Apache-2.0` license expression and a `[project.urls]` table: `readme =
  "README.md"` copies the entire README into the distribution metadata, where
  every relative link in it — publication policy, threat model, the ADRs that
  bound what this tool claims — resolves against the repository and nowhere
  else, and a reader holding only the built artifact had no route back to it.
  What did not change is worth stating, because a version number is the kind of
  thing that gets read as more than it is: the wheel ships `src/contextsafe` and
  its locale catalogs, `fixtures/` and `schemas/` remain repository files rather
  than package data, so the quickstart runs from a clone and not from an
  installed wheel; the pipeline still builds an sdist and a wheel and has no
  publish or sign step; and a version number buys no distribution channel, no
  clinical approval, and no governed pack that the untagged tree did not have.

- **`make mutants` asks whether the suite would notice a change, not whether it
  ran the line.** The 95% branch floor over the safety modules is an execution
  measure; a suite that imports every module and asserts almost nothing reports
  the same number. `tools/mutation_gate.py` changes one operator or constant in
  a declared safety module and requires the tests to fail. Five operators, each
  a real defect shape in validation code: a comparison swapped with its
  neighbour, a boolean operator flipped, a `not` removed, a boolean constant
  flipped, a numeric bound moved by one. String constants are never mutated,
  because a mutated regular expression is a different program rather than a
  probe for a missing assertion. Mutants come only from lines the suite executes,
  measured with `coverage` in the same run, and the covered line count is
  printed so the denominator is visible. Two stages: a mutant the four fast
  screening modules do not kill meets the whole suite before being reported,
  because the claim is about the suite and 14 of the 35 mutants here survive
  screening while none survives the suite. The baseline is the suite for the
  same reason: while it was only the screening set, an unrelated failing test
  made every mutant's second stage return non-zero and this gate reported
  `clean` over 35 mutants it had proved nothing about, which is the defect class
  this program exists to close committed by the gate written to close it.
  Measured in isolation once fixed: 35 mutants over 143 covered lines in
  `contract_validation.py` and `identifiers.py`, every one killed. Not part of `make verify`, for runtime alone. It writes
  nothing into the working tree: the package is copied to a temporary directory,
  mutated there, and put ahead of the editable install with `PYTHONPATH`, and a
  test watches the file while the mutant runs and requires it to be unmutated
  the whole time -- a before-and-after comparison cannot tell a gate that never
  touched the tree from one that mutated it and put it back. See
  [ADR 0009](docs/adr/0009-mutation-evidence-over-declared-safety-modules.md).

### Changed

- **Nine boundaries the suite executed and did not check are now asserted.**
  `make mutants`, run honestly for the first time, reported nine survivors:
  `Grammar` and `Detector` being `frozen=True, slots=True`, the non-string and
  empty-string branch of `provenance_string`, a value of exactly `max_length` in
  `bounded_string`, the upper end of the surrogate block, the 256-byte
  relative-path bound, and the 253-byte host bound. Every one sat in a module at
  95% branch coverage. `tests/test_contracts.py` pins each.

- **`make secret-scan` exits 2 instead of 127 when gitleaks is not installed,
  and 2 instead of 1 for every other failure to scan.** This is a deliberate
  exit-code change on failure paths, called out here because a caller chaining
  on `$?` will see it. Three states, and they are three because two is how a
  gate lies: 0 examined and found nothing, 1 examined and found something, 2 did
  not examine. Before this, a damaged object database and a leaked credential
  were both exit 1, and "gitleaks is not installed" was 127. Now an absent
  scanner, an unpinned scanner, an object the scan enumerated and could not
  read, and zero blobs enumerated are all exit 2; a gitleaks finding stays 1.
  `security.yml` and `release.yml` both fail on any non-zero, so no workflow
  behaviour changes. See
  [ADR 0008](docs/adr/0008-one-exit-code-contract-for-every-gate.md).
- **`make a11y-full` exits 2 instead of 1 when the node harness is missing.**
  `engine-unavailable`, `engine-not-executed`, `engine-examined-nothing` and
  `check-examined-nothing` name a failure to run a check, not an accessibility
  defect, and they now exit 2 even when the same run also has real findings,
  because those findings were gathered without every requested engine and
  nothing in the list says so. A real accessibility defect still exits 1.
- **`make i18n` exits 2 instead of 1 when it examined no catalog.** The
  `no-catalogs` rule id is gone; the gate refuses instead, and a `--locale` with
  no published catalog is the same refusal rather than an unhandled traceback.
- **`tools/secret-scan-full-history.sh` has tests.** It had none: it is the one
  gate written in shell and the one whose dependency is not in `uv.lock`, so no
  state of it was ever exercised. `tests/test_gate_exit_contract.py` drives it
  with a stand-in gitleaks that answers `version` and returns a chosen code from
  `detect`, which gives all three states on a machine with no gitleaks
  installed, and asserts the three are three distinct codes. Those tests run
  inside `make verify`.
- One test now asserts the contract of every gate program at once, and derives
  the list it compares against from the tree, so a gate added later that sits
  outside the contract fails the suite rather than sitting outside it quietly.

### Added

- **`make scope` fails when a tree of Python exists that no analysis was ever
  pointed at.** Every other gate can now tell "I looked and found nothing" from
  "I could not look"; none of them could tell either from "nobody ever pointed
  me at that tree", which is exactly what `tools/` was for the marker scan and
  the coverage floor. `tools/scope_gate.py` scans no files. It reads the trees
  each analysis claims, from the configuration that makes the claim rather than
  a copy of it, and compares them against the tracked Python that exists: a file
  under no claimed root, a claimed root with nothing under it, and a declared
  exception that excuses nothing are each a finding. Narrowing `MARKER_ROOTS`
  and `[tool.mypy] files` back to what the previous commit carried produces ten
  findings and exit 1. It exits 2, never 0, when it cannot establish a claim:
  no tracked Python, no `git`, an unreadable or unparseable `pyproject.toml`, a
  missing key, a missing or unrecognised Makefile recipe, a `hygiene_gate.py`
  that will not import, or a command that overrides the configured scope. Two
  declared exceptions exist, both `tests/`, both printed on every run with the
  reason, so coverage declared away is as visible as coverage achieved. See
  [ADR 0007](docs/adr/0007-declared-analysis-scope.md).

### Changed

- **Strict typing covers `tools/`.** `make typecheck` was `mypy --strict src`,
  so the five gate programs that decide whether anything merges were never
  type-checked. Running it over them found seven errors, six of them
  `# type: ignore[arg-type]` comments on calls to `parse_bundle`, whose three
  parameters are declared `object`: suppressions that suppressed nothing, which
  is a claim about a problem that is not there. They are deleted.
  `i18n_gate.reference_document` now returns the `dict[str, JsonValue]` it
  actually returns, and the three functions that consume it take a covariant
  `Mapping`.
- The scope of strict typing and of the coverage floor moved into
  `pyproject.toml` as `[tool.mypy] files` and `[tool.coverage.run] source`.
  `make typecheck` passes no path and `make test` passes a bare `--cov`, because
  an argument on the command line beats the config and the claim would then live
  somewhere `make scope` is not reading. `.pre-commit-config.yaml` drops its
  `src` argument for the same reason, so the hook and the gate check the same
  trees.

### Added

- **`make claims` — a gate over the prose, because every other gate here checks
  the code and nothing checked the sentences about it.** `tools/claims_gate.py`
  re-derives nine claims from the repository and fails when a document and the
  repository disagree: the `verify` stage list against the `Makefile`, the ADR
  index against `docs/adr/`, the coverage floors against `make test`, the
  contract count and table against `schemas/`, the accessibility gate's default
  locales against the catalogs that ship, the README's status line against the
  iterations the README describes, a retired flag name that may not come back
  while the `Makefile` disagrees with it, a dated correction that has to travel
  with the text it corrects, and the rule that a standards row may not declare
  "N/A" for something `verify` gates. Every check fails in both directions: a
  wrong value is a finding, and so is a document that stopped stating the value,
  because a regex that quietly matches nothing is how a gate becomes decoration.
  Stdlib only, no network, no git history, so it costs `verify` nothing and runs
  in a shallow CI checkout. It prints what it cannot see on every run, the way
  the hygiene gate prints every exemption it honored.

### Fixed

- **The standards table declared Performance, Accessibility and
  Internationalization "N/A" on the grounds that no HTML ships, in a README that
  documents the HTML renderer eighty lines earlier.** `make verify` has run both
  `i18n` and `a11y` since 2026-08-19, and `docs/I18N.md` had already recorded the
  English-only declaration as superseded. Accessibility and Internationalization
  now say "Applies" and say precisely what the gates cover and what they do not:
  AA conformance is still not claimed, because B-044 needs a person and has not
  happened, and `es-US` is still an unreviewed machine translation. Performance
  stays N/A, on the reason that is actually true — no hosted route and no served
  surface — rather than on "no shipped HTML". `make claims` now refuses the
  contradiction rather than the wording.
- **Three different, all incomplete lists of what `make verify` runs.** The
  README quickstart omitted `a11y`, the README prose omitted `i18n` and `a11y`,
  and `CONTRIBUTING.md` omitted both and had no row for `sync`. There is now one
  enumeration per document and both are derived: the quickstart names the target
  list literally, `CONTRIBUTING.md`'s gate table has one row per stage, and the
  README prose that was the third list points at the table instead of repeating
  it.
- **The README described `make verify` as a "frozen sync" over "the frozen
  lockfile".** True until 2026-08-15, when `sync` moved to `uv sync --locked`;
  the `Makefile` and `CONTRIBUTING.md` have both explained since then that
  `--frozen` installs a drifted lock and still exits 0, so it cannot gate drift.
  The README was the one place still using the word its neighbours warn against.
- **The ADR index listed four of the seven ADRs on disk.** 0004, 0005 and 0006
  were never added.
- **"Last reviewed: 2026-08-15" sat under a table on a file edited repeatedly
  after that date.** Removed rather than corrected: nothing re-derives a review
  date, the CI checkout is shallow so `git log` cannot either, and a corrected
  literal restarts the same clock. The instruction to re-review remains.
- **The README's status line stopped at iteration 4** while the README described
  iteration 5 and the B-046 operator surface.
- **`docs/PUBLICATION-READINESS.md` was being read on the public repository
  while stating "Current visibility: PRIVATE" and inviting a reader to recover a
  pricing document with a command that does not work.** None of the commit names
  that document cites resolve in the published history, and
  `docs/11-GTM-BUSINESS-MODEL.md` is in none of its refs. The audit's findings
  are untouched and nothing is retracted; a dated note now records what a fresh
  clone shows, and `make claims` keeps that note with the text it corrects.
- `tools/a11y_gate.py`'s default locale list is now the named `DEFAULT_LOCALES`
  rather than a literal inside `main`, and `make claims` fails when it stops
  matching the catalogs in `src/contextsafe/locales/`. `tools/i18n_gate.py`
  discovers its locales; this one does not, so before this a third catalog would
  have been translated, gated for parity, rendered to a reader, and never
  audited.

### Changed

- **`collector_id`, `system_id` and `system_version` have narrower published
  grammars, and this is a breaking contract change.** They were
  `^[A-Za-z0-9][A-Za-z0-9:/_.-]{0,127}$` and `^[A-Z][A-Z0-9-]{2,63}$`, which
  match a social security number, a date of birth and the string
  `realpatientcanary` without complaint. Each field now publishes a base
  pattern plus named `not` clauses in
  `schemas/contextsafe-evidence-v1.schema.json`, and
  `contextsafe.contract_validation` carries the identical strings, so a test
  compares them rather than a comment claiming they agree. In practice:
  `system_version` must be a dotted number, so a calendar version is written
  `2026.8.27` rather than `2026-08-27`, and the fixture value `fixture-1.0`
  became `1.0.0`; a `collector_id` expressed as a URI is no longer accepted,
  since neither a colon nor a slash is in the alphabet any more; and no field
  may carry a run of four or more digits or a separated segment that does not
  begin with a letter. There is no tagged release, no stored record, and the
  only caller of this path has no CLI route, so nothing existing is affected and
  the schema is narrowed in place rather than versioned. See
  [ADR 0006](docs/adr/0006-provenance-token-grammar-and-boundary-scan.md).
- The boundary detectors live in `contextsafe.identifiers`, a leaf module, so
  the evidence layer can reach one definition of them without importing
  `preflight`, which imports the evidence layer. `preflight.identifier_hits` is
  re-exported and behaves identically: it is the documented extension point and
  where `diagnostics` already imports it from. The 709 tests that passed before
  the move passed unchanged after it, before any behavior was added.

- **The gate implementations are now inside the trees they scan and inside the
  coverage floor.** `tools/` held four gate programs and one shell script that
  between them decide whether anything merges, and it was the one tree exempt
  from the marker rule those programs enforce; `[tool.coverage.run]` had
  `source = ["contextsafe"]`, so the 90% branch floor never measured them
  either. Measured on 2026-08-27 before the change, `tools/` sat at 91% branch
  coverage overall with `tools/publication_sweep.py` at 77%, `main`,
  `history_sources` and `load_denylist` almost entirely unexercised, which is
  why the `SweepUnavailable` branch added the same week shipped untested.
  `MARKER_ROOTS` is now `("src", "tests", "tools")` and the marker scan reads
  55 files where it read 47. Because a rule has to be able to name what it
  bans, `hygiene: allow` on the same line as a marker, **followed by a reason**,
  exempts it; an allow with no reason after it is a new `unreasoned-exemption`
  finding, and every honored exemption is printed on every run, pass or fail,
  with the count in the clean line. Three exist, all in
  `tools/hygiene_gate.py`, and a test pins that so a fourth anywhere else has to
  be argued for. See
  [ADR 0005](docs/adr/0005-hygiene-marker-exemptions.md) and
  [docs/18-ASSURANCE-PROGRAM.md](docs/18-ASSURANCE-PROGRAM.md).
- **The publication sweep reports the sources it did not read.** An oversized,
  non-UTF-8, or non-regular tracked file was a bare `continue`, and the clean
  line counted the files the sweep managed to read, which is the one number
  that cannot reveal a file it failed to read. Demonstrated on a scratch
  repository holding one readable file and one binary file, the sweep printed
  `clean over 1 source(s)` and exited 0; the binary file would have been
  published without anything having looked at it. Each of those is now an
  `unexaminable-source` finding, in tracked mode and in `--history` mode, and
  the clean line prints sources read over sources listed. The failure hint says
  the line-marking exemption does not apply to an unexaminable source, because
  there is no readable line to put it on. Measured on 2026-08-27: 117 tracked
  paths, all read, and 2006 blobs in the object database, none over the bound
  and none non-UTF-8, so this turns no green run red today. An object git
  enumerates and then refuses to output stays exit 2, because there is nothing
  to name.

- **`cleanup --remove --confirm` now exits 2 instead of 0 when a directory it
  set out to remove could not be removed.** This is a deliberate exit-code
  change on a failure path, called out here because a caller chaining on `&&`
  or checking `$?` will see it: work that used to run after a cleanup that had
  silently not happened will now correctly not run. The success path, the
  documented retain path, and the emitted JSON on success are all unchanged,
  and no exit code moves in the other direction. See Fixed, below.
- `make hygiene` is `tools/hygiene_gate.py`, and it can now fail. The target was
  two shell lines — `! rg -n '(TODO|FIXME|HACK)' src tests` and
  `! find . -maxdepth 2 ... | grep .` — and neither could report anything but
  success on a machine without the tool it called. `rg` exits 1 when it matches
  nothing and 2 when it cannot run at all, including when it is not installed,
  and the leading `!` maps both onto a pass; ripgrep is not in `uv.lock`, no CI
  step installs it, and a clean clone does not carry it, so the gate that is
  supposed to keep markers out of `src` and `tests` was passing over zero bytes
  anywhere it was absent. The `find` line has the same defect one step removed:
  `!` negates the status of `grep`, the last stage of the pipe, so a `find` that
  never ran produced no output, `grep` exited 1 on the empty input, and the
  negation called that clean. Measured before the change,
  `env PATH=/var/empty make hygiene` exited 0 with `rg: command not found` and
  `find: command not found` on stderr. The replacement is stdlib Python, like
  the publication sweep and the i18n gate, so `verify` still needs nothing a
  clean clone lacks, and it separates the three states the shell version
  conflated: exit 0 with a count of what it read, exit 1 on a finding, exit 2
  when it could not examine anything — no git, no repository, or no tracked file
  under `src`/`tests`. Both checks read tracked files now, so an ignored
  directory is never searched and an untracked local config cannot trip the
  config check; CI, where everything is tracked, was always the authoritative
  run. `tests/test_hygiene_gate.py` watches every state, including a planted
  marker for each of the three words in each scanned tree and a `git` removed
  from `PATH`. Nothing had slipped through in the meantime: the tree carried no
  marker in `src` or `tests` when the gate was replaced.
- The publication sweep refuses to report clean over nothing. It printed
  `clean over tracked files` whatever the file list contained, including an
  empty one, which is the same false green in a different shape: the sweep now
  counts its sources, prints the count with the clean line, and exits 2 rather
  than 0 when it read none. In `--history` mode, an object it enumerated and
  then could not read was `except CalledProcessError: continue` — a blob nobody
  looked at, inside a run that would still say clean. That is now exit 2 with
  the object id.
- The full-history secret scan stops on an object it cannot read. Phase 2 wrote
  every blob and commit out with `git cat-file ... || true`, then counted the
  object as materialized regardless, so a damaged or unreadable object was
  scanned by nobody and reported by nothing. The script already refused to
  report success after enumerating zero blobs; it now refuses to report success
  after failing to read one.
- `CONTRIBUTING.md` documents the environment as `uv sync --locked`. The
  Makefile and `ci.yml` already used `--locked` and explained why; the setup
  instructions still told contributors to run `--frozen`, which installs a
  drifted lock and exits 0.
- The README's Standards Conformance table declares all fifteen standards.
  Performance, AI Development Measurement, Incident Response, and Data
  Governance had no row, and the state column was headed "Status".
- The `accessibility` CI job installs with `uv sync --locked` like every other
  job. It was the last `--frozen` left in the repository, and a job whose whole
  purpose is refusing to pass on an unverified input should not itself install a
  lockfile it declined to check.


### Fixed

- **A PHI canary in operator-supplied provenance reached `contextsafe.sqlite`,
  inside a record whose own field said the boundary check passed.** Every byte
  of a caller's evidence *source* goes through the canary and direct-identifier
  scan before acceptance. The three provenance fields on the record that scan
  produces went through nothing of the kind: `parse_evidence_metadata` checked
  token shape and stopped. Measured against 28ef915, end to end through
  `store_internal_synthetic_evidence`, the only caller: `stored collector_id:
  realpatientcanary` alongside `stored boundary_check: passed`, with the canary
  bytes present in the SQLite index and the value hashed into the evidence id.
  `parse_evidence_metadata` now scans each token with
  `identifiers.provenance_hits` after the grammar accepts it, rejecting
  `phi_canary_detected` or `direct_identifier_detected` at the field's own path
  and never echoing the value. The obvious version of this fix was attempted in
  PR #38 and closed: run the fields through `preflight._reject_unsafe_string`
  and five values the published schema declares valid start failing, including
  `SYS-MEDICAL-RECORD-SYSTEM`, which is an ordinary name for a system. The
  grammar is what makes the identifier unwritable; the scan is only for what a
  grammar cannot see. One detector, `record-locator`, does not apply to a
  bounded provenance token, is named rather than positional, and its residual is
  pinned in `tests/test_privacy_canaries.py` next to the three blind spots that
  suite already records. The free-text scan is unchanged. Closes #35.

- `remove_cleanup` reported a failed directory removal as a retained entry.
  The `rmdir` call was wrapped in a bare `except OSError`, so a permission
  bit, a read-only mount, or a device error was counted into `retained_count`
  and the command exited 0 with the directories still on disk, while the file
  branch immediately below raised `cleanup_io_error` on exactly the same
  condition. The two halves now agree. The directory branch absorbs one errno
  set — `ENOTEMPTY`/`EEXIST`, the "still holding something the enumerator
  refused to touch" case that `docs/13-BACKLOG.md` describes and that the
  deepest-first walk makes the only legitimate one — and raises
  `cleanup_io_error` on everything else. A retained count now reports a choice
  and never a failure. Two tests cover it, both watched to fail first: one
  drives a real read-only parent rather than a patched `rmdir`, and one pins
  the CLI exit code at 2 so the change recorded under Changed cannot silently
  revert.

### Added

- Opt-in gate threshold for `evaluate`: `--fail-on finding`. Issue #22 observed
  that a receipt recording a semantic mismatch still exits 0, which is correct
  for a receipt generator but leaves a pipeline nothing to block on. The
  default behaviour is unchanged and is now pinned by test rather than left as
  an accident; with `--fail-on finding`, a valid receipt containing at least
  one `fail` outcome exits `EXIT_FINDING` (1) after its artifact is fully
  emitted — stdout, `--output`, and stderr bytes are identical either way, and
  the new code is documented in `main()` beside the others. Whether findings
  should block remains the caller's decision; the flag asserts no threshold of
  its own.
- B-043 slice: `tools/a11y_gate.py`, `make a11y` (in `make verify`), and
  `make a11y-full` plus an `accessibility` CI job that adds axe-core in a
  headless DOM. The whole design is a refusal to report a pass it did not earn.
  The gate renders its own subjects from the bundled reference fixture and
  checks each page against the *receipt document* — payload hash, case id, every
  mandated limitation — before auditing it, so an error page, an empty file, or
  a page rendered from a different receipt is `wrong-subject` and is not counted
  as audited. An empty page set is `no-pages`; a run that requested no engine at
  all is `no-engines`; a check that examined nothing is
  `check-examined-nothing`; a requested engine that cannot run is
  `engine-unavailable`, never a skip; an engine that executed no rules against a
  page is `engine-examined-nothing`. Rules axe cannot decide in a DOM with no
  layout — `color-contrast`, `landmark-one-main`, `page-has-heading-one` — are
  listed by name, never counted as passes, and each must map to a built-in check
  that does decide it, so "could not determine" cannot quietly become "fine".
  Built-in checks cover structural validity (landmarks, heading order, duplicate
  ids, table captions and header scope, resolvable `aria-labelledby` and in-page
  links, no script, no external resource), WCAG 2.2 contrast computed from the
  stylesheet for screen and print rules alike, colour-only status encoding, and
  a print block that does not hide a mandated disclosure. Every failure mode has
  a negative control in `tests/test_a11y_gate.py` that was watched to fail.
  Dependabot now covers the npm harness, because a gate running a stale ruleset
  reports yesterday's answer.
- pa11y is deliberately absent rather than skipped: HTML_CodeSniffer, the engine
  pa11y drives, loads its rulesets by injecting script tags and does not
  complete in a headless DOM without a browser. Wiring it in as an optional
  engine that silently does nothing would be worse than not having it, and the
  rules it would add over axe — contrast, colour-only encoding, print — are the
  three the built-in checks compute.

- B-046 slice: `contextsafe diagnostics`, `contextsafe cleanup`,
  `contextsafe support-bundle`, and an opt-in local event log via `--log-dir`.
  The support bundle is redacted **by construction**, not by filter. Every
  field is a typed `SafeValue` (`src/contextsafe/safe_value.py`): a count, a
  flag, a member of a closed set declared at the call site, a SHA-256 of text
  that does not itself survive, a dotted numeric version, or the *shape* of a
  path — depth, published extension, and a digest of the final component, with
  no directory name and no filename kept. There is no constructor that accepts
  free text and no escape hatch, so a caller holding a string with a patient
  name in it has nowhere to put it, and the serializer raises on anything that
  is not a `SafeValue`. The assembled bundle is then scanned with the
  repository's boundary detectors and refuses to be emitted if anything fires;
  that pass is belt and braces and is documented as such, because a detector
  firing would mean the constructive layer is broken rather than that the
  redaction worked.
- The hostile fixture behind that design is in `tests/test_diagnostics.py`: a
  workspace path carrying a synthetic patient name in a *directory* component,
  a name spelled with a Cyrillic homoglyph, and a record number written with
  spaces between its digits. One test runs the repository's own detectors over
  those strings and asserts they come back clean, so "a filter would have
  shipped these" is checked rather than claimed; a second control replaced the
  path constructor with a regex scrubber and watched the suite fail. Writing
  the property test found a real weakness, now fixed: the version constructor
  accepted `exports-Jordan-Rivera-1987` as a version string.
- The cleanup enumerator classifies every entry under a workspace — index,
  content-addressed object, staging leftover, directory, and anything it cannot
  classify — and reports shapes, counts, and sizes rather than names. Removal
  needs `--remove --confirm`, never follows a symbolic link, never leaves the
  workspace, and never deletes an entry it could not classify; a directory
  still holding a retained entry is retained with it.
- The local event log is off unless `--log-dir` is given and is never enabled
  from the environment, because output that varies with the environment is what
  `tests/test_determinism.py` exists to prevent. A record is a closed
  vocabulary — command, outcome, error code — with no message field, so there is
  nowhere for an exception string, a path, or a token to land. It carries no
  clock reading: the runner reads no clock anywhere else, so records carry a
  per-file sequence number instead, which is a real limitation for anyone
  correlating them with external events. Nothing imports `logging`, so the
  structural log canary still holds, the log is owner-only, it refuses a
  symbolic link, it stops at a published size limit, and a logging failure
  never changes the exit code of the command it logged.
- `safe_value.py`, `diagnostics.py`, and `eventlog.py` are now in the
  `SAFETY_MODULES` coverage gate, which requires 95% rather than the 90%
  applied to the package as a whole.

### Fixed

- `make verify` could fail at its own audit gate: pip 26.1.2, seeded into the
  environment through the lockfile, matched PYSEC-2026-3721. The lock now
  carries pip 26.2.1 and `make audit` is green again.
- `a11y_gate.py --engines ''` rendered both real pages, ran no check at all, and
  printed `a11y-gate: clean` with exit 0 — the gate committing, on its own
  command line, the exact defect it exists to catch. The report body was honest
  throughout (`engines executed: none`), which is the shape this keeps taking:
  the absence is computed correctly and then dropped by the line a human reads
  and the exit code a pipeline reads. An empty engine set is now `no-engines`.
- The machine-translation notice carried `role="note"`, which overrides the
  implicit `complementary` landmark of `<aside>` and put the notice outside
  every landmark on the page — making the one element addressed to readers who
  cannot rely on the translation skippable by landmark navigation. axe's
  `region` rule caught it on the first run of the new gate. The notice is now
  named by its own heading through `aria-labelledby`.

- B-034 slice: `contextsafe render` and `src/contextsafe/html_receipt.py`, the
  script-free semantic HTML rendering of a receipt document. The package had no
  human-facing surface at all before this — every command emitted canonical
  JSON — which is why B-041 was blocked and why the old i18n declaration could
  truthfully say "N/A". The page is one self-contained file with no script, no
  event-handler attribute, no external stylesheet, font, or image, and no
  network reference; it is deterministic in the receipt document and the
  catalog, reads no clock and no environment, and a three-environment
  subprocess test pins byte equality across time zone, locale, and hash seed.
  Every status carries its word and a distinct symbol rather than a colour, so
  nothing is lost in black-and-white print or to any colour vision; `<main>`
  carries `data-cs-payload-sha256` and `data-cs-case-id` so a checker can prove
  which receipt it examined rather than reporting zero findings against
  whatever page it was handed. Unpublished enum values, non-boolean scope
  entries, and any envelope claiming a signature or trusted time are refused
  rather than printed. B-034 is not closed: this is the receipt surface only,
  the print stylesheet has had no B-038 evidence-minimization pass, and
  independent accessibility review remains B-043 and B-044.
- B-041 slice: message catalogs, and the rule that an unreviewed translation
  says so. Every user-facing string now lives in `src/contextsafe/locales/`,
  and `src/contextsafe/i18n.py` hands back a `Message` carrying its text *and*
  the provenance of its wording — never a bare string — so "we forgot to check
  whether this was reviewed" is not a reachable state. A `Surface` declares
  what it claims about the text it shows, and a surface claiming
  `human_reviewed` refuses an unreviewed string by construction. B-042, the
  professional translation and independent community review, has not happened,
  so the shipped `es-US` catalog is marked machine-translated on every entry
  and no surface claims review: the rendered page carries the notice in Spanish
  *and* in English, marks each string with `data-cs-review`, and renders every
  mandated safety disclosure next to its `en-US` original, because a machine
  translation of "not an approved clinical oracle" is exactly the sentence a
  reader must not be left alone with. Limitation translations are matched by
  the source sentence rather than by position, so rewording a mandated
  limitation drops its translation and says so instead of keeping a stale one.
  Hash-covered artifacts stay in one fixed language and a test pins that no
  catalog string reaches one; CLI help is externalized but rendered only in the
  source locale, because `--help` and usage errors are part of the byte surface
  `tests/test_determinism.py` guards. `make i18n` (`tools/i18n_gate.py`, in
  `make verify`) fails on catalog-key drift, placeholder drift, empty or
  mismarked strings, a review record nobody signed, an unreviewed string
  reaching a claiming surface, a missing or spurious disclosure, and any
  visible text on the pseudolocalized page that no catalog message accounts
  for — which is how "externalize every string" is checked rather than
  asserted. It also fails, rather than passing, when it has examined no catalog
  at all. Every rule has a negative control in `tests/test_i18n.py` that was
  watched to fail. B-041 is not closed while its only translation is
  unreviewed; `docs/I18N.md` now records "Partial" and supersedes the
  2026-07-16 "N/A" declaration.

- Full-history secret scan (SEC-19): `tools/secret-scan-full-history.sh`, run by
  `make secret-scan`, by the `security` workflow on every push, pull request,
  and the weekly schedule, and by the release workflow before anything is built
  at a tag. Both previous secret scans were diff-scoped — the pre-commit hook
  sees staged changes, the CI job saw a pull request's commit range — so neither
  could ever support a claim about the history as a whole. The new gate has
  three phases: every reachable commit on every ref; every object in the object
  database, which adds unreachable blobs and every commit message, neither of
  which phase 1 reads; and the working tree including untracked files. gitleaks
  is installed from one named release verified against a recorded SHA-256, by a
  local composite action rather than a wrapper action that would resolve the
  scanning binary at run time — pinning the action does not pin the ruleset. The
  script also refuses to run against an unpinned gitleaks version. Scanner
  choice is recorded in the script's header: TruffleHog's Lob detector has
  matched ordinary `test_`-prefixed pytest function names and then promoted them
  to "verified" by POSTing them to a third party, and this repository contains
  five distinct test names of exactly that shape.
- Publication sweep (`tools/publication_sweep.py`, `make publication-sweep`, and
  part of `make verify`): the readiness audit's employer / private-repo /
  internal-host / personal-path sweep, made executable. It was run by hand,
  which made it true of one commit rather than of the repository. The sweep
  fails on an absolute path out of somebody's machine, a hostname a public
  reader cannot resolve or should not probe, a pointer to a repository under
  this owner that is not on the published allowlist, and a relative link that
  resolves outside the repository — resolved against the containing file's
  directory, so the pull-request template's parent-relative link to the
  definition of done is correctly not a finding, while the README's
  parent-relative pointer at a sibling standards directory was.
  Reserved names (`.invalid`, `.example`, `.test`, `localhost`) are never
  flagged, because this repository uses `*.contextsafe.invalid` on purpose.
  Terms that must not appear in the repository *or in the scanner*, a former
  employer's name being the obvious one, come from a denylist file outside
  version control (`--denylist`, `PUBLICATION_SWEEP_DENYLIST`) and are reported
  by rule, file, and line only — never by content. The one exemption mechanism
  is a `publication-sweep: allow` marker on the offending line, so every
  exemption is greppable. `--history` extends the scan to every blob in the
  object database. 29 tests cover each rule in both directions, plus one that
  asserts the repository itself sweeps clean. It also runs as its own job in
  the security workflow, which carries no `paths-ignore`: `ci.yml` skips
  docs-only changes by design, and the one gate whose job is documentation
  hygiene must not be blind to documentation changes.
- Dependency-update automation (SEC-14): `.github/dependabot.yml` covering the
  two places this repository pins — the `uv` lock and the SHA-pinned GitHub
  Actions — weekly, with a seven-day cooldown on both ecosystems (SEC-26 asks for
  72 hours) and Python updates grouped into one pull request. The repository
  previously had neither a `dependabot.yml` nor a `renovate.json`, so no advisory
  against a locked dependency could open a pull request, nothing kept the action
  pins current, and OpenSSF Scorecard's `Dependency-Update-Tool` check scored 0
  by construction.
- B-039 slice: `tests/test_privacy_canaries.py`, the near-miss, log, and
  crash-output half of the canary suite RG-12 gates on. It pins the privacy
  boundary in both directions — approved codes that resemble identifiers must
  not be false positives, values one character from acceptable must fail closed
  with a named code — and records three identifier-shaped values the pattern
  scan does not catch (a date outside its 19xx/20xx window, a dotted date, a
  seven-digit local number) as blind spots for the independent security review
  rather than as accepted behavior; the synthetic-namespace grammar is what
  bounds them. It adds a structural log canary (no module imports `logging` or
  prints, and no accepted or rejected command emits a record), a crash canary
  (an unexpected failure after the boundary read carries neither evidence
  content nor the caller's source path, and a CLI rejection prints a structured
  error rather than a traceback), an index canary (raw bytes stay in the
  content-addressed object; the queryable SQLite index carries hashes, tokens,
  and provenance only), and a matrix property that no rejection echoes the
  value that triggered it. No detector, schema, or runtime behavior changes.
  B-039 is not closed: pattern tuning is a security-owned decision whose
  independent review has not happened, FHIR/HL7/LIS sources do not exist
  (B-023–B-025), and the diagnostics, support bundle, and local logs RG-12 also
  covers are B-046.
- B-021 slice: `tests/test_determinism.py`, the three-run reproducibility
  evidence R-10 and RG-15 ask for and the process half of status-algebra
  invariant 10. Each shipped command runs three times in fresh interpreters
  under different time zones, locales, hash seeds, UTF-8 modes, working
  directories, and input directories, and must produce byte-identical exit
  codes, stdout, stderr, and `--output` artifacts. Every artifact must be one
  canonical UTF-8 JSON line with one terminal newline and no carriage return,
  the reference `evaluate` document has a pinned SHA-256, no absolute input
  path or environment value may reach an artifact, a caller-declared
  `claimed_generated_at` must move the envelope without moving
  `payload_sha256`, and a fail-closed rejection must emit the same stderr bytes
  and error code every run. A CI matrix (`ubuntu-24.04`, `macos-15`,
  `windows-2025`) reproduces the pinned digest, and a monkeypatched test pins
  the documented fail-closed rejection on platforms without descriptor-relative
  no-follow open — Windows among them, where `pack validate`, `plan validate`,
  and `evidence preflight` therefore cannot run. This is byte-reproducibility
  evidence only: packaging and fresh-install evidence remain B-045, and B-021
  stays open pending normalization (B-019/B-026) and signing (B-035).
- `docs/PUBLICATION-READINESS.md`: a gate-by-gate audit of whether this
  repository could ever be made public, with evidence. Gate 1 is a dual-use and
  misuse assessment specific to this project — a tool that reports where
  transgender and nonbinary identity data is lost also reports where it is
  retained — including what the threat model already covers, four things it
  does not, and what must be decided before B-010. The verdict is *technically
  ready*, not *ready to publish*. No tag, release, visibility change, or
  history rewrite accompanies it.
- `docs/17-PUBLICATION-POLICY.md`: the publication policy the readiness audit
  said had to exist, written as a decision document rather than an adopted
  control. It classifies everything this project could publish as method,
  locator, or instance; states what may be said about a governed pack and what
  never may (no receipt, customer, vendor, version, or small-population
  aggregate); names an approval owner with a community co-chair veto and an
  interim rule that blocks locator material entirely while the maintainer is the
  only available approver; says what happens to already-published material when
  a pack lands; and lists the conditions under which the project stops
  publishing. Its five open decisions carry options and a recommendation —
  split publication, "publish the judgment, withhold the locator" — and none is
  in force until the maintainer records a date.
- Publication as a first-class part of the threat model and governance, closing
  the four dual-use gaps the readiness audit named. `docs/06` states the
  inversion in section 1 rather than deriving it later, adds TB-10 (publication)
  with its irreversibility called out, adds the reader of public project
  material, the party using lawful process, and the maintainer publishing under
  time pressure as actors, and adds T-16 through T-18, two assets, and three
  residual risks including that withholding locators buys friction rather than
  secrecy. `docs/07` gains publication decision rights, a RACI row, HAZ-09 and
  HAZ-10, a launch gate, and section 14. `docs/14` splits R-23, which was titled
  "weaken demand **or increase harm**" and mitigated only demand: R-23 is now
  demand alone, R-25 is the harm half at score 15, and R-26 is compelled
  disclosure. `docs/13` gates B-009 on an adopted policy, `docs/15` adds two
  RG-19 checks, and the README carries the inversion above the quickstart.
- CLI: `contextsafe evidence preflight` now accepts `--output`, matching `pack
  validate`, `plan validate`, and `evaluate`. Previously the only way to obtain
  the boundary-check result was stdout, so combining `--quiet` with `evidence
  preflight` silently discarded the command's only output and left nothing but
  the exit code. `--output` writes the same non-sensitive result document
  (`boundary_check_status`, hashes, declared scope — `PreflightResult` never
  carries evidence content) that would otherwise print; it does not change what
  the command reads, copies, indexes, or logs.
- B-033 slice: `schemas/contextsafe-receipt-v0.1.schema.json`, the published
  contract for the receipt document and its deterministic payload — the pre-1.0
  shape of the receipt schema required by `docs/04-ARCHITECTURE.md` section 8.
  The contract closes every object (`additionalProperties: false`), pins the
  unsigned envelope constants so a signing layer cannot relabel these documents
  in place, keeps the payload claim-minimal by rejecting timestamp, signature,
  reviewer, run-environment, and semantic-value fields, pins the mandated
  limitation set as a closed ordered list so a stripped, reworded, reordered, or
  padded disclosure fails validation (F-030) and the payload carries no
  unbounded free-text channel, and publishes closed status, reason, checkpoint,
  and concept enums. Tests enforce schema/runtime agreement on the reference
  document, the `evaluate --output` artifact, and every Hypothesis-generated
  bundle; a companion test asserts that every file in `schemas/` is a valid,
  self-consistent Draft 2020-12 contract. Outcome reasons are now the typed
  `OutcomeReason` enum, so an unpublished reason string cannot reach a receipt
  without a schema change. Receipt bytes are unchanged.
- B-027 slice: Hypothesis-based property tests seeding the documented property
  layer (`docs/09-TEST-AND-EVALUATION.md` section 2) for the machine-checkable
  status-algebra invariants — no pass without exactly one affirmative evidence
  match, not-applicable only from a predeclared rule, fail-closed cross-concept
  rejection, order-independent byte-identical receipts, and value-minimized
  receipts that never echo generated semantic values. Invariants needing pack
  lifecycle, review signatures, HTML, or signature verification remain untested
  because those components do not exist yet.
- B-020 slice: every CLI command accepts `--quiet` (suppress the stdout success
  payload; exit codes, `--output` files, and stderr JSON errors unchanged) and
  `--no-color` (an explicit pin of the always-plain contract — output never
  contains ANSI escape sequences), and exit codes are documented and stable:
  `0` success, `2` fail-closed contract rejection, `64` command-line usage
  error (previously argparse's default `2`, which collided with contract
  rejections).

- V1 planning corpus (`docs/00`–`16`): PRD, service design, architecture, data and
  evidence model, security/privacy threat model, governance, test strategy,
  operations, roadmap, backlog, risk register, and release checklist.
- Iteration 1: strict versioned case and observation-set schemas; separately typed
  GI, RSG, SPCU, name-to-use, and pronoun values; fail-closed cross-concept
  rejection; pure exact-match evaluator (missing/ambiguous evidence is
  indeterminate); deterministic value-minimized JSON receipts; offline `validate`
  and `evaluate` CLI commands with a synthetic reference fixture.
- Iteration 2: strict pack envelope, deterministic unsigned compiler with semantic
  component hashes and lifecycle/withdrawal checks; strict engagement and
  execution-plan contracts with fail-closed non-production attestations, host
  allowlisting, and hash pinning.
- Iteration 3: canonical JSON evidence boundary envelope with field allowlist,
  namespace pins, PHI canaries, and direct-identifier checks; read-only
  `evidence preflight`; recoverable two-pass persistence into a SHA-256 object
  store with an update/delete-protected SQLite index.
- Iteration 4 (B-021 slice): receipt payload/envelope separation. `contextsafe
  evaluate` now emits a receipt document instead of the bare iteration-1
  receipt — the byte-identical deterministic payload plus `payload_sha256`
  over the payload only, and an untrusted envelope with caller-declared
  `claimed_generated_at` (optional canonical whole-second UTC, via
  `--claimed-generated-at`), `signature_status: not_signed`, and
  `trusted_time: false`. Timestamps and signatures stay outside the
  deterministic payload (P0-14); no signing or trusted-time path exists.
- Standards-conformance baseline (2026-07-16 sweep): LICENSE (Apache-2.0),
  SECURITY.md, CONTRIBUTING.md, CITATION.cff, CHANGELOG, pre-commit config,
  Semgrep/gitleaks/pip-audit security workflow, tag-triggered release workflow,
  ADR log seed (existing ADRs relocated from `docs/decisions/` to `docs/adr/`),
  docs/I18N.md declaration, and a README Standards Conformance table.

### Fixed

- Schema identity: five of the eleven published contracts claimed `$id` under
  `contextsafe.dev`, a domain nobody had registered. On a public repository an
  unregistered domain in a contract identity is squattable — whoever buys the
  name can serve documents at URIs this project publishes as canonical. All
  eleven now use `https://contextsafe.invalid/schemas/<file>`. `.invalid` is
  reserved by RFC 2606 and can never be delegated, so the identifiers are
  stable and unique without depending on anyone owning anything, and nothing
  here is dereferenced in any case: no code fetches a schema, and every `$ref`
  is local. The choice and the alternative (register a domain and serve them)
  are written down in the new `schemas/README.md`, and a test pins every `$id`
  to the reserved domain so a resolvable identity cannot come back by accident.
- `CITATION.cff` no longer advertises a release that was never cut. It carried
  `date-released: 2026-07-17` while `git tag -l` is empty, `gh release list`
  returns nothing, and the repository's `latestRelease` is null. CFF treats
  `version` and `date-released` as optional; both return when a release is
  actually tagged.
- `SECURITY.md` no longer publishes a personal email address as the disclosure
  channel. It did so for a reason the file stated — private vulnerability
  reporting is not available on a private repository — and that reason stops
  applying the moment this repository is public. Reports now go through GitHub
  private vulnerability reporting, with a details-free public issue as the
  fallback if that form is unavailable. *The setting has to be enabled in
  repository settings for the link to work; until it is, the form 404s.*
- Three README claims that had drifted from what the repository does. `ci.yml`
  does not run on "every push/PR": it skips docs-only changes by design, and
  the row now says so and notes that the security workflow has no such skip.
  The documentation row enumerated a planning corpus `docs/00`–`16` that no
  longer matches the files on disk. The release row now records that no tag and
  no release exist, which is the same fact the citation fix above turns on. The
  "last reviewed" date moved to the date of this review.
- The Semgrep SAST gate (SEC-07) had been red on `main` for every one of its
  fourteen runs since 2026-07-17, on four blocking findings against the two
  evidence-index header PRAGMAs in
  `evidence_store.py`. SQLite does not accept bound parameters
  in a PRAGMA, so the statements are now rendered once at module scope from their
  integer constants with the `:d` conversion — which can emit only digits and an
  optional sign — and `_publish_new_database` executes those constants instead of
  building a string at the call site. A new test pins the exact rendered text of
  both statements, requires each to match `PRAGMA [a-z_]+ = -?\d+`, and asserts
  that SQLite rejects the parameterized form. No waiver, `.semgrepignore`, or
  `# nosemgrep` was added; the registry auto config now reports 0 findings over
  72 targets. Store bytes and the on-disk index header are unchanged.
- Command output is written as UTF-8 bytes instead of through a text stream.
  Text-mode writes translate the terminal newline into the platform line
  separator and encode with the platform's preferred encoding, so the same
  receipt would have left a POSIX host and a Windows host with different bytes
  and different file digests — the cross-platform nondeterminism R-10 names and
  RG-15 gates. Artifact and payload content is unchanged on POSIX hosts.
- `CITATION.cff` no longer advertises a release that was never cut. It carried
  `date-released: 2026-07-17` while `git tag -l` is empty and no GitHub release
  exists. CFF treats `version` and `date-released` as optional; both return when
  a release is actually tagged.
- The README no longer points readers at a parent-relative sibling standards
  directory, a path that exists only in the author's local checkout and names a
  repository a reader cannot open. The standards are now described rather than
  linked; the conformance table is unchanged. The literal path is deliberately
  not quoted here: the publication sweep landed in the same batch flags that
  string in any tracked file, correctly, and a changelog entry describing the
  removal is not a reason to weaken the rule or to spend its one exemption.
- `.gitignore` covers `.hypothesis/`, which was previously ignored only by the
  nested ignore file Hypothesis generates for itself.
- Three links to ADR 0001 pointed at `docs/decisions/`, which does not exist;
  the ADRs live in `docs/adr/`. Every relative link in `docs/` and the README
  now resolves.
- `docs/PUBLICATION-READINESS.md` Gate 0 records that the maintainer reviewed
  it and decided on 2026-08-15 to proceed. The status changed; the findings did
  not.

### Security

- The Semgrep SAST gate (SEC-07) reported a green check on every pull request
  while scanning nothing. `semgrep ci` resolves a diff baseline on a
  `pull_request` event by running `git fetch origin --force --depth=1 <head-sha>`;
  this repository is private and the checkout sets `persist-credentials: false`,
  so the fetch failed, Semgrep aborted before scanning, and its default
  `--suppress-errors` turned the aborted run into exit 0. The job logs carry the
  scan-environment banner and the fetch error with no scan summary — no rule
  count, no target count, no findings line. A HIGH finding introduced by a pull
  request would have passed the gate. Replaced with
  `semgrep scan --config auto --error --strict`, which needs no baseline and no
  credential, runs the identical full scan on push, pull request, and schedule,
  and fails on an analysis error so a scan that cannot run can no longer report
  success. See [ADR 0004](docs/adr/0004-sast-gate-pragma-and-scan-invocation.md).
