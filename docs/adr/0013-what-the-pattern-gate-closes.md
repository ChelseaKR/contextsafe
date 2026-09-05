# ADR 0013 — What the pattern gate closes, and what still needs a hand-written pin

Status: proposed; whether `make patterns` may be cited as closing the #58 class is the maintainer's call and is not made here
Date: 2026-09-05
Decision owners: technical owner for the gate's scope and for where its limit is written down
Review trigger: acceptance of this record, any change to `tools/pattern_gate.py`'s accounting, and the deletion of any per-field pin in `tests/test_mapping_profile_schema.py` or `tests/test_receipt_schema.py`

## Context

#58 was a published contract and a runtime that had drifted. `nameToUseTarget`
in the mapping-profile contract inlined its own regular expression instead of
referencing the `syntheticToken` definition the same file already carried;
nothing compared the published pattern with the runtime constant; the two
drifted; the runtime was the looser of the pair; and the field it was loose
about was the one that carries a person's name.

`tools/pattern_gate.py` (#73, `make patterns`, a stage of `make verify`) was
built for that. It collects every `pattern` in every `.json` file anywhere under
`schemas/` and requires each one to be accounted for in one of three ways:
`equal` to a runtime constant character for character once grouping is
normalised, `derived` from named runtime constants by a function the gate
recomputes on every run, or `declared` as having no runtime regular expression
behind it with the reason printed on every run, clean or not. On this tree today
it reports:

    pattern-gate: clean - 51 distinct pattern(s) in 168 place(s) across 22
    published contract(s): 43 equal to a runtime constant, 5 derived from one,
    3 declared without one.

**It answers "some runtime constant says this". It does not answer "the right
one does."** That is not an inference from reading the code; it is a test.
`test_a_grammar_the_runtime_holds_for_another_field_is_not_detected` copies the
schemas, replaces the mapping profile's `fixtureSystem` pattern with
`validation._CASE_ID.pattern` — an unrelated grammar for an unrelated field —
and requires the gate to exit **clean**. Swapping one published pattern for
another runtime grammar passes.

So the gate catches the *shape* of #58: a published pattern with nothing behind
it, or one that drifted away from every constant the runtime holds. It does not
catch a published pattern pinned against a constant that is not the field's own.
Whether that residue matters depends on what the pattern is for. For most of the
168 places it is a bookkeeping risk. For `nameToUseTarget` — the #58 field — it
is the same failure again with a different cause: a name field held to a grammar
that is real, compiled, and about something else.

What stands between that residue and a repeat is hand-written and small: four
tests in two modules, holding a named field to a named constant.
`test_contract_constants_are_the_runtime_constants` in
`tests/test_mapping_profile_schema.py` holds `sourceToken`, `syntheticToken`,
`fixtureSystem` and `pronounSet` to `SOURCE_TOKEN_PATTERN`,
`SYNTHETIC_TOKEN_PATTERN`, `FIXTURE_SYSTEM_PATTERN` and `PRONOUN_SET_PATTERN`
(and `nameToUseTarget` to a `$ref` at `syntheticToken`, which is the #58 fix
itself); `test_contract_pointer_grammar_is_the_runtime_segment_vocabulary`,
`test_the_published_pointer_bounds_are_the_runtime_constants` and
`test_the_published_hl7_dialect_is_the_runtime_segment_allowlist` in
`tests/test_receipt_schema.py` do the same for the receipt's structural pointer.

Nobody enumerates that set. A contributor reading `make patterns` in the gate
table, seeing 168 places accounted for, and deleting a pin as redundant would
pass every gate in this repository — and would remove the only thing holding a
name field to the name grammar. #110 is the request to decide that before it
happens rather than after.

## The decision the maintainer must make

Whether `make patterns` may be described as closing the #58 defect class, and if
not, where the limit is written so a later contributor cannot read the gate as
sufficient.

### (a) Cite the gate as closing the class

- **Cost:** the claim is false, and the repository already owns the test that
  proves it false. `docs/18-ASSURANCE-PROGRAM.md` names one defect class — *a
  check reports a clean result over content it did not examine* — and the
  identity of the constant behind a field is precisely content this gate does
  not examine. Citing it would put the program's own defect in the document that
  defines the program.
- Recorded here so the option is on the record with its cost attached, rather
  than left out and refused by silence. The recommendation below argues against
  it; the choice is the maintainer's.

### (b) Declare it one layer of two, and say so where the gate is described

The gate is the **enumeration** layer: no published pattern is unaccounted for,
and the count is printed so a run over less than the directory holds is visible.
The per-field pins are the **identity** layer: this field holds this constant.
Neither subsumes the other, and the pins are load-bearing rather than legacy.

Written down in three places, each chosen because it is where a contributor
would form the wrong belief:

1. `CONTRIBUTING.md`'s gate table row for `make patterns`, which today describes
   what the gate checks and stops before what it does not;
2. the docstring of each per-field pin test, saying that `make patterns` does not
   subsume it and that deleting it removes the only identity check on those
   fields;
3. `tools/pattern_gate.py`'s module docstring, which already carries the
   paragraph and would be pointed at from (1) rather than restated.

- **Cost:** three short edits, and the residue stays. The pin set remains
  hand-maintained and unenumerated: nothing says which of the 168 places *ought*
  to carry a pin, so a new published pattern for a new identity-carrying field
  can arrive with no pin and nothing will say so. That is the #58 shape one level
  up, and (b) does not close it — it writes it down.

### (c) Strengthen the gate to an identity check

Each published pattern names the constant it is pinned against — a declared map
from contract and JSON pointer to a runtime constant name — so the gate compares
the named constant rather than searching an index of all of them. Presence
becomes identity, and the pins become derivable rather than remembered.

- **Cost:** 168 places to declare and keep declared, in a new file that is itself
  a claim somebody has to maintain; a declaration naming the wrong constant is
  the same defect wearing the gate's uniform, so the map needs its own negative
  tests; and the work is larger than the residue it removes for most fields. The
  issue says this needs the decision in (b) first, and that is right: a stronger
  gate built before anyone has said whether the pins are required would arrive
  with no rule about whether to delete them.

## Recommendation

**Option (b) now, with (c) named as the eventual shape and left untriggered.**

The gate is genuinely good at what it does, and the honest sentence about it is
two clauses long: it closes "a published pattern with no runtime constant behind
it", which is what #58 was; it does not close "a published pattern behind the
wrong constant", which is what #58 could become. Citing the first without the
second is the one thing this repository has decided it will not do.

(b) is cheap, and it is the version of the fix that survives a contributor who
never reads this file. A paragraph in an ADR does not stop a pin from being
deleted; a sentence in the pin's own docstring does.

(c) is the right end state and the wrong next step. It should be triggered by
evidence rather than by ambition — a second published pattern arriving with no
pin, or a pin deleted in review, is the signal that the enumeration layer needs
to become an identity layer. Until then the declaration in (b) is what the tree
can honestly assert.

## Consequences if (b) is accepted

- `make patterns` keeps its scope and its clean line unchanged. No gate is
  weakened and none is widened.
- The `CONTRIBUTING.md` row for `make patterns` gains its second clause, so the
  contributor who reads only the table learns the limit at the same moment as
  the coverage.
- Each per-field pin becomes explicitly load-bearing, and removing one is a
  visible act rather than a tidy-up.
- The claim available to a reviewer becomes: *every published pattern is
  accounted for by the runtime, and the fields those four tests name are held to
  their own constants by name.* Nothing may be said beyond that.

## What this does not decide

- **Whether the pin set should be enumerated.** Which published patterns must
  carry an identity pin is a judgment about which fields carry identity, and it
  is the residue (b) leaves standing. It is the natural entry condition for (c).
- **Whether `make patterns` belongs in the assurance program's phase list.**
  `docs/18-ASSURANCE-PROGRAM.md` does not mention the gate today. Adding it is a
  program-structure decision, not this one.
- **Anything about the three declared exceptions.** Each prints its reason on
  every run and each names the code that decides the rule; this record does not
  reopen them.
- **The `(?:` to `(` normalisation.** Grouping is not the subject here.

## Rejected alternatives

- **Delete the per-field pins as redundant with the gate.** They are not
  redundant; the gate's own boundary test is the demonstration. This is the
  outcome (b) exists to prevent, and it is named here so that a contributor
  cannot reach it as a tidy-up nobody had considered.
- **Say nothing and rely on the module docstring.** The paragraph is already
  there and is already accurate. It is in the file a contributor opens *after*
  deciding the gate is sufficient, not before, and the gate table is the surface
  that forms the belief.
- **Widen the gate to reject any published pattern that matches more than one
  runtime constant.** Rejected: several constants legitimately share a grammar,
  the collision count is a fact about the runtime rather than about the contract,
  and a gate that fails on a coincidence trains its readers to ignore it.
