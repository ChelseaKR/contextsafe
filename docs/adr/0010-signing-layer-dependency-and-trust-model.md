# ADR 0010 — The signing layer: its first dependency, and the trust model it has to carry

Status: proposed; the dependency decision is pending the maintainer and is not delegated
Date: 2026-09-04
Decision owners: technical owner for the dependency, the document shapes and the command contract; security/privacy design review (B-040) before any of it ships; clinical safety chair and community co-chair for the pack threshold, which this record restates and does not set
Review trigger: acceptance of this record, any change to `[project] dependencies`, the first `sign` or `verify` command, any trusted-time source, any change to approval roles

## Context

[Architecture section 6.6](../04-ARCHITECTURE.md) has described the signature
trust model since before the first commit: one offline ContextSafe trust root
whose fingerprint the runner pins; a root-signed trust manifest binding each key
to an organization, a human role, a set of permitted artifact purposes, an
algorithm, a validity interval and a status; detached Ed25519 signatures over
canonical artifacts; explicit thresholds per purpose; rotation with an overlap
interval; root-signed monotonic revocation bundled with releases; a 31-day
freshness rule for an offline verifier; and a compromise runbook.
[ADR 0002](0002-unsigned-compilation-before-authorization.md) made that Stage 2
and built Stage 1, deterministic unsigned compilation, so that the signing layer
would have stable content-addressed subjects to authorize and nothing else to
design.

Today every artifact the tool emits says the layer is absent. A compiled pack
and a compiled plan carry `signature_status: not_verified`, `executable: false`,
`valid_for_signing: true` and the limitation
`cryptographic-authorization-requires-b-035`. A receipt document's envelope
carries `signature_status: not_signed` and `trusted_time: false`. An evidence
record carries `authorization_status: not_verified_internal_test_only`. Each of
the modules that writes those constants says in its own docstring that a later
signature layer may not relabel what it produced, the receipt contract pins the
unsigned envelope constants as closed, and this record keeps that promise as
its first rule: **a signing layer signs new artifacts; it never rewrites an old
one into a signed one.**

What has kept the layer from being built is not its design. It is one line:

```toml
dependencies = []
```

The standard library has SHA-256 and HMAC. It has no Ed25519, no other
public-key signature, and no constant-time arithmetic to build one from; `ssl`
links OpenSSL and exposes none of its signing interface. So the first
`contextsafe pack sign` is also the first runtime dependency of a project whose
empty dependency list is a supply-chain claim (T-11, TB-08) that every
customer's `pip-audit` and every security questionnaire inherits. That is a
decision the maintainer makes once, and it is not one an implementation task
can make on the way past. This record lays the options out with their
consequences, recommends one, and then fixes everything B-035 and B-036 must
implement whichever option is chosen, so that the implementation is a
transcription and not a second design.

## The decision the maintainer must make

Four options. One is rejected here and not held open; three are open. The
package facts below were read from PyPI's release metadata and the OSV
vulnerability database on 2026-09-04 and are dated to that day. They age with
every release — wheel coverage in particular moved twice in the five months
before this record — so whoever makes the decision re-reads them first. The
fresh-install matrix B-045 owns is what proves a wheel claim at release; this
record does not.

### (a) `cryptography` as the first runtime dependency

PyCA's `cryptography` provides Ed25519 through the OpenSSL it bundles, and its
advisory stream is the one the most people in the Python ecosystem watch.

On 2026-09-04 the current release is 50.0.1 (2026-08-25). It is three packages,
not one: on CPython it declares `cffi>=2.0.0`, and `cffi` 2.1.1 (2026-08-03)
declares `pycparser`. Its binary wheels cover manylinux and musllinux on x86_64
and aarch64 (manylinux also on ppc64le and armv7l), macOS on arm64 only, and
Windows on amd64 only. That is narrower than it was: 46.0.7 (2026-04-08) shipped
a macOS `universal2` wheel and a `win32` wheel, and 49.0.0 (2026-06-12) shipped
neither. Of the three platforms B-045 names, Ubuntu is covered, macOS is covered
on Apple silicon and not on Intel, and Windows is covered on amd64 and not on
arm64 or 32-bit; on a platform without a wheel the install builds from source
and needs a Rust toolchain, a C toolchain and OpenSSL headers, and if that
fails, the whole install fails, not the signing commands. OSV holds 42 advisory
records against the package over its history, 17 of them published in 2026,
many of them advisories for the OpenSSL it bundles rather than for the Python
layer; each one turns `make audit`, and so `make verify`, red until the fixed
release is locked, whether or not the Ed25519 path is affected. That is the gate
doing its job, and it is a recurring cost.

