# Conductor — Session Handoff

**Date:** 2026-05-29  
**Repo:** https://github.com/asat2094/conductor  
**Working dir:** `/Users/ankitatiwari/Desktop/claude-playground/conductor`  
**Tests:** 68 passing  
**Last commit:** `498e152 docs: add multi-provider harness design spec`

---

## What was built

Local multi-agent harness. Claude orchestrates; gemma4 (ollama, local) executes mechanical coding tasks. Goal: save Claude API tokens and context on small, bounded work.

```
Claude (orchestrator)
  ├─ route → gemma4 (local, free)   code_edit · code_gen · test_write
  └─ route → Claude agent           research · cross_file_refactor · complex tasks
```

---

## Architecture

### Fastest path (all-in-one)

```bash
python3 -m harness.pipeline '{
  "id": "t1",
  "description": "Add docstring to validate_order",
  "type": "code_edit",
  "files": ["backend/orders.py"]
}' --workdir /path/to/project [--diff] [--no-heal]
# Exit: 0=done, 1=routed to claude_agent, 2=strategy C (escalate)
```

### Step-by-step flow

```
1. python3 -m harness.router '{...}'          → gemma4 | claude_agent (auto-estimates tokens)
2. bash harness/gemma4_delegate.sh ...        → calls gemma4_call.py (--diff supported)
   OR
   bash harness/gemma4_delegate.sh --parallel <workdir> '<tasks_json>' [--workers N] [--diff]
3. python3 harness/gemma4_call.py ...         → ollama REST API → writes file or applies patch
                                                (--diff falls back to full rewrite if patch fails)
4. python3 -m harness.evaluator '{...}' [--auto-heal]
                                              → score/100; changed_files optional (derived from workdir)
5. score < 70 → auto_heal(diff_mode=) tries A then B → surfaces C only if both fail
6. bash harness/stats.sh                      → session token savings report
```

### Key files

| File | Role |
|---|---|
| `harness/pipeline.py` | `run_pipeline(subtask, workdir, diff_mode, auto_heal)` — full loop; `python3 -m harness.pipeline` |
| `harness/models.py` | Dataclasses: SubTask, EvalResult, CapabilityProfile (last_updated, decay_per_day); Enums |
| `harness/router.py` | 5-rule routing logic + CLI; auto-estimates tokens from file sizes if omitted |
| `harness/tokens.py` | `estimate_tokens(files, workdir)` — chars/4 × per-extension multiplier |
| `harness/evaluator.py` | 4-axis scoring + CLI; `--auto-heal` flag; `changed_files` auto-derived from workdir |
| `harness/healer.py` | `auto_heal(subtask, result, profiles, workdir, diff_mode=False)` — A→B→C |
| `harness/parallel_delegate.py` | `delegate_parallel(workdir, tasks, heal=, diff_mode=, subtasks=)` — ThreadPoolExecutor |
| `harness/parallel_cli.py` | `python3 -m harness.parallel_cli <workdir> <tasks_json> [--diff] [--workers N]` |
| `harness/profiles.py` | `load_profiles()` (applies decay per `profile.decay_per_day`), `save_profiles()`, `update_accuracy()` |
| `harness/gemma4_delegate.sh` | Bash wrapper; `--parallel` → `parallel_cli.py`; `--diff` → gemma4_call |
| `harness/gemma4_call.py` | `run(workdir, task, files, diff_mode=False)` importable + CLI; diff falls back to full rewrite |
| `harness/session_stats.py` | SQLite log; `log_delegation()`, `update_score()`, `print_report()` |
| `harness/stats.sh` | CLI wrapper for `session_stats.py` |
| `harness/capability_profiles.json` | Live gemma4 thresholds (includes `decay_per_day`) |
| `gemma4-bench/bench.py` | Calibration benchmark; merges via rolling avg — real-session scores survive recalibration |
| `gemma4-bench/bench_results.json` | Latest benchmark results (all cells 90/100) |
| `docs/2026-05-24-adaptive-multi-agent-orchestration-design.md` | Design spec (multi-provider future) |
| `setup.sh` | Idempotent one-shot setup; writes `~/.claude/CLAUDE.md` |
| `CLAUDE.md` | Auto-read by Claude Code when CWD is this repo |

