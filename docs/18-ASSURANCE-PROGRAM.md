# Assurance program: a multiyear plan for the gates themselves

Status: proposed, phases 1 and 2 built
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

**Status: planned, not built.**

After phase 1, every gate knows its denominator but each states it in its own
words, on stdout, where nothing compares them. A reader who wants to answer
"what does `make verify` actually cover?" still has to read five programs.

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

**Status: planned, not built.**

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
retrofit per gate.

### Phase 5 — Evidence that the suite can detect a regression

**Status: planned, not built.**

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

**Status: planned, not built.**

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