### (b) `PyNaCl`

Bindings to libsodium through `cffi`, from the same PyCA organization.
libsodium's Ed25519 verifier rejects non-canonical encodings and small-order
inputs that RFC 8032 leaves to implementations, which is the property a verifier
that must agree with itself on every platform cares about most.

On 2026-09-04 the current release is 1.6.2 (2026-01-01). It is the same three
packages, `pynacl`, `cffi` and `pycparser`. Its wheels cover manylinux and
musllinux on x86_64 and aarch64, macOS as one `universal2` build, and Windows on
`win32`, `win_amd64` and `win_arm64`: every platform B-045 names has a wheel
today, including the two that (a) leaves to a source build. A source build
needs a C toolchain and the libsodium the sdist bundles, and no Rust. Its
release history is bursty: nothing between 1.5.0 (2022-01-07) and 1.6.0
(2025-09-10), then 1.6.1 (2025-11-10) and 1.6.2. OSV holds two records against
it, and they are one issue: CVE-2025-69277, a libsodium point-validity check
(`crypto_core_ed25519_is_valid_point`) that accepted points outside the main
group in atypical use, fixed in 1.6.2. That is Ed25519-adjacent and should be
read as such — it is in a function a signer and verifier do not call, and it is
also the kind of edge that (d) below would have to get right unaided. `cffi`
has no OSV record. A reader should weigh the three-year gap and the recent
cadence together, not either alone.

### (c) An optional extra, `contextsafe[signing]`

The base wheel keeps `dependencies = []`. One extra pulls exactly one of (a) or
(b), pinned to a range and hash-locked in `uv.lock`. Only the `sign` and
`verify` commands import the backend, lazily; when it is absent they fail
closed with exit 2 and one JSON error object on stderr whose code is
`signing_unavailable`. No other command imports it, so the determinism matrix
is unaffected by whether the extra is installed, and a test asserts that by
running the matrix with the backend hidden.

Consequences. "Zero runtime dependencies" stays true of the artifact a
customer audits when all they run is `evaluate` and `render`, and stays honest
for the rest, because the signing commands say plainly that they cannot run.
One wheel now has two documented shapes, so CI tests both and
`contextsafe diagnostics` reports which one an installation has as a flag, not a
version string. `signing_unavailable` is an installation error, never a
verification result: it is never written into any artifact, and the receipt's
mandated limitations already tell a reader that an unverified receipt proves
nothing. An extra cannot be made required, so a partner's verifier is only as
good as the instruction to install it, which the packaging item B-045 must
carry. Whichever library backs the extra, it is one library on every platform:
there is no "use whichever is installed", because two Ed25519 verifiers can
disagree on the edge cases, and a signature that verifies on one machine and
not another is a determinism failure this repository does not permit.

### (d) A pure-Python Ed25519 — rejected

Rejected outright. CPython integers are not constant-time, so a pure-Python
signer leaks its private key through timing on any host where an attacker can
measure it. Verification is over public inputs and is not itself a side-channel
problem, but a verifier has to get RFC 8032 section 5.1.7 exactly right — the
canonical encoding checks, the cofactor decision, the small-order rejections
that CVE-2025-69277 shows even libsodium once got wrong at one edge — and there
is nobody in this repository qualified to review that and no plan to hire them.
The rule that a module deciding validity is a safety module would put it under
95% branch coverage and the [ADR 0009](0009-mutation-evidence-over-declared-safety-modules.md)
mutation subset as its only assurance. "Zero dependencies" would be achieved by
making this project the dependency, which is T-11 with the auditors removed.

### Where Windows stands, under any option