---

## Critical discoveries

### 1. opencode run = conversational only
`opencode run -m ollama/gemma4:latest` is a **chat interface** — no file tools. gemma4 asked clarifying questions instead of editing files.

**Fix:** `gemma4_call.py` embeds file content in prompt, calls `http://localhost:11434/api/generate` directly via `urllib.request`, writes extracted code block to disk.

### 2. Benchmark first run scored 20-50
First benchmark used `opencode run` — prose responses, no code blocks.

**Fix:** Rewrote to use ollama REST API + explicit `` ```python `` block instruction. Re-run: all 30 cells 90/100.

### 3. Router CLI AttributeError
`subtask.type.value` failed — JSON gives `type` as plain string.

**Fix:** `subtask_data["type"] = TaskType(subtask_data["type"])` in `__main__` of `router.py` and `evaluator.py`.

### 4. Evaluator scope check — path mismatch
Full absolute paths vs relative paths → set diff found "extra" files → 10/20.

**Fix:** `_basenames()` — compare filenames only.

### 5. Semantic check — short output scored wrong
"Written successfully" had low word-overlap with description.

**Fix:** `estimate_semantic()` reads actual file content when output < 30 words. Takes `max(output_score, file_score)`.

### 6. Test score penalised unfairly
`_run_tests()` returned 0 when no test file existed, regardless of task type.

**Fix:** 20 partial credit when no test file exists.

### 7. gemma4 can't create files
`gemma4_call.py` errored on missing target.

**Fix:** Skip file read for missing files; use creation-mode prompt.

---

## Routing rules

```python
_ALWAYS_CLAUDE = {TaskType.RESEARCH, TaskType.CROSS_FILE_REFACTOR}

def route(subtask, profiles):
    g = profiles["gemma4"]
    if subtask.type in _ALWAYS_CLAUDE:                              return AgentType.CLAUDE_AGENT
    if subtask.estimated_tokens > g.max_reliable_tokens:            return AgentType.CLAUDE_AGENT
    if g.session_failures >= g.retry_budget:                        return AgentType.CLAUDE_AGENT
    if g.accuracy_by_type.get(subtask.type.value, 1.0) < 0.70:    return AgentType.CLAUDE_AGENT
    return AgentType.GEMMA4
```

`estimated_tokens` auto-derived via `estimate_tokens(files, workdir)` (chars/4 × ext multiplier) when 0 or omitted.

---

## Token estimation multipliers

| Extension | Multiplier | Reason |
|---|---|---|
| `.json` | 1.4× | Dense quotes, repeated keys |
| `.yaml` / `.yml` | 1.2× | Indentation + colons |
| `.html` | 1.3× | Tag overhead |
| `.sql` / `.css` | 1.1× | Moderate overhead |
| `.py` / `.js` / `.ts` / `.sh` | 1.0× | Baseline |
| `.md` / `.txt` | 0.8× | Prose compresses well |
| Unknown | 1.0× | Default |

---

## Evaluator scoring

| Check | Max | Method |
|---|---|---|
| Syntax | 25 | `ast.parse()` on changed `.py` files |
| Tests | 35 | Run pytest if test file exists; 20 partial credit if no tests |
| Scope | 20 | `_basenames(changed) - _basenames(requested)` |
| Semantic | 20 | Word overlap: description vs output (or file content if output short) |

Score ≥ 70: accept. Score < 70: `auto_heal()` fires.

`changed_files` optional in CLI JSON — derived from `workdir + subtask.files` when absent.

---

## Healer strategies

| Strategy | Trigger | Action |
|---|---|---|
| A — Shrink | Auto (first) | Halve files list (min 1), halve token estimate, retry gemma4 |
| B — Re-prompt | Auto (if A < 70) | Inject failure detail as constraint, retry gemma4 |
| C — Escalate | Manual (if A+B fail) | Route to claude_agent, increment `session_failures` |

```python
auto_heal(
    subtask, result, profiles, workdir,
    delegate_fn=None,   # default: gemma4_call.run
    evaluate_fn=None,   # default: evaluator.evaluate
    diff_mode=False,    # propagated to both A and B delegate calls
) -> tuple[EvalResult | None, "A" | "B" | "C"]
```

---

## Parallel delegation

```python
# Python API
from harness.parallel_delegate import delegate_parallel
results = delegate_parallel(
    workdir="/path/to/project",
    tasks=[{"task": "...", "file": "orders.py"}, ...],
    max_workers=3,
    diff_mode=False,
    heal=True,           # auto_heal per-task on failure
    subtasks=[...],      # required when heal=True
)
# returns list in input order; exceptions captured per-task; diff_mode propagates to heal calls

