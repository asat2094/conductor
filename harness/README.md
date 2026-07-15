# harness/

The conductor harness. A lean orchestrator decomposes a dev task into a DAG of bounded work-units,
dispatches each to a capability×cost-ranked model, and accepts work **only through mechanical gates**
(tests / AST / mutation / lint) — never a maker's self-report.

## Entrypoints

```bash
python3 -m harness briefs.json --workdir <repo> --report   # distributed build (CLI)
python3 -m harness.evalkit --model gemma4 --ingest          # calibrate model capability profiles
python3 -m harness.router '<subtask_json>'                  # legacy single-task route
python3 -m harness.pipeline '<subtask_json>' --workdir <d>  # legacy one-off route+delegate+eval+heal
```

Library: `from harness.live_pipeline import build_live` (full knobs — judge, confidence, best-of-N,
merge queue, style/tdd/codegraph/probes gates, cost ceiling, checkpoints).

## Module map

**Spine** (decompose → waves → dispatch → gate → repair → merge)
- `__main__.py` — the distributed-build CLI
- `live_pipeline.py` — `build_live`: onboard repo → decompose → per-wave dispatch → gates → merge
- `run_dag.py` — topo waves, cost-skip, best-of-N, per-wave promotion, cost ceiling, checkpoints
- `live_maker.py` — real maker: model → files → diff → in-loop test → `UnitArtifact`
- `process_unit.py` — bounded repair loop around the gate
- `merge_queue.py` / `git_merge_queue.py` — DAG/per-wave atomic merge (bookkeeping / real git ff)
- `decompose.py`, `dag.py`, `run_brief.py`, `brief.py` — brief → DAG plumbing

**Gates** (mechanical, Law 2 — no model judges output)
- `unit_gate.py` — composed gate: scope-guard → pbt → acceptance/oracle → extra stages → style
- `gate_stages.py` — opt-in git-RED / mutation / characterization stages
- `evaluator.py`, `scope_guard.py`, `pbt_gate.py`, `held_out_oracle.py`, `mutation.py`,
  `characterization_gate.py`, `git_red_gate.py`, `strict_gates.py`, `style_gate.py`, `deps_check.py`
- `judge.py` — inconclusive-only LLM-judge tiebreak (bounded exception, ADR-0038)

**Routing & admission**
- `router.py` — ROI ranking + cost-skip + sensitivity boundary
- `confidence.py` — adaptive per-(model, task-type) confidence (ADR-0039)
- `role_policy.py`, `profiles.py`, `capability_profiles.json`, `cost_model.py`, `tokens.py`
- `admission.py` — AIMD / token-bucket / circuit-breaker / cost ceiling
- `model_call.py`, `provider_call.py`, `providers.json` — model backends (ollama / claude CLI / cloud)

**Observability & context**
- `tracker.py` / `tracker_store.py` / `progress.py` — event-sourced board + sinks (live / JSONL / webhook)
- `checkpoint.py` — checkpoint / resume / replay
- `codegraph_live.py`, `verify.py`, `spec_probes.py`, `ccr_store.py`, `retrieve.py`, `sensitivity.py`
- `optimizer_wiring.py` + `optimizer/` — reader-aware context compression (see `optimizer/README.md`)

**Subpackages**
- `lang/` — pluggable per-language adapters ([README](lang/README.md))
- `evalkit/` — generic model-evaluation framework ([README](evalkit/README.md))
- `optimizer/` — pluggable context-optimizer facade ([README](optimizer/README.md))
- `tests/` — `python3 -m pytest -q`

The design rationale for every module lives in `docs/adr/` (42 ADRs). Base modules never branch on
language — that seam is `lang/`; correctness is never a model's opinion — that's `unit_gate.py`.
