# 0. Record architecture decisions

## Status

Accepted

## Context

ContextSafe makes a small number of consequential, hard-to-reverse decisions — the
v1 synthetic/non-production boundary, the deliberately unsigned compilation stage,
the recoverable evidence-commit protocol. This repository's planning corpus is
large, but the *decisions* embedded in it must not live only inside long planning
documents, a commit message, or a closed PR thread, or a later change will either
re-litigate a settled question or unknowingly reverse a decision made for a reason
nobody re-reads.

## Decision

We will record architecture decisions in **Architecture Decision Records (ADRs)**
using the format described by Michael Nygard.

- Each ADR is a short Markdown file in `docs/adr/`, numbered sequentially and named
  `NNNN-title-in-kebab-case.md`.
- Each ADR has the sections **Title**, **Status**, **Context**, **Decision**, and
  **Consequences**.
- **Status** is one of *Proposed*, *Accepted*, *Deprecated*, or *Superseded*. A
  superseded ADR is not deleted; it is marked superseded and points to the ADR that
  replaces it, and the replacement points back.
- ADRs are immutable once accepted, except to change their status. A new decision is
  a new ADR, not an edit to an old one.

This ADR establishes the practice. ADRs 0001–0003 are the existing decision records
(previously kept in `docs/decisions/`, relocated here so the whole log lives in one
conventional place); their content is unchanged.

## Consequences

- The reasoning behind structural decisions is preserved and versioned alongside the
  code it explains.
- Writing an ADR is a small, deliberate friction on consequential change — intended,
  since it makes reversing a load-bearing decision (like the v1 non-production
  boundary) a visible act rather than an accident.
- ADRs add a modest maintenance habit. They capture decisions, not the full design —
  the planning corpus in `docs/` remains the home for requirements, threat model,
  and roadmap.
