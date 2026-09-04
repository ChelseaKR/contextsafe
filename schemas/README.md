# Published contracts

Every file here is a JSON Schema Draft 2020-12 contract for one ContextSafe
document shape. They are the published half of the fail-closed boundary: the
runtime has no dependencies and does not validate its own output at run time,
so these files are what a consumer validates against, and
`tests/test_contracts.py` and `tests/test_receipt_schema.py` are what keep them
in agreement with the code. There are sixteen contracts:

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
| `contextsafe-lis-export-v0.1.schema.json` | the synthetic LIS export identity profile `import --format lis-json` reads; reference-only, ungoverned, result columns recognized but not observed |
| `contextsafe-mapping-profile-v1.schema.json` | a versioned mapping profile: one importer format's token table, from source token to canonical concept and value; reference-only, the only review status is `not_reviewed`, and no row may reach SPCU from GI or RSG |
| `contextsafe-compiled-mapping-profile-v1.schema.json` | the unsigned compiled mapping profile `mapping validate` emits: the canonical profile and its digest, `signature_status: not_verified`, `executable: false` |

That is sixteen contracts. The LIS export profile and the mapping profile are
*input* shapes rather than output ones: they say what `contextsafe import
--format lis-json` and `contextsafe import --mapping` will read, and
`tests/test_lis_export_schema.py` and `tests/test_mapping_profile_schema.py`
keep each in agreement with the runtime's allowlists and grammars. Neither
is a claim that any laboratory system exports this shape or that any
interoperability reviewer has approved a mapping.

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

This was not always consistent. Five of the eleven that existed then claimed
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
were added as required fields. The rule-set contract's 0.1.0 shape is the one exception to "one file per
contract": it predates the published schemas, is still accepted unchanged by
the runtime and pinned by the pack contract, and has no file here.
