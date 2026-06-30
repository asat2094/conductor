# ADR-0031: Discriminated brief/work-unit schema guards

- **Status:** Proposed
- **Date:** 2026-06-30
- **Requirements:** REQ-D10
- **Borrowed from:** microsoft/conductor (`config/schema.py` — one discriminated model, per-type forbidden-field guards).

## Context

`brief.validate_brief` checks required keys + a few enums. But a `SubtaskBrief` carries task-type-specific shape: a `signature_change` unit must declare the new signature; a `test_write` unit legitimately writes a test file (and is exempt from the scope guard); a `perf` unit needs a benchmark target. Today a malformed-for-its-type brief (right keys, wrong combination) passes validation and fails late, mid-dispatch. microsoft/conductor's `AgentDef` is one model covering 7 step types with rigorous "type X cannot have field Y / must have field Z" guards that reject malformed nodes before execution.

## Decision

Strengthen brief validation into **discriminated, per-task-type guards** (stdlib — no pydantic dependency, keeping the harness dep-light):

- Validate the brief against task-type-specific rules: required/forbidden fields per `task_type` (e.g. `signature_change` requires a declared new signature; `test_write` permits test-file `writes_files`; `refactor`/`perf` require a characterization target; functional types require a `verify_cmd` or discoverable test).
- Reject malformed-for-type briefs at decompose time (feeds the hard gate, ADR-0011, and the verifier, ADR-0022) — before any dispatch.
- Pure, deterministic; extends `lint_plan`/`validate_brief`, no new dep.

## Considered alternatives

- **Adopt pydantic + discriminated unions (as ms/conductor does)** — Pros: declarative, battle-tested. Cons: a heavy new runtime dep on a stdlib-only harness; overkill for ~6 task types. Rejected — port the *pattern* (per-type guards) in stdlib.
- **Keep flat validation (status quo)** — Pros: simplest. Cons: malformed-for-type briefs fail late. Rejected.

## Consequences

- **Positive:** malformed briefs caught before dispatch, not mid-run; the per-type rules document the brief contract precisely; strengthens the decomposition hard gate.
- **Negative:** a per-task-type rule table is new surface to maintain as task types evolve; stdlib validation is more verbose than a pydantic schema.
- **Neutral:** complements (does not replace) the JSON Schema in `docs/specs/conductor/schemas/`.

## Related

[ADR-0011](./0011-hardgate-decomposition-briefs.md) (hard gate), [ADR-0022](./0022-codegraph-decomposition-verifier.md) (verifier consumes well-formed briefs), [ADR-0010](./0010-nonfunctional-characterization-gate.md) (per-type gate profiles). REQ-D10.