# Bash
bash harness/gemma4_delegate.sh --parallel /abs/workdir '<tasks_json>' [--diff] [--workers 2]
# OR
python3 -m harness.parallel_cli /abs/workdir '<tasks_json>' [--diff] [--workers N]
# Exit: 0=all OK, 1=any failed
```

---

## Diff mode

```bash
bash harness/gemma4_delegate.sh /abs/workdir "<task>" file.py --diff
```

Asks gemma4 for unified diff → applies with `patch(1)`.  
If `patch(1)` unavailable or diff apply fails → **automatically falls back to full file rewrite** (re-calls gemma4 without `--diff`). Warning logged to stderr.

`diff_mode` propagates through: `auto_heal` → `_try_heal` → individual delegate calls.

---

## Pipeline (end-to-end)

```python
from harness.pipeline import run_pipeline, PipelineResult

pr = run_pipeline(
    subtask,
    workdir="/my/project",
    diff_mode=False,
    auto_heal=True,
)
# pr.agent_used, pr.final_score, pr.strategy ("A"/"B"/"C"/None), pr.routed_to_claude
```

```bash
python3 -m harness.pipeline '<subtask_json>' --workdir /path [--diff] [--no-heal]
# Exit: 0=done, 1=routed to claude_agent, 2=strategy C needed
```

Does: auto-estimate tokens → route → delegate → evaluate → auto_heal → update rolling accuracy → save profiles.

---

## Capability profiles (current)

```json
{
  "gemma4": {
    "max_reliable_tokens": 32000,
    "accuracy_by_type": { "code_edit": 0.9, "code_gen": 0.9, "test_write": 0.9 },
    "session_failures": 0,
    "retry_budget": 3,
    "last_updated": <unix timestamp>,
    "decay_per_day": 0.98
  },
  "claude_agent": {
    "max_reliable_tokens": 180000,
    "accuracy_by_type": { "code_edit": 0.95, "code_gen": 0.92, "research": 0.9, "cross_file_refactor": 0.9, "test_write": 0.93 },
    "session_failures": 0,
    "retry_budget": 10,
    "last_updated": <unix timestamp>,
    "decay_per_day": 0.98
  }
}
```

Rolling avg update: `current * 0.7 + (score/100) * 0.3`  
Cross-session decay: `0.5 + (accuracy - 0.5) * decay_per_day^days_since_last_update`  
Applied on `load_profiles()` if days > 1. Benchmark merges via rolling avg — does NOT hard-overwrite.

---

## Session stats

- SQLite DB at `harness/session_stats.db` (gitignored)
- `log_delegation()` → called by `router.py` `__main__` and `pipeline.py`
- `update_score()` → called by `evaluator.py` `__main__` and `pipeline.py`
- `CONDUCTOR_SESSION_ID` env var groups delegations (fallback: `"default"`)
- `bash harness/stats.sh [<session_id>]`

---

## Session awareness

| File | Loads when |
|---|---|
| `~/.claude/CLAUDE.md` | Every Claude Code session globally (written by `setup.sh`) |
| `conductor/CLAUDE.md` | CWD is inside this repo |

Re-run `setup.sh` after moving repo to fix absolute paths.

---

## Test suite

68 tests across 10 files, all passing:

```
harness/tests/test_models.py            — dataclass defaults, enum values, decay_per_day
harness/tests/test_profiles.py          — load/save/update_accuracy, decay, last_updated, custom decay_per_day
harness/tests/test_router.py            — all 5 routing rules
harness/tests/test_evaluator.py         — syntax/tests/scope/semantic checks
harness/tests/test_healer.py            — A/B/C strategy, auto_heal A→B→C, diff_mode propagation
harness/tests/test_session_stats.py     — log/update/report, empty db, print
harness/tests/test_tokens.py            — estimate_tokens empty/missing/existing/per-extension multipliers
harness/tests/test_parallel_delegate.py — order, success, exception, heal=True, diff_mode, no subtasks
harness/tests/test_parallel_cli.py      — exit codes, --workers, missing args
harness/tests/test_pipeline.py          — gemma4 route, claude route, auto_heal, no_heal, strategy C
```

Run: `/opt/homebrew/bin/pytest -q`

---

## Setup (new machine)

```bash
brew install ollama
ollama pull gemma4:latest
ollama serve &
git clone https://github.com/asat2094/conductor && cd conductor
bash setup.sh
python3 gemma4-bench/bench.py   # optional, 15-30 min
```

---

## Day-to-day commands

```bash
export CONDUCTOR_SESSION_ID="$(date +%Y%m%d-%H%M%S)"

