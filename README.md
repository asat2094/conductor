# conductor

Local multi-agent harness that lets Claude delegate mechanical coding tasks to **gemma4** running on your machine via ollama — saving API tokens and context for work that actually needs a frontier model.

```
Claude (orchestrator)
  ├─ route → gemma4 (local, free)   code edits · code gen · test writing
  └─ route → Claude agent           research · cross-file refactors · complex tasks
```

## How it works

1. **Router** classifies a subtask and picks the right agent based on task type, token count, and gemma4's live accuracy
2. **Delegate** embeds file content in a prompt, calls ollama REST API directly, extracts the code block, writes it back to disk
3. **Evaluator** scores the output (syntax, tests, scope, semantic) out of 100
4. **Healer** fires on score < 70 — presents 3 recovery strategies
5. **Session stats** track every delegation in SQLite, showing tokens routed locally vs Claude API

## Prerequisites

| Tool | Purpose |
|---|---|
| [ollama](https://ollama.com) | Runs gemma4 locally |
| [opencode](https://opencode.ai) | Claude-side AI CLI (optional for smoke test) |
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
- Installs `@ai-sdk/openai-compatible` for opencode
- Writes `~/.claude/CLAUDE.md` so every Claude Code session auto-knows about the harness
- Runs the full 30-test suite
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
```

### 2. Delegate to gemma4

```bash
bash harness/gemma4_delegate.sh \
  /path/to/your/project \
  "Add type hints to validate_order" \
  backend/orders.py
```

### 3. Evaluate output

```bash
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
```

Score ≥ 70: done. Score < 70: healer shows recovery options.

### 4. Session stats

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

## Task types

| Type | Use for |
|---|---|
| `code_edit` | Add docstrings, type hints, rename, reformat, single-function changes |
| `code_gen` | Generate boilerplate, stubs, helpers from a clear spec |
| `test_write` | Write a pytest test for a known function |
| `research` | Always Claude — needs web access or broad context |
| `cross_file_refactor` | Always Claude — multi-file coordination |

## Healer strategies

When evaluator score < 70:

| Strategy | Action | Cost |
|---|---|---|
| **A — Shrink** | Halve the file scope, retry gemma4 | Same cost, +~30s |
| **B — Re-prompt** | Inject failure detail as constraint, retry gemma4 | Same cost, +~30s |
| **C — Escalate** | Hand to Claude agent, mark gemma4 failure (counts against retry budget) | Higher cost, +~60s |

## Evaluation scoring

Output scored out of 100:

| Check | Max | Method |
|---|---|---|
| Syntax | 25 | `ast.parse()` on changed files |
| Tests | 35 | Run pytest if test file exists; 20 partial credit if no tests |
| Scope | 20 | Changed files match requested files (by filename) |
| Semantic | 20 | Word overlap between task description and output/file content |

## Capability profiles

Live in `harness/capability_profiles.json`. Updated by the benchmark and after each real scored run.

Current benchmarked values (gemma4 via ollama REST API, 2 trials × 5 token sizes × 3 task types):

```
max_reliable_tokens: 32,000
accuracy — code_edit:  0.90
accuracy — code_gen:   0.90
accuracy — test_write: 0.90
```

### Recalibrate

```bash
python3 gemma4-bench/bench.py   # ~15-30 min
```

Benchmarks 30 cells (1k / 4k / 8k / 16k / 32k tokens × code_edit / code_gen / test_write), updates profiles automatically.

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
│   ├── router.py                   # routing logic + CLI
│   ├── evaluator.py                # scoring + CLI
│   ├── healer.py                   # failure recovery strategy builder
│   ├── profiles.py                 # load/save/update capability_profiles.json
│   ├── session_stats.py            # SQLite delegation log + report
│   ├── gemma4_delegate.sh          # thin bash wrapper
│   ├── gemma4_call.py              # ollama REST API caller
│   ├── stats.sh                    # stats report CLI
│   ├── capability_profiles.json    # live gemma4 thresholds
│   └── tests/
│       ├── test_models.py
│       ├── test_profiles.py
│       ├── test_router.py
│       ├── test_evaluator.py
│       ├── test_healer.py
│       └── test_session_stats.py
└── gemma4-bench/
    └── bench.py                    # calibration benchmark
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

**Rolling accuracy update** — each evaluated run updates `accuracy_by_type` as: `current × 0.7 + (score/100) × 0.3`. Decays toward real performance without overreacting to single failures.
