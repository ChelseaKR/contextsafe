# Published contracts

Every file here is a JSON Schema Draft 2020-12 contract for one ContextSafe
document shape. They are the published half of the fail-closed boundary: the
runtime has no dependencies and does not validate its own output at run time,
so these files are what a consumer validates against, and `tests/test_contracts.py`,
`tests/test_receipt_schema.py`, `tests/test_receipt_delta_schema.py`,
`tests/test_review_schema.py`, and `tests/test_event_log_summary_schema.py` are
what keep them in agreement with the code. There are twenty-two contracts:

| Contract | Shape |
| --- | --- |
| `contextsafe-case-v0.1.schema.json` | a synthetic patient case |
| `contextsafe-observation-set-v0.1.schema.json` | a set of observations for a case |
| `contextsafe-observation-v1.schema.json` | one ambiguity-preserving observation |
| `contextsafe-evidence-v1.schema.json` | an accepted evidence record |
| `contextsafe-evidence-source-v1.schema.json` | the canonical JSON evidence boundary envelope |
| `contextsafe-fhir-r4-source-v0.1.schema.json` | the FHIR R4 JSON subset the `fhir-r4-json` importer reads; reference-only, not a conformance profile |
| `contextsafe-pack-v1.schema.json` | a test-pack envelope |
| `contextsafe-compiled-pack-v1.schema.json` | the unsigned compiled pack |
| `contextsafe-engagement-v1.schema.json` | an engagement declaration |
| `contextsafe-plan-v1.schema.json` | an execution plan |
| `contextsafe-compiled-plan-v1.schema.json` | the unsigned compiled plan |
| `contextsafe-receipt-v0.3.schema.json` | the receipt document: deterministic payload plus untrusted envelope; 0.2 widened the closed outcome-reason set for the rule-set predicates, and 0.3 adds the first-observed-divergence section and the per-outcome evidence trace with a closed structural-pointer grammar |
| `contextsafe-rule-set-v0.2.schema.json` | a deterministic fixture rule set whose rules may name a closed, reference-only predicate; the exact-only 0.1.0 shape has no separate schema and is still accepted by the runtime |
| `contextsafe-lis-export-v0.1.schema.json` | the synthetic LIS export profile `import --format lis-json` reads: identity columns and result columns, the latter becoming laboratory result observations under the two contracts below since B-030. Reference-only and ungoverned; a range or flag cell in a dialect the reader cannot type is carried as untyped rather than guessed at |
| `contextsafe-mapping-profile-v1.schema.json` | a versioned mapping profile: one importer format's token table, from source token to canonical concept and value; reference-only, the only review status is `not_reviewed`, and no row may reach SPCU from GI or RSG |
| `contextsafe-compiled-mapping-profile-v1.schema.json` | the unsigned compiled mapping profile `mapping validate` emits: the canonical profile and its digest, `signature_status: not_verified`, `executable: false` |
| `contextsafe-receipt-delta-v0.1.schema.json` | the envelope-free delta between two compatible receipt documents (reference-only, ungoverned) |
| `contextsafe-review-event-v1.schema.json` | one declared, unverified review decision about one receipt outcome; `$defs/log_record` is one line of the append-only review log |
| `contextsafe-review-state-v1.schema.json` | the disposition per outcome that `finding list` derives from a review log |
| `contextsafe-result-set-v0.1.schema.json` | a set of laboratory result observations for one synthetic case: analyte code, value, unit, order, specimen, and a reference interval and abnormal flag that are each present, absent, or in a dialect the reader could not type. Reference-only and ungoverned; every analyte, unit, bound, and flag admitted here is an invented fixture token and none is a clinical reference range |
| `contextsafe-result-rule-set-v0.1.schema.json` | pure rules over those results, each naming one of the four closed laboratory predicates. Reference-only and ungoverned mechanisms for A-025 to A-030, not the assertions, and deliberately separate from the identity rule set so widening one can never widen the other |
| `contextsafe-event-log-summary-v0.1.schema.json` | what `events summarize` derives from one local event log: counts by command, outcome, and error code, the record count, and the digest of the bytes read |

That is twenty-two contracts, and `make claims` fails when this file and the
directory disagree, both ways: a filename here that `schemas/` does not carry,
and a contract in `schemas/` that this file does not name.

