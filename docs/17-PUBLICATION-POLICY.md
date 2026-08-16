# Publication policy

Status: **proposed decision document.** The maintainer adopts, amends, or rejects
it; nothing here is in force until §12 records a decision.
Owner: the maintainer today; clinical safety chair and community co-chair jointly
once those roles are seated ([Governance §2](07-GOVERNANCE-LEGAL-SAFETY.md)).
Scope: everything this project makes readable by someone who is not a party to a
contract — repository contents and history, documentation, schemas, packs,
assertions, receipts, fixtures, release artifacts, issues, talks, papers, posts,
and case studies.
Review: before any pack authoring milestone, before any external publication that
is not already classified below, and at each threat-model review.

## 1. Why this document exists

**A tool that reports where transgender and nonbinary identity data is lost is,
in the same breath, reporting where it is retained.** A finding that says "the
value was absent at the laboratory" also says "the value was present in the EHR
at version X, in this field, at this boundary." That is the artifact's purpose
and also its dual use. It is not a flaw to be engineered away; it is the shape of
the work, and it is why this project needs a rule about what it says in public
rather than a habit.

The rule matters on a schedule. Today this repository contains a method, a
deterministic evaluator, synthetic fixtures, and a concept separation that is
published HL7 Gender Harmony material. Someone hostile learns approximately
nothing from it that a specification would not tell them faster. That stops being
true at [B-009 and B-010](13-BACKLOG.md), when twelve governed case manifests and
thirty-six reviewed assertions would encode, in one reviewable artifact, exactly
which fields at which boundaries carry this data and exactly how to detect
whether it is there. It stops being true a second time when a receipt about a
real installed workflow exists.

So there is a window in which publishing is cheap and safe, and it closes. This
policy is meant to be decided inside the window, not during the work that closes
it.

## 2. Three disclosure classes

Every artifact this project could publish falls into one of three classes. The
classification test is one question:

> Would this text shorten the work of someone who has obtained a health data
> extract and wants to find the trans and nonbinary people in it, or who wants to
> know which organization or vendor to pressure?

| Class | What it is | Default |
|---|---|---|
| **Class 1 — method and concept** | That the five concepts are distinct and why conflating them harms patients; the four-checkpoint model; the review process, decision rights, dissent, and evidence rules; behavior-level fault classes ("a value was coerced," "a range was missing"); the evaluator, schemas, status algebra, and determinism properties; synthetic fixtures under the enforced `CSYN-` namespace | **Publishable.** No approval beyond ordinary review |
| **Class 2 — locator** | Where a concept lives in a format or at a boundary: mapping profiles, field, segment, and extension paths, the machine-readable pack payload, assertion predicates that name concrete fields, and any prioritized "look here first" ordering | **Restricted.** Not published without a recorded decision under §5 and §6 |
| **Class 3 — instance** | Any statement about a real organization, deployment, vendor, product version, customer, partner, reviewer, or person — including receipts, redacted receipts, screenshots, defect lists, and small-population aggregates | **Never published.** No approval path exists |

Classification is a judgment, and a wrong one is not recoverable. When an
artifact sits between classes, it is treated as the higher class until someone
with approval authority under §6 says otherwise.

## 3. What may be published about a pack

Class 1, and therefore publishable when a governed pack exists:

- that the pack exists, its version, its validity window, and its compiled hash,
  so that any receipt can be checked against the pack that produced it;
- the case narratives at the level of human situation — who the synthetic patient
  is, what they are having done, what should remain true about them — without the
  field-level expectation predicates;
- the assertion register at the level of intent and outcome: what each assertion
  is trying to protect, its severity rubric, its applicability rule, and its
  status, without the predicate that names where to look;
- the review record: reviewer roles (not identities, see §10), evidence sources,
  dissent, conflicts, compensation policy, and approval dates;
- the seeded-fault library at behavior level, as [docs/09 §4](09-TEST-AND-EVALUATION.md)
  already states it, and aggregate detection results over that corpus;
- limitations, known gaps, withdrawn content, and the reasons for withdrawal.

That set is enough for an outside reader to judge whether this project's
governance is real, which is the only thing publication needs to buy.

## 4. What must never be published

Categorical, with no approval path. These are Class 3:

