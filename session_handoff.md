# Conductor — Session Handoff

**Date:** 2026-05-29  
**Repo:** https://github.com/asat2094/conductor  
**Working dir:** `/Users/ankitatiwari/Desktop/claude-playground/conductor`

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

### Core flow

```
1. python3 -m harness.router '{...}'        → gemma4 | claude_agent (auto-estimates tokens)
2. bash harness/gemma4_delegate.sh ...      → calls gemma4_call.py (supports --diff)
3. python3 harness/gemma4_call.py ...       → ollama REST API → writes file or applies patch
4. python3 -m harness.evaluator '{...}'     → score/100
5. score < 70 → auto_heal() tries A then B → only surfaces C if both fail
6. bash harness/stats.sh                    → session token savings report
```

### Key files

| File | Role |
|---|---|
| `harness/models.py` | Dataclasses: SubTask, EvalResult, CapabilityProfile (last_updated, decay_per_day); Enums |
| `harness/pipeline.py` | `run_pipeline(subtask, workdir, diff_mode, auto_heal)` — full loop; `python3 -m harness.pipeline` |
| `harness/router.py` | 5-rule routing logic + CLI; auto-estimates tokens from file sizes |
| `harness/tokens.py` | `estimate_tokens(files, workdir)` — chars/4 with per-extension multipliers |
| `harness/evaluator.py` | 4-axis scoring + CLI; `--auto-heal`; derives changed_files from workdir if missing |
| `harness/healer.py` | `auto_heal(diff_mode=)` — A→B→C; diff_mode propagated to delegate calls |
| `harness/parallel_delegate.py` | `delegate_parallel(workdir, tasks, heal, diff_mode, subtasks)` via ThreadPoolExecutor |
| `harness/parallel_cli.py` | `python3 -m harness.parallel_cli <workdir> <tasks_json>` — bash-friendly parallel dispatch |
| `harness/profiles.py` | `load_profiles()` (applies decay via profile.decay_per_day), `save_profiles()`, `update_accuracy()` |
| `harness/gemma4_delegate.sh` | Bash wrapper; `--parallel` routes to `parallel_cli.py`; `--diff` passes through |
| `harness/gemma4_call.py` | Importable `run(workdir, task, files, diff_mode)` + CLI; diff fallback to full rewrite |
| `harness/session_stats.py` | SQLite log; `log_delegation()`, `update_score()`, `print_report()` |
| `harness/stats.sh` | CLI wrapper for `session_stats.py` |
| `harness/capability_profiles.json` | Live gemma4 thresholds (includes decay_per_day) |
| `gemma4-bench/bench.py` | Calibration benchmark; merges via rolling avg — preserves real-session accuracy |
| `gemma4-bench/bench_results.json` | Latest benchmark results |
| `setup.sh` | Idempotent one-shot setup; writes `~/.claude/CLAUDE.md` |
| `CLAUDE.md` | Auto-read by Claude Code when CWD is this repo |

---

## Critical discoveries

### 1. opencode run = conversational only
`opencode run -m ollama/gemma4:latest` is a **chat interface** for local models — no file tools, no agentic loop. gemma4 asked clarifying questions instead of editing files.

**Fix:** `gemma4_call.py` embeds file content in prompt text, calls `http://localhost:11434/api/generate` directly via `urllib.request`, parses fenced code block from response, writes to disk. gemma4 never touches the filesystem — Python does I/O.

### 2. Benchmark first run scored 20-50 (wrong)
First benchmark used `opencode run` — gemma4 responded as prose, no code blocks. Evaluator found nothing to score.

**Fix:** Rewrote benchmark to use ollama REST API directly. Added explicit `\`\`\`python` block instruction in prompts. Added `_extract_code_block()` before scoring. Re-run: all 30 cells scored 90/100.

### 3. Router CLI AttributeError
JSON deserialization gives `type` as plain string. `subtask.type.value` failed with `AttributeError: 'str' object has no attribute 'value'`.

**Fix:** Added `subtask_data["type"] = TaskType(subtask_data["type"])` in `__main__` blocks of both `router.py` and `evaluator.py`.

### 4. Evaluator scope check — path mismatch
`check_scope()` compared full absolute paths (from `changed_files`) vs relative paths (from `subtask.files`). Set difference found "extra" files → 10/20 instead of 20/20.

**Fix:** Added `_basenames()` — compare by filename only.

### 5. Evaluator semantic check — short output scored against summary text
When `output` is a short summary string ("Written successfully"), word-overlap with description was low. But the actual file content had the right words.

