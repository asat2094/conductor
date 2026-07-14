# ADR-0002: Do not trust maker self-report as gate evidence (Law 1)

- **Status:** Accepted
- **Date:** 2026-06-09
- **Requirements:** REQ-C1

## Context

A maker is an untrusted, possibly-cheap, possibly-misaligned model. When it finishes a unit it returns an envelope: an `output` string, a status, a heartbeat, sometimes a claim like "tests pass" or "I created the file as specified." The fundamental hazard is that **the thing being checked is the thing supplying the evidence**. A maker that hallucinates success, silently truncates a file, or reports green on a suite it never ran will pass any gate that reads its own report. This is the classic verification-theater failure: the check exists, but its input is controlled by the party it is meant to police.

Conductor's correctness depends on gates whose evidence the maker cannot author.

## Decision

All gate evidence is **harness-derived**:

- syntax/structure verdicts come from the harness's own AST parse of the file actually written to disk,
- RED/GREEN/suite verdicts come from the harness independently re-running the tests,
- seam conformance comes from AST-extracted signatures compared against the orchestrator-owned contract.

The maker's self-report — its `output` field, envelope status, and heartbeat — is treated strictly as a **routing and health signal** (useful for liveness, retry, and profiling) and is **never** admitted as gate evidence. No accept/reject decision may cite a maker-reported field.

## Considered alternatives

- **Trust the self-report, audit a sample** — Pros: cheap, fast, no independent re-run on the hot path. Cons: the audited sample is the only honest check, and the un-audited majority pass on the maker's own word — verification theater, since the checked party supplies the evidence for most units. Rejected: violates the core hazard this ADR addresses.
- **A model judge reads the maker's output and rules on it** — Pros: catches semantic problems a parser misses; flexible. Cons: adds model cost per unit, is non-deterministic, and a judge reading the maker's narrative can be talked into agreement (collusion / shared blind spot) rather than checking ground truth. Rejected as gate evidence; permitted only as an **advisory** escalation signal under ADR-0003, never as the deterministic gate.

## Consequences

- **Positive:** a lying, truncating, or hallucinating maker cannot pass a gate, because the gate never reads what the maker says — only what the maker actually wrote and what the harness independently observed. Evidence is reproducible from disk.
- **Negative:** independent re-run and AST parsing cost real wall-clock time and compute on every unit, and the harness must own robust parse/test-run infrastructure for the target language — this is the price of not trusting the cheap report.
- **Neutral:** the maker envelope is not discarded; it still drives liveness/retry/profiling, so the system keeps the cheap signal where cheapness is safe.

## Related

ADR-0001 (lean orchestrator) — the lean verdicts the orchestrator consumes are exactly these harness-derived results. ADR-0003 (mechanical-first, model-last) — defines when a model check may fire as advisory escalation. REQ-C1; underpins REQ-T1/T3/I1 which all forbid using the maker envelope.
