# Changelog

All notable changes to ContextSafe are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project has no tagged
release yet, so everything to date lives under Unreleased.

## [Unreleased]

### Added

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
  test asserts the tree is unchanged after a run. See
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
- One test now asserts the contract of all five Python gate programs at once,
  and compares its case list against `tools/*.py`, so a gate added later that
  sits outside the contract fails the suite rather than sitting outside it
  quietly.

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
  repository could ever be made public, with evidence. Gate 0 is the
  IP/inventions-agreement question created by the repository's creation date
  falling during prior employment, which only the maintainer's attorney can
  clear; Gate 1 is a dual-use and misuse assessment specific to this project —
  a tool that reports where transgender and nonbinary identity data is lost
  also reports where it is retained — including what the threat model already
  covers, four things it does not, and what must be decided before B-010. The
  verdict is *technically ready pending IP clearance*, not *ready to publish*.
  No tag, release, visibility change, or history rewrite accompanies it.
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
  the IP question and decided on 2026-08-15 to proceed. The status changed; the
  findings did not. The audit's recommendation to wait for counsel is kept
  verbatim alongside the decision that departed from it, because a record that
  deleted the recommendation once it was overridden would be the less honest
  document.

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
