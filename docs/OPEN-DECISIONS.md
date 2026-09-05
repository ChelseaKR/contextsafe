# Open decisions: three questions, with the evidence assembled

**Dated 2026-09-05 · Evidence read at `cf3bf07`, twenty-two commits ahead of
`main` at `ab92013` · This document decides nothing.**

Three questions in the issue tracker are labelled `question` because none of
them is a defect. Each asks what the product should be, and each has been
sitting behind the work of finding out what is actually true today.

- [#100](https://github.com/ChelseaKR/contextsafe/issues/100) — the changelog
  names a release date, and no tag exists.
- [#96](https://github.com/ChelseaKR/contextsafe/issues/96) — whether an import
  report is ever a published contract.
- [#94](https://github.com/ChelseaKR/contextsafe/issues/94) — whether pa11y
  goes into the accessibility gate.

This document is the finding-out. Each section states what is true today with
the file, line, or command that shows it; then the options, what each costs,
and what each forecloses; then a recommendation, which is a recommendation and
not a decision. Where the evidence contradicts the issue that raised it — and
in one place it does — the contradiction is recorded rather than smoothed over.

**Nothing here is a decision record.** No option below has been chosen, and no
sentence should be read as one having been. When a decision is made it belongs
in the issue that asked, in `## [Unreleased]` in
[`CHANGELOG.md`](../CHANGELOG.md), and — where it is consequential, per
[`CONTRIBUTING.md`](../CONTRIBUTING.md) — in an ADR under [`adr/`](adr/). None
of those has been written for any of these three.

The three are also not equal in weight. #100 changes what every published
contract in this repository may do next; #96 adds or declines one output
document; #94 adds or declines one gate engine. They are grouped here because
each is a question with an owner rather than a task with an assignee, not
because they are the same size.

---

## 1. The tag that does not exist (#100)

### What is true today

`git tag -l` prints nothing. `gh release list --repo ChelseaKR/contextsafe`
returns nothing. Both were run at `cf3bf07`.

[`CHANGELOG.md`](../CHANGELOG.md) carries `## [Unreleased]` at the top and,
far below it, `## [0.1.0] - 2026-09-02`. The file's own opening paragraph
explains the ordering: the release workflow "refuses to build unless this file
already carries a matching `## [X.Y.Z]` heading, so the section is written and
dated before the tag exists rather than after it." So the dated heading is not
an error in itself. What it becomes, once no tag follows, is a date on which
nothing happened.

**The issue's premise has moved, and this is the correction.** #100 says
`CITATION.cff` "deliberately carries no `version` and no `date-released`". That
was true when the issue was written and stopped being true at `d472f76`
("release: prepare 0.1.0"). The file now carries `version: "0.1.0"` and
`date-released: 2026-09-02`, above a comment saying the release exists once
`v0.1.0` is pushed and that "if that happens on a different day, this date and
the `## [0.1.0]` heading in CHANGELOG.md move together." `pyproject.toml` line
7 carries `version = "0.1.0"`.

The README's Release and Versioning standards row still said the citation file
deliberately carried neither field. That sentence is false whichever way this
question is decided, so it is corrected in the same change that adds this
document rather than left to wait for a decision.

### What a tag would actually run

A pushed `v*.*.*` tag triggers exactly two workflows.
[`ci.yml`](../.github/workflows/ci.yml) and
[`security.yml`](../.github/workflows/security.yml) are `pull_request` and
`push` to `main` only, so the Semgrep job and the CI determinism matrix do not
run at a tag; `mutation.yml` runs weekly and on pull requests that touch the
package, the suite, or the gate.

[`release.yml`](../.github/workflows/release.yml), in order:

1. checkout at full depth with credentials not persisted, because the scan
   below cannot mean anything on a shallow checkout;
2. the pinned gitleaks composite action, then `make secret-scan` over every
   ref, every object in the object database, and the working tree — before
   anything is built;
3. Python 3.12 and uv 0.11.28 with the cache deliberately disabled on the tag
   path;
4. `grep -Fq "## [${VERSION}]" CHANGELOG.md`, from the runner-provided
   `GITHUB_REF_NAME` with no template interpolation;
5. `make verify`, the literal local gate;
6. `uv build`.

Two properties of that list matter to the decision. The grep is a fixed-string
substring match, so any text after `## [0.1.0]` in the heading — including a
word saying the section was prepared and never tagged — still satisfies it.
And the job **uploads nothing, signs nothing, publishes nothing, and creates no
GitHub Release**: the sdist and wheel it builds go away with the runner. "The
release workflow succeeded" and "a release exists" would remain two different
facts, and `gh release list` would stay empty until someone created a release
by hand.

[`package.yml`](../.github/workflows/package.yml) fires on the same tag shape
and on `workflow_dispatch`. It builds, exports the CycloneDX SBOM from the
locked graph, records checksums, installs the wheel with `pip --no-index` into
an empty virtual environment on Ubuntu, macOS and Windows, runs the README
Quickstart from outside the checkout, and only then attests build provenance
over the recorded checksums. **It has never fired.** Neither trigger has
happened, so the whole packaging pipeline — the SBOM export, the three-platform
fresh install, the attestation step — has never executed as a workflow. Its own
header already says an attestation is not evidence that the release gate
passed, because the two workflows run independently on the same tag.

So a first tag is also the first execution of two pipelines nobody has watched
run. That is a separable risk, and section 1's recommendation separates it.

### What a tag would assert

- The changelog heading's date, as the date of that release.
- `CITATION.cff`'s `version` and `date-released`, which GitHub renders in its
  "Cite this repository" panel, as citable release metadata.
- `SECURITY.md`'s supported-versions table, whose `main` / latest tag row and
  whose sentence "there is no tagged release yet" (line 13) are written for a
  repository that has none.

### What a tag forecloses, and this is the part that is easy to miss

Three separate places in this repository justify changing a published contract
**without moving its version** on the grounds that nothing has been tagged:

- [`schemas/README.md`](../schemas/README.md) line 92: "Nothing here has been
  tagged or released, so the contracts carry no stability guarantee yet beyond
  the tests in this repository."
- [ADR 0006](adr/0006-provenance-token-grammar-and-boundary-scan.md) line 163,
  on a breaking narrowing of `system_version`: "There is no tagged release and
  the only caller has no CLI route, so no stored record and no external consumer
  is affected; the schema is narrowed in place rather than versioned for that
  reason, and this is the moment when that is still free." Line 208 rejects a
  version bump for the same reason: it "would record a compatibility event that
  has no one on the other side of it."
- [`docs/13-BACKLOG.md`](13-BACKLOG.md) line 525, on the mapping-profile
  contract: "no ContextSafe version has been tagged, so every document of the
  removed class was written against an untagged working tree."

That argument ends at the first tag, for every contract, from the tag forward.
[#109](https://github.com/ChelseaKR/contextsafe/issues/109) is the live instance
of the same question and is open. Tagging is therefore not only a release
decision; it is the moment the versioning policy in `schemas/README.md` starts
having someone on the other side of it. Whether that is a cost or the point is
the maintainer's call.

### The options

**A. Tag `v0.1.0` now.** Requires a preparatory commit first, because the
citation file's own comment says the date moves to the day the tag lands: the
changelog heading, `CITATION.cff`'s `date-released`, and the tag would all have
to name the same day. It also requires deciding what the `[Unreleased]` entries
on the tagged tree are. On `main` today that is one documentation entry; on this
integration branch it is the whole 2026-09 wave, which would then be shipped
inside an artifact whose release notes exclude it.
*Cost:* the tagged commit must pass `make secret-scan` and `make verify` on a
GitHub runner, and `make verify` needs the network for `pip-audit`
([#74](https://github.com/ChelseaKR/contextsafe/issues/74) is the standing
instance of that failing for reasons unrelated to the change). A tag whose
release job goes red is a tag pointing at a commit whose gate failed.
*Forecloses:* the free-narrowing argument above, for everything after it.

**B. Tag `v0.2.0` at the 2026-09 wave boundary, and let 0.1.0 stand as a
section that never became a tag.** Requires renaming `## [Unreleased]` to
`## [0.2.0] - <that day>`, moving `CITATION.cff` and `pyproject.toml` to 0.2.0,
and saying in the 0.1.0 section that it was prepared and never released —
without that last part, the file still names a release date on which nothing
was released, which is exactly what #100 reports.
*Cost:* 0.1.0 becomes a version number no artifact ever carried, and the
version metadata jumps from an untagged 0.1.0 to a tagged 0.2.0.
*Forecloses:* the same narrowing argument, and any possibility of a 0.1.0
artifact.

**C. Restate the 0.1.0 heading as prepared rather than released, and leave
tagging as a later decision.** The `-F` grep makes the heading text after
`## [0.1.0]` free, so this costs nothing mechanically. `CITATION.cff` would
either drop `version` and `date-released` again or say in its comment that the
date is a preparation date.
*Cost:* dropping the citation fields reverses a deliberate act three days old
and gives up the citable version that motivated it. The question stays open.
*Forecloses:* nothing. It is the only option that keeps all the others
available.

**D. Do nothing.** *Cost:* the changelog keeps naming a release date on which
nothing was released, and the citation file keeps exporting a version and a
release date for a release nobody can fetch. Both are read by strangers, which
is the reason #100 exists.

### Recommendation

Two things that are independent, and separating them is most of the value here:

1. **Exercise `package.yml` by `workflow_dispatch` now.** It costs no version
   claim, no tag, and no changelog edit, and it converts "the packaging pipeline
   has never fired" into evidence — or into a bug report — before any tag
   depends on it. This is available today and nothing blocks it.
2. **Prefer C now and B at the wave merge.** C removes the false sentence at
   once and holds every other option open; B makes the tag land on a boundary
   that means something, rather than on a version prepared before the wave that
   the artifact would contain. Whichever tag is first, the free-narrowing
   argument in `schemas/README.md`, ADR 0006 and the backlog should be settled
   before it rather than discovered after — #109 is where that question is
   already waiting.

A reasonable maintainer could take A instead, on the grounds that the citable
version is worth more than the versioning freedom it spends. That is a judgment
about who is on the other side of these contracts, and this document has no
evidence about that: there is no design partner
([#87](https://github.com/ChelseaKR/contextsafe/issues/87)) and no recorded
consumer.

---

## 2. The import report (#96)

### What is true today

`ImportResult` (in
[`src/contextsafe/importers/base.py`](../src/contextsafe/importers/base.py))
carries the format name, mapping version, source digest, source byte count,
record count, observations, warnings, `profile_reviewed`, an unobserved-cell
count, laboratory results, source tokens, and the applied profile's digest and
version. `to_dict()` states its own status in its docstring: "In-process and
test-only. This shape has no schema in `schemas/` and no command emits it: the
CLI writes only the observation set."

`_import_command` in [`src/contextsafe/cli.py`](../src/contextsafe/cli.py)
confirms it: it returns the observation-set document and sets
`args.event_warnings` from the result's warnings, and nothing else leaves the
process.

Run at `cf3bf07`, from an exported fixture directory:

```sh
contextsafe import --format fhir-r4-json \
  --source fixtures/reference/fhir-patient.json \
  --case fixtures/reference/case.json \
  --checkpoint ehr --output obs.json --log-dir logs
```

exits 0, prints nothing, and appends one record (one line in the log, wrapped
here):

```json
{"command":"import","error_code":null,"outcome":"accepted",
 "schema_version":"contextsafe.event-log/0.2.0","sequence":0,
 "warnings":["checkpoint_asserted_by_caller","mapping_profile_not_bound"]}
```

So the warnings do reach a surface, which is what closed
[#68](https://github.com/ChelseaKR/contextsafe/issues/68). Two limits on that,
both measurable:

- **The log's only reader does not count them.** `contextsafe events summarize
  --directory logs` on that same log returns `counts_by_command`,
  `counts_by_error_code`, `counts_by_outcome`, `record_count` and `log_sha256`,
  and no warning counts at all: `EventLogSummary` reduces each record to
  command, outcome and error code. The field the writer added for this purpose
  is the one field the summary drops. The writer landed in `b2c2b03` and the
  reader on this branch, so this is a same-wave seam rather than an old
  oversight. This document records it and does not fix it.
- **The log is off unless asked.** An operator who does not pass `--log-dir`
  sees nothing, because `import` writes its document and stderr carries the one
  JSON error object only on a rejection.

**The larger fact the issue does not name.** The same fixture read as
`lis-csv` produces this report in process:

```json
{"format": "lis-csv", "mapping_version": "0.2.0", "observation_count": 3,
 "persisted": false, "profile_reviewed": false, "profile_sha256": null,
 "profile_version": null, "record_count": 3, "result_count": 2,
 "source_byte_count": 399,
 "source_sha256": "26014e6d08be1b9cc3923fdfc270b9115382f877b30f38d7f169ac7700327579",
 "unobserved_cell_count": 0,
 "warnings": ["mapping_profile_not_bound", "result_observations_not_written"]}
```

`result_count` is 2. `contextsafe.result-set/0.1.0` is already a **published
contract** with a row in [`schemas/README.md`](../schemas/README.md), and no
command emits it; `RESULT_OBSERVATIONS_NOT_WRITTEN` exists to say so on every
conversion that produces one. So "is there ever a second output document from
`import`" is two questions, not one: the report, and the result set whose
contract is published and unemitted. #96 asks about the first;
[#76](https://github.com/ChelseaKR/contextsafe/issues/76) holds the second.
Deciding the report without noticing the result set would answer the smaller
half.

One property makes the report cheaper to publish than most documents here:
every field of `to_dict()` is already a count, a boolean, a digest, a dotted
version, a format name from the registry, or a closed warning code. There is no
token, no path, and no free text in it, so publishing it needs no redaction
rule invented for it — it is already the shape the receipt payload and the
event log record are.

### The options

**A. Publish it.** A `--report PATH` output, a
`contextsafe-import-report-v0.1.schema.json`, a row in `schemas/README.md` with
the stated count moved, an agreement test, a determinism vector, and a docstring
that says it is a contract rather than a test aid.
*Cost:* one more published shape to version forever. The repository's own rule
is that a closed set which widens moves the contract version, and the warning
set is still growing — `result_observations_not_written` was added this wave —
so each new warning code would move the report contract with it.
*Gains:* the operator sees a profile that bound nothing at the moment they can
still fix the profile, without having asked for a log first; and the source
digest and byte count become evidence a partner can file beside a receipt.
*Forecloses:* little structurally, but a published shape is expensive to
withdraw, and this repository has no consumer on the other side of one yet.

**B. Never publish it; the event log is the surface.** This is the current
direction, and closing #96 this way means finishing it rather than declaring it
finished: either the summary counts warnings — which widens
`contextsafe.event-log-summary/0.1.0` and moves that contract version — or the
operations documentation says plainly that warning codes in the log are for
inspection by hand.
*Cost:* the diagnostic stays behind a flag that is off by default, and the
count that would make it usable does not exist yet.
*Forecloses:* nothing; the report can still be published later.

**B2, a variant worth pricing separately.** Print the closed warning codes to
stderr on success unless `--quiet`. It publishes no document, breaks no
exit-code contract (0 with output on stdout; 2 with one JSON error object on
stderr), and carries only closed-vocabulary codes, so it cannot leak a token.
*Cost:* stderr today is trivially describable — one error object on rejection,
nothing otherwise — and this makes it two things. It is also a CLI-wide
decision rather than an import-only one, because the next command with a
warning would want the same treatment.

**C. Decide the result set first, and let the report follow it.** The result
set has a published contract already; the report does not. If the answer to the
result set is "yes, a second output document exists and here is how it is
named", the report is a smaller version of a question already answered.

### Recommendation

**B with B2**, and the result set decided as its own question under #76.

The reasoning is that the report's value today is one diagnostic — a profile
that binds nothing — and B2 delivers that diagnostic to the person who can act
on it, at the cost of one stderr line of closed codes, without adding a contract
this repository would then owe a version to for every warning code it invents.
The report becomes worth publishing when something downstream consumes it: a
partner filing import evidence beside a receipt, or a receipt section that
carries laboratory outcomes. Neither exists.

If the decision goes the other way, the honest form of A is the whole of A —
schema, README row and count, agreement test, determinism vector — because a
`--report` flag emitting an unversioned shape would be a document published in
practice and unpublished on paper, which is the state the contract list in
`schemas/README.md` exists to make impossible.

And whichever way it goes, the docstring on `to_dict()` should say which, since
that is what #96 asks for. It currently says "if a second output document is
ever decided", which is accurate today and will be wrong the moment it is.

---

## 3. pa11y (#94)

### What is true today

`make a11y` runs `tools/a11y_gate.py --engines builtin` inside `make verify`.
`make a11y-full` adds axe-core in a headless DOM and runs as its own CI job,
with the harness pinned in `tools/a11y/package.json` (axe-core 4.13.0, jsdom
30.0.1) and installed by `npm ci`.

Run at `cf3bf07`:

```
$ uv run python tools/a11y_gate.py --engines builtin
a11y-gate: 2/2 page(s) audited; engines executed: builtin
  html-validity: examined 532
  contrast: examined 54
  color-only: examined 26
  print: examined 44
  minimization: examined 315
a11y-gate: clean
```

The gate's discipline is the thing any third engine has to meet, and it is
already stated as code rather than as intent: a requested engine that cannot
run is `engine-unavailable` and never a skip; an engine that executed no rules
against a page is `engine-examined-nothing`; no engine requested at all is
`no-engines`; a page that does not match the receipt it should have rendered is
`wrong-subject` and is not counted as audited; and a rule axe returns as
undetermined is listed by name and must map to a built-in check that decides
it, or the absence of that mapping is itself a finding.

The recorded reason pa11y is out is in
[Accessibility §11](08-ACCESSIBILITY-I18N.md) and repeated in the gate's own
module docstring (`tools/a11y_gate.py`, lines 103–107): pa11y's default engine,
HTML_CodeSniffer, loads its rulesets by injecting script tags and does not
complete in a headless DOM without a browser; and the rules it would add over
axe — contrast, colour-only encoding, print — are the ones the built-in checks
compute.

**Two measurements that bear on the decision, one of which cuts against an
argument for adding subjects.**

`build_subjects` renders one page per shipped locale from the bundled reference
fixture, so the audited set is two pages from one receipt. The obvious worry is
that a receipt with five passes never exercises the other statuses. It does:
the en-US page carries `data-cs-status` markers for `pass` (6), and one each of
`blocked`, `fail`, `indeterminate` and `not_applicable`, plus three
`data-cs-boolean` markers, because the summary table carries a row per status.
So the colour-only check has examined every status word, not just the one the
result rows use. And `check_contrast` reads the stylesheet rather than the page,
so every declared foreground/background pair is checked whether or not this
receipt happens to use it.

The coverage argument for more subjects is therefore weaker than
[§7](08-ACCESSIBILITY-I18N.md)'s fixture list implies — which is worth knowing
before spending anything on either more subjects or more engines.

**One inconsistency the decision has to clear up either way.** §7 still lists,
under "Automated on every change", "pa11y or equivalent on summary, all-status,
long-evidence, and ES fixtures", while §11 says pa11y is not wired in and the
audited subjects are two pages from one receipt. "Or equivalent" carries some of
that, and the fixture list carries none of it. Whichever way #94 goes, that line
moves: either it names what actually runs, or its fixture list becomes a work
item with an owner.

### The options

**A. Record the exclusion as permanent, close #94, and reconcile §7.**
*Cost:* almost nothing to do, and the accessibility evidence base does not grow.
*Forecloses:* nothing permanently — a later ADR can reopen it — but it answers
a measurable question by argument rather than by measurement.

**B. Measure once, outside the gate, then decide.** Install pa11y in a scratch
environment, run it against the two rendered pages, and record in #94 what it
reports that the built-in checks and axe do not, and whether it completes at
all in this harness.
*Cost:* one bounded experiment, dev-only, merged into nothing.
*What it has to establish:* whether HTML_CodeSniffer's techniques report
anything on these pages that is not already computed; and, if pa11y is
configured to use a runner that does complete here instead, whether that
runner is axe-core itself — in which case the third engine is the second
engine behind another driver, and adds a dependency and no rule.

**C. Wire it in as a third engine, to the same bar.** `--engines
builtin,axe,pa11y`; unavailable is a failure and not a downgrade; a page it
examined with no rules is `engine-examined-nothing`; every rule it cannot
determine is named and mapped to a covering built-in check or is a finding; the
harness pinned in `package-lock.json` like axe's.
*Cost:* on the repository's own account of why pa11y is out, its default
runner needs a real browser rather than a headless DOM, so `make a11y-install`
would grow a browser download and the pinned node surface would grow a large
transitive tree, in a repository whose runtime dependency list is empty by
rule and whose dev tooling is deliberately small. That cost is the first thing
option B measures, and it should be measured rather than assumed. The CI job grows minutes; that job is
separate from `make verify`, so
[#93](https://github.com/ChelseaKR/contextsafe/issues/93) is not made worse
directly. `[project] dependencies` is untouched either way — pa11y is node-side.
*Forecloses:* the small-toolchain property, and it puts a browser inside the
accessibility gate's trust boundary.

### What none of the three does

None of them moves the repository closer to an AA claim. The gap between this
gate and conformance is a person with a screen reader — B-044, unstarted,
[#83](https://github.com/ChelseaKR/contextsafe/issues/83) — and the README's
accessibility row already says conformance is not claimed for that reason.
Static engines are bounded by construction, and a third one does not change the
bound.

### Recommendation

**B, then almost certainly A**: one bounded measurement recorded in #94, and,
unless it finds something the two current engines miss on these pages, restate
the exclusion as permanent and reconcile §7's automated list with what runs.

Skipping straight to A is defensible: the §11 argument is specific and
technical, and nothing about jsdom or HTML_CodeSniffer has changed since it was
written. What the measurement buys is that the exclusion stops resting on an
argument nobody has re-checked — which is the same reason #94 exists.

What is not defensible in either direction is spending the accessibility budget
on a third static engine while B-044 has not started. If a choice has to be
made between the two, the person with the screen reader is the one that changes
what this project can honestly say.

---

## What this document does not claim

- **No review happened.** No clinical, laboratory, community, legal, security,
  interoperability, translation or accessibility reviewer has read this
  document or anything it describes, and nothing here records an approval.
- **No decision is recorded.** Three recommendations are stated as
  recommendations. Each of the three questions is open, and each remains the
  maintainer's.
- **The evidence is dated.** Every figure and quotation above was read at
  `cf3bf07` on 2026-09-05, and every command shown is re-runnable. A number here
  is a measurement of one run, not a running total; re-run the command rather
  than trusting the number.
- **The branch matters for section 2.** The event-log warning field and its
  reader are on this integration branch and not on `main`, so the seam described
  there is a state of the branch and not of the published default.