**Fix:** `estimate_semantic()` now also scores against file content when output < 30 words. Takes `max(output_score, file_score)`.

### 6. Evaluator test score — penalised agent unfairly
`_run_tests()` returned 0 when no test file existed, even though the agent wasn't asked to write tests and no tests existed before.

**Fix:** `_has_test_file()` returns 20 (partial credit) when no test file exists — not the agent's fault.

### 7. gemma4 can't create files (fixed)
`gemma4_call.py` errored when target file didn't exist. CLAUDE.md incorrectly stated gemma4 can only edit.

**Fix:** Skip read for missing files; use creation-mode prompt. Both edit and create now work.

---

## Routing rules

```python
_ALWAYS_CLAUDE = {TaskType.RESEARCH, TaskType.CROSS_FILE_REFACTOR}

def route(subtask, profiles):
    g = profiles["gemma4"]
    if subtask.type in _ALWAYS_CLAUDE:          return AgentType.CLAUDE_AGENT
    if subtask.estimated_tokens > g.max_reliable_tokens:  return AgentType.CLAUDE_AGENT
    if g.session_failures >= g.retry_budget:    return AgentType.CLAUDE_AGENT
    if g.accuracy_by_type.get(subtask.type.value, 1.0) < 0.70: return AgentType.CLAUDE_AGENT
    return AgentType.GEMMA4
```

`estimated_tokens` auto-derived via `estimate_tokens(files, workdir)` (chars/4) when 0 or omitted.

---

## Evaluator scoring

| Check | Max | Method |
|---|---|---|
| Syntax | 25 | `ast.parse()` on changed `.py` files |
| Tests | 35 | Run pytest if test file exists; 20 partial credit if no tests |
| Scope | 20 | `_basenames(changed) - _basenames(requested)` |
| Semantic | 20 | Word overlap: description vs output (or file content if output short) |

Score ≥ 70: accept. Score < 70: `auto_heal()` fires.

---

## Healer strategies

| Strategy | Trigger | Action |
|---|---|---|
| A — Shrink | Auto (first) | Halve files list (min 1), halve token estimate, retry gemma4 |
| B — Re-prompt | Auto (if A < 70) | Inject failure detail as constraint, retry gemma4 |
| C — Escalate | Manual (if A+B fail) | Route to claude_agent, increment `session_failures` |

`auto_heal(subtask, result, profiles, workdir, delegate_fn, evaluate_fn)` returns `(EvalResult|None, "A"|"B"|"C")`.

---

## Parallel delegation

```python
from harness.parallel_delegate import delegate_parallel

results = delegate_parallel(
    workdir="/path/to/project",
    tasks=[
        {"task": "Add docstring to parse_order", "file": "orders.py"},
        {"task": "Add type hints to validate",   "file": "validators.py"},
    ],
    max_workers=3,
)
# returns list in same order as input; exceptions captured per-task
```

Only for independent tasks (no shared file dependencies).

---

## Diff mode

```bash
bash harness/gemma4_delegate.sh /abs/workdir "<task>" file.py --diff
```

Asks gemma4 for a unified diff → applies with `patch(1)`. Safer for large files — gemma4 only outputs changed lines. Falls back to error if patch apply fails.

---

## Capability profiles (current)

```json
{
  "gemma4": {
    "max_reliable_tokens": 32000,
    "accuracy_by_type": {
      "code_edit": 0.9,
      "code_gen": 0.9,
      "test_write": 0.9
    },
    "session_failures": 0,
    "retry_budget": 3,
    "last_updated": <unix timestamp>
  },
  "claude_agent": { ... }
}
```

Accuracy update formula (rolling avg): `current * 0.7 + (score/100) * 0.3`

Cross-session decay: `0.5 + (accuracy - 0.5) * 0.98^days_since_last_update`  
Applied automatically on `load_profiles()` if `days > 1`.

---

## Session stats system

- SQLite DB at `harness/session_stats.db` (gitignored)
- `log_delegation()` called by `router.py` `__main__` after routing decision
- `update_score()` called by `evaluator.py` `__main__` after scoring
- `CONDUCTOR_SESSION_ID` env var groups delegations into sessions (fallback: `"default"`)
- `bash harness/stats.sh` → table of sessions, tokens routed local, avg score

---

## Session awareness (how Claude auto-knows)

Two layers:

| File | Loads when |
|---|---|
| `~/.claude/CLAUDE.md` | Every Claude Code session globally (written by `setup.sh`) |
| `conductor/CLAUDE.md` | Any session where CWD is inside this repo |

