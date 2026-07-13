# ADR-0011: Hard-gate decomposition into self-contained SubtaskBriefs

- **Status:** Accepted
- **Date:** 2026-06-09
- **Requirements:** REQ-D1, REQ-D2, REQ-D3, REQ-D4, REQ-D5, REQ-O2, REQ-O3

## Context

The token blast in Claude-driven development happens when a task is not cleanly decomposable: Claude does the work in the main context with full file bodies resident, and history grows every turn. Decomposition is also where logical coupling must be captured — codegraph gives structural edges but not logical ones. And the decomposer is the orchestrator (a non-deterministic LLM), so its output cannot be blindly trusted downstream.

## Decision

DECOMPOSE is a **HARD-GATE phase**: no unit dispatches until the orchestrator emits self-contained `SubtaskBrief` JSON per unit (goal, `context_slices` cut once, contract, `verify_cmd`, `exit_criteria`, `produces`/`consumes`, `logical_deps`, `sensitivity`), built from a codegraph + `logical_deps` producer→consumer DAG. `lint_plan` must pass (every consumed symbol resolves to an upstream producer/contract; no placeholders). A **phase-boundary compaction** then drops the file bodies the orchestrator read to cut slices — this is the token-saving mechanism. Because the orchestrator is untrusted, its outputs are gated too: orchestrator-authored acceptance/assembly tests are RED-validated against HEAD (REQ-O2) and the DAG/contracts get an independent second-model review on high-stakes units (REQ-O3). Codegraph degrade path is defined (REQ-D4).

## Considered alternatives

- **Claude decomposes ad-hoc inline** — Pros: no new phase. Cons: the token blast itself; bodies stay resident. Rejected.
- **Deterministic structural-only split (codegraph edges only)** — Pros: cheap, deterministic. Cons: misses logical coupling → local-green/global-broken. Rejected (codegraph is a *hint*, augmented by logical_deps).
- **Cheap-model decomposer** — Pros: offloads the weak-LLM work. Cons: low-quality DAG with no oracle. Rejected.

## Consequences

- **Positive:** bodies leave main context (the savings); coupling is explicit; the orchestrator's own output is no longer an ungated trust hole.
- **Negative:** decomposition correctness is bounded by orchestrator judgment with no full mechanical oracle (`lint_plan` catches missing symbols, not wrong groupings) — mitigated by the assembly golden gate (ADR-0004/0010) and REQ-O3 review; decomposition itself burns Claude tokens, so net savings only above a break-even size (gated by ADR-0016).
- **Neutral:** introduces a hard dependency on a codegraph provider (codegraphcontext MCP) with a defined fallback.

## Related

ADR-0016 (cost-skip below break-even), ADR-0012 (contracts from briefs), ADR-0004 (assembly backstop), ADR-0001 (compaction keeps orchestrator lean). REQ-D1..D5, REQ-O2, REQ-O3.
