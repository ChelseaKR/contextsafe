# Changelog

All notable changes to ContextSafe are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project has no tagged
release yet, so everything to date lives under Unreleased.

## [Unreleased]

### Added

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
