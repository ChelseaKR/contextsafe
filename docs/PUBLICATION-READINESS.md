# Publication readiness

**Audit date:** 2026-08-15 · **Commit audited:** `main` @ `09e0317` (open PRs
#11 and #12 excluded) · **Visibility when audited:** PRIVATE · **Recorded
publication state:** the maintainer decided on 2026-08-15 to publish (Gate 0);
the visibility change itself is a separate, deliberate act and was not made by
this document. It has since been made — see the 2026-08-29 update below

**Verdict: technically ready to publish, pending an IP clearance the maintainer
must obtain and a dual-use decision that is hers and her governance group's to
make.** Every technical gate below passes or has a stated, bounded remediation.
None of them answer Gate 0, which governs whether this repository may become
public at all, and none of them answer Gate 1, which governs whether it should.

Publication is the maintainer's recorded decision. This document exists to make
that decision cheap and safe to make — not to make it.

**Update, 2026-08-15 — the maintainer has decided to publish.** The verdict above
is the audit's, unchanged, and everything it found stands as written. What
changed is the decision on top of it: Gate 0 was reviewed and closed by the
maintainer as a decision rather than an adjudication (see the status line below),
and the four dual-use gaps Gate 1 identified were closed in the corpus itself —
TB-10, the public-reader actor, T-16 through T-18, the inversion stated in
`docs/06` section 1 and in the README, R-25 splitting the harm half out of R-23,
HAZ-09, a publication row in the `docs/07` decision-rights table, and a
[publication policy](17-PUBLICATION-POLICY.md) whose own decisions remain open
for the maintainer to record. Gate 1's substantive holding is unchanged and still
governs: publishing these contents is defensible, and the pack question must be
decided before B-009 authoring begins.

The prior employer is deliberately not named anywhere in this file. A
publication-readiness document becomes public with the repository it audits,
and the sweep below confirms that name appears nowhere in this history today.

**Update, 2026-08-29 — this document is now being read on the public
repository, and parts of it are no longer true of that repository.** Nothing
below is retracted or softened; every finding stands as the audit wrote it. What
changed is the repository underneath, and a reader about to run one of these
commands should know that before it fails rather than after.

- The repository is public. `gh repo view ChelseaKR/contextsafe --json isPrivate`
  returns `false`.
- **The commit names cited here are unreachable from any branch, and GitHub
  still serves them.** `09e0317`, `bba81c8`, `a557626`, `cbcb9e3` and
  `d3d3d04` are `fatal: bad object` in a fresh `git clone`, whose `main` begins
  at `a8b62c9`, because a clone fetches only what its refs reach. GitHub keeps
  unreachable objects and serves them by explicit id, so every one of these
  resolves over the API and the web. The history this audit read is not the
  history a clone gets; it is still the history the host will hand to anyone who
  asks for it by name.
- **§6's docs finding is NOT closed. The document is still served, publicly and
  without authentication.** Checked 2026-08-29 against the live repository:

  ```
  gh api "repos/ChelseaKR/contextsafe/contents/docs/11-GTM-BUSINESS-MODEL.md?ref=a557626"
    -> name=11-GTM-BUSINESS-MODEL.md size=10187

  curl -so /dev/null -w '%{http_code}' \
    https://github.com/ChelseaKR/contextsafe/blob/a557626/docs/11-GTM-BUSINESS-MODEL.md
    -> 200

  curl -so /dev/null -w '%{http_code}' \
    https://raw.githubusercontent.com/ChelseaKR/contextsafe/a557626/docs/11-GTM-BUSINESS-MODEL.md
    -> 200
  ```

  The `git show` printed in §6 fails for a reader who only cloned, which is why
  this was briefly recorded here as closed. That was wrong, and the direction of
  the error is the dangerous one: it told a reader an exposure was over while it
  was live. **The option-B cost has not been paid**, §6 stands exactly as
  written, and row 9 of the summary table ("still fully recoverable from
  history") is the accurate line.

  Two things follow. Removing the blob takes more than a history rewrite: GitHub
  keeps unreachable objects until it garbage-collects, which a repository owner
  cannot trigger and which forks and cached views can outlive, so closing this
  means asking GitHub Support to purge, or accepting the content as public.
  And this document is itself part of the exposure surface: it prints the commit
  ids by which the blob is addressed, so publishing the audit is what makes the
  pointer easy. That is a maintainer's call, recorded here rather than quietly
  fixed.

  A clone taken before the rewrite also still holds the blob. That was always
  true and is not the point; the point is that the published repository does.

One thing §7 is not: a running total. Every figure in it is a measurement of one
`make verify` run at the commit that section names, correct for that run and
stale by construction thereafter. Re-run the command rather than reading the
number.

---

## Gate 0 — IP / inventions-agreement clearance (MAINTAINER + ATTORNEY)

**Status: REVIEWED BY THE MAINTAINER AND CLOSED AS A DECISION, 2026-08-15. She
read this section, weighed the question it raises, and decided to proceed with
publication.**

Read that status precisely. It records a decision, not a resolution. No
adjudication has occurred, no opinion of counsel is recorded in this repository,
and nothing below has been retracted, softened, or re-tested: every fact in the
table, every limit on what the sweeps could establish, and the analysis of the
unresolved question stand exactly as the audit wrote them. The maintainer decided
with the question open, which is a legitimate thing to do and is worth recording
as what it is.

| Fact | Evidence |
|---|---|
| Repository created **2026-07-14** (`2026-07-13 21:40 PDT` local) | `gh repo view ChelseaKR/contextsafe --json createdAt` → `2026-07-14T04:40:32Z` |
| First commit **2026-07-13T21:41:33-07:00** | `git log --reverse`: `a557626 add v1 delivery plan` |
| Employment ended **2026-07-21** — **seven days after creation** | maintainer-supplied fact; it is not derivable from this repository |
| `main` spans **2026-07-13 → 2026-08-04**; branch work continues to 2026-08-15 | `git log main --format=%ad`; 14 commits on `main`, 26 across all refs |
| Authored under **personal identity and a GitHub noreply alias** throughout | every author and committer is `Chelsea Kelly-Reif` (three display spellings) at `3114598+ChelseaKR@users.noreply.github.com`; the only other committer is `GitHub <noreply@github.com>` on 10 squash merges |
| **No employer address, system, or asset appears anywhere** | 0 hits for the employer name and every consultancy/agency term across all 193 blob objects in the object database, all 37 commit objects, and all commit messages; no `/Users/`, `/home/`, `C:\Users`, no internal hostname, no VPN/Jira/Confluence/Okta reference |
| **No `NOTICE` asserting independent authorship exists** | `ls NOTICE` → absent. The sibling repository has one; this one does not |

**The unresolved question.** The creation date falls **during prior
employment**, and the subject matter — clinical informatics tooling for
registration, EHR, HL7/FHIR, and laboratory workflows — sits closer to that
former employer's line of business than most of this maintainer's personal
projects, because that employer carries a healthcare engineering portfolio.
Depending on the wording of the applicable inventions/IP agreement and on state
law, an assignment obligation can attach to work created during employment even
when it is authored on personal time and equipment, and the "related to the
employer's business" test is exactly where such clauses bite. Seven days is a
short interval, and a repository initialized one week before a departure is the
fact pattern such clauses are written to reach.

**Nothing in this repository resolves that.** There is not even the sibling
repository's `NOTICE`, and adding one now would not resolve it either: a
`NOTICE` is the author's own assertion, evidence of intent rather than an
adjudication. No scan, test, or gate below speaks to the question. What the
sweeps *can* say — and do say above — is narrower and still useful: no employer
address, system, credential, code, or asset is present in any version of this
history, and every commit is authored under personal identity.

**This is a question for the maintainer's attorney**, and it should be answered
*before* visibility changes, because publication cannot be undone in the way
that matters: a repository can be un-published, but it cannot be un-seen.

Until it is answered, the correct state is the current one: repository private.

**Maintainer's decision, 2026-08-15.** The two paragraphs above are the audit's
recommendation, kept verbatim, and on the timing point the maintainer decided
otherwise: she reviewed the finding, weighed the risk it describes, and elected
to proceed with publication without an attorney's answer on the record here.
That is her call to make. The record preserves both the recommendation and the
departure from it, because a document that quietly deleted the recommendation
once it was overridden would be a worse record and a less honest one. The
irreversibility the audit names is unchanged and is now carried as a standing
control rather than a warning: TB-10 in `docs/06`, and the
[publication policy](17-PUBLICATION-POLICY.md) that governs everything crossing
it.

---

## Gate 1 — dual-use and misuse (MAINTAINER + CLINICAL CHAIR + COMMUNITY CO-CHAIR)

**Status: OPEN, and not resolvable by a scan. This gate is a judgment, and the
judgment belongs to the maintainer and the governance group `docs/07` defines.**

**Update, 2026-08-15.** The four documentation gaps this gate found are closed;
the judgment it describes is not, and closing the gaps did not close it. What
exists now is a written threat, a named owner, and a decision document with the
options laid out. What does not exist is the governance group that owns the pack
decision, so the [publication policy](17-PUBLICATION-POLICY.md) blocks
publishing locator material until both governance chair seats are filled. The
gate stays open until its decision record names a date.

### What this tool actually maps

ContextSafe's stated capability is to find the first boundary at which gender
identity, recorded sex or gender, sex parameter for clinical use, name to use,
and pronoun data stops surviving as it crosses registration, EHR, interface,
and laboratory systems. A-032 through A-035 exist to localize that boundary,
and `docs/09` section 4 enumerates 36 seeded faults describing precisely how
each value gets dropped, coerced, overwritten, or silently normalized.

The inversion is unavoidable and is worth stating in one sentence, because no
document in this repository states it: **a tool that reports where trans
identity data is lost is, in the same breath, reporting where it is retained.**
A receipt that says "the value was absent at the laboratory" also says "the
value was present in the EHR at version X." That is the artifact's purpose and
also its dual use.

*"No document in this repository states it" was true when this audit was written
and is not true now. The sentence is stated in `docs/06` section 1, `docs/07`
section 14, `docs/17` section 1, and the README. The finding is left standing
because it was the finding.*

### What publishing today would and would not disclose

| Published today | Not published today |
|---|---|
| JSON Schemas, a deterministic evaluator, an unsigned pack/plan compiler, a read-only evidence boundary check | Any governed case pack (B-009) or approved assertion (B-010) — none exists |
| Five synthetic fixtures using invented tokens (`CSYN-`, `fixture-gender-1`) | Any real system, vendor, version, customer, or partner name — none exists |
| The concept separation itself: GI ≠ RSG ≠ SPCU ≠ NtU ≠ pronouns, and why conflating them harms patients | Any receipt about any real installed workflow — none has ever been produced |
| The four-checkpoint model and the seeded-fault taxonomy | Reviewer identities — the governance roster is unrecruited |

The concept separation this repository encodes is HL7 Gender Harmony, which is
published, and the extension shapes it names are documented in FHIR and US Core.
The marginal uplift a hostile reader gains from this repository *today* is
therefore small: it organizes public standards material into a testing
methodology; it does not disclose where any particular organization keeps trans
patients' data.

That is a statement about today's contents, not about the product. It stops
being true at B-009/B-010, when a governed twelve-case pack and 36 reviewed
assertions would encode, in one reviewable artifact, exactly which fields at
which boundaries carry this data and exactly how to detect their presence. It
stops being true a second time when a receipt about a named system exists.

### What the threat model already covers

`docs/06` does address surveillance-adjacent harm, and the language is not
weak. Section 4 lists as a misuse case:

> Actor using customer/reviewer relationships to identify trans people or
> organizations.

T-08 in the STRIDE table:

> | T-08 | Information disclosure | Customer/reviewer list exposes trans
> affiliation | confidential CRM, minimum access, no public attribution by
> default, no tracking | legal compulsion/insider |

Section 10 names two of the right risks outright:

> - Test scenarios could normalize excessive collection of sensitive fields.
> - Published output could encourage surveillance or forced disclosure.

`docs/07` section 8 acknowledges the political frame:

> Federal and state nondiscrimination requirements are legally and politically
> volatile. ContextSafe should sell consistent patient safety and data
> integrity, not promise that a receipt proves compliance with any current
> civil-rights regime.

And `docs/02` forbids exposing a partner: "Never publish a partner's defects,
screenshots, system names, or reviewer identities without written permission."

That is a real and unusually careful treatment of *operational* exposure, and
`legal compulsion` appearing in a residual-risk column is more honesty than most
threat models manage.

### What the threat model does not cover

Four specific gaps, stated plainly. Each is followed by what closed it on
2026-08-15; the findings themselves are unedited.

1. **No actor is a reader of a public repository.** Every threat actor in
   section 4 is an operator, an insider, an external attacker, a compromised
   dependency, a vendor or customer misusing a receipt, an overconfident
   clinician, or the founder. Trust boundaries TB-01 through TB-09 are all
   operational — evidence intake, staging connection, mapping, pack update,
   workspace, signing, receipt transfer, build chain, support channel. Open
   publication is not among them.
   **Closed 2026-08-15:** TB-10 (publication) is in `docs/06` section 3, with
   the note that it differs in kind from the others because it is crossed
   deliberately and cannot be uncrossed. Section 4 adds three actors: the reader
   of published project material, the party using lawful process, and the
   maintainer publishing under time pressure.
2. **The inversion is never written down.** Nothing in `docs/06` or `docs/07`
   says that the artifact locating loss also documents retention. Every control
   in section 6 is aimed at keeping PHI *out*; none is aimed at what the
   findings themselves reveal once they exist.
   **Closed 2026-08-15:** stated in `docs/06` section 1 under its own heading,
   in `docs/07` section 14, in `docs/17` section 1, and in the README's "Dual
   use" section, which a stranger reads before the quickstart. T-16 gives it
   controls; the residual-risk list says plainly that withholding buys friction
   rather than secrecy.
3. **R-23 analyzes the wrong half of its own title.** The risk is stated as
   "Political/certification changes weaken demand **or increase harm**," and
   every mitigation and contingency addresses demand — "patient-safety
   positioning; multiple buyer triggers; quarterly policy watch," contingency
   "focus risk/insurer/lab channels; mission remains but market may shrink."
   The harm half is never analyzed anywhere in the corpus.
   **Closed 2026-08-15:** R-23 is now scoped to demand alone, and the harm half
   is R-25 (P3 I5, score 15, owner COM/F/LEG) with its own mitigations, leading
   indicators, and an explicitly irreducible residual. R-26 separates compelled
   disclosure. The register records the split so the change is traceable rather
   than silent.
4. **No publication policy exists.** `docs/07` section 3 assigns approval for
   an "Intended-use/marketing claim" to the founder, clinical chair, community
   co-chair, and counsel. Nothing assigns approval for *publishing an artifact*
   — not the pack, not a receipt, not the repository. The compelled-disclosure
   question ("a customer is ordered to produce its receipts") has no owner.
   **Closed 2026-08-15:** [`docs/17`](17-PUBLICATION-POLICY.md) is the policy;
   `docs/07` section 3 now carries four publication rows and a repository
   visibility row, section 4 a RACI row, section 7 HAZ-09 and HAZ-10, and
   section 14 the governance statement. Compelled disclosure has an owner
   (counsel, T-18, R-26) and a design constraint: minimization, because the only
   control that works against valid process is having little to produce.
   The policy's own decisions — including whether the pack payload is ever
   published — are open and recorded as options with a recommendation, which is
   the state this gate says they should be in.

### The honest balance

Publishing **this** repository, in **this** state, is defensible. It contains
no governed clinical content, no customer, no receipt, no reviewer identity,
and no capability a determined adversary could not assemble from published HL7
and FHIR material. The people most exposed by publication are not patients;
they are the maintainer, whose public authorship permanently associates a named
individual with trans-health data infrastructure in a hostile environment, and
future reviewers, whose participation is itself a disclosure — which is why
`docs/06` section 10 already gives reviewers an attribution choice and why the
governance roster should inherit that choice before it is recruited in public.

The argument against is not that this code is dangerous. It is that
publication is a ratchet: it is easier to open a repository than to reason
later about a pack that should never have been public, and the governance
structure that would make that call does not exist yet. Publishing now
establishes an open-by-default posture for a project whose most sensitive
artifacts have not been built.

That is a real cost, and it is the maintainer's to weigh. It is not a reason to
keep this repository private today; it is a reason to decide the pack question
before it becomes urgent.

### What should be decided, and when

| Decision | Owner | When | Status (2026-08-15) |
|---|---|---|---|
| Publish this repository at its current contents | maintainer, after Gate 0 | now | **decided** — maintainer elected to proceed; Gate 0 closed as a decision, not an adjudication |
| Whether the governed pack and assertions are ever published, licensed to customers, or held | clinical chair + community co-chair + counsel (`docs/07` §3) | **before B-010 authoring begins**, not after | **framed, not decided** — `docs/17` §5 sets out four options and recommends split publication ("publish the judgment, withhold the locator"). The policy moves the deadline one step earlier, to **before B-009**, because the case manifests are already the artifact that encodes necessity and prohibited inference. `docs/13` carries it as a dependency on B-009 |
| Posture on compelled disclosure of a customer's receipts | counsel + customer contract (`docs/07` §8) | before the first paid pilot | **owned** — T-18, R-26, and `docs/17` §9 name counsel and state minimization as the operative control. The contract language itself is still to be drafted |
| Add publication as an explicit trust boundary, adversarial actor, and hazard | security/privacy lead + community co-chair | at the next threat-model review | **done** — TB-10, three new actors, T-16/T-17/T-18, HAZ-09/HAZ-10 |

A concrete form for the last row, offered as drafting material and not as an
adopted control: a TB-10 for published artifacts, an actor entry for "reader of
public project material seeking to locate or pressure trans patients or the
organizations serving them," and a HAZ-09 in `docs/07` section 7 whose control
is the pack-publication policy above and whose release evidence is the recorded
governance decision.

That drafting material was adopted on 2026-08-15 in substantially the shape
proposed, with two additions the audit did not name: a lawful-process actor with
its own STRIDE row, and a contributor-exposure hazard, because publication turns
every contributor into a disclosure and the corpus previously gave that choice
only to reviewers.

**This gate does not block publishing the current contents. It blocks treating
publication as settled for everything that comes after.**

---

## Technical gates

Legend: **PASS** · **PASS (fixed here)** · **ACTION** — remediation stated,
maintainer decides · **MAINTAINER'S CALL** — a choice, not a defect.

| # | Gate | Status | Evidence |
|---|---|---|---|
| 1 | Full-history secret scan | **PASS** | gitleaks 8.30.1 over all refs and over the working tree: *no leaks found*; see §1 |
| 2 | Employer-adjacent reference sweep | **PASS** | 0 hits across all 193 blobs and 37 commit objects; see §2 |
| 3 | Private repo names, internal hosts, personal paths | **PASS (fixed here)** | one live pointer to a private sibling repository reworded; 0 hits for hostnames and filesystem paths; see §2 |
| 4 | Every fixture synthetic; no real patient data anywhere | **PASS** | 5 fixture files, namespace enforced in code; see §4 |
| 5 | License correctness | **PASS** | complete unmodified Apache-2.0, `Copyright 2026 Chelsea Kelly-Reif` |
| 6 | `NOTICE` | **ACTION** | absent; Apache-2.0 does not require one, and its content is an assertion only the maintainer can make; see §5 |
| 7 | `CITATION.cff` accuracy | **PASS (fixed here)** | valid CFF 1.2.0 that advertised a release never cut — 0 tags, 0 GitHub releases; corrected, see §5 |
| 8 | `schemas/` publication intent | **ACTION** | 5 of 11 schemas claim `$id` under the **unregistered** domain `contextsafe.dev`; see §6 |
| 9 | `docs/` publication intent — deleted GTM/pricing document | **MAINTAINER'S CALL** | still fully recoverable from history; see §6 |
| 10 | Clean-clone verification | **PASS** | fresh clone, `make verify` green, README quickstart reproduces the pinned digest; see §7 |
| 11 | CI parity and workflow hygiene | **PASS** | `ci.yml` runs the literal `make verify`; all actions SHA-pinned; see §8 |
| 12 | Telemetry / analytics | **PASS — none exists** | no networking import in any version ever committed; see §9 |
| 13 | Claim accuracy against the code | **PASS** | README hedging matches what the code proves; see §10 |
| 14 | Tracked cache, venv, or environment artifacts | **PASS (fixed here)** | none tracked, ever; `.hypothesis/` added to `.gitignore`; see §11 |
| 15 | AI-authorship trailers and session URLs in history | **MAINTAINER'S CALL** | 20 commits carry a `Co-Authored-By: Claude` trailer, 9 carry a session URL; see §12 |
| 16 | Personal email as the disclosure channel | **ACTION** | `SECURITY.md` publishes a personal address *because* the repo is private; see §12 |
| 17 | Supported-platform claim vs shipped behavior | **ACTION** | `docs/10` lists Windows 11; three commands fail closed there; see §13 |

### §1 Secret scan

```
gitleaks detect --no-banner --redact -v --log-opts="--all"
  → 22 commits scanned (24 reachable minus 2 merges, which add no blobs;
    the scan predates the two commits on the open PR branches, and `main`
    is unchanged since)
  → ~1.27 MB scanned
  → no leaks found

gitleaks detect --no-git --no-banner --redact -v     # working tree + untracked
  → ~2.29 MB scanned
  → no leaks found
```

trufflehog is not installed on this machine and was deliberately not installed
for one audit. The compensating control was a regex battery run over **all 193
blob objects in the object database** — a strict superset of `git log -p --all`,
since it includes unreachable and orphaned blobs — plus all 37 commit messages:
private-key headers, `AKIA`, `ghp_`/`gho_`/`ghs_`/`github_pat_`, `xox*`, JWTs,
bearer/authorization headers, `api[_-]?key`, `password`, `token =`, `.env`
content, and base64 runs over 100 characters. **Zero hits.** The only
`secret`-keyword matches are `${{ secrets.GITHUB_TOKEN }}` in
`.github/workflows/security.yml`, the Python standard library's `secrets` module
in `src/contextsafe/evidence_store.py`, and prose in the planning docs.

If a second opinion is wanted before publishing, run
`trufflehog git file://. --exclude-detectors=Lob` (the `Lob` exclusion avoids a
known upstream false positive).

### §2–3 Employer, private-repo, and path sweep

| Term class | Hits |
|---|---|
| Former employer name and every consultancy/agency term tried | **0** |
| Other private repository names in this portfolio | **0** |
| `/Users/`, `/home/`, `C:\Users`, `/Volumes/` | **0** |
| `*.internal`, `*.corp`, `*.local`, VPN/Jira/Confluence/Okta/SharePoint | **0** |
| Real people other than the maintainer | **1**, a public citation: Michael Nygard, credited in `docs/adr/0000` for the ADR format |
| Email addresses in all history | **2**: `person@example.invalid` (an RFC 2606 canary used in rejection tests) and the maintainer's own address in `SECURITY.md` — see §12 |

Two cross-repository pointers were live in the working tree, and one of them
resolves nowhere for a public reader:

- `README.md` — "this repository should inherit the portfolio standards in
  `../STANDARDS`" and "Status against the portfolio standards (per the portfolio
  applicability manifest…)". These name a **private** sibling repository and a
  path that exists only inside the maintainer's local checkout. **Fixed here:**
  reworded to describe the standards as the maintainer's own, without a path a
  reader cannot follow. The conformance table itself is unchanged and still
  useful.
- `.github/PULL_REQUEST_TEMPLATE.md` — `[definition of done](../DEFINITION_OF_DONE.md)`.
  **Verified correct, not a defect:** the template lives in `.github/`, so the
  relative link resolves to this repository's own root `DEFINITION_OF_DONE.md`.

Two commit subjects (`d3d3d04`, `cbcb9e3`) cite "CI-CD-STANDARD §11h", a section
number in the private standards repository. It leaks no content, only the fact
that an unpublished internal standards document exists. Left as-is; rewriting
history for a section number is not worth the cost, and the fact is unremarkable.

### §4 Synthetic-data confirmation

`fixtures/` holds exactly five files, 7,957 bytes total, and **no fixture path
has ever been deleted** — the 89-path full-history file list contains no other
fixture.

| File | Evidence that it is synthetic |
|---|---|
| `case.json` | `urn:contextsafe:synthetic`, `CSYN-CTP-I01`, name `CSYN-ASTER`, `fixture-gender-1` under `urn:contextsafe:fixture`, `source: synthetic-fixture` |
| `observations.json` | `OBS-I01-*` identifiers; `CSYN-`/`fixture-` values; evidence pointers are SHA-256 only |
| `evidence-source.json` | `PLAN-SYNTHETIC-TEST`, `CSYN-CTP-I01`, `CSYN-PRONOUN-THEY-THEM` |
| `pack-draft.json` | `PACK-SYNTHETIC-REFERENCE-DRAFT`, limitations `synthetic-reference-only`, `not-clinically-reviewed`, `not-community-approved` |
| `rules.json` | expectations mirror the values above |

No name, MRN, date of birth, address, phone number, SSN, or NPI appears in any
fixture; there is no `birthDate` field anywhere. The rule is enforced in code,
not by convention — `src/contextsafe/plan.py` pins
`SYNTHETIC_IDENTIFIER_SYSTEM`, `SYNTHETIC_VALUE_PREFIX = "CSYN-"`, and
`^CSYN-CTP-[A-Z0-9]{3,16}$`, and rejects anything outside them.

The only PII-shaped literals in the repository are deliberate rejection canaries
in `tests/test_preflight.py`: `123-45-6789` (the textbook invalid SSN),
`415-555-0199` (the reserved fictional range), `MRN: ABCD1234`,
`person@example.invalid`, `https://patient.invalid/record`. Each exists to be
refused, and a companion assertion requires that the refusal never echoes it.

### §5 License, NOTICE, and citation

`LICENSE` is the complete, unmodified Apache-2.0 text with the appendix filled
in as `Copyright 2026 Chelsea Kelly-Reif`. Nothing further is required for
publication.

**`NOTICE` — ACTION.** There is none. Apache-2.0 only obliges downstream
recipients to propagate a `NOTICE` if one exists, so its absence is not a
license defect. It is worth adding one anyway, because the sibling repository's
version does useful work: it states that the project is independent and
personal, authored on the author's own time and equipment, and contains no
employer- or client-proprietary code, data, or methods. **That text is an
assertion about the maintainer's own employment, so it is hers to write and not
this document's to draft.** Note also that it is evidence of intent, not an
answer to Gate 0.

**`CITATION.cff` — PASS (fixed here).** The file was valid CFF 1.2.0, but
carried `date-released: 2026-07-17` while `git tag -l` is empty and
`gh release list` returns nothing. It advertised a release that was never cut —
the same defect the sibling audit found. **Fixed here** the same way the sibling
fixed it: the field is removed, with a comment recording that CFF treats
`version` and `date-released` as optional and that both return when a release is
actually tagged.

### §6 `schemas/` and `docs/` publication intent

**Schemas — ACTION.** Eleven schemas, six using `$id` under
`https://contextsafe.invalid/` and five under `https://contextsafe.dev/`:

```
contextsafe-compiled-pack-v1  contextsafe-compiled-plan-v1
contextsafe-engagement-v1     contextsafe-pack-v1
contextsafe-plan-v1
```

`contextsafe.dev` resolves to nothing — no A record, no NS record. On a public
repository that is a squattable identity: anyone may register the domain and
serve documents at `$id`s this project publishes as canonical. The split is
also simply inconsistent. Two clean options, both the maintainer's: register the
domain, or move all eleven to `.invalid`. Not fixed here, because a `$id` is
published contract identity and `schemas/` is a code-owner-reviewed path.

**Docs — MAINTAINER'S CALL. Closed since: see the 2026-08-29 update at the top.
The commit names and the `git show` below do not resolve on the published
repository, and the file is in none of its refs.** `bba81c8` ("docs: move
working notes to the private archive") deleted `docs/11-GTM-BUSINESS-MODEL.md`
and scrubbed dollar figures from five other documents. The content was never
removed from history:

```
git show a557626:docs/11-GTM-BUSINESS-MODEL.md     # 221 lines, still returns
```

The blob is reachable from 29 commits, including the first. Making the
repository public makes that recoverable by anyone. It exposes the full pricing
ladder, unit economics and margin floors, the 90-day founder plan, the
qualification scorecard, the objection-handling script, and the commercial kill
gates. It contains no customer name, no third-party confidential information,
and no employer material — the exposure is competitive and negotiating position,
not privacy.

**If the intent of `bba81c8` was "this is private now," a delete commit does not
achieve it.** Options, for the maintainer, and no history rewriting has been
attempted:

| Option | What it costs | What it leaves |
|---|---|---|
| **A. Publish as-is** | Nothing | Pricing and GTM strategy readable by anyone who runs one `git show`. Defensible if the figures are stale or unembarrassing |
| **B. `git filter-repo` the file out of history** | Rewrites every commit SHA; breaks clones and PR references; the scrubbed figures in five other documents need the same treatment | Full history, document removed |
| **C. Publish a fresh repository from the current tree** | New repository with no history; the private one is retained as the archive | Clean public history, private history preserved |

**Recommendation for the decision, not the decision itself:** if the pricing is
still the pricing she intends to quote, option A gives every prospect her
negotiating floor for free, and option C is the cheapest of the rewriting
options because this repository has almost nothing external to break: zero
forks, zero stars, and no published tag.

### §7 Clean-clone verification

From a fresh clone of `main` at `09e0317`, in a directory unrelated to the
working checkout:

| Step | Result |
|---|---|
| `git clone --branch main --single-branch …` | 85 tracked files, no submodule, no LFS pointer |
| `make verify` | **green in 15.7s** — frozen sync, ruff lint and format, mypy `--strict`, 469 tests, 95.6% overall and 96% safety-module branch coverage, `pip-audit` clean, hygiene clean |
| README quickstart, exactly as written | `uv run contextsafe evaluate … --output receipt.json` → exit 0 |
| Receipt digest | `f34e58fa…3dce80`, identical to the digest the CI determinism matrix reproduces on Ubuntu, macOS, and Windows in PR #11 |
| `contextsafe validate` | exit 0 |
| `contextsafe pack validate` on the committed draft pack | exit 2, `pack_not_active` — the documented, intentional failure |
| Private-resource dependency | none. `uv.lock` resolves only `pypi.org` and `files.pythonhosted.org`, with zero VCS dependencies |

One documentation observation, not a defect: a visitor can run `validate` and
`evaluate` end to end, but the extended walkthrough's `pack validate`,
`plan validate`, and `evidence preflight` examples use `path/to/…` placeholders,
and the repository ships no runnable plan or engagement fixture. The draft pack's
failure is documented as intentional; the missing plan fixture is not mentioned.
Worth one sentence in the README before publishing.

### §8 CI parity and workflow hygiene

`ci.yml` runs the literal `make verify` — the same gate a contributor runs
locally — on `ubuntu-24.04` with `UV_PYTHON_DOWNLOADS: never` and the frozen
lockfile. `release.yml` re-runs it at a tag and gates on a matching CHANGELOG
section; it has never fired, because no tag exists, and it deliberately has no
publish or sign step rather than a stub that would always report success.
`security.yml` runs Semgrep, gitleaks, and pip-audit on push, PR, and weekly.

Every action is SHA-pinned with a version comment, `persist-credentials: false`
is set on every checkout, job permissions are `contents: read` (plus
`pull-requests: read` where gitleaks needs it, with the reason recorded inline),
and the release job disables the shared cache on the tag path. `actionlint` and
`zizmor --persona=regular` are clean.

### §9 Telemetry, analytics, and network egress

**None exists, in any version ever committed.** The complete import inventory
across all 193 historical blobs contains no `requests`, `urllib`, `httpx`,
`aiohttp`, `socket`, `http.client`, `subprocess`, `posthog`, `segment`,
`sentry`, `analytics`, `opentelemetry`, `statsd`, or `datadog`. No source file
constructs or fetches a URL; the only URLs in code are JSON Schema `$id` and
`$schema` identifiers, which are never dereferenced. `ipaddress` appears in
`contract_validation.py` solely to *reject* raw IP forms in the host allowlist.

The documented intent matches: `docs/10` section "No telemetry" and `docs/04`
"No product analytics leaves the customer environment in v1."

Two egress points exist in CI only, outside the product, and both are worth
knowing before publication: `semgrep ci --config auto` contacts the Semgrep
registry at run time and sends project metadata (a pinned local ruleset removes
that call), and `pip-audit` queries the PyPI advisory database.

### §10 Claim accuracy

The README's hedging is load-bearing and, as far as this audit can determine,
accurate. It states that no clinically governed, cryptographically authorized,
or externally validated product exists; that the code proves only bounded
offline fixture evaluation, unsigned contract compilation, a read-only
code-envelope boundary check, and an internal-test evidence-store primitive;
that the committed reference pack is intentionally `draft` and must fail
compilation; that declared approvals are not authenticated signatures; that the
preflight scanner is a fallible boundary check rather than proof of no PHI; and
that the work was built ahead of the plan's discovery and governance gates and
cannot be represented as pack approval, pilot evidence, or V1 progress.

Nothing in the repository implies users, adoption, scale, clinical validation,
or regulatory approval. There is no badge, no metric, no adoption claim, and no
"trans-safe score" — `docs/12` section 8 explicitly forbids the last one.

### §11 Working-tree hygiene

No cache, virtualenv, coverage, or environment artifact is tracked, and none
ever was: `git ls-files` matches nothing against `venv`, `__pycache__`,
`coverage`, `mypy_cache`, `hypothesis`, `pytest_cache`, `ruff_cache`, `.cache`,
`.env`, `dist/`, `build/`, or `*.egg-info`, and neither does the full 89-path
history. `.gitignore` additionally carries two thoughtful project-specific
rules, `artifacts/customer/` and `receipts/private/`.

One gap, **fixed here**: `.hypothesis/` was not in `.gitignore`. It was ignored
only because Hypothesis writes its own nested `.hypothesis/.gitignore`
containing `*`. Delete the directory, or use a version that stops writing that
file, and a cache of generated examples becomes committable by accident. One
line added.

### §12 Two things that are choices, not defects

**AI-authorship trailers and session URLs.** Twenty commits carry a
`Co-Authored-By: Claude …` trailer and nine carry a `Claude-Session:` URL
exposing three session identifiers. Neither is a security issue — the URLs are
not credentials and resolve only for the account that owns them. Both are
positioning choices: on a portfolio repository, every reviewer sees AI
co-authorship on the majority of substantive commits. Removing them means
rewriting history, with the same cost as §6 option B. Making the choice
deliberately is the point; this document does not make it.

**Personal email in `SECURITY.md` — ACTION.** The disclosure channel is
`ckellyreif@gmail.com`, and the file explains exactly why: "the repo is private,
and GitHub's private vulnerability reporting is not available on a private
free-plan repo." **Publishing removes that constraint.** On a public repository,
private vulnerability reporting can be enabled in settings, which gives a
disclosure channel that does not publish a personal address to scrapers.
Enabling it and updating `SECURITY.md` should happen in the same change as the
visibility flip, not after it.

### §13 Supported-platform claim

`docs/10` lists Windows 11 among supported platforms. Three of the five shipped
commands — `pack validate`, `plan validate`, and `evidence preflight` — require
descriptor-relative no-follow reads (`O_NOFOLLOW`, `dir_fd`), which Windows does
not provide, so they fail closed there with `input_path_unsupported`. That
fail-closed behavior is correct; the documentation claim is what is out of date.
PR #11 pins the behavior in a test and records the gap in the backlog. Whether
to narrow the supported matrix or design a Windows-safe read is a maintainer
decision, and it is not a publication blocker — but a public reader on Windows
will hit it.

---

## Summary for the decision

| | |
|---|---|
| **Technical readiness** | Ready. Every technical gate passes or has a stated remediation; `make verify` is green from a clean clone with no secrets, no employer reference, no real patient data, no telemetry, and no private-resource dependency. |
| **Blocking** | **Gate 0 (IP clearance)** — an attorney question, unanswered, and not addressable inside this repository. |
| **Judgment, not scan** | **Gate 1 (dual-use)** — publishing the current contents is defensible; the pack-publication policy must be decided before B-010 authoring, and the threat model has no publication actor, boundary, or hazard today. |
| **Maintainer's call, not blocking** | The recoverable GTM/pricing document (§6), the AI-authorship trailers (§12), and the `contextsafe.dev` schema identity (§6). |
| **Do in the same change as the visibility flip** | Enable GitHub private vulnerability reporting and update `SECURITY.md` (§12); consider adding a `NOTICE` (§5). |
| **Not done, deliberately** | No tag created. No release cut. No visibility change. No merges. No history rewriting. No employer named. |

The repository should stay private until Gate 0 is cleared. Gate 1 does not
block the current contents, but the pack-publication decision it names should be
recorded before the work that makes it urgent begins.

### Where the summary stands on 2026-08-15

The table above is the audit's, unchanged. Three of its rows have moved:

| Row | Then | Now |
|---|---|---|
| **Blocking — Gate 0** | open attorney question | reviewed by the maintainer and closed **as a decision**, not as an answer. The findings and the recommendation both remain on the page |
| **Judgment — Gate 1** | four documentation gaps, no publication actor, boundary, or hazard | gaps closed: TB-10, three actors, T-16/T-17/T-18, the inversion stated where readers meet it, R-23 split from R-25, HAZ-09/HAZ-10, publication decision rights, and `docs/17`. The judgment the gate names is still open, and locator material is blocked until both governance chair seats are filled |
| **Same change as the visibility flip** | private vulnerability reporting, `SECURITY.md`, `NOTICE` | unchanged and still outstanding; those are technical-gate work, not governance work |

The closing paragraph above stands as written, and the maintainer decided
otherwise on its first sentence. What replaces it is not a claim that the
question was answered; it is a decision made with the question open, recorded as
such, on 2026-08-15.