# Full pipeline (recommended)
python3 -m harness.pipeline '{"id":"t1","description":"<task>","type":"code_edit","files":["<file>"]}' \
  --workdir /abs/workdir

# Route only
python3 -m harness.router '{"id":"t1","description":"<task>","type":"code_edit","files":["<file>"]}'

# Single file delegate
bash harness/gemma4_delegate.sh /abs/workdir "<task>" file.py [--diff]

# Parallel delegate (bash)
bash harness/gemma4_delegate.sh --parallel /abs/workdir '[{"task":"...","file":"..."}]' --workers 2

# Evaluate (changed_files optional)
python3 -m harness.evaluator '{"subtask":{...},"agent":"gemma4","workdir":"/abs","output":"..."}' [--auto-heal]

# Stats
bash harness/stats.sh [<session_id>]
```

---

## System (user's machine)

- **RAM:** 18 GB (Apple M3 Pro, 11 cores)
- **gemma4:** 9.6 GB — fits comfortably
- **ollama:** v0.24.0 at `localhost:11434`
- **Python:** 3.14.5 (`python3`; `python` not in PATH)
- **pytest:** `/opt/homebrew/bin/pytest`

---

## What's done / remaining

**All major items complete** across 3 phases:

| Phase | Items |
|---|---|
| 1 | Parallel delegation, diff mode, auto token counting, healer auto-apply, cross-session decay, README bench section |
| 2 | Diff fallback, per-ext token multipliers, `--auto-heal` in evaluator CLI, `decay_per_day` as profile field, per-task heal in parallel |
| 3 | `pipeline.py` end-to-end, `parallel_cli.py`, `--parallel` in bash wrapper, `diff_mode` propagation through heal chain, bench merge via rolling avg, evaluator `changed_files` auto-derive |

**Minor remaining (low priority):**
- `gemma4_delegate.sh --parallel` — raw JSON quoting awkward for complex descriptions. Could add `--tasks-file <json_file>`.
- `pipeline.py` — no batch/parallel mode. Could add `--parallel` for multi-subtask dispatch.
- `gemma4-bench/bench.py SOURCE_FILES` — hardcoded absolute paths, breaks on other machines. Could accept CLI arg or auto-discover.
- Design spec at `docs/2026-05-24-adaptive-multi-agent-orchestration-design.md` exists — not yet implemented (multi-provider routing, OpenAI/Anthropic API fallback).
