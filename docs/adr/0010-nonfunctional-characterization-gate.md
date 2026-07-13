# ADR-0010: Gate non-functional tasks via property-driven characterization + contract-surface diff

- **Status:** Accepted
- **Date:** 2026-06-09
- **Requirements:** REQ-T6, REQ-I4

## Context

Refactor, rename, docstring, and perf tasks change no observable behavior, so RED/GREEN has nothing to assert — the legacy evaluator gave them a free pass, and a behavior-changing "refactor" would sail through green existing tests. These need a gate that verifies *behavior preserved* without a behavior-change contract.

## Decision

Non-functional units are gated by **characterization**: capture observable I/O over the touched symbols *before* the edit, re-derive *after*, and diff. Drive the capture with **property-based generated inputs under a pinned seed** (not a handful of fixed seeds), so the before/after comparison spans an input space. Add a **contract-surface diff** (exported signatures/types must match unless the task is explicitly `signature_change`). Rename uses **compile-RED** (a test referencing the new name fails to import against old code, then passes after). Perf uses an advisory benchmark-delta band, never a hard 0-score.

## Considered alternatives

- **No gate (legacy free pass)** — Pros: trivial. Cons: behavior-changing refactors accepted. Rejected.
- **Fixed-seed goldens only** — Pros: cheap, deterministic. Cons: false safety — covers only the captured seeds (the seed-input ceiling). Rejected in favor of property-generated inputs.
- **Full behavioral re-derivation** — Pros: strongest. Cons: cost, and there is no behavior-change contract to derive against. Rejected.

## Consequences

- **Positive:** the previously-ungated refactor class is gated, model-free, over a wide input space.
- **Negative:** property generators and golden capture are infra to build; perf benchmarks flake on variance (hence advisory).
- **Neutral:** requires the touched symbols to have a discoverable observable surface (entrypoint/fixtures) — defined in design.

## Related

ADR-0008/0009 (functional gates), ADR-0012 (contract diff), ADR-0004 (property inputs bound the seed ceiling). REQ-T6, REQ-I4.
