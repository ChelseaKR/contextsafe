# ADR 0015 — What a narrowing costs before the first tag

Status: proposed; the versioning rule for a narrowing is the maintainer's to set and is not set here
Date: 2026-09-05
Decision owners: technical owner for the published versioning rule and the mapping-profile contract; no clinical, laboratory, community or legal judgment is in this record. Versioning a published contract would be an interoperability judgment the moment a consumer could hold a version — what keeps it a technical call today is that nothing has been tagged and no consumer exists, which is itself one of the facts under review here
Review trigger: acceptance of this record, the first `vX.Y.Z` tag (#100), and any later change that removes a document class a published contract accepts

## Context

Closing #66 removed one value from a closed set. `CANONICAL_JSON_CARRIERS`
listed `sex_parameter_for_clinical_use`, and the canonical-JSON converter
refuses that concept every time — the canonical envelope cannot express the
supporting-observation link — so a mapping-profile row naming that carrier
could never match a token. The key is gone from the runtime table, and the
published contract's canonical-json carrier enum lost the same value
(`schemas/contextsafe-mapping-profile-v1.schema.json`, the `format` conditional
whose `then` now enumerates `gender_identity`, `name_to_use`, `pronouns`,
`recorded_sex_or_gender`).

The break was measured rather than reasoned about. A canonical-JSON profile
whose one row read that carrier as that concept and bound it to a synthetic
sex-parameter value passed `mapping validate` at exit 0 and compiled to a
document declaring `contextsafe.mapping-profile/1.0.0` and
`valid_for_signing: true`. The same file now exits 2 with
`mapping_profile_carrier_unknown` at `$.rows[0].source.carrier`, and
`tests/test_mapping_profile.py` stands on the refusal.

Such a row was inert: no token is ever emitted under that carrier, so it bound
nothing and an import behaved as though it were not there. Inert is not
invalid. A document the published contract accepted is refused, and the version
did not move.

**The published rule does not cover this case, and that is the actual defect.**
`schemas/README.md` says two things:

> When a closed set in a published contract widens, the contract's version moves
> with it: the `schema_version` constant the runtime emits, the filename, and the
> `$id` change together, and the previous file is not kept beside the new one.

> When a published contract narrows to the grammar the runtime already enforced,
> the version does not move and the definition records the date and the issue
> instead […] A narrowing that refuses something the runtime accepts is not this
> case and moves the version like a widening.

The second paragraph's exemption is for a contract catching up to a stricter
runtime: the file was stating something the validator refused, so no document
that was accepted has stopped being accepted. Its last sentence covers a
contract narrowing *below* the runtime. #66 is neither. The runtime and the
contract narrowed together, in the same change, and a class of document that
was accepted end to end is now refused end to end. There is no sentence about
that, so the version stayed where it was for want of a rule rather than because
of one, and #109 exists to say so.

Two facts bound how much the answer matters. Nothing has been tagged or
released (#100), so no consumer can be pinned to
`contextsafe.mapping-profile/1.0.0` other than by reading an untagged working
tree. And the contracts are declared pre-1.0 in the same file: "Nothing here has
been tagged or released, so the contracts carry no stability guarantee yet
beyond the tests in this repository."

## The decision the maintainer must make

What the published versioning rule says about a narrowing that removes a class
of document the contract accepted, before the first tag — and, given that
answer, whether `contextsafe.mapping-profile` stays at 1.0.0.

Three options, with what each costs. The blast radius quoted under (b) and (c)
was enumerated from the tree on 2026-09-05 and is the same for both.

### (a) The rule gains a sentence about narrowing; the contract stays at 1.0.0

`schemas/README.md` gains a third paragraph in *Compatibility*: before the
first tag, a narrowing that removes a class of document the contract accepted
does not move the version, provided the contract's own definition records the
date and the issue, the changelog states the removed class as a break, and a
test stands on the refusal. The exemption lapses at the first `vX.Y.Z` tag;
after that, such a narrowing moves the version the way a widening does.

- **Cost paid now:** one paragraph, and the description of the canonical-json
  conditional in the mapping-profile contract gains the date and the issue, the
  way the receipt's `structural_pointer` narrowing carried them on 2026-09-04.
- **Cost carried:** the rule now permits a class of silent break. Its whole
  safety comes from the boundary — no tag — and from every use being written
  down. A boundary nothing re-derives is a boundary that erodes: no gate checks
  "we have not tagged yet" today, and whether one can is not obvious (see *What
  this does not decide*).
- **What it is honest about:** it says the version did not move *because a rule
  says so*, rather than because the question went unasked.

### (b) Move to `contextsafe.mapping-profile/1.1.0`

- **Cost:** the full radius below.
- **Cost of the signal itself:** the receipt contract's precedent reads the
  minor position as *widening* — 0.1 to 0.2 added outcome reasons, 0.2 to 0.3
  added the divergence section and the outcome trace. A minor move for a removal
  would put a break in the position this repository has twice used for an
  addition, and a later reader would have to know which was which. That is a
  worse rule than no rule.

### (c) Move to `contextsafe.mapping-profile/2.0.0`

- **Cost:** the full radius below, plus the filename and `$id` moving from `-v1`
  to `-v2`, which is the larger half of it.
- **Cost of the signal itself:** it states a compatibility break to a consumer
  set that is provably empty, and it makes the first mapping-profile major
  version anybody could hold be 2, when nothing ever published a 1. It is the
  most conservative option. It needs no *new* sentence in the versioning rule
  only in the sense that it takes the strictest reading of an inapplicable one:
  "a narrowing that refuses something the runtime accepts … moves the version
  like a widening" is the closest published sentence to this case, but by the
  reading above it covers a contract narrowing *below* the runtime, and #66 is
  not that. Closest is not applicable, so (c) too needs the rule extended to
  cover a contract and a runtime narrowing together — it extends it toward the
  answer (c) already gives, which is why the extension is one clause rather
  than a paragraph.

### The radius (b) and (c) share

- `schemas/contextsafe-mapping-profile-v1.schema.json` is renamed and its `$id`
  changes; three sibling contracts name that filename in prose and move with it
  (`contextsafe-compiled-mapping-profile-v1`, `contextsafe-observation-v1`,
  `contextsafe-observation-set-v0.1`), as do the row in `schemas/README.md`, the
  README, `CHANGELOG.md` and `docs/13-BACKLOG.md`.
- `MAPPING_PROFILE_SCHEMA_VERSION` moves in `src/contextsafe/mapping_profile.py`
  (line 80 today) and with it the acceptance check at line 651; the schema's
  `const` and the pins in `tests/test_mapping_profile_schema.py` follow.
- Five packaged reference profiles are rewritten
  (`src/contextsafe/fixtures/reference/mapping-{canonical-json,fhir-r4-json,hl7v2-er7,lis-csv,lis-json}.json`).
- Sixteen of the seventeen negative fixtures under `tests/fixtures/mapping/` are
  rewritten. The seventeenth, `reject-wrong-schema.json`, deliberately carries a
  version the runtime refuses, and the value it carries today is
  `contextsafe.mapping-profile/2.0.0` — exactly the version (c) moves to. Under
  (b) it keeps refusing; under (c) it silently becomes a valid document, and a
  negative test that no longer rejects is a test that cannot fail. So under (c)
  its version has to be re-chosen rather than edited, and that is a cost (c)
  carries alone.
- Six pinned digests move in `tests/test_determinism.py`: the five
  `MAPPED_OBSERVATIONS_SHA256` entries, because every bound observation carries
  the profile's version and digest beside the source's, and
  `COMPILED_MAPPING_PROFILE_SHA256`.
- The packaged-fixture table in `docs/PUBLICATION-READINESS.md` names all five
  reference profiles and is re-read against them.

None of that is difficult. It is about twenty-five files, and the reason to
count it is that it is the whole argument for (a): the work buys a signal for
consumers who do not exist.

## Recommendation

**Option (a)**, with the boundary written as a condition — *while no version has
been tagged* — rather than as a judgment about how much a break matters.

The reason is not that the radius is expensive. It is that a version bump is
itself a claim, and under (b) or (c) the claim would be false in a specific way:
it would tell a reader that a consumer of 1.0.0 existed and was being protected.
Nothing has been tagged. What happened is that a pre-release contract advertised
a carrier its importer always refused, and the correction removed a document
class nobody could have used for anything. Saying that in the versioning rule,
with the removed class named in the contract and in the changelog, is a more
accurate record than a version number that implies a migration.

The recommendation is conditional on the boundary being real. If the answer to
"when does this exemption stop" is anything other than "at the first tag, and
something checks it", then (c) is the better option, because an exemption
without an end is how a pre-release contract quietly becomes a released one.

## Consequences if (a) is accepted

- `contextsafe.mapping-profile` stays at 1.0.0, and the reason is written where a
  consumer reads rather than in an issue.
- The canonical-json conditional in the contract gains its date and issue, so the
  removed class is discoverable from the contract itself.
- The exemption is one sentence with one condition and one expiry, and #100 (the
  first tag) inherits an action: check that no unrecorded narrowing is riding on
  it, and delete the exemption when the tag lands.
- A future narrowing that removes an accepted class has a rule to follow, which
  is the thing #66 did not have.

## What this does not decide

- **Whether anything can re-derive the "nothing has been tagged" condition.**
  `make claims` reads the working tree and makes no network call and no `git log`
  call — the CI checkout is shallow, which is why `UNCOVERED` in
  `tools/claims_gate.py` names history-dependent facts rather than checking them
  — so "no tag exists" is not a fact that gate can establish today. Something has
  to hold the boundary or (a) degrades into a permanent exemption; what that
  something is, and whether it belongs in a gate or in the release workflow, is a
  separate decision.
- **Anything about `contextsafe.compiled-mapping-profile/1.0.0`.** Its shape did
  not change; only the class of profile it can carry did.
- **Whether the canonical-JSON importer should ever emit a sex-parameter
  carrier.** That needs the supporting-observation link the canonical envelope
  does not have, and it belongs to B-026 and its successors, not here.
- **Anything about review or approval.** No profile has been reviewed by anyone;
  `not_reviewed` remains the only status the contract admits, and nothing in this
  record changes that.

## Rejected alternatives

- **Restore the carrier and keep the contract as it was.** It would undo the
  break, and it would restore a table that advertises a concept the importer
  always refuses, in a table whose only purpose is to say what an importer can
  emit. A false claim is worse than a removed document class that never bound
  anything.
- **Keep both files, `-v1` and `-v2`, side by side.** `schemas/README.md` already
  rules this out for widenings ("the previous file is not kept beside the new
  one"), and the reason applies unchanged: two published files for one shape is
  two grammars to keep in agreement with one runtime, which is the #58 defect
  with a second file in place of a second field.
- **Decide it case by case at each narrowing.** That is what happened at #66, and
  the outcome was a version that did not move for want of a rule. A rule
  re-derived per change is not a published rule.