The LIS export profile and the mapping profile are *input* shapes rather than
output ones: they say what `contextsafe import --format lis-json` and
`contextsafe import --mapping` will read, and
`tests/test_lis_export_schema.py` and `tests/test_mapping_profile_schema.py`
keep each in agreement with the runtime's allowlists and grammars. Neither
is a claim that any laboratory system exports this shape or that any
interoperability reviewer has approved a mapping.

Three document shapes the runtime emits are deliberately absent: what
`diagnostics`, `cleanup`, and `support-bundle` print says what one installation
can do or holds right now, and nothing consumes it later. The event log summary
is the operator document that is published, because it is the one a partner may
keep beside a release decision.

## Why every `$id` is under a domain that will never resolve

Each schema's `$id` is `https://contextsafe.invalid/schemas/<filename>`.

`.invalid` is one of the top-level domains RFC 2606 reserves. It is guaranteed
never to be delegated, which means the identifier cannot be registered by
anyone, cannot start resolving to content this project did not write, and does
not depend on a domain registration being renewed for the contract's identity
to remain stable. JSON Schema treats `$id` as an identifier first — a base URI
for resolving references, and the name a consumer uses to talk about the
contract — and nothing here is dereferenced: no code in this repository fetches
a schema over the network, and the `$ref`s inside these files are all local
(`#/$defs/...`).

This was not always consistent. Five of the contracts that existed at the time claimed
`$id` under `contextsafe.dev`, a domain nobody had registered. That is a real
defect on a public repository rather than a cosmetic one: an unregistered
domain in a published contract identity is squattable, and whoever registers it
can serve documents at URIs this project has told the world are canonical.
Anything that resolved those `$id`s would then be reading somebody else's
schema under this project's name.

Two ways to fix that: buy the domain and serve the schemas from it, or choose
an identifier that is deliberately not resolvable and say so. This project
chose the second, for the same reason it uses `urn:contextsafe:synthetic`
namespaces and `*.contextsafe.invalid` hostnames in its fixtures: an identifier
that cannot be dereferenced cannot quietly become a network dependency, and it
cannot be taken over. `tests/test_contracts.py` pins the rule, so a new schema
cannot reintroduce a resolvable identity by accident.

If ContextSafe ever does own a domain and wants resolvable schema identities,
that is a versioned contract change, not a find-and-replace: `$id` is published
identity, and consumers may be pinned to the current values.

## Compatibility

These are pre-1.0. `v0.1` in a filename means the shape may still change; `v1`
means the shape is settled for the v1 boundary but the project itself is
pre-release. Nothing here has been tagged or released, so the contracts carry
no stability guarantee yet beyond the tests in this repository.

When a closed set in a published contract widens, the contract's version moves
with it: the `schema_version` constant the runtime emits, the filename, and the
`$id` change together, and the previous file is not kept beside the new one.
The receipt contract went from 0.1 to 0.2 this way when the rule-set predicates
added outcome reasons, so a consumer pinned to the 0.1 `$id` rejects a 0.2
receipt on its `schema_version` rather than accepting a reason it has never
seen, and from 0.2 to 0.3 when the divergence section and the outcome trace
were added as required fields. The laboratory result family added no reason
and no pointer word to the receipt contract, which is why 0.3 did not move for
it: a laboratory outcome reaches no receipt, and an importer points a result
at the row it read rather than at a cell, so the closed pointer vocabulary the
receipt copies is unchanged. Widening either is a receipt version bump, and
belongs to the item that puts a result on a receipt.

When a published contract narrows to the grammar the runtime already enforced,
the version does not move and the definition records the date and the issue
instead: the file was stating something the validator refused, so no document
that was accepted has stopped being accepted, and a consumer pinned to that
`$id` gains nothing by being handed a document the runtime would reject at the
door. The receipt contract's `structural_pointer` narrowed that way on
2026-09-04 — one `maxLength`, the JSON Pointer depth, and the HL7 segment
name — and the receipt stayed at 0.3 (#72). A narrowing that refuses something
the runtime accepts is not this case and moves the version like a widening.

The rule-set contract's 0.1.0 shape is the one exception to "one file per
contract": it predates the published schemas, is still accepted unchanged by
the runtime and pinned by the pack contract, and has no file here.