Two facts about Windows are independent of the backend and should be in front
of the maintainer. First, `pack validate` and `plan validate` already fail
closed on Windows with `input_path_unsupported`, because their component reads
need descriptor-relative no-follow opens the platform lacks; a `pack sign` or
`plan sign` that recompiles its subject inherits that, so on Windows those two
signing commands fail closed before any backend is consulted. Second,
`receipt sign`, `receipt verify` and `pack verify` over a single compiled
artifact read one file through the same bounded open that `evaluate` and
`render` use today, which runs on Windows. So the wheel question on Windows is
mostly a question about verifiers — a customer release owner on a Windows
desktop checking a receipt — and the platform that
[Operations](../10-OPERATIONS-SRE.md) still lists as supported is one where (a)
today has a wheel for amd64 only and (b) has one for all three architectures.

### Recommendation

Choose **(c)**, backed by **`PyNaCl`**, pinned to a range and hash-locked, the
same library on every platform. The base install is what a customer's security
review reads and what `evaluate` and `render` need, and it should keep saying
`dependencies = []` because that will be true of it; the signing commands are
the part of the tool that authorizes, and a command that authorizes should
refuse loudly when its backend is absent rather than let a missing wheel look
like a verification result. Between the two backends, this tool needs exactly
one primitive, and `PyNaCl` is the smaller surface that contains it: no TLS, no
X.509, two OSV records that are one Ed25519 edge fixed in the current release
against 42 for a library most of whose advisories are for code this tool would
never call; a verifier that rejects the non-canonical and small-order inputs a
cross-platform verifier must agree about; and, on 2026-09-04, a wheel for every
platform B-045 names, including the Intel Mac and the Windows arm64 machine
that `cryptography` leaves to a Rust build. The honest counterweight is that
`cryptography`'s advisory stream has more eyes on it and its release cadence
has never paused for three years; a maintainer who weights ecosystem scrutiny
over minimal surface chooses `cryptography` under the same design, and nothing
below changes. What does not survive either choice is (a) as the *shape*: a
tool with one dependency for every install is a worse supply-chain claim than a
tool with none and a documented extra, and (d) is closed.

On acceptance, this section is retitled `## Decision`, names the option and the
backend chosen, and re-dates the package facts to the day they were re-read.
Until then this record has no decision section, which is what "proposed" means.

## Design that holds under (a), (b) or (c)

Everything below is written so that B-035 and B-036 implement it and so that a
reviewer can object to it before a line of it exists. The two draft schema
fragments live in this record and nowhere else: nothing is added to `schemas/`
until the decision is made and the shapes have been through review, and every
fragment here is labelled a draft, reference-only and ungoverned.

### What is signed

A signature is over a **subject hash**, never over a file. The subject is the
canonical hash each artifact already publishes and excludes its envelope:
`compiled_pack_sha256`, `plan_sha256`, a mapping profile's hash, a review
event's hash, a receipt document's `payload_sha256`, and a trust manifest's
canonical hash. The signed message is the canonical JSON
(`contextsafe.canonical`) of the signature document's `signed` object, prefixed
by a fixed domain-separation string, so a signature over a ContextSafe subject
cannot be replayed as a signature over anything else and a signature over one
artifact kind cannot be presented as a signature over another:

```text
message = b"contextsafe-detached-signature/1\n" + canonical_json(signed)
```

`claimed_signed_at` sits outside `signed`, exactly as section 6.6 puts it
outside the deterministic payload: it is the signer's unauthenticated note, the
verifier reads it for no decision, and keeping it out of the signed bytes means
nobody can mistake it for a signed timestamp. A signature document carries no
name, no organization name and no free text; who a key belongs to is the trust
state's business.

### Draft: detached signature document

