# conductor

Local multi-agent harness that lets Claude delegate mechanical coding tasks to **gemma4** running on your machine via ollama — saving API tokens and context for work that actually needs a frontier model.

```
Claude (orchestrator)
  ├─ route → gemma4 (local, free)   code edits · code gen · test writing
  └─ route → Claude agent           research · cross-file refactors · complex tasks
```

## How it works

1. **Router** classifies a subtask and picks the right agent based on task type, token count, and gemma4's live accuracy. Auto-estimates tokens from file sizes (with per-extension multipliers) if not supplied.
2. **Delegate** embeds file content in a prompt, calls ollama REST API directly, extracts the code block, writes it back to disk. Supports `--diff` mode (applies unified diff via `patch(1)`; auto-falls back to full rewrite if patch unavailable).
3. **Parallel delegate** dispatches multiple independent tasks concurrently via `ThreadPoolExecutor`. Optionally runs per-task `auto_heal` on failures.
4. **Evaluator** scores the output (syntax, tests, scope, semantic) out of 100. `--auto-heal` flag runs A→B automatically and returns the best result.
5. **Healer** auto-tries strategy A (shrink) then B (re-prompt) on score < 70. Only surfaces strategy C (escalate) if both fail.
6. **Session stats** track every delegation in SQLite, showing tokens routed locally vs Claude API.
7. **Capability profiles** decay toward neutral across sessions. Decay rate is configurable per-profile (`decay_per_day`, default 0.98).

## Prerequisites

