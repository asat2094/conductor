# Conductor — Local Multi-Agent Harness

This repo IS the harness. When working here, you are configuring or extending the conductor system.

## What conductor does

Offloads mechanical coding tasks (code edits, code gen, file creation, test writing) to gemma4 running locally via ollama. Claude orchestrates; gemma4 executes small, bounded tasks.

gemma4 can **edit existing files** and **create new files** — the harness handles filesystem I/O, gemma4 only does the text transformation.

## Running a distributed build (PRIMARY — the ADR-gated DAG spine)

```bash
# Decompose -> verify -> per-wave dispatch through real makers, mechanical gates only.
# briefs.json = JSON list of SubtaskBriefs (see docs/specs/conductor/schemas/).
python3 -m harness briefs.json --workdir <repo> --report
# Opt-in gates/features:
#   --style        repo-native lint/format gate (ADR-0036)
#   --tdd-gates    git-RED commit-order gate (ADR-0030)
#   --codegraph    codegraph verify + per-wave reverify (ADR-0022)
#   --probes       advisory spec-completeness probes (ADR-0032)
#   --atomicity wave|dag   per-wave vs whole-DAG merge (ADR-0041)
#   --budget N --budget-mode audit|enforce   token ceiling (ADR-0034)
#   --checkpoint ck.json / --resume ck.json  wave-boundary checkpoints (ADR-0028)
# Exit: 0 = no unit failed.
```

Library form: `harness.live_pipeline.build_live(...)` (judge tiebreak, confidence store,
best-of-N, merge queue, webhook sink are library-only knobs — see its docstring).

## Running single tasks (legacy one-off path)

```bash
# FASTEST: end-to-end pipeline — route + delegate + evaluate + auto_heal in one shot
python3 -m harness.pipeline '{"id":"t1","description":"<task>","type":"code_edit","files":["<path>"]}' \
  --workdir <absolute-workdir>
# Exit: 0=done, 1=routed to claude_agent, 2=strategy C (escalate)

# 1. Route only — check which agent should handle a task
#    estimated_tokens is optional; auto-estimated from file sizes if omitted
python3 -m harness.router '{"id":"t1","description":"<task>","type":"code_edit","files":["<path>"]}'

# 2a. Delegate to gemma4 (full file rewrite)
bash harness/gemma4_delegate.sh <absolute-workdir> "<task>" <file>

# 2b. Delegate in diff mode (safer for large files; falls back to full rewrite if patch fails)
bash harness/gemma4_delegate.sh <absolute-workdir> "<task>" <file> --diff

# 2c. Delegate multiple independent files in parallel (bash)
bash harness/gemma4_delegate.sh --parallel <absolute-workdir> \
  '[{"task":"<task1>","file":"<file1>"},{"task":"<task2>","file":"<file2>"}]' \
  --workers 2

# 2d. Delegate multiple files in parallel with per-task healing (Python)
python3 -c "
from harness.parallel_delegate import delegate_parallel
from harness.models import SubTask, TaskType
results = delegate_parallel('<workdir>', [
    {'task': '<task1>', 'file': '<file1>'},
], heal=True, subtasks=[SubTask(...)])
"

# 3. Evaluate output (changed_files optional if workdir + subtask.files supplied)
python3 -m harness.evaluator '{"subtask":{...},"agent":"gemma4","workdir":"<path>","output":"<output>"}'

# 3b. Evaluate with auto-healing
python3 -m harness.evaluator '{...}' --auto-heal

# 4. Stats
bash harness/stats.sh
```

## Routing rules

| Condition | Agent |
|---|---|
| type = `research` or `cross_file_refactor` | claude_agent |
| estimated_tokens > 32,000 | claude_agent |
| gemma4 failures ≥ 3 in session | claude_agent |
| gemma4 accuracy < 70% for task type | claude_agent |
| otherwise | gemma4 |

`estimated_tokens` auto-derived from file sizes (chars/4) when not supplied.

## Healer auto-apply

When evaluator score < 70, call `auto_heal()` — it tries strategy A (shrink) then B (re-prompt) automatically. Only surface strategy C (escalate to claude_agent) if both fail.

## Cross-session accuracy decay

`load_profiles()` applies ~2%/day decay toward 0.5 (neutral) based on `last_updated` timestamp. Prevents stale high scores from over-routing to gemma4 after a long gap.

## Model evaluation (evalkit — generic framework, ADR-0042)

```bash
# Evaluate ANY model over the default grid (or a bring-your-own suite); objective merit scorecard.
python3 -m harness.evalkit --model gemma4 --text
python3 -m harness.evalkit --model gemma4 --model sonnet --report card.json   # rank several
python3 -m harness.evalkit --model gemma4 --suite my_suite.json               # BYO tasks
python3 -m harness.evalkit --model gemma4 --ingest                            # feed routing profiles
```
Library: `from harness.evalkit import calibrate, default_suite, load_suite, ingest, register_dimension`.
Pluggable `Dimension` (accuracy/latency/cost_per_pass/refusal_rate/context_degradation/reliable_context)
+ mechanical `Grader` (syntax via LanguageAdapter, keyword, oracle, composite). Objective/deterministic.

## Development

```bash
bash setup.sh          # idempotent setup + prereq check
/opt/homebrew/bin/pytest -q   # run the full test suite
python3 gemma4-bench/bench.py  # calibrate gemma4 (thin evalkit client; == python3 -m harness.evalkit --model gemma4 --ingest)
```

Key files:
- `harness/__main__.py` — `python3 -m harness` distributed-build CLI (the DAG spine)
- `harness/live_pipeline.py` — build_live: onboard -> decompose -> waves -> gates -> merge
- `harness/run_dag.py` / `harness/unit_gate.py` / `harness/merge_queue.py` — spine internals
- `harness/pipeline.py` — legacy one-off route+delegate+eval+heal; `python3 -m harness.pipeline`
- `harness/router.py` — routing logic (auto token estimation)
- `harness/tokens.py` — estimate_tokens() from file sizes (per-extension multipliers)
- `harness/evaluator.py` — output scoring; --auto-heal flag; derives changed_files from workdir
- `harness/healer.py` — auto_heal(diff_mode=) propagates mode through A→B→C
- `harness/parallel_delegate.py` — concurrent multi-task delegation (heal=True, diff_mode propagation)
- `harness/parallel_cli.py` — bash-accessible parallel delegation; `python3 -m harness.parallel_cli`
- `harness/gemma4_call.py` — ollama REST API caller (importable run(), --diff + fallback)
- `harness/profiles.py` — load/save/update + cross-session decay (decay_per_day per-profile)
- `harness/session_stats.py` — SQLite delegation log
- `harness/capability_profiles.json` — live gemma4 thresholds (includes decay_per_day)
- `gemma4-bench/bench.py` — benchmark; merges results via rolling avg (preserves real-session accuracy)