A draft fragment, kept here and not in `schemas/`. It follows the published
contracts' conventions — an `$id` under the reserved never-resolving domain,
closed objects, closed enums, every property constrained — so that promotion
is a copy and a review, not a redesign. Every date and time in both fragments
is an explicit pattern rather than `"format"`, because `format` is an
annotation in JSON Schema 2020-12 and constrains nothing unless a validator opts
in; a shape that is fail-closed only under a test suite's format checker is not
fail-closed.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://contextsafe.invalid/schemas/contextsafe-detached-signature-v1.schema.json",
  "title": "ContextSafe detached signature",
  "description": "DRAFT held in ADR 0010. Reference-only and ungoverned: not a published contract, not reviewed, and not a shape any command emits or accepts.",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "signed", "signature", "claimed_signed_at"],
  "properties": {
    "schema_version": {"const": "contextsafe.detached-signature/1.0.0"},
    "signed": {
      "description": "The only bytes the signature covers, as canonical JSON behind the domain-separation prefix.",
      "type": "object",
      "additionalProperties": false,
      "required": ["subject", "purpose", "role", "key_id", "algorithm"],
      "properties": {
        "subject": {
          "type": "object",
          "additionalProperties": false,
          "required": ["artifact_kind", "subject_schema_version", "subject_sha256"],
          "properties": {
            "artifact_kind": {"enum": ["compiled_pack", "compiled_plan", "mapping_profile", "review_event", "receipt_document", "trust_manifest"]},
            "subject_schema_version": {"type": "string", "pattern": "^contextsafe\\.[a-z-]+/(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)$"},
            "subject_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
          }
        },
        "purpose": {"enum": ["plan", "pack", "runner", "mapping", "review", "receipt", "revocation"]},
        "role": {"enum": ["clinical_safety_chair", "community_co_chair", "technical_release_owner", "laboratory_reviewer", "contextsafe_delivery_owner", "contextsafe_interoperability_reviewer", "contextsafe_clinical_service_approver", "customer_sponsor", "customer_technical_owner", "customer_clinical_owner", "customer_release_owner", "trust_root"]},
        "key_id": {"description": "SHA-256 of the raw 32-byte Ed25519 public key.", "type": "string", "pattern": "^[0-9a-f]{64}$"},
        "algorithm": {"const": "ed25519"}
      }
    },
    "signature": {"description": "The 64-byte Ed25519 signature, lower-case hex.", "type": "string", "pattern": "^[0-9a-f]{128}$"},
    "claimed_signed_at": {"description": "Signer-declared, unauthenticated, outside the signed bytes; the verifier reads it for no decision.", "type": ["string", "null"], "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"}
  }
}
```

The role enum is the roster section 6.6 already names, closed so that a role is
a code and not a string a signer types; its first three members are the values
`contextsafe.pack.ApprovalRole` already uses, so a pack's declared approvals
and its signatures speak one vocabulary. Several signatures over one subject
travel as separate documents in a directory beside the artifact, one file per
signature, as [Architecture section 9](../04-ARCHITECTURE.md) has always said
("stored alongside and excluded from the canonical payload"); a bundle format
is not designed here.

### Draft: trust manifest, with the revocation set inside it

The revocation set is a member of the manifest and not a separate artifact:
one document, one canonical hash, one root signature, one thing to carry to an
offline verifier. A key's `status` and the `revoked_key_ids` list say the same
thing twice on purpose, so that a reader of either finds it; a manifest in
which they disagree — a key listed under `revoked_key_ids` whose `status` is
not `revoked`, or the reverse — is rejected as a whole with the category
`trust_manifest_inconsistent`, never resolved in favour of either.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://contextsafe.invalid/schemas/contextsafe-trust-manifest-v1.schema.json",
  "title": "ContextSafe trust manifest",
  "description": "DRAFT held in ADR 0010. Reference-only and ungoverned: not a published contract, not reviewed, and not a shape any command emits or accepts. Holder and organization fields are opaque tokens; the roster that resolves them is confidential and lives in no repository.",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "manifest_sequence", "issued_on", "root_key_id", "keys", "revocations"],
  "properties": {
    "schema_version": {"const": "contextsafe.trust-manifest/1.0.0"},
    "manifest_sequence": {"description": "Strictly increasing across manifests signed by one root.", "type": "integer", "minimum": 1},
    "issued_on": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
    "root_key_id": {"description": "Must equal the fingerprint the runner pins; a manifest for any other root is not a manifest.", "type": "string", "pattern": "^[0-9a-f]{64}$"},
    "keys": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["key_id", "public_key", "organization_id", "holder_id", "role", "permitted_purposes", "valid_from", "valid_until", "status"],
        "properties": {
          "key_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
          "public_key": {"description": "Raw 32-byte Ed25519 public key, lower-case hex; key_id must be its SHA-256.", "type": "string", "pattern": "^[0-9a-f]{64}$"},
          "organization_id": {"type": "string", "pattern": "^org-[a-z0-9][a-z0-9-]{2,62}$"},
          "holder_id": {"type": "string", "pattern": "^holder-[a-z0-9][a-z0-9-]{2,62}$"},
          "role": {"enum": ["clinical_safety_chair", "community_co_chair", "technical_release_owner", "laboratory_reviewer", "contextsafe_delivery_owner", "contextsafe_interoperability_reviewer", "contextsafe_clinical_service_approver", "customer_sponsor", "customer_technical_owner", "customer_clinical_owner", "customer_release_owner", "trust_root"]},
          "permitted_purposes": {"type": "array", "minItems": 1, "maxItems": 6, "uniqueItems": true, "items": {"enum": ["plan", "pack", "runner", "mapping", "review", "receipt", "revocation"]}},
          "valid_from": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
          "valid_until": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
          "status": {"enum": ["active", "rotating_out", "revoked", "retired"]}
        }
      }
    },
    "revocations": {
      "type": "object",
      "additionalProperties": false,
      "required": ["revocation_sequence", "issued_on", "revoked_key_ids"],
      "properties": {
        "revocation_sequence": {"description": "Strictly increasing; a verifier handed two sets rejects the lower.", "type": "integer", "minimum": 0},
        "issued_on": {"description": "The date the 31-day freshness rule is measured from, against the caller's --as-of.", "type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
        "revoked_key_ids": {"type": "array", "uniqueItems": true, "items": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}
      }
    }
  }
}
```

