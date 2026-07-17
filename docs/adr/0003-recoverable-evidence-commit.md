# ADR 0003 — Preflight before persistence and recoverable evidence commit

Status: accepted for internal iteration 3; pilot use prohibited
Date: 2026-07-13
Decision owners: technical owner; independent security/privacy review still required

## Context

B-017 requires the complete privacy boundary check to finish before ContextSafe writes
source bytes. B-018 then requires content-addressed files plus an append-only SQLite
index. A portable local process cannot atomically commit a filesystem object and a
SQLite row as one transaction. Reopening the source by pathname between checking and
copying would also allow validated bytes to differ from stored bytes.

## Decision

- Open a caller-owned, seekable regular file once with final-component no-follow and
  retain the descriptor.
- Complete the bounded first pass, strict format/field/namespace/free-text/canary
  checks, descriptor metadata comparison, and H1 without creating a workspace.
- Initialize a brand-new SQLite index completely in an owner-only temporary file and
  publish it by no-overwrite hard link. Existing indexes are opened without create;
  read APIs use SQLite read-only/query-only mode and never run schema DDL or repair.
- For internal store tests only, start an exclusive SQLite write transaction before
  staging the second pass. Validate SQLite integrity, the exact schema/header, every
  denormalized row column, and every referenced object before removing crash remnants.
- Seek the same descriptor, copy to an owner-only same-filesystem staging object,
  compute H2, compare descriptor metadata again, and continue only when H1=H2.
- Promote by no-overwrite hard link to the full SHA-256 address, append the canonical
  index row, and commit SQLite with `synchronous=FULL`.
- Remove the new object on an ordinary pre-commit failure. If commit outcome is
  uncertain, retain the object and let the next exclusive recovery retain it when the
  row committed or remove it when no row exists.
- Protect evidence rows against update/delete. All current records remain
  `not_verified_internal_test_only` and non-executable; no CLI import route exists.

## Consequences

Bytes rejected by the complete first pass never enter a ContextSafe workspace,
quarantine area, temporary file, index, or content-bearing log. After first-pass
success, the second pass writes a private staging file before its final H2 and descriptor
metadata checks. A mutation fails before promotion or indexing and cleanup is attempted;
if the filesystem denies cleanup, partial second-pass bytes can remain until a permitted
exclusive recovery or explicit operator remediation. A crash may likewise leave an
unindexed content object until the next transaction; neither condition creates an
indexed passing result from an incomplete copy. The implementation must describe this
as recoverable consistency, not cross-resource atomicity. A workspace must not be used
for pilot evidence until signature authorization, governed cleanup, independent
security/privacy review, and operational recovery drills exist. The bounded first-pass
buffer and parsed values exist in process memory; platform crash dumps remain a residual
risk and must be disabled/controlled by the approved operating environment rather than
described as durable zeroization.

## Rejected alternatives

- Reopen by pathname for the second pass: rejected because of pathname races.
- Write a quarantine copy before scanning: rejected because prohibited bytes would
  already be persisted.
- Store raw bytes as a SQLite BLOB: rejected because it breaks the planned local
  content-addressed workspace and makes customer custody/inspection less direct.
- Claim filesystem and SQLite atomicity: rejected because it is not technically true.
