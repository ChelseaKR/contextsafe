# ADR 0006 — Provenance tokens get a grammar and a boundary scan, not a filter

Status: accepted
Date: 2026-08-27
Decision owners: technical owner

## Context

Every byte of a caller's evidence *source* goes through the boundary scan before
it is accepted: `_boundary_scan` walks the parsed JSON and rejects a PHI canary,
a direct-identifier pattern, a prohibited field name, a control character.

Three fields on the record that scan produces never went through anything of the
kind. `collector_id`, `system_id` and `system_version` are operator-supplied and
reach `parse_evidence_metadata`, which checked token *shape* and stopped there.
`SAFE_TOKEN_PATTERN` is `^[A-Za-z0-9][A-Za-z0-9:/_.-]{0,127}$`, which happily
matches a social security number, a date of birth, or the string
`realpatientcanary`.

Measured against `main` at 28ef915:

```
parse_evidence_metadata ACCEPTED collector_id = 'realpatientcanary'
free-text scan on the same value: ('canary:realpatientcanary',)
...but nothing calls it on this field.
```

End to end, through the one caller that exists:

```
evidence_id            : EVD-99699e8e059f043f00881585f9d35466d0ebabbec0132d0e...
record.collector_id    : realpatientcanary
canary bytes in sqlite : True
stored collector_id    : realpatientcanary
stored boundary_check  : passed
```

The last two lines are the whole issue. The record's own
`boundary_check_status` field says `passed`, in a row that carries a canary no
boundary check ever read. That is
[the assurance program](../18-ASSURANCE-PROGRAM.md)'s defect class stated in the
product rather than in the tooling: a clean result reported over content nobody
examined.

Reachability today is limited. `store_internal_synthetic_evidence` has no CLI
route, by its own docstring. But the same docstring says a future verified-plan
layer is meant to invoke the durable store, and the field is hashed into the
evidence id, so the value is load-bearing before it is reachable.

### Why the obvious fix is wrong

Run the three fields through `preflight._reject_unsafe_string`. That was PR #38,
and it was closed. Measured against the same commit, with the schema that commit
publishes:

```
 system_version = 2026-08-27              schema-valid=True  naive fix -> REJECTED
 system_version = BUILD-20260827          schema-valid=True  naive fix -> REJECTED
   collector_id = https://collector...    schema-valid=True  naive fix -> REJECTED
      system_id = SYS-MEDICAL-RECORD-SYS  schema-valid=True  naive fix -> REJECTED
   collector_id = collector-1234567       schema-valid=True  naive fix -> REJECTED
```

Five values the published contract declares valid, rejected by the code. A
calendar version trips the date detector. A build number trips the
seven-digit-run detector. A collector expressed as a URI trips the URL detector,
using the colon and slash the schema itself admits. And
`SYS-MEDICAL-RECORD-SYSTEM`, which is an ordinary and honest name for a system,
trips the record-locator detector.

PR #38 also reached `_reject_unsafe_string` through a function-local import of a
private name, because `preflight` imports `evidence` and the reverse edge would
be a cycle.

### What the repository already decided about this shape of problem

`src/contextsafe/safe_value.py` faced the same question for the support bundle
and answered it in its own module docstring:

> The usual defence is a redactor: assemble the bundle, then run patterns over
> it and blank what matches. That defence fails the way every denylist fails.
> [...] And each miss ships something a filter said was clean.
>
> So there is no filter here. There is a type.

The same file records the specific near-miss that produced its version rule: a
pattern that merely forbade spaces accepted `exports-Jordan-Rivera-1987` as a
version string, so a version now has to be a dotted number.

## Decision

Two layers, and they are not the same layer twice.

**The grammar is the control.** `collector_id`, `system_id` and
`system_version` get published grammars narrow enough that a direct identifier
cannot be written in them at all. Each is expressed as a base pattern plus named
exclusions, in `contextsafe.contract_validation`, in ECMA-262 syntax with no
inline flags, so the identical strings appear in
`schemas/contextsafe-evidence-v1.schema.json` as a `pattern` and a list of `not`
clauses with a `$comment` each.

- **Provenance label** (`collector_id`): `^[A-Za-z][A-Za-z0-9._-]*$`, at most 128
  characters, excluding `[0-9]{4}` (no run of four or more digits),
  `[._-](?![A-Za-z])` (every separated segment begins with a letter) and
  `[Ww][Ww][Ww]\.` (no host label). Neither a colon nor a slash is in the
  alphabet, so no URL scheme can be written.
- **System label** (`system_id`): the same, restricted to the upper-case
  alphabet the field already published, at most 64 characters. A host label
  needs a lower-case letter and a dot, so that exclusion is absent rather than
  redundant.
- **Version** (`system_version`): the shape `safe_value.VERSION_PATTERN` already
  requires, `^[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9.]{1,16})?$`, at most 64
  characters, excluding `[0-9]{7}`, `[0-9]{3}[.-][0-9]{3}[.-][0-9]{4}` and
  `[Ww][Ww][Ww]\.`.

Between them these make a bare number, a date, a social security number, a
telephone number, an email address and a URL unwritable in these fields.