The manifest is itself a subject: its canonical hash is signed by the root key
with purpose `revocation` and role `trust_root`, and the runner pins the root's
`key_id`. A manifest whose root signature does not verify against the pinned
fingerprint is not a manifest. `maxItems: 6` on `permitted_purposes` is the
schema's way of saying what the lifecycle below says in words: a key enrolled
for every purpose is rejected. A validator also has to check what a schema
cannot — `key_id` equals the SHA-256 of `public_key`, `valid_from` precedes
`valid_until`, the two revocation views agree, `root_key_id` matches the pin —
and schema success alone authorizes nothing, as
[Data and evidence section 9.1](../05-DATA-AND-EVIDENCE.md) already says of the
published contracts.

Four points depart from or add to the wording of section 6.6 and need the
maintainer's confirmation rather than this record's assertion. First,
`holder_id` and `organization_id` are opaque tokens, not the "human/role" and
organization names 6.6 lists: a manifest that must travel to every verifier and
is producible under lawful process (T-18) would otherwise be the reviewer
roster T-08 and T-17 exist to keep small, and the roster that resolves a
`holder_id` to a person stays confidential and off this repository. Second,
customer and engagement keys are never in this manifest; they are enrolled in
the compiled plan in the same key-record shape, that enrolment verifies only
under the plan's own `customer_sponsor` and `contextsafe_delivery_owner`
signatures, and a key present in both places is a rejection, not a
convenience. Third, rotation overlap is bounded at 90 days; 6.6 says "an
overlap interval" and gives no bound. Fourth, a key with every purpose is
rejected; 6.6 requires an explicit purpose set and does not say a complete one
is disallowed.

### Key lifecycle

- **Enrolment.** A ContextSafe key enters by a new root-signed manifest with a
  higher `manifest_sequence`. A customer key enters by plan enrolment, signed
  as above. A key is enrolled for one role and an explicit purpose set.
- **Rotation with overlap.** The replacement key is added `active` with its own
  interval; the old key becomes `rotating_out` with `valid_until` set to the end
  of the overlap, at most 90 days after the replacement's `valid_from`. During
  the overlap both keys verify. Because verification has no trusted time, a key
  past `valid_until` at `--as-of` fails whether or not the signature was made
  before then, so **an artifact that must stay verifiable is countersigned by
  the replacement key during the overlap**, and one that is not has a
  verifiability horizon equal to its signing keys' validity. That is the honest
  consequence of "verification-time validity" in 6.6 and the maintainer should
  read it as a cost, not a footnote: a pilot receipt's signatures expire with
  the keys that made them unless it is re-signed. The alternative — accepting a
  historical signature from an expired key — is a trusted-time claim and waits
  for the RFC 3161 or witnessed-log ADR that 6.6 already defers to P1.