1. Any receipt about any real system, in any form. A redacted receipt still says
   "some organization's laboratory interface drops sex parameter for clinical
   use," and the population of organizations running a ContextSafe pack will be
   small enough to narrow.
2. Any customer, partner, or prospect name; any system, product, or version name
   observed in a real deployment; any defect, finding, screenshot, or
   configuration detail from one. This restates and extends
   [docs/02](02-USER-RESEARCH-AND-PILOT.md), which already forbids it without
   written permission, by removing the permission path for the subset that
   identifies where identity data is retained: a customer cannot consent on
   behalf of its patients.
3. Aggregates over a customer population small enough to re-identify a member.
   Until there are at least twenty customers, "three of our customers drop
   pronouns at the interface engine" is a Class 3 statement. Twenty is a
   threshold chosen here rather than derived; the governance group may set
   another, but the rule that a small-n aggregate is an instance statement
   should survive whatever number it picks.
4. Any vendor-attributed retention or loss claim — "product X keeps gender
   identity in field Y" — whether or not it came from a customer engagement.
5. Reviewer or contributor identities beyond what that individual has separately
   and in writing consented to (§10), and never a roster.
6. Real patient data, which is already prohibited everywhere else in this corpus
   and is repeated here only so that this list can be read alone.

## 5. The crux: does the governed pack payload get published?

This is the decision the rest of the policy exists to frame, and it is the
maintainer's. It cannot be deferred past the start of B-009, because the artifact
that would be published is the artifact B-009 and B-010 create.

**D-1. Publication posture for the governed pack and assertion payload.**

| Option | What it publishes | What it costs |
|---|---|---|
| **A. Open pack** | The complete pack, including predicates, mapping profiles, and field locators | Publishes one curated, validated, machine-readable index of where trans identity data lives across registration, EHR, HL7 v2, FHIR, and LIS. Maximum reproducibility and maximum external scrutiny of the clinical oracle. Irreversible |
| **B. Split publication** *(recommended)* | Everything in §3, plus the compiled pack hash and the schema the pack conforms to. The payload — predicates, mapping profiles, locators — is distributed under contract to customers and under agreement to reviewers | Loses public reproducibility of individual results; requires maintaining a public record and a restricted artifact; creates a "trust us" tension the project otherwise avoids, partly answered by the published hash and by §5.1 |
| **C. Closed pack** | Nothing about the pack beyond its existence and version | Cheapest and safest. Also removes the mechanism that makes governed content credible to anyone who has not bought it, and sits oddly against a public repository |
| **D. Embargo** | Option A, delayed by one pack version or a fixed interval | Changes when the disclosure happens, not whether. Useful only as a modifier on A |

**Recommendation: B**, stated as a rule that survives cases this table does not
anticipate: **publish the judgment, withhold the locator.** Everything that lets
an outsider evaluate whether the review was real is public. The part that
functions as a retrieval recipe is not.

**Be honest about what B buys.** The locators are derivable from published
material. US Core and the Gender Harmony extension URLs are public; HL7 v2 GSP
and the relevant PID fields are in a specification anyone can read. Withholding
the payload does not deny a determined adversary anything they cannot reconstruct
with a week and a specification. What it denies is convenience and curation: a
pre-validated, prioritized, machine-readable list that has been checked against
real installed behavior. That is friction, not secrecy, and the policy should not
be defended as more than it is. Friction is still worth buying when the price is
low, and here the price is one artifact split in two.

### 5.1 The credibility problem B creates, and its answer

A governed pack whose content is not public asks readers to take the governance
on faith, which is the posture this project criticizes elsewhere. Two controls
answer most of it, and neither requires publishing the payload:

- the compiled pack hash is public, so a receipt can always be tied to a specific
  reviewed artifact and to nothing else;
- a named independent reviewer — not a customer, not a ContextSafe contractor —
  may inspect the withheld payload under agreement and publish an attestation
  about the review process. The attestation is Class 1; what they read is not.

If neither control is funded, B degrades toward C in practice, and the project
should say so rather than claim a transparency it is not delivering.

## 6. Who approves

The gap this closes: [docs/07 §3](07-GOVERNANCE-LEGAL-SAFETY.md) assigns approval
for an intended-use or marketing claim, but nothing assigned approval for
*publishing an artifact*. It does now.

