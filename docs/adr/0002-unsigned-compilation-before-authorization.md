# ADR 0002: deterministic unsigned compilation precedes authorization

Status: accepted for internal implementation; not a clinical, community, legal, or pack-content approval
Date: 2026-07-13
Technical decider: repository implementation owner for this bounded compiler boundary
Required future deciders: clinical safety chair, community co-chair, security/privacy lead, and partner technical owner for their respective governed releases
Review trigger: B-035 signing implementation, any executable runner, any network adapter, any production request, or any change to approval roles

## Context

ContextSafe needs deterministic pack and execution-plan artifacts before it can implement detached signatures and key enrollment. It also must not let a machine-generated artifact impersonate clinical or community approval. A simple `valid: true` result would collapse three different claims:

1. the files are structurally and semantically compatible;
2. required human-decision declarations are present, current, unwithdrawn, and bound to the content;
3. the people and declarations have been cryptographically authenticated and authorized.

Only the first two can be implemented in B-012 through B-016. B-035 owns key enrollment, signature thresholds, revocation, and verification. The current runner also has no authorized network execution path.

## Decision

ContextSafe uses a two-stage release contract.

### Stage 1: deterministic unsigned compilation

The pack compiler:

- accepts only the exact supported pack, case, rule-set, and runner contracts;
- validates lifecycle dates, withdrawal state, current source review metadata, and the complete declared-role set;
- binds every approval declaration to a canonical hash of the pack content excluding the declarations themselves;
- opens the pack root once, traverses component paths relative to retained directory descriptors without following links, accepts only regular files, parses the bytes read from those same descriptors through typed validators, and verifies semantic content hashes;
- sorts semantically unordered collections before hashing and emitting manifests;
- takes an explicit `as_of` date rather than consulting a wall clock;
- retains a clearly named canonical source-pack hash, hashes the complete compiled payload including `as_of` and every manifest, and emits the deterministic artifact marked `valid_for_signing: true`, `signature_status: not_verified`, and `executable: false`.

Approval declarations are machine-readable records, not signatures. Passing their checks means only that the declared controls are internally complete and current. It does not authenticate the reviewer or establish that a real review occurred.

The plan validator:

- pins the canonical engagement hash and the exact compiled-payload hash, then recomputes the latter and validates its manifest relationships before using its case scope;
- accepts only `sandbox`, `test`, or `staging` classifications with explicit non-production and production-prohibition attestations;
- rejects URLs, wildcards, uppercase hosts, IPv6 literals, and canonical or legacy numeric IPv4 forms (single-integer, abbreviated, octal, and hexadecimal), then requires every target host to appear in the engagement allowlist;
- requires the fixed synthetic namespace, all owner roles, an exact cleanup contract whose deadline is current and covers the complete plan validity interval, all four bounded checkpoints, and the compiled pack's exact case-token scope;
- validates engagement, plan, and pack dates against the same explicit `as_of` date;
- performs no DNS lookup, connection, write, or other network action;
- emits a deterministic artifact with the same unsigned, non-executable status.

### Stage 2: authorization

B-035 must add pinned trust roots, role and purpose constraints, enrolled keys, detached Ed25519 signatures, signature thresholds, revocation freshness, rotation, and compromise recovery. No artifact from Stage 1 becomes executable merely because it compiled. A later runner must require a successfully verified Stage 2 artifact and must not introduce an unsigned bypass.

## Options considered

### Treat declared approvals as authorization

Rejected. A string reviewer ID and decision can test lifecycle and content binding, but cannot prove identity, authority, independence, or consent.

### Block all compiler work until real governance and signing are complete

Rejected. Deterministic canonicalization, compatibility, negative controls, and plan-scope enforcement can be implemented and tested safely with clearly synthetic test data. Deferring them would concentrate integration risk in the signing milestone.

### Add a test-only bypass that marks artifacts executable

Rejected. A bypass is likely to survive into demos or later runner code. Tests instead create visibly test-only declarations in memory, while the committed reference pack remains draft, unreviewed, and unapproved.

### Infer production from host-name substrings

Rejected. Heuristics can both miss production and reject legitimate non-production names. The contract uses an explicit classification and two required attestations, followed by exact host allowlisting. Partner review remains responsible for the truth of those declarations.

## Consequences

### Positive

- Canonical output is reproducible across key and array ordering.
- Expiry, withdrawal, compatibility, compiled-payload or source hash, role, namespace, owner, cleanup, host, and scope drift fail closed before signing.
- Source provenance is retained without copying source text into the pack manifest.
- Test tooling can advance without fabricating a clinically approved pack.
- A future signing layer has stable, content-addressed subjects to authorize.

### Negative

- An unsigned artifact cannot be executed, even when every declared control passes.
- The compiler cannot determine whether a reviewer ID belongs to a real, qualified, independent reviewer.
- Explicit environment attestations can be false; machine validation cannot inspect a partner's infrastructure truthfully without a separately approved integration.
- Exact compatibility intentionally rejects newer schema or runner contracts until a reviewed compiler release adds them.

## Follow-up actions

1. B-013 must conduct and record independent clinical and community review; no repository fixture satisfies that work.
2. B-035 must implement signing and verification before any execution path.
3. B-036 must verify the full schema/hash/approval/signature/withdrawal graph.
4. B-017 must add synthetic-data and no-PHI preflight before any persistence work.
5. Any future runner must consume only verified artifacts and preserve the non-production, allowlist, namespace, owner, and cleanup constraints without a bypass.

## Validation

This decision is implemented correctly when permutation tests produce byte-identical canonical artifacts; expired, withdrawn, incomplete, incompatible, manifest-tampered, out-of-directory, symlinked, non-regular, production, numeric-IP, unallowlisted, ownerless, cleanup-expired, or namespace-mismatched inputs fail closed; schemas validate every successful artifact; the committed reference pack cannot compile; and no validation command performs a network action.