- **Revocation.** Root-signed, inside the manifest, with a
  `revocation_sequence` that only increases and an `issued_on` that only
  advances. A verifier handed two manifests rejects the lower sequence. It
  keeps no state of its own between runs — a hidden file the verifier trusts
  would be a second trust root nobody signed — so monotonicity is enforced
  within one invocation and by the release bundle.
- **Freshness, without a clock.** The verifier takes an explicit `--as-of`
  date, as `pack validate` and `plan validate` do, and never reads a wall
  clock. When `as_of` is more than 31 days after `revocations.issued_on`, the
  trust state is stale — section 6.6's `trust_status=stale` — and under the
  command contract below that is exit 2 with the category `trust_stale`, not a
  report with a status field: no document this layer emits carries a
  `trust_status`, and no verification report is written unless the result is
  verified. The rule is two-sided: an `as_of` earlier than
  `revocations.issued_on` or `manifest.issued_on` is a trust state issued after
  the date the caller declared, category `trust_issued_after_as_of`, never an
  implicit pass. `as_of` is recorded in the verification report, so a caller
  who misstates the date has written the misstatement into the output.
- **Compromise recovery.** A compromised signing key is revoked, and because
  nothing can say which of its signatures predate the compromise, every
  signature by that key fails from the revocation onward; what should survive
  is re-signed by a replacement key. A compromised root cannot be revoked by
  the root: recovery is a new pinned fingerprint distributed with a verifier
  release through a channel that does not depend on the old root, plus the
  isolation, partner notification, historical scope review and SEV-1 steps of
  [threat model section 11](../06-SECURITY-PRIVACY-THREAT-MODEL.md), exercised
  under B-047. This record does not write that runbook; it names what the
  runbook must do.
- **The pinned root, before one exists.** No root key exists today, and
  generating one offline is a maintainer act at release, not a fixture
  promoted. Until it is pinned, the `verify` commands fail closed with
  `trust_root_not_pinned`; the fixture root that tests need is injected
  through the module API and never through a command-line flag, so the CLI
  can never be pointed at a root of the caller's choosing.

### Threshold rules per artifact purpose

Restated from section 6.6 as the verifier will apply them; roles are the
closed enum above. "Distinct" is by `holder_id` and, where stated, by
`organization_id`; two keys with one holder count once.

| Purpose | Subject | Required signatures | Distinctness |
|---|---|---|---|
| `pack` | compiled pack | `clinical_safety_chair` + `community_co_chair` + `technical_release_owner`; laboratory assertions additionally require a `review` signature by `laboratory_reviewer` in the approval graph | three holders; the technical signature attests build integrity and never substitutes for either semantic approval |
| `plan` | compiled plan, including its key enrolment | `customer_sponsor` (plan-enrolled) + `contextsafe_delivery_owner` (manifest) | two holders, two organizations |
| `mapping` | mapping profile | `customer_technical_owner` (plan-enrolled) + `contextsafe_interoperability_reviewer` (manifest) | two holders, two organizations |
| `review` | review event | one signature by the exact role the event names; an accepted clinical residual-risk event needs `customer_clinical_owner` (plan-enrolled) + `clinical_safety_chair` (manifest) | two holders, two organizations; neither substitutes for the other |
| `receipt` | receipt document | `customer_release_owner` (plan-enrolled) + `contextsafe_clinical_service_approver` (manifest) | two holders, two organizations |
| `revocation` | trust manifest | `trust_root` against the pinned fingerprint | one |
| `runner` | release artifact | reserved for B-045; not verified by this layer | — |

A threshold is met by valid signatures only. A signature by an unknown key, a
key without the purpose, a key with the wrong role, a key outside its interval
at `as_of`, a revoked key, a key enrolled in both the manifest and a plan, or a
second signature by an already-counted holder does not count and is reported
as a failure category. Absence is not a partial pass: a pack with two of three
is `not_verified`, not two-thirds verified, and no command reports a fraction.

### Command contract