**D-2. Approval owner for publication.**

**Standing rule, once the governance group is seated.** Publication of any
Class 2 artifact, and of any Class 1 artifact that describes a governed pack,
requires the clinical safety chair and the community co-chair, the same pair that
approves a pack release. Counsel is consulted for anything touching a customer,
a contract, or a jurisdiction. The security/privacy lead is consulted for
anything describing system internals. **The community co-chair holds a
unilateral veto over publishing anything that describes where trans identity data
lives**, mirroring the emergency-withdrawal right in
[docs/07 §11](07-GOVERNANCE-LEGAL-SAFETY.md): the people whose exposure is the
subject get a stop, not a vote. Silence is not approval.

**Interim rule, in force until both the clinical safety chair and the community
co-chair seats are filled by people who are not the maintainer.** Until then the
maintainer is the only available approver, and
a single approver with no counterparty is exactly the failure mode
[R-05](14-RISK-REGISTER.md) describes. The interim rule is therefore not "the
maintainer decides"; it is:

- Class 1 material may be published by the maintainer alone, with the decision
  recorded in §12;
- **Class 2 material may not be published at all** while either chair seat is
  unfilled. The absent governance group is the gate, not an excuse for one;
- Class 3 material has no approval path in either state.

This makes the missing roster load-bearing in the right direction: the pack
cannot become public because nobody was available to say no.

Every publication decision under this policy — including a decision to publish
nothing — is recorded with date, artifact, class, approvers, and reasoning. The
record is short by design; the point is that it exists before the artifact does.

## 7. When a pack lands, what happens to what is already public

Publication is a ratchet, and the ratchet turns on old material too. Documents
that were Class 1 when they were published can be re-read against a pack that did
not exist then: the assertion identifiers A-001 through A-036 and the fault
library F-001 through F-036 in [docs/09 §4](09-TEST-AND-EVALUATION.md) are
behavior-level today, and stay Class 1 under §2, but they become an index into a
pack the moment one exists.

Required before B-009 authoring begins, not after:

1. **Adopt or amend this policy.** B-009 is blocked on a recorded §12 decision.
2. **Re-read every already-public document against §2** and record the
   classification of each. Anything that would not be approved for publication
   today gets one of three dispositions: leave with a stated reason, revise going
   forward, or remove.
3. **Do not confuse removal with retraction.** Git history, forks, archives, and
   search caches persist; this repository's own audit demonstrates that a deleted
   document remains one command away. Removal is a forward-looking signal, not an
   undo. Prefer "leave and own it" or "revise going forward," and reserve removal
   for material whose continued presence is actively harmful.
4. **Fix the reference, not just the document.** If a public document points into
   a restricted pack, the pointer is the disclosure.

When a pack version is withdrawn under
[docs/07 §11](07-GOVERNANCE-LEGAL-SAFETY.md), its public Class 1 record is marked
withdrawn rather than deleted, for the same reason receipts remain immutable but
visibly invalidated.

## 8. Stop conditions

The project stops publishing new material — all classes, immediately, pending a
recorded decision to resume — on any of these:

- credible evidence that published material has been used, or is being assembled,
  to locate or pressure trans and nonbinary people or the organizations serving
  them: a citation in an enforcement action or demand letter, legal process
  referencing this project, or a fork or derivative whose evident purpose is
  targeting;
- legal process compelling production of project material (§9);
- counsel advising that publication creates legal exposure for the maintainer,
  reviewers, contributors, or customers in a relevant jurisdiction;
- a halt called by the community co-chair, or, before that role is filled, by any
  compensated community reviewer;
- inability to obtain the approvals §6 requires for ninety days. Publication of
  that class pauses automatically rather than defaulting open.

**What "stop" means.** Stop new publication. Do not treat takedown as the
default response: withdrawing published material is rarely effective, frequently
draws the attention it is meant to avoid, and cannot un-publish anything already
mirrored. Whether to withdraw is a deliberate decision with counsel and the
community co-chair, taken after the stop, not as part of it. Record the stop, its
trigger, and the resumption decision.

## 9. Compelled disclosure

An order to produce receipts, customer lists, reviewer identities, or pack
content is a legal event, and counsel owns it. Two things are worth stating here
because they are design constraints, not legal ones:

