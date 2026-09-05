# Assurance program: a multiyear plan for the gates themselves

Status: phases 1 to 5 built; phase 6 blocked, see below
Owner: technical owner
Planning unit: ordinal phases with entry conditions, not dates

## Why this document exists

[`docs/12-ROADMAP.md`](12-ROADMAP.md) plans the product: forty elapsed weeks to
v1.0, seven decision gates, and a capacity model. [`docs/13-BACKLOG.md`](13-BACKLOG.md)
carries B-001 to B-057 and a P1 parking lot. Between them the product is owned.

What neither owns as a program is the **assurance apparatus** — the checks that
decide whether anything merges at all. Those grew one at a time: a coverage
floor, a lint config, a hygiene line in the Makefile, a publication sweep, an
i18n gate, an accessibility gate, a secret scan, a SAST job. Each was added for
a good reason. None of them was ever asked the question this document asks.

The question came from evidence, not from taste. Two changes on 2026-08-27
found four separate instances of one defect:

- `make hygiene` was `! rg -n '(TODO|FIXME|HACK)' src tests`, and `rg` exits 2
  when it is not installed. The leading `!` turned "the tool is missing" into a
  pass, identically to "the tool found nothing". Ripgrep is not in `uv.lock`
  and no CI step installs it.
- The second hygiene line, `! find ... | grep .`, took its exit status from the
  last stage of the pipe, so a `find` that never ran also passed.
- `tools/secret-scan-full-history.sh` wrote each object out with
  `git cat-file ... || true` and then counted it as materialized, so an
  unreadable object was scanned by nobody inside a run that still said clean.
- `tools/publication_sweep.py` printed `clean over tracked files` for an empty
  file list.

And earlier, recorded in [ADR 0004](adr/0004-sast-gate-pragma-and-scan-invocation.md):
the Semgrep gate reported a green SAST check over zero files on every pull
request for weeks, because its baseline fetch failed and `--suppress-errors`
converted the aborted run into exit 0.

Five instances is not five bugs. It is one defect class with a name:

> **A check reports a clean result over content it did not examine.**

A gate with this defect is worse than no gate, because it is *load-bearing in
the reader's head*. `make verify` being green is the sentence this repository
says instead of "somebody looked". The program below exists so that sentence
keeps being true as the surface grows.

## The invariant

Every phase drives toward one property:

> **A green check states its denominator.** It names what it examined. Anything
> it did not examine is either a finding or a printed exemption carrying a
> reason. Silence is never one of the options.

Three states, never two: found nothing (pass), found something (fail), did not
run or did not look (fail loudly, and differently).

## What this program is not

It does not re-open anything the corpus already decided.

- The roadmap's *Later exploration* section already rules on RIS/DICOM,
  pharmacy, CDS, a hosted control plane, and production synthetic canaries.
  Each carries stated prerequisites. Nothing here touches them.
- The P1 parking lot (B-101 to B-106) is trigger-gated. Nothing here pulls one
  forward. B-102 (JUnit/SARIF) in particular is *not* an assurance-program item;
  its trigger is a release-engineering renewal conversation, not gate integrity.
- ADR 0001's v1 boundary, ADR 0002's unsigned-compilation decision, and ADR
  0003's recoverable evidence commit are settled. No phase here reverses one.
- ADR 0004 already chose `semgrep scan --config auto --error --strict` over the
  alternatives it lists. Phase 4 inherits that decision rather than revisiting it.