`sign` and `verify` are new subcommands under the existing `pack`, `plan` and
`receipt` groups (`mapping sign` and `review sign` follow their artifacts, which
do not exist yet) and inherit every convention the shipped commands have:
`--quiet`, `--no-color`, `--output`, `--log-dir`, the bounded 1 MiB read, and
fail-closed on a platform without descriptor-relative no-follow reads wherever
the subject's own validation needs them. Exit codes are the contract every
command has: 0 when the artifact is verified, 2 with one JSON error object on
stderr for everything else, 64 for usage. A verification that does not reach
verified is a failure of the command, not a report with a soft status; the
error object names a category from a closed set and a location, never a value:
`signing_unavailable`, `trust_root_not_pinned`, `trust_root_mismatch`,
`trust_manifest_inconsistent`, `trust_stale`, `trust_issued_after_as_of`,
`key_not_enrolled`, `key_wrong_purpose`, `key_wrong_role`,
`key_outside_validity`, `key_revoked`, `key_enrolled_twice`,
`signature_invalid`, `signature_threshold_not_met`, `subject_mismatch`. On any
exit other than 0 nothing is written to `--output`.

`sign` recomputes the subject hash from the artifact and refuses one that is
non-canonical, that fails its own validation, or that does not say
`valid_for_signing: true`; it reads the private key from a file the caller
names, never from an argument or the environment, which is the rule
[threat model section 8](../06-SECURITY-PRIVACY-THREAT-MODEL.md) already sets
for credentials. Hardware-backed keys, which T-01 prefers, are not delivered by
this design and are recorded as a residual. The verification report — the
`--output` document on success — carries the subject hash, `as_of`, the
manifest and revocation sequences, and per signature a `key_id`, role,
purpose and status. No holder, no organization, no path, no name.

The module that decides validity — signature, enrolment, threshold, freshness
— is a safety module under the rule this repository already applies, whichever
backend it calls: B-035 adds it to `SAFETY_MODULES` in the Makefile, so it sits
under the 95% branch floor and is a candidate for the ADR 0009 mutation subset,
and the backend's own test suite is not a substitute for that. Every `sign` and
`verify` command joins the matrix in `tests/test_determinism.py`, and the
safety-negative cases are the ones that must be written first: a tampered
subject, a signature moved between artifacts, a forged role, a revoked key, a
stale set, an `as_of` before the set, two signatures from one holder, and an
artifact produced before this layer presented as signed.

No key exists in this repository today. When B-035 adds one, every key is a
fixture key derived from a fixed 32-byte seed that is visibly a fixture,
enrolled in a manifest whose `organization_id` and `holder_id` begin
`org-fixture-` and `holder-fixture-`, and labelled reference-only and
ungoverned in the file and in the test that loads it. The fixture root's
fingerprint is never the pinned constant.

### What verification proves, and what it does not

It proves that the canonical bytes whose hash is the subject were signed by the
holder of a private key whose public key the supplied trust state authorizes
for that purpose and role on the `as_of` date the caller declared; that enough
such signatures from distinct holders exist to meet the purpose's threshold;
and that the trust state was root-signed and no more than 31 days older than
`as_of`.

It does not prove when anything was signed: there is no trusted time without
an RFC 3161 timestamp or an independently witnessed append-only log, both P1
and both needing their own ADR, and `claimed_signed_at` is a note. It does not
prove the trust state supplied is the newest that exists, only that it is not
stale relative to a date the caller chose. It does not prove that the person
the confidential roster maps to a `holder_id` is who they say, holds the role,
was independent, or performed the review: a signature authenticates a key. It
does not prove a key was uncompromised before its revocation. It does not
prove a pack is clinically correct, a receipt truthful, or a synthetic case
safe (T-13, R-04 and the residual risks in
[threat model section 13](../06-SECURITY-PRIVACY-THREAT-MODEL.md) all still
apply). And it never turns an artifact produced before this layer into a
signed one.

### Threats this layer answers, and the surface it opens

