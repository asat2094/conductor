# Conductor — Local Multi-Agent Harness

This repo IS the harness. When working here, you are configuring or extending the conductor system.

## What conductor does

Offloads mechanical coding tasks (code edits, code gen, file creation, test writing) to gemma4 running locally via ollama. Claude orchestrates; gemma4 executes small, bounded tasks.

gemma4 can **edit existing files** and **create new files** — the harness handles filesystem I/O, gemma4 only does the text transformation.

## Running tasks via the harness

```bash
# 1. Route — check which agent should handle a task
python3 -m harness.router '{"id":"t1","description":"<task>","type":"code_edit","files":["<path>"],"estimated_tokens":2000}'

# 2. Delegate to gemma4
bash harness/gemma4_delegate.sh <absolute-workdir> "<task>" <file>

# 3. Evaluate output (score ≥ 70 = accept, < 70 = healer)
python3 -m harness.evaluator '{"subtask":{...},"agent":"gemma4","changed_files":["<path>"],"output":"<output>"}'

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

## Development

```bash
bash setup.sh          # idempotent setup + prereq check
/opt/homebrew/bin/pytest -q   # run all 30 tests
python3 gemma4-bench/bench.py  # recalibrate capability profiles (15-30 min)
```

Key files:
- `harness/router.py` — routing logic
- `harness/evaluator.py` — output scoring (syntax, tests, scope, semantic)
- `harness/healer.py` — failure recovery strategies A/B/C
- `harness/gemma4_call.py` — ollama REST API caller
- `harness/session_stats.py` — SQLite delegation log
- `harness/capability_profiles.json` — live gemma4 thresholds