| Tool | Purpose |
|---|---|
| [ollama](https://ollama.com) | Runs gemma4 locally |
| Python 3.10+ | Harness runtime |
| pytest | Test suite |

gemma4 requires ~10 GB disk and ≥16 GB RAM for comfortable use.

## Setup

```bash
git clone https://github.com/asat2094/conductor
cd conductor
bash setup.sh
```

`setup.sh` is idempotent — safe to re-run after moving the repo or upgrading.

What it does:
- Evaluates system specs (RAM, CPU, GPU, disk) and recommends model tier
- Checks ollama is running with gemma4 pulled
- Writes `~/.claude/CLAUDE.md` so every Claude Code session auto-knows about the harness
- Runs the full test suite
- Verifies capability profiles are calibrated

After setup, every new Claude Code session automatically loads the routing instructions — **no manual prompt required**.

## Quick start

### 1. Route a task

```bash
cd conductor
python3 -m harness.router '{
  "id": "t1",
  "description": "Add type hints to validate_order function",
  "type": "code_edit",
  "files": ["backend/orders.py"],
  "estimated_tokens": 1500
}'
# → gemma4

# estimated_tokens is optional — router auto-estimates from file sizes:
python3 -m harness.router '{
  "id": "t1",
  "description": "Add type hints to validate_order function",
  "type": "code_edit",
  "files": ["backend/orders.py"]
}'
```

### 2. Delegate to gemma4

```bash
# Full file rewrite (default)
bash harness/gemma4_delegate.sh \
  /path/to/your/project \
  "Add type hints to validate_order" \
  backend/orders.py

# Diff mode — safer for large files, applies a unified diff with patch(1)
bash harness/gemma4_delegate.sh \
  /path/to/your/project \
  "Add type hints to validate_order" \
  backend/orders.py \
  --diff
```

### 3. Delegate multiple files in parallel

```python
from harness.parallel_delegate import delegate_parallel

results = delegate_parallel(
    workdir="/path/to/project",
    tasks=[
        {"task": "Add docstrings to parse_order",    "file": "orders.py"},
        {"task": "Add type hints to validate_email", "file": "validators.py"},
    ],
)
# → [{"file": "orders.py", "success": True, "output": "..."}, ...]
```

Only use for truly independent tasks (no shared file dependencies).

### 4. Evaluate output

```bash
# Basic evaluation
python3 -m harness.evaluator '{
  "subtask": {
    "id": "t1",
    "description": "Add type hints to validate_order function",
    "type": "code_edit",
    "files": ["backend/orders.py"],
    "estimated_tokens": 1500
  },
  "agent": "gemma4",
  "changed_files": ["/abs/path/to/backend/orders.py"],
  "output": "Written successfully"
}'
# → {"score": 78, "details": "syntax=25/25 tests=20/35 scope=20/20 semantic=13/20", ...}

# With automatic healing on score < 70
python3 -m harness.evaluator '{...}' --auto-heal
# If score < 70: tries strategy A then B automatically.
# Returns best result with "healer_strategy": "A"|"B"|"C".
# Exit code 2 if both fail (caller should escalate to claude_agent).
```

Score ≥ 70: done. Score < 70 with `--auto-heal`: healer runs A→B automatically before surfacing C.

### 5. Session stats

```bash
bash harness/stats.sh
```

```
══════════════════════════════════════════════
  Conductor Session Stats
══════════════════════════════════════════════

  SESSION                  DATE              TOTAL GEMMA4 TOKENS→LOCAL AVG SCORE
  ------------------------ ----------------- ----- ------ ------------ ---------
  session-20260524         2026-05-24 16:55      4      3        5,800    87/100

  Tokens routed to gemma4 (local):  5,800
  Tokens saved from Claude API:     5,800
  Local offload rate:               75%
  gemma4 avg accuracy:              87/100
```

## Routing rules

| Condition | Agent |
|---|---|
| `type` is `research` or `cross_file_refactor` | `claude_agent` always |
| `estimated_tokens` > 32,000 | `claude_agent` |
| gemma4 session failures ≥ 3 | `claude_agent` |
| gemma4 accuracy < 70% for task type | `claude_agent` |
| otherwise | `gemma4` |

`estimated_tokens` is auto-derived from file sizes (chars/4) when not supplied.

## Task types

| Type | Use for |
|---|---|
| `code_edit` | Add docstrings, type hints, rename, reformat, single-function changes |
| `code_gen` | Generate boilerplate, stubs, helpers from a clear spec |
| `test_write` | Write a pytest test for a known function |
| `research` | Always Claude — needs web access or broad context |
| `cross_file_refactor` | Always Claude — multi-file coordination |

## Healer strategies

When evaluator score < 70, the healer runs automatically:

| Strategy | Action | Cost | Trigger |
|---|---|---|---|
| **A — Shrink** | Halve the file scope, retry gemma4 | Same, +~30s | Auto (first) |
| **B — Re-prompt** | Inject failure detail as constraint, retry gemma4 | Same, +~30s | Auto (if A fails) |
| **C — Escalate** | Hand to Claude agent, mark gemma4 failure | Higher, +~60s | Manual (if both fail) |

`auto_heal()` in `harness/healer.py` runs A then B programmatically. If both fail, it returns `(None, "C")` so Claude can decide whether to escalate.

## Evaluation scoring

Output scored out of 100:

| Check | Max | Method |
|---|---|---|
| Syntax | 25 | `ast.parse()` on changed files |
| Tests | 35 | Run pytest if test file exists; 20 partial credit if no tests |
| Scope | 20 | Changed files match requested files (by filename) |
| Semantic | 20 | Word overlap between task description and output/file content |

## Capability profiles

Live in `harness/capability_profiles.json`. Updated after each real scored run. Accuracy decays toward 0.5 (neutral) across sessions if not updated — ~2% per day — so stale calibrations don't over-route to gemma4.

### Benchmark results

Benchmarked on Apple M3 Pro (18 GB), gemma4 9B via ollama REST API.  
30 cells: 5 token sizes × 3 task types × 2 trials.

| Token size | code_edit | code_gen | test_write | avg latency (code_edit) | avg latency (test_write) |
|---|---|---|---|---|---|
| 1,000 | 90/100 | 90/100 | 90/100 | 42.5s | 54.0s |
| 4,000 | 90/100 | 90/100 | 90/100 | 14.3s | 47.9s |
| 8,000 | 90/100 | 90/100 | 90/100 | 22.0s | 87.2s |
| 16,000 | 90/100 | 90/100 | 90/100 | 17.9s | 49.7s |
| 32,000 | 90/100 | 90/100 | 90/100 | 14.0s | 58.5s |

All cells scored 90/100. `max_reliable_tokens` set to 32,000.

### Recalibrate

```bash
python3 gemma4-bench/bench.py   # ~15-30 min
```

Benchmarks 30 cells, updates `capability_profiles.json` automatically.

## Session ID

Set `CONDUCTOR_SESSION_ID` for per-session stats grouping:

```bash
export CONDUCTOR_SESSION_ID="$(date +%Y%m%d-%H%M%S)"
```

Add to your shell profile or set at the start of each Claude Code session.

## Project structure

```
conductor/
├── setup.sh                        # one-shot idempotent setup
├── CLAUDE.md                       # auto-read by Claude Code when in this repo
├── pyproject.toml
├── harness/
│   ├── models.py                   # SubTask, EvalResult, CapabilityProfile dataclasses
│   ├── router.py                   # routing logic + CLI (auto token estimation)
│   ├── tokens.py                   # estimate_tokens() from file sizes
│   ├── evaluator.py                # scoring + CLI
│   ├── healer.py                   # failure recovery — auto A→B, manual C
│   ├── parallel_delegate.py        # concurrent multi-task delegation
│   ├── profiles.py                 # load/save/update + cross-session decay
│   ├── session_stats.py            # SQLite delegation log + report
│   ├── gemma4_delegate.sh          # thin bash wrapper (supports --diff)
│   ├── gemma4_call.py              # ollama REST API caller (importable run())
│   ├── stats.sh                    # stats report CLI
│   ├── capability_profiles.json    # live gemma4 thresholds
│   └── tests/
│       ├── test_models.py
│       ├── test_profiles.py
│       ├── test_router.py
│       ├── test_evaluator.py
│       ├── test_healer.py
│       ├── test_session_stats.py
│       ├── test_tokens.py
│       └── test_parallel_delegate.py
└── gemma4-bench/
    ├── bench.py                    # calibration benchmark
    └── bench_results.json          # latest benchmark results
```

## Development

```bash
# Run tests
/opt/homebrew/bin/pytest -q        # or: python3 -m pytest -q

# Run setup (idempotent)
bash setup.sh

# Recalibrate gemma4 thresholds
python3 gemma4-bench/bench.py
```

## Key design decisions

**ollama REST API, not opencode CLI** — `opencode run` is conversational-only for local models (no file tool access). The harness calls `http://localhost:11434/api/generate` directly, embeds file content in the prompt, and parses fenced code blocks from the response.

**Scope check by filename, not full path** — evaluator compares basenames so relative paths in subtask definitions match absolute paths in changed_files.

**Semantic scoring reads file content for short outputs** — when output is a summary string (< 30 words), evaluator reads the actual changed file and takes the max overlap score vs the description.

**Rolling accuracy update** — each evaluated run updates `accuracy_by_type` as: `current × 0.7 + (score/100) × 0.3`. Decays toward neutral across sessions to prevent stale high scores from misleading the router.

**Diff mode for large files** — `--diff` flag asks gemma4 for a unified diff instead of full file output, reducing hallucination risk on large context. Applied with `patch(1)`.

**Parallel delegation** — `delegate_parallel()` uses `ThreadPoolExecutor` for independent tasks. Results returned in input order. Exceptions caught per-task — one failure doesn't block others.

**Healer auto-apply** — `auto_heal()` runs strategy A (shrink) then B (re-prompt) automatically before surfacing strategy C (escalate) to the user. Keeps the human out of the loop for recoverable failures.

**Token auto-estimation** — if `estimated_tokens` is 0 or omitted in router CLI, it's computed from file sizes (chars/4). Removes a manual step that users often guess wrong.