From [the threat model](../06-SECURITY-PRIVACY-THREAT-MODEL.md): T-01 (forged
reviewer identity) is the reason for the manifest, the role enum and the
distinctness rule, and its residual — a compromised endpoint or trust root —
is the reason the compromise section above exists; T-03 (evidence or result
changed after review) and T-05 (repudiated disposition) are the reason for
detached signatures over canonical hashes; T-12 (expired oracle still yields
pass) is the reason revocation ships inside the manifest and staleness blocks
a verified result; T-11 and TB-08 are the reason the dependency is a decision
and not a default, and why the extra is one hash-locked library; TB-06
(reviewer identity and signing) is the boundary this whole record sits on;
T-13 is why a verified receipt is still not a certification and why its
mandated limitations survive signing unchanged. The layer also opens surface:
the manifest and the plan's enrolment are exactly the roster T-08, T-17 and
T-18 protect, which is why they carry tokens and not names; R-20 (revocation
does not reach an offline customer) is bounded to 31 days and no further; R-21
(signing key or build chain compromised) gains a revocation path and a
root-replacement path that is unexercised until B-047.

## Consequences

- One decision, the maintainer's, unblocks B-035 and B-036. Until it is made,
  neither starts, and nothing here changes what the tool emits today.
- Under (c), the base install keeps a true `dependencies = []`, and the wheel
  gains a documented second shape that CI has to test in both forms.
- Every artifact keeps its verifiability horizon in plain view: without
  trusted time, a signature is as durable as its key's validity interval, and
  keeping an artifact verifiable across rotation is a re-signing act.
- The manifest holds tokens; the roster that makes them people is confidential
  and lives nowhere in this repository.
- The two draft fragments above are the whole of the shape design, and they
  are not contracts until a reviewed change publishes them under `schemas/`
  with a row in `schemas/README.md` and a schema/runtime agreement test in the
  style of `tests/test_receipt_schema.py`.
- The receipt contract's closed envelope constants (`not_signed`,
  `trusted_time: false`) are untouched by this design: a signed receipt is a
  receipt document plus detached signature documents beside it, not a receipt
  whose envelope says something new. Whether the envelope ever gains a
  `signature_status` value other than `not_signed` is a versioned contract
  change for B-035 to propose and this record does not pre-empt.

## What this is not

- **Not an implementation.** No module, command, schema, fixture, key, test or
  dependency is added by this record. The shipped tool is byte-identical.
- **Not a decision.** The dependency choice is the maintainer's and has not
  been made; the recommendation above is a recommendation.
- **Not an approval.** Nothing here has had the security/privacy design
  review B-040 requires, and the pack threshold it restates is the clinical
  safety chair's and community co-chair's to hold, not this record's to set.
- **Not a trusted-time design.** Every sentence about time above says
  `as_of`, and `as_of` is the caller's word.
- **Not a relabeling.** The existing `not_signed`, `not_verified` and
  `not_verified_internal_test_only` artifacts stay exactly that.

## Rejected alternatives

- **A pure-Python Ed25519.** Rejected above, and the reasons do not age: the
  interpreter's arithmetic is not constant-time, and the reviewer this would
  need does not exist here.
- **Selecting the backend at import time from whatever is installed.** Two
  verifiers, one artifact, platform-dependent validity. A determinism failure.
- **Signing whole files instead of subject hashes.** An envelope field would
  become signed content, `claimed_signed_at` would become a signed timestamp
  by accident, and a re-serialized artifact would fail verification while its
  payload was unchanged. The subject hash is the thing every artifact already
  publishes for exactly this use.
- **Accepting a historical signature from an expired key.** A trusted-time
  claim wearing a validity interval. It waits for its own ADR.
- **A verifier that keeps its own state to enforce revocation monotonicity.**
  A hidden file the verifier trusts is a second trust root nobody signed.
- **A `--trust-root` command-line flag.** Whoever can pass a flag can pass a
  root; the pin is a constant in the runner, replaced only by a verifier
  release.
- **Names and organizations in the manifest, as section 6.6's wording
  suggests.** Rejected in favour of tokens plus a confidential roster, pending
  the maintainer's confirmation, because a manifest is producible and a roster
  of trans-health reviewers is what T-08, T-17 and T-18 exist to keep small.
- **Relabeling existing artifacts once a signing layer exists.** Closed by
  every module that emits one, by the receipt contract, and by this record.
