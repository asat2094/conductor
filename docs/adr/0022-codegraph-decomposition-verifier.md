# ADR-0022: Codegraph-backed decomposition verifier — advisory, degrade-clean, separate from pure decompose()

- **Status:** Proposed (refines [ADR-0011](./0011-hardgate-decomposition-briefs.md): codegraph moves from a pure hint to an *active but advisory* verifier)
- **Date:** 2026-06-11
- **Requirements:** REQ-D6, REQ-D7, REQ-D8, NFR-VERIFY-1

## Context

The decomposer (ADR-0011) compiles orchestrator-declared contracts (`produces`/`consumes`/`logical_deps`) into a DAG and lints them — but it **blindly trusts the declarations**. Three honest limits follow: declaration quality is unverified (L1), wrong groupings (real code coupling the LLM didn't declare) pass undetected (L3), and garbage contracts produce garbage waves (L4). All three are the same hole: nothing cross-checks the declared contract against the actual code.

Codegraph (codegraphcontext MCP) can supply ground-truth dependency edges. The temptation is to make codegraph a hard gate. That would make things *worse* in specific ways (recorded in Consequences): a degrade-only dependency becomes load-bearing, environments diverge (local vs CI), static-analysis false positives block valid plans, decompose-time latency grows, `decompose()` loses its purity, and — most dangerously — the team gains false confidence because static analysis cannot see dynamic/reflective coupling.

## Decision

Introduce a codegraph-backed **verifier** as a **separate, advisory, degrade-clean layer** — never folded into the pure DAG construction:

1. **`decompose()` stays pure** (briefs → validated waves, deterministic given briefs). The verifier is a distinct step that **annotates**, never silently mutates the DAG.
2. The verifier cross-checks declarations against codegraph edges (consumed via the existing injectable `dependency_edges`, so it is unit-testable with mocked edges):
   - **Under-declared edge (L1/L3):** a unit's files reference a symbol owned by another unit with no declared `consumes`/edge → **ERROR only when high-confidence**, else warning.
   - **Over-declared edge (L4):** declared `consumes` never referenced in code → warning.
   - **Dangling-against-real-repo (L1):** consumes an existing symbol codegraph says doesn't exist → ERROR.
   - **Coverage signal (L4):** `% of declared edges corroborated` + list of unverifiable units.
   - **Density/decomposability signal (L2):** if the graph is near-complete / collapses to one coupled blob → advisory "not cleanly decomposable; prefer inline/interactive." **Advisory only — does not auto-route.**
3. **Degrade-clean:** when codegraph is absent or errors, the verifier emits an explicit `unverified` status (logged) and the build proceeds on the lint-only gate — **REQ-D4 and S10 preserved**. The verifier never becomes a hard requirement.
4. **Phase-aware:** at decompose time it checks `consumes` of *existing* symbols + file-locality coupling; `produces` of not-yet-written code are trusted now and re-verified post-wave (folds into the S4 seam check).

## Considered alternatives

- **Make codegraph a hard decomposition gate** — Pros: strongest catch of wrong groupings. Cons: load-bearing dep, env non-determinism, false-positive blocking, latency, loss of `decompose()` purity, false confidence. Rejected — the cure exceeds the disease.
- **Leave the limits unaddressed (ADR-0011 as-is)** — Pros: simplest, pure. Cons: blindly trusts declarations; local-green/global-broken survives decomposition. Rejected — but its degrade path is preserved as the fallback.
- **Static AST analysis in-harness instead of codegraph** — Pros: no MCP dep. Cons: reinvents a worse code graph; same dynamic-coupling blind spot. Rejected in favor of the existing codegraph adapter.

## Consequences

- **Positive:** L1/L3/L4 substantially closed — declarations become machine-verified against code; coverage signal turns "trust the LLM" into a measurable number; wrong-grouping and dangling-against-repo caught before dispatch.
- **Negative (the honest worsening):**
  - codegraph risks drifting from optional → expected; guarded by keeping the verifier advisory + degrade-clean.
  - results differ by environment (codegraph present vs not) — mitigated by emitting `unverified` explicitly so the difference is visible, not silent.
  - static-analysis **false positives** can flag valid plans → ERROR reserved for high-confidence; rest are warnings.
  - decompose-time latency/cost grows (per-unit queries) — batch/cache required.
  - heuristic symbol→unit ownership can produce wrong edges → wrong errors.
  - density threshold is new tuning debt.
  - **false confidence:** the verifier is only as good as static analysis; dynamic/reflective coupling escapes it — this residual is recorded in the spec's Unresolved, deliberately, so trust stays calibrated.
- **Neutral:** the verifier is a separable layer (like the optimizer) — it could be extracted or disabled wholesale without touching `decompose()`.

## Related

[ADR-0011](./0011-hardgate-decomposition-briefs.md) (refined), [ADR-0004](./0004-bound-seed-input-ceiling.md) (assembly golden is the backstop for residual wrong-grouping), [ADR-0012](./0012-contract-conformance-ast-drop-pact.md) (post-wave seam check). REQ-D6/D7/D8, NFR-VERIFY-1.