- **Minimization is the only control that works against valid process.** The
  project cannot produce what it does not hold. That is why receipts carry
  hashes, statuses, and counts rather than values; why raw evidence stays
  customer-local; why there is no hosted service; and why the reviewer roster is
  confidential and small. Every future feature that would centralize customer
  findings should be read against this sentence.
- **The customer is usually the party served, not this project.** The posture on
  a customer's own receipts belongs in the contract before the first paid pilot,
  per [docs/07 §8](07-GOVERNANCE-LEGAL-SAFETY.md), and the customer should know
  before signing what this project can and cannot be made to produce about them.

A warrant canary is a possible additional control and is deliberately not adopted
here: its legal effect is unsettled, and an ambiguous canary can mislead the
people it is meant to protect. If counsel advises otherwise, it becomes a §12
decision.

## 10. Contributors and reviewers

Public participation in this project is itself a disclosure. Someone whose name
appears on a commit, an approval, or an acknowledgement has been publicly
associated with trans-health data infrastructure, permanently and in an
environment where that carries risk.

- The attribution choice [docs/06 §10](06-SECURITY-PRIVACY-THREAT-MODEL.md) gives
  reviewers — public attribution, private attribution, or pseudonymity — extends
  to every contributor and to every public artifact, and it is offered before the
  first contribution rather than after.
- Pseudonymous contribution is accepted. A contributor is never required to
  disclose identity, employer, or gender to contribute.
- No roster, acknowledgement list, or thank-you is published without individual
  written consent, and consent to one artifact is not consent to the next.
- Consent is revocable going forward. Say plainly that revocation cannot reach
  archives, forks, or history, so that the choice is made with that known.

The maintainer accepted her own exposure knowingly on 2026-08-15, with the open
question in [Gate 0](PUBLICATION-READINESS.md) in front of her. That is her
decision about her own name, and it is not a precedent anyone else is asked to
follow.

## 11. What this policy does not do

- It does not make publication safe. It makes publication decided.
- It does not prevent reconstruction. Every concept this project works with is
  documented in public standards; a determined reader with a specification is not
  stopped by anything here (§5).
- It does not bind a fork. Apache-2.0 permits derivative work with none of these
  restrictions, and this policy governs only what this project publishes.
- It does not survive contact with a governance group that disagrees with it. The
  group named in [docs/07 §2](07-GOVERNANCE-LEGAL-SAFETY.md) inherits the right
  to amend it, including the recommendation in §5.

## 12. Decision record

To be completed by the maintainer. A row is in force only when it names a date.

| ID | Decision | Options | Recommendation | Status |
|---|---|---|---|---|
| D-0 | Adopt this policy | adopt / amend / reject | adopt before B-009 authoring begins | **proposed** |
| D-1 | Pack payload publication posture (§5) | A open / B split / C closed / D embargo | **B**, "publish the judgment, withhold the locator" | **proposed** |
| D-2 | Approval owner and interim rule (§6) | as written / alternative | as written, including the community co-chair veto and the interim Class 2 block | **proposed** |
| D-3 | Independent-reviewer attestation (§5.1) | fund / defer | fund before the first pack release, or state that B has degraded to C | **proposed** |
| D-4 | Warrant canary (§9) | adopt / decline | decline pending counsel | **proposed** |

## 13. Relationship to the rest of the corpus

| Document | What it carries |
|---|---|
| [docs/06 §1, §3, §4, §5, §10, §13](06-SECURITY-PRIVACY-THREAT-MODEL.md) | the inversion stated up front, the TB-10 publication boundary, the public-reader and lawful-process actors, T-16 through T-18, and the publication entries in the privacy impact and residual risks |
| [docs/07 §3, §4, §7, §14](07-GOVERNANCE-LEGAL-SAFETY.md) | publication decision rights and the RACI row, HAZ-09 and HAZ-10, and the governance statement pointing here |
| [docs/14 R-23, R-25, R-26](14-RISK-REGISTER.md) | the demand half, the harm half, and compelled disclosure, separated |
| [docs/13 B-009](13-BACKLOG.md) | the dependency that keeps this decision ahead of the work |
| [docs/PUBLICATION-READINESS.md](PUBLICATION-READINESS.md) | the audit that identified the gap, and the maintainer's Gate 0 decision |