`setup.sh` section 5 writes `~/.claude/CLAUDE.md` with absolute path to conductor dir. Idempotent — strips old block, appends fresh one. Re-run after moving repo to fix paths.

---

## Test suite

68 tests across 10 files, all passing:

```
harness/tests/test_models.py            — dataclass defaults, enum values
harness/tests/test_profiles.py          — load/save/update_accuracy, decay, last_updated, decay_per_day
harness/tests/test_router.py            — all 5 routing rules
harness/tests/test_evaluator.py         — syntax/tests/scope/semantic checks
harness/tests/test_healer.py            — A/B/C strategy, auto_heal A→B→C, diff_mode propagation
harness/tests/test_session_stats.py     — log/update/report, empty db, print
harness/tests/test_tokens.py            — estimate_tokens empty/missing/existing/per-extension
harness/tests/test_parallel_delegate.py — order, success, exception, heal=True, diff_mode, no subtasks
harness/tests/test_parallel_cli.py      — exit codes, --workers flag, missing args
harness/tests/test_pipeline.py          — gemma4 route, claude route, auto_heal, no_heal, strategy C
```

Run: `/opt/homebrew/bin/pytest -q`

---

## Setup commands (new user)

```bash
# Prerequisites
brew install ollama
ollama pull gemma4:latest
ollama serve &

# Clone + setup
git clone https://github.com/asat2094/conductor
cd conductor
bash setup.sh                    # installs deps, writes ~/.claude/CLAUDE.md, runs tests

# Optional: calibrate gemma4 thresholds (15-30 min)
python3 gemma4-bench/bench.py
```

---

## Usage commands (day-to-day)

```bash
# Set session ID (add to shell profile)
export CONDUCTOR_SESSION_ID="$(date +%Y%m%d-%H%M%S)"

# Route (estimated_tokens optional)
cd /path/to/conductor
python3 -m harness.router '{"id":"t1","description":"<task>","type":"code_edit","files":["<relpath>"]}'

# Delegate (edit existing file)
bash harness/gemma4_delegate.sh /abs/workdir "<task>" relative/path/to/file.py

# Delegate (diff mode)
bash harness/gemma4_delegate.sh /abs/workdir "<task>" relative/path/to/file.py --diff

# Delegate (create new file)
bash harness/gemma4_delegate.sh /abs/workdir "<task>" new_file.py

# Parallel delegate (Python)
python3 -c "from harness.parallel_delegate import delegate_parallel; ..."

# Evaluate
python3 -m harness.evaluator '{"subtask":{...},"agent":"gemma4","changed_files":["/abs/path"],"output":"<output>"}'

# Stats
bash harness/stats.sh
bash harness/stats.sh <session_id>   # single session
```

---

## System (user's machine)

- **RAM:** 18 GB (Apple M3 Pro, 11 cores)
- **GPU:** Apple M3 Pro (integrated)
- **Tier:** Medium — 7B–12B comfortable; 26B possible with swap
- **gemma4** (9.6 GB): fits comfortably
- **ollama:** v0.24.0 at localhost:11434
- **Python:** 3.14.5 (`python3`; `python` not in PATH)
- **pytest:** `/opt/homebrew/bin/pytest`

---

## What's NOT done / future ideas

**All previously listed items complete:**
- ✅ README benchmark section
- ✅ Parallel delegation (`harness/parallel_delegate.py`)
- ✅ Diff-mode output (`--diff` + fallback to full rewrite)
- ✅ Auto token counting (`harness/tokens.py` with per-extension multipliers)
- ✅ Healer auto-apply (`auto_heal()` A→B→C)
- ✅ `--auto-heal` flag in evaluator CLI (exit 2 on C)
- ✅ Diff mode fallback (re-calls gemma4 in full-rewrite mode if patch fails)
- ✅ Per-extension token multipliers (JSON 1.4×, YAML 1.2×, markdown 0.8×, etc.)
- ✅ Per-task auto_heal in `delegate_parallel()` (`heal=True` + `subtasks=` param)
- ✅ Decay rate as `CapabilityProfile.decay_per_day` field (default 0.98, JSON-serializable)

**All items complete. No remaining known gaps.**

Minor nice-to-haves (low priority):
- `gemma4_delegate.sh --parallel` currently passes raw JSON through shell — quoting complex task descriptions can be awkward. Could add a `--tasks-file` flag reading JSON from a file.
- `pipeline.py` doesn't support `subtasks` list (parallel mode is separate). Could add `--parallel` to pipeline for batched subtask dispatch.
- Benchmark `SOURCE_FILES` are hardcoded absolute paths — break on other machines. Could auto-discover from project root or accept CLI arg.
