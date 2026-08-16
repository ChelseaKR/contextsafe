# Published contracts

Every file here is a JSON Schema Draft 2020-12 contract for one ContextSafe
document shape. They are the published half of the fail-closed boundary: the
runtime has no dependencies and does not validate its own output at run time,
so these files are what a consumer validates against, and
`tests/test_contracts.py` and `tests/test_receipt_schema.py` are what keep them
in agreement with the code.

| Contract | Shape |
| --- | --- |
| `contextsafe-case-v0.1.schema.json` | a synthetic patient case |
| `contextsafe-observation-set-v0.1.schema.json` | a set of observations for a case |
| `contextsafe-observation-v1.schema.json` | one ambiguity-preserving observation |
| `contextsafe-evidence-v1.schema.json` | an accepted evidence record |
| `contextsafe-evidence-source-v1.schema.json` | the canonical JSON evidence boundary envelope |
| `contextsafe-pack-v1.schema.json` | a test-pack envelope |
| `contextsafe-compiled-pack-v1.schema.json` | the unsigned compiled pack |
| `contextsafe-engagement-v1.schema.json` | an engagement declaration |
| `contextsafe-plan-v1.schema.json` | an execution plan |
| `contextsafe-compiled-plan-v1.schema.json` | the unsigned compiled plan |
| `contextsafe-receipt-v0.1.schema.json` | the receipt document: deterministic payload plus untrusted envelope |

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

This was not always consistent. Five of the eleven contracts previously claimed
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