It also does not pretend to capacity that does not exist. The roadmap's capacity
checkpoint has the `E` pool at 94.3% loaded at DG-04, and R-09 ("no budget
owner") is an open risk scored 16. So this program is deliberately sized as
maintenance-tier work measured in days, not as a workstream, and phases are
ordered by entry condition rather than by date. A phase that cannot be afforded
is a phase that does not start; it is not a phase that ships half-built.

## The phases

### Phase 1 — The gates account for what they did not examine

**Status: built.** This is the change that accompanies this document.

The two gates rewritten on 2026-08-27 were left with two known holes, on
purpose, because closing them needed a design decision rather than a patch:

1. `tools/` was outside `MARKER_ROOTS`, so the four gate implementations that
   decide whether this repository merges were themselves never scanned for
   unowned markers. The gates were exempt from the rule they enforce.
2. `tools/publication_sweep.py` skipped an oversized or non-UTF-8 source with a
   bare `continue` and still printed a clean line. Its denominator was the count
   of files it managed to read, which is the one number that cannot reveal a
   file it failed to read.

A third hole was found while sizing the first two: `[tool.coverage.run]` had
`source = ["contextsafe"]`, so the coverage floor never measured `tools/` at
all. That is the same defect one level up — the coverage gate reporting green
over code it does not look at — and it is why the `SweepUnavailable` branch
added on 2026-08-27 shipped with no test covering it.

Delivered:

- The marker scan covers `tools`, with a line-level exemption that must carry a
  reason, and every honored exemption printed on every run. See
  [ADR 0005](adr/0005-hygiene-marker-exemptions.md).
- An unexaminable source is a finding in the publication sweep, in both tracked
  and `--history` mode, matching the precedent the hygiene gate already set with
  its `unreadable` rule. The clean line carries the denominator.
- The coverage floor measures the gate implementations.

Entry condition: none. This is the phase that makes the later ones checkable.

### Phase 2 — The boundary claim covers the fields it names

**Status: built.** Closes issue #35. See
[ADR 0006](adr/0006-provenance-token-grammar-and-boundary-scan.md).

`build_evidence_record` writes `boundary_check_status: "passed"` into every
persisted `EvidenceRecord`. Three of that record's fields — `collector_id`,
`system_id`, `system_version` — are operator-supplied and pass through
`parse_evidence_metadata`, which checks token *shape* and nothing else. The
PHI and direct-identifier scan that every byte of the evidence *source* goes
through never runs on them. So a record whose own field says a boundary check
passed carries three values no boundary check examined.

That is this program's invariant, stated in the product rather than in the
tooling, which is why it is phase 2 and not a separate concern.

It is not phase 1 for a specific reason. The obvious fix — run the three fields
through `preflight._reject_unsafe_string` — was attempted in PR #38 and closed,
because it rejects values the published contract declares valid.
`schemas/contextsafe-evidence-v1.schema.json` allows `system_version` to match
`^[A-Za-z0-9][A-Za-z0-9:/_.-]{0,127}$`, which admits a calendar version like
`2026-08-27`; the direct-identifier set contains a date-shaped pattern that
rejects exactly that. The same collision exists between the seven-digit-run
pattern and a hyphen-delimited build tag, and between the URL pattern and a
`collector_id` expressed as a URI, which the schema's colon and slash both
permit. PR #38 also reached into a private function through a function-local
import rather than the documented extension point, `preflight.identifier_hits`.

So phase 2 is a contract decision before it is a code change, and it needs:
an ADR choosing which detectors apply to structured provenance tokens versus
free text; a schema change if the answer narrows what a valid `system_version`
may look like, with the version implications that carries; the canary detectors
applied unconditionally, since no legitimate provenance value contains one; and
`tests/test_privacy_canaries.py` extended in both directions, as B-039's
implementation note already requires — values that must fail closed and with
which error code, and schema-valid values that must not become false positives.

Entry condition: none technical. It is second because it is the phase most
likely to be got subtly wrong, and phase 1's exemption-and-denominator
mechanism is the thing that will make its coverage claim checkable. It bears
directly on R-07 ("real PHI enters workspace", score 15, open).

### Phase 3 — Coverage is declared, and drift from it fails

**Status: built.** See
[ADR 0007](adr/0007-declared-analysis-scope.md) and `make scope`.

After phase 1, every gate knows its denominator but each states it in its own
words, on stdout, where nothing compares them. A reader who wants to answer
"what does `make verify` actually cover?" still has to read every program in
`tools/`. (A count stood here and went stale the moment `tools/` grew another
gate, which is the small version of the defect `make claims` now catches.)

Phase 3 gives each gate a declaration of what it examines and what it exempts,
and adds a check that fails when a gate's declared coverage and its measured
coverage disagree. The failure mode this closes is the one phase 1 cannot: a
gate whose scope silently narrows, or a tree that grows a directory no gate was
ever pointed at. `tools/` was exactly that for the marker rule until phase 1,
and nothing would have noticed if it had stayed that way for another year.

This is also where the marker rule's scope question gets settled. Phase 1
widened it to `tools` because that was the demonstrated hole. Widening it to
every tracked file is deferred here rather than done in phase 1, because
`README.md`, `CONTRIBUTING.md`, `DEFINITION_OF_DONE.md` and `CHANGELOG.md` each
name the banned words while describing the rule, and exempting four documents
line by line to widen a scan is a decision that should be made against a
declared-coverage model rather than ahead of one.

Entry condition: phase 1 merged, and a second gate added or a gate's scope
changed. Doing this before there is drift to catch is building a model of a
system that is still moving.

### Phase 4 — One contract for the gates that cannot always run

**Status: built,** with the CI-side proof replaced by a local one. See
[ADR 0008](adr/0008-one-exit-code-contract-for-every-gate.md).

Three gates sit outside `make verify` because each needs something a clean clone
does not have: `make secret-scan` needs gitleaks 8.30.1, `make a11y-full` needs
the node harness, and the Semgrep job needs the registry. Each handles "the tool
is absent" its own way today, and each of those handlers was written by hand.
ADR 0004 and the 2026-08-27 changes are both, in the end, reports that a
hand-written absent-tool path was wrong.

Phase 4 gives them one contract: a requested engine that cannot run is a
failure, never a downgrade to the engines that can; and CI proves it by removing
the tool and asserting the job fails. `tools/a11y_gate.py` already implements
half of this with its `engine-unavailable` result, which makes it the model
rather than a fourth variant.

Entry condition: B-045 (packaged artifacts with SBOM and signatures) or B-040
(independent security review), whichever comes first, because both add a gate
with an external dependency and phase 4 is cheap to do once and expensive to
retrofit per gate. Brought forward because the measurement was cheap and the
result was three live conflations, not because either entry condition arrived.

One part of this phase as planned was **not** built the way it was written. The
plan said CI would prove it by removing the tool and asserting the job fails.
That was written on the belief that GitHub Actions was unavailable on this
account, which was not true: `ci.yml` and `security.yml` both run on every pull
request, and 93 of the last 100 workflow runs succeeded. The reason the
CI-side proof is still not built is a different and smaller one -- a job that
removes a tool to watch a gate fail is a job whose green means the opposite of
every other job's green, and it needs its own design. The stand-in gitleaks
inside `make verify` gives the same evidence in a place CI already runs, so the
proof exists and the workflow does not.

**The third of those three gates joined the contract on 2026-09-05**, and the
reason it had not is worth keeping. ADR 0008 excluded Semgrep on the grounds
that whether the scanner distinguishes a finding from an analysis error is a
property of a tool this repository cannot verify offline. That was right about
the exit code and wrong about the gate: #114 found the scanner had been
partially parsing `src/contextsafe/validation.py` — a safety module — and
exiting 0, so the SAST check was green over a module it had read in part, and
went red only when a branch's larger file set turned the same warning into a
different exit code. The scan's `--json` report carries the parse errors and the
list of files actually scanned, so `tools/sast_gate.py` reads that instead and
answers in the three states, with the report shapes and a stand-in scanner
covering them inside `make verify`. See
[ADR 0012](adr/0012-sast-partial-parse-and-the-syntax-it-forbids.md). This is
the program's own defect class found in the gate ADR 0004 had already been
written about once, which is the argument for phase 6 rather than against it:
each of these was found by the person who wrote the thing.

What is proved today is proved by `make sast` locally and by the tests inside
`make verify`. The security workflow's first run of the new step is what will
show that the CI container carries what the gate needs; nothing in a checkout
can see a workflow run, and this document does not date one.

### Phase 5 — Evidence that the suite can detect a regression

**Status: built,** over a declared subset of three of the twenty-nine modules
named in `SAFETY_MODULES`, and wired into CI on 2026-09-04
(`.github/workflows/mutation.yml`); its first run has not been observed. See
[ADR 0009](adr/0009-mutation-evidence-over-declared-safety-modules.md),
`make mutants`, and that workflow, which is configured to run weekly and
on any pull request touching the package, the suite or the gate. Configuration
is not execution, and this document does not treat it as such: the evidence
that the mutation gate runs in CI is its first run, which nobody has watched
yet. What is proved today is proved by `make mutants` locally. Widening the
declared subset is a runtime decision and has not been taken; twenty-six safety
modules still have no mutation evidence.

Everything above proves a gate can fail. None of it proves the *test suite* can
fail — that the assertions covering the safety modules would actually catch a
regression rather than merely execute the lines. Branch coverage is an execution
measure, not a detection measure; a 95% floor over the safety modules is
consistent with a suite that asserts almost nothing.

Phase 5 introduces mutation evidence over the modules named in the Makefile's
`SAFETY_MODULES`, and treats a surviving mutant in one of them as a finding.
This is the largest phase here and the one most likely to be descoped to a
subset of modules; that is an acceptable outcome as long as the subset is
declared, which phase 3 is what makes possible.

It connects to B-048, which requires all 41 published and hidden faults to be
detected and correctly localized before release. B-048 measures detection
against an authored fault corpus. Phase 5 measures it against mechanically
generated ones, which is a weaker signal about clinical correctness and a
stronger one about assertion strength. Neither substitutes for the other.

Entry condition: phase 2 complete, so the boundary scan being measured is the
one that will ship, and B-039's canary suite settled.

### Phase 6 — The apparatus reviewed by someone who did not write it

**Status: blocked. Not built, and not buildable here.**

What blocks it, precisely:

- **A named independent reviewer.** The whole content of this phase is a person
  who did not write the gates reading them. Nothing produced inside this
  repository can stand in for that, and a document that looked like a review
  would be this program's own defect class committed by the program itself: a
  green mark over something nobody examined.
- **Funding.** B-040 buys an independent threat-model and security design
  review. R-09 ("no budget owner; interest remains unfunded DEI") is open at
  score 16, and the roadmap's capacity checkpoint has the `E` pool at 94.3%
  loaded at DG-04. This is not a technical condition.
- **A release dossier that does not exist.** B-054 assembles it from pilot
  evidence produced in B-049 to B-053. There is no pilot, so there is nothing
  for gate-coverage evidence to be filed into yet.
- **A decision that is the owner's.** Widening B-040's acceptance criteria to
  cover the assurance apparatus changes what a paid reviewer is contracted for.
  That is a scope and spend decision, so this document proposes it and does not
  make it.

What would unblock it: DG-01's funding path resolved, B-040 scheduled with a
named reviewer, and B-054 opened. At that point the work is small, because
phases 1 to 5 produced the material a reviewer would ask for: five ADRs stating
what each gate examines and what it declares away, three gates that print their
denominator on every run, and one that prints every exemption.

Deliberately **not** done in the meantime: no review checklist, no reviewer
brief, no placeholder dossier section, and no change to B-040's acceptance
criteria. Each of those would be building for a reviewer who does not exist,
and the first one that got skimmed and marked complete would be worse than the
gap it filled.

Every phase above is the author of the gates auditing the gates. B-040 already
buys an independent threat-model and security design review; the release dossier
(B-054) already has to close every P0, risk, and checklist item. Phase 6 puts
the assurance apparatus itself into both: the reviewer is asked not only whether
the code is safe but whether a green `make verify` means anything, and the
dossier carries gate-coverage evidence rather than a screenshot of a green
check.

This is also where the program's own claim gets bounded honestly. None of the
above can prove absence. R-14 is recorded as irreducible — a finite test pack
cannot prove safety — and a gate that states its denominator is a gate a reader
can calibrate against, not a gate that has removed the risk.

Entry condition: B-040 funded and scheduled, which per R-09 and the capacity
checkpoint is not a technical condition at all.

## What implementation work can and cannot close

Phases 1 to 5 are implementation and can be finished in this repository. Phase 6
cannot, and saying so is part of the plan rather than an omission from it.

| Phase | Closable by implementation | What else it needs |
|---|---|---|
| 1 | yes | nothing |
| 2 | yes | a contract decision, recorded as an ADR and a schema change |
| 3 | yes | nothing |
| 4 | the contract and its local proof, yes | a CI run per absent tool, which needs GitHub Actions on this account |
| 5 | yes, bounded to a declared module set | judgement on where the bound sits |
| 6 | **no** | a named independent reviewer, funded per B-040, and a release dossier that does not exist yet |

Built, as of 2026-09-05:

| Phase | State | Where it landed |
|---|---|---|
| 1 | built | ADR 0005; `make hygiene` covers `tools`, the sweep names unread sources, the coverage floor measures the gates |
| 2 | built | ADR 0006; provenance grammars and the boundary scan on `parse_evidence_metadata`, closing issue #35 |
| 3 | built | ADR 0007; `make scope` |
| 4 | built, with one substitution, and widened to the SAST gate on 2026-09-05 | ADR 0008 and ADR 0012; the three-state contract, proved locally rather than by a CI job nobody has watched run, now including the scan whose partial parse used to leave a safety module read in part and reported clean (#114) |
| 5 | built over three of twenty-nine safety modules | ADR 0009; `make mutants`, wired into `.github/workflows/mutation.yml` on 2026-09-04, first run not yet observed |
| 6 | **blocked on people and money** | nothing, deliberately |

Phase 6 is blocked on people and money, not on code. Nothing in this repository
can stand in for a review by someone who did not write the gates, and a
placeholder that looked like one would be this program's own defect class:
a green mark over something nobody examined.

## Sequence and horizon

| Phase | Depends on | Roughly when, against the product roadmap |
|---|---|---|
| 1 | nothing | now, built |
| 2 | nothing technical; issue #35 | before DG-04, since DG-04 gates on PHI canaries passing |
| 3 | phase 1, plus observed drift | before M4 trust beta |
| 4 | B-045 or B-040 | around M4 to M5 |
| 5 | phase 2, B-039 settled | before B-048, so before DG-06 |
| 6 | B-040 funded | release dossier, and then each annual assurance cycle |

Phases 1 to 3 are affordable now and measured in days. Phases 4 to 6 are bound
to milestones this repository does not control the funding for, so their
placement is an ordering claim and not a schedule. The roadmap's own decision
gates move if capacity does; so do these.

## What the gate costs, measured

A gate people wait on is a gate people find ways around, so what `make verify`
costs is a property of the apparatus rather than a detail of somebody's
afternoon. Issue #93 recorded that the cost had roughly doubled over the 2026-09
wave, named the three-run determinism suite as the obvious suspect because it
spawns fresh interpreters, and listed three ways to split the gate. It also said
that splitting it wrongly would be worse than leaving it, so the suite was
measured before anything was split. The suspect is not the cost, and what
follows is the measurement rather than a decision taken on it.

**Method, and what it is worth.** Measured on 2026-09-05 at commit `8a23096`,
Python 3.12, a ten-core macOS workstation, 3,258 tests as
`pytest --collect-only -q` counted them at that commit, across the 52 modules
`tests/` holds today: five of those are named in the module table below and the
other 47 are its residual row, which is the denominator every share in this
section is taken over. One of the 47, `tests/test_sast_gate.py`, landed with the
SAST gate after the measurement was taken, so it is inside the denominator and
none of the seconds below are its; the measured run saw 51 modules and 3,258
tests, and re-measuring is what would put the 52nd module's cost on the record.
Wall time on a developer machine is not a stable number: the identical pytest
command over the identical tree measured 218 seconds and 1,769 seconds
twenty minutes apart, because other work shared the machine. So the figures
below are CPU seconds — the process plus every subprocess it waited on —
wherever a comparison depends on them, and wall seconds appear only where the
runs being compared were taken back to back. None of them is a CI number: that
is a different machine and a different operating system, and nothing here was
measured there.

| Part of `make verify` | Cost |
|---|---|
| `test` | 197 s CPU, 218 s wall |
| the other twelve stages together | 25 s wall |

The twelve are `sync` 0.2 s, `lint` 0.1 s, `format` 0.1 s, `typecheck` 1.7 s,
`audit` 6.4 s, `hygiene` 0.4 s, `scope` 0.3 s, `patterns` 1.1 s,
`publication-sweep` 6.6 s, `i18n` 1.6 s, `a11y` 6.2 s, `claims` 0.4 s. The
pytest stage is about 90% of the gate; of the remaining tenth, one stage waits
on the network (`audit`) and two read the whole tree (`publication-sweep` and
`a11y`).

Inside the pytest stage, by CPU, with 192 s of the 197 s attributable to
individual tests:

| Test module | CPU | Share of the stage |
|---|---|---|
| `tests/test_a11y_gate.py` | 56.6 s | 29.5% |
| `tests/test_property_invariants.py` | 20.5 s | 10.7% |
| `tests/test_import_hl7v2_er7.py` | 17.2 s | 8.9% |
| `tests/test_mutation_gate.py` | 13.9 s | 7.2% |
| `tests/test_determinism.py` | 13.8 s | 7.2% |
| the other 47 modules | 70.0 s | 36.5% |

Two things fall out of that table. The determinism suite is 7.2% of the stage by
CPU and 6.7% by wall — fourteen seconds of a four-minute gate — so the
hypothesis the issue was written on does not survive being measured. And the
cost is diffuse: the largest module is under a third, and more than a third of
the stage is spread across the 46 measured modules of that row, which are
individually small.

The largest module is not slow by accident either. `tests/test_a11y_gate.py` is
142 tests, and nearly every one damages the rendered receipt in a different way
and audits it. Rendering both shipped pages costs about 5 ms of CPU; one
`audit()` over one page costs about 240 ms and over the pair about 570 ms.
Nearly every one of the 142 damages and audits a single page, so 240 ms is the
per-test figure that reconciles with the table: 142 single-page audits is about
34 s, and the rest of the module's 56.6 s is the coverage instrumentation over
that plus the few tests that audit the pair. Reading the pair figure as the
per-test one gives 101 s, which is nearly twice what the module costs. (Those
three figures were timed on their own on 2026-09-05; an earlier timing on this
machine put the pair at 713 ms and the rendering at 7 ms, which is the
run-to-run spread the method paragraph warns about.) The cost is the checking
rather than the setup, so it is not shareable between tests that are checking
different damage.

Coverage instrumentation costs 55 s CPU, 39% on top of the 141 s the same suite
takes without it. That is worth stating because the naive comparison — a run
with coverage against a run without it, taken hours apart on a shared machine —
suggests it more than doubles the suite, and it does not.

**What this supersedes.** Two places in the repository compare a gate that sits
outside the merge gate against what the merge gate itself costs, and both were
written when that cost was seconds: ADR 0009, which says `make mutants` "takes
about two minutes against roughly a second for everything else in `verify`" and
rejects putting it inside on "two minutes on every push, against one second
today", and the gate table in `CONTRIBUTING.md`, which said the same in fewer
words. Measured, the comparison is two minutes against about four minutes, not
two minutes against one. Both places now carry a dated correction pointing here.
What the corrected ratio implies for where `make mutants` runs is not settled
here: it is the same kind of judgment as the options below, and it belongs with
them.

### The options in issue #93, against that measurement

1. **Parallel pytest.** The only one of the three that matches the measured
   shape, because the cost is spread across all the measured modules rather than sitting
   in one. With `pytest-xdist` installed for the experiment and not committed,
   `-n auto` on ten cores ran the whole suite green four times out of four, in
   91, 82, 87 and 151 wall seconds against 218 serial, and
   `tests/test_determinism.py` alone passed five runs out of five under it.
   Total CPU rose from 197 s to 231 s, which is worker startup and combining. A
   four-worker run took 160 s here, but the machine was not idle, so that is not
   the shape of a four-core runner and should not be read as one. The costs are
   two new dev dependencies — `pytest-xdist` pulls `execnet` — and the
   obligation below.
2. **Split the CI job so the fast stages report first.** Buys nothing for the
   local wait, which is where the issue locates the pain: the same 218 seconds
   are still spent on the contributor's machine. What it costs depends on a
   shape the issue does not fix. A second job that runs the fast stages ahead of
   the job that still runs `make verify` duplicates a few seconds of work and
   leaves the equivalence intact — `ci.yml` already carries three jobs, and what
   `tests/test_ci_workflows.py` asserts is that `ci.yml` runs `make verify` at
   all.
   Decomposing `verify` into per-stage jobs instead would be the first time CI
   and a contributor ran different gates, and the equivalence that
   `tests/test_ci_workflows.py` exists to hold is exactly what that spends.
   Which of the two is meant is the maintainer's to say; the first is cheap and
   the second is not, and neither is chosen here.
3. **Move the three-run determinism suite into its own job.** Buys 6.7% of the
   pytest stage, which is 6% of the gate, and costs the local half of the
   evidence for RG-15 and invariant 10 — the determinism proof would then exist
   only where CI runs it, not on the machine the change was written on. That is
   the measured price; whether 6% is worth it is not a measurement.

A fourth was found while measuring and is recorded so that it is not found
again. Coverage.py can trace through `sys.monitoring` (`COVERAGE_CORE=sysmon`)
rather than through its C tracer. That needs no dependency and changes nothing
about what is checked, which makes it the most attractive of the four on paper.
It is not adopted, because the one check it has to pass — that it measures the
same thing — could not be completed, for the reason in the next paragraph.

### What could not be established: the coverage number is not reproducible

The measured coverage that the floor is applied to is not the same number twice.
Across six runs of the identical serial command on this tree, the reported
missing-statement total was 147 three times and 149 three times; four ten-worker
runs reported 147 once and 149 three times, and a single four-worker run
reported 145. Every difference is in one module,
`src/contextsafe/evidence_store.py`, and in the arms of `_ensure_store` and its
hierarchy walk that run only when another writer got there first — two lines
across the serial runs, and two more in the four-worker run.
`tests/test_evidence_store.py` reaches those arms with real threads: a two-way
`Barrier`, and a six-thread pool over identical imports. Which arm a thread
takes is a scheduling outcome, so which of those lines executes moves from run
to run.

Two consequences, both narrow. Comparing coverage totals cannot be the
equivalence test for a change to how the suite runs, which is exactly the
evidence a parallel gate or a re-tracered gate would need in this repository;
that is why option 1 and the fourth option are recorded here rather than taken.
And a reader who treats the 98% as a reproducible figure is taking more from it
than it carries — the floors are 90% and 95%, the headroom is wide, and no
verdict has moved, but the number drifts by about four statements. Fixing that
is not this issue, and nothing here changes it. Nothing indexes it either: no
backlog item covers it and no issue is open on it, so it needs one before the
derived `backlog-status` column can carry it, and until then this paragraph is
the only place it exists.

**Nothing is decided here.** The measurement says what each option buys and
what it spends; which one to take, and whether four minutes is a cost worth a
dependency inside the merge gate, is the maintainer's call. What the measurement
settles is narrower than a choice. The determinism suite is not where the time
goes, so option 3 buys 6% of the gate rather than the bulk of it. Option 2 buys
nothing locally, and its price is a second CI job whose shape decides whether CI
still runs the target a contributor runs. Option 1 is the only one whose shape
matches a diffuse cost, and it needs a way to prove it measures the same thing —
which, by the finding above, comparing coverage totals cannot give it. Ranking
those against each other is a judgment about what the wait is worth, and this
section does not make it.

## What would make this program wrong

Recorded so a later reader can check it rather than inherit it:

- If phases 2 to 6 produce no finding that a reviewer agrees was worth catching,
  the defect class was exhausted at phase 1 and the rest is ceremony. Stop.
- If the exemption mechanism from phase 1 accumulates entries faster than it
  retires them, it has become the hole it replaced. Every honored exemption is
  printed on every run specifically so this is countable.
- If a gate is ever made to pass by narrowing what it examines rather than by
  fixing what it found, that is this program's defect class committed by the
  program itself.
