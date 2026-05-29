# Conductor — Local Multi-Agent Harness

This repo IS the harness. When working here, you are configuring or extending the conductor system.

## What conductor does

Offloads mechanical coding tasks (code edits, code gen, file creation, test writing) to gemma4 running locally via ollama. Claude orchestrates; gemma4 executes small, bounded tasks.

gemma4 can **edit existing files** and **create new files** — the harness handles filesystem I/O, gemma4 only does the text transformation.

## Running tasks via the harness

```bash
# 1. Route — check which agent should handle a task
#    estimated_tokens is optional; auto-estimated from file sizes if omitted
python3 -m harness.router '{"id":"t1","description":"<task>","type":"code_edit","files":["<path>"]}'

# 2a. Delegate to gemma4 (full file rewrite)
bash harness/gemma4_delegate.sh <absolute-workdir> "<task>" <file>

# 2b. Delegate in diff mode (safer for large files, applies unified diff)
bash harness/gemma4_delegate.sh <absolute-workdir> "<task>" <file> --diff

# 2c. Delegate multiple independent files in parallel (Python)
python3 -c "
from harness.parallel_delegate import delegate_parallel
results = delegate_parallel('<workdir>', [
    {'task': '<task1>', 'file': '<file1>'},
    {'task': '<task2>', 'file': '<file2>'},
])
print(results)
"

# 3. Evaluate output (score >= 70 = accept; < 70 = auto_heal tries A then B before C)
python3 -m harness.evaluator '{"subtask":{...},"agent":"gemma4","changed_files":["<path>"],"output":"<output>"}'

# 4. Auto-heal (called programmatically after score < 70)
python3 -c "
from harness.healer import auto_heal
new_result, strategy = auto_heal(subtask, result, profiles, workdir='<workdir>')
# strategy: 'A' (shrunk), 'B' (reprompted), 'C' (escalate to claude_agent)
"

# 5. Stats
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

## Development

```bash
bash setup.sh          # idempotent setup + prereq check
/opt/homebrew/bin/pytest -q   # run all 47 tests
python3 gemma4-bench/bench.py  # recalibrate capability profiles (15-30 min)
```

Key files:
- `harness/router.py` — routing logic (auto token estimation)
- `harness/tokens.py` — estimate_tokens() from file sizes
- `harness/evaluator.py` — output scoring (syntax, tests, scope, semantic)
- `harness/healer.py` — auto_heal() A→B→C + build_healer_report()
- `harness/parallel_delegate.py` — concurrent multi-task delegation
- `harness/gemma4_call.py` — ollama REST API caller (importable run(), --diff support)
- `harness/profiles.py` — load/save/update + cross-session decay
- `harness/session_stats.py` — SQLite delegation log
- `harness/capability_profiles.json` — live gemma4 thresholds
