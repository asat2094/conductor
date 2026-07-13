# ADR-0021: Pluggable context-optimizer facade — baked-in defaults, opt-in heavy backends

- **Status:** Accepted (supersedes the compression-engine portion of [ADR-0019](./0019-caveman-compression-paid-boundaries.md))
- **Date:** 2026-06-10
- **Requirements:** REQ-E1, REQ-E2, REQ-E3

## Context

Token optimization (compressing what the LLM reads) is a top-priority efficiency lever, but the candidate engines differ wildly in weight: a stdlib prose trim (zero deps, deterministic) vs. headroom (Rust `_core` wheel + optional HF model + tree-sitter, content-aware + reversible). ADR-0019 picked a single hand-rolled caveman engine; the analysis of headroom showed a far more capable engine but a heavy native dependency that gives the *current* on-disk functional set zero benefit and would forfeit the harness's stdlib-only portability.

Committing the basic functional set to any one engine — light or heavy — is the wrong shape. The basics must stay exceptional-free and work out of the box; the heavy optimizer must be an opt-in enhancement, not a baked-in dependency. And the optimizer is generically useful — there is no reason to couple it to conductor.

## Decision

Introduce a **provider-agnostic optimizer facade** with a **pluggable backend registry**:

- A single host entry point `optimize(messages, cfg) -> OptimizeResult`. Default backend is **`null` (passthrough)** — always available, zero deps, cannot break the host.
- Backends implement a `Compressor` Protocol (`name`, `available()`, `optimize()`, optional `retrieve()`) and `register(name, factory)`. Third parties / other systems can add backends without touching the facade.
- **Baked in out of the box:** `null` (passthrough) + `caveman` (stdlib prose trim, deterministic, no deps). These are the non-exceptional defaults.
- **Opt-in, flag-gated:** `headroom` (and any future backend) lazy-imports its dependency; if absent or erroring, the facade **degrades to `null`** — never crashes.
- **Selection by config/flag:** `OptimizeConfig.backend` / env `CONDUCTOR_OPTIMIZER`. Flipping the flag changes behavior with no host code change.
- **Safety invariants enforced by the facade regardless of backend** (`guard`): skip payloads below `min_tokens`; a hard **protect-list** (gate evidence, code-to-edit, system/contract messages) is restored byte-identical in the output even if a backend ignores it; any backend failure degrades to passthrough.
- The facade package has **no conductor-specific imports** → it is extractable as a standalone package/plugin and usable by any system.

ADR-0019's caveman engine is demoted to one backend among several; its paid-boundary guidance (prose-only, never gate evidence) is preserved as the facade's protect-list invariant.

## Considered alternatives

- **Adopt headroom directly as the engine (the earlier framing)** — Pros: most capable immediately. Cons: forces a heavy native dep into the basics, zero benefit to current on-disk code, vendor lock-in, kills stdlib portability. Rejected in favor of a neutral facade with headroom as an opt-in backend.
- **Keep the single hand-rolled caveman engine (ADR-0019)** — Pros: zero deps. Cons: prose-only, lossy, not reversible, not swappable; can't grow into headroom-class capability without a rewrite. Rejected — superseded by the facade (caveman survives as a backend).
- **No optimizer; rely on the model's own context handling** — Pros: nothing to build. Cons: forfeits the headline efficiency lever. Rejected.

## Consequences

- **Positive:** basics stay zero-dep and inert by default; the heavy engine is a flag away, not a commitment; the seam is vendor-neutral and reusable beyond conductor; the protect-list invariant makes Law 1 violations structurally impossible on the compression path.
- **Negative:** an indirection layer + a backend registry to maintain; the `OptimizeResult`/Protocol shape must stay stable as a public contract; two backends (null/caveman) ship even when unused.
- **Neutral:** reversible (CCR) semantics are expressed via the optional `retrieve()` Protocol method — backends without reversibility simply return `None`.

## Related

[ADR-0019](./0019-caveman-compression-paid-boundaries.md) (superseded engine choice), [ADR-0001](./0001-lean-orchestrator-no-file-bodies.md) (the read-path this optimizes), [ADR-0002](./0002-no-trust-maker-self-report.md) (protect-list keeps gate evidence off the compression path). REQ-E1/E2/E3.