**The scan is the second pass, and it is what a grammar cannot do.** A canary is
ordinary letters. No grammar excludes `realpatientcanary`, and only inspecting
content finds it. So `parse_evidence_metadata` runs each token through
`identifiers.provenance_hits` after the grammar accepts it, and rejects a hit as
`phi_canary_detected` or `direct_identifier_detected` at the field's own path.

A detector that fires on a value the grammar admitted is therefore a defect in
the grammar rather than a filter that saved the day. That is the relationship
`diagnostics.build_support_bundle` already has with `identifier_hits`, described
there as belt and braces, and it is now checked rather than asserted:
`test_every_value_the_schema_admits_passes_the_provenance_scan` draws from each
published base shape and requires that anything the exclusions let through trips
no detector.

**The detectors move to a leaf module.** `contextsafe.identifiers` holds
`KNOWN_CANARIES` and `DETECTORS`, and defines both `identifier_hits` (the
free-text pass, output unchanged) and `provenance_hits` (the bounded-token
pass). `preflight` imports from it and re-exports `identifier_hits`, which is
the documented extension point and stays exactly where `diagnostics` and its
tests already import it from. `evidence` imports from `identifiers` directly.
No cycle, and no function-local import of a private name.

**One detector is exempt for provenance, by name.**
`PROVENANCE_EXEMPT_DETECTORS` is `{"record-locator"}`. That detector matches a
locator word followed by a separator and four or more alphanumerics. In free
text that is how a medical record number is written. In a system name it is how
a system is named, and rejecting `SYS-MEDICAL-RECORD-SYSTEM` would be rejecting
a value the contract declares valid, which is the defect that closed PR #38.
What bounds the residual is the grammar: a run of four or more digits is
unwritable and every segment begins with a letter, so `MRN-1234567` and
`MRN-12-3456` are both refused before any detector runs. What survives is a
locator word next to letters, which identifies nobody. Canary detection is never
exempt anywhere.

## Consequences

- The canary no longer reaches the index. `collector_id='realpatientcanary'`
  is `phi_canary_detected` at `$.collector_id`, and nothing is written.
- No detector is disabled for free text. `identifier_hits` and
  `_reject_unsafe_string` behave exactly as before; the 709 tests that passed
  before the move passed unchanged after it.
- **This is a breaking contract change.** `system_version` must now be a dotted
  number: the fixture value `fixture-1.0` is no longer valid and became `1.0.0`.
  A calendar version must be written `2026.8.27` rather than `2026-08-27`, and a
  collector expressed as a URI is no longer accepted. There is no tagged release
  and the only caller has no CLI route, so no stored record and no external
  consumer is affected; the schema is narrowed in place rather than versioned
  for that reason, and this is the moment when that is still free.
- A rejection names the shape rule that was broken and never the value, so a
  rejected identifier cannot reach a log or an error payload by way of the
  message that rejected it. `test_no_rejection_ever_echoes_the_value_that_triggered_it`
  already required that of the source scan; the provenance rejections are held
  to it too.
- No canary fits a version prerelease: the shortest is seventeen characters and
  the prerelease is bounded at sixteen. The canary scan on `system_version` is
  therefore pure belt and braces today, which is worth knowing rather than
  assuming, and the test suite records it.
- The code and the published schema cannot drift, because
  `test_the_published_schema_carries_the_grammars_the_code_enforces` compares
  the strings rather than describing them.
- `src/contextsafe/identifiers.py` joins `SAFETY_MODULES`, so it carries the
  95% branch floor rather than the 90% one.
- This closes issue #35 and bears on R-07 ("real PHI enters workspace", score
  15, open), whose recorded mitigation includes pre-persistence checks. It does
  not close R-07, and no detector set proves absence.

## Rejected alternatives

- **Run the fields through `preflight._reject_unsafe_string`.** PR #38. Rejects
  five values the published schema declares valid, and reaches a private name
  through a function-local import to avoid a cycle it should have removed.
- **Apply the full detector set and leave the schema alone**, treating the
  schema as shape-only and the runtime as content-only. Defensible, and the
  schema's own `$comment` already draws that line for `evidence_id`. Rejected
  because it repeats PR #38's actual defect in a different wrapper: an operator
  reading the published pattern would still be told `2026-08-27` is a valid
  version and then be refused one.
- **Narrow the grammar and apply no scan.** The type is the better control, and
  it is not sufficient: a canary is ordinary letters and a grammar cannot see
  it. Defence in depth here is not decoration; it is the only thing that catches
  the case this repository's canary suite exists for.
- **Exclude the record-locator vocabulary in the grammar** with a `not` clause
  forbidding `mrn`, `medical` and `account` as substrings. Rejected: forbidding
  the word "medical" in a system name, in a tool for healthcare systems, is a
  worse contract than the residual it removes.
- **Loosen the record-locator detector** so it requires a digit in the token
  after the locator word. That would have made it apply cleanly here, and it
  would have weakened the free-text scan that reads caller-owned evidence, which
  is the one thing this change must not do.
- **Version the schema to 1.1.0 or 2.0.0 for the narrowing.** There is no tagged
  release, no stored record, and no CLI route to the only caller. A version bump
  would record a compatibility event that has no one on the other side of it.
