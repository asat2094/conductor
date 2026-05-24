#!/usr/bin/env bash
# conductor/setup.sh
# One-shot idempotent setup for the conductor multi-agent harness.
# Run from any directory. Safe to re-run.

set -euo pipefail

CONDUCTOR_DIR="$(cd "$(dirname "$0")" && pwd)"
OPENCODE_CONFIG_DIR="$HOME/.config/opencode"
OPENCODE_CONFIG="$OPENCODE_CONFIG_DIR/opencode.jsonc"

# ── colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*"; FAILED=1; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
section() { echo -e "\n${YELLOW}▶ $*${NC}"; }

FAILED=0

# ── 0. System evaluation ──────────────────────────────────────────────────────
section "System evaluation"

# RAM
TOTAL_RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
TOTAL_RAM_GB=$(python3 -c "print(round($TOTAL_RAM_BYTES / 1024**3, 1))")
echo "  RAM:  ${TOTAL_RAM_GB} GB"

# CPU
CPU_BRAND=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || sysctl -n hw.model 2>/dev/null || echo "unknown")
CPU_CORES=$(sysctl -n hw.logicalcpu 2>/dev/null || nproc 2>/dev/null || echo "?")
echo "  CPU:  $CPU_BRAND ($CPU_CORES logical cores)"

# GPU / Apple Silicon
GPU_INFO=$(system_profiler SPDisplaysDataType 2>/dev/null | awk '/Chipset Model/{print $NF; exit}' || echo "unknown")
echo "  GPU:  $GPU_INFO"

# Disk free (where ollama models live)
DISK_FREE=$(df -h "$HOME" 2>/dev/null | awk 'NR==2{print $4}')
echo "  Disk: $DISK_FREE free (home)"

# Ollama currently loaded models
echo ""
echo "  Ollama loaded models:"
ollama ps 2>/dev/null | tail -n +2 | while IFS= read -r line; do
  echo "    $line"
done || echo "    (none)"

# All pulled models + sizes
echo ""
echo "  Ollama available models:"
ollama list 2>/dev/null | tail -n +2 | while IFS= read -r line; do
  echo "    $line"
done

# Model tier recommendation based on RAM
echo ""
RAM_INT=$(python3 -c "print(int($TOTAL_RAM_GB))")
if   [[ $RAM_INT -ge 64 ]]; then
  TIER="Large (70B+ models viable)"
  GEMMA4_OK=1
elif [[ $RAM_INT -ge 32 ]]; then
  TIER="Medium-Large (26B–34B models comfortable)"
  GEMMA4_OK=1
elif [[ $RAM_INT -ge 16 ]]; then
  TIER="Medium (7B–12B comfortable, 26B possible with swap)"
  GEMMA4_OK=1
elif [[ $RAM_INT -ge 8 ]]; then
  TIER="Small (3B–7B models only — gemma4 9.6GB may be marginal)"
  GEMMA4_OK=0
else
  TIER="Minimal (<8GB — local LLMs not recommended)"
  GEMMA4_OK=0
fi
echo "  Tier: $TIER"

# gemma4 suitability
if [[ $GEMMA4_OK -eq 1 ]]; then
  ok "Hardware supports gemma4 (9.6 GB) comfortably"
else
  warn "gemma4 (9.6 GB) may cause memory pressure on ${TOTAL_RAM_GB}GB RAM"
  warn "Consider: ollama pull gemma3:4b (2.5 GB) as a lighter alternative"
fi

# ── 1. Prerequisites ──────────────────────────────────────────────────────────
section "Checking prerequisites"

# ollama binary
if command -v ollama &>/dev/null; then
  ok "ollama installed ($(ollama --version 2>&1 | head -1))"
else
  fail "ollama not found — install from https://ollama.com"
fi

# ollama running + gemma4 available
if curl -s http://localhost:11434/api/tags &>/dev/null; then
  ok "ollama server running"
  if curl -s http://localhost:11434/api/tags | python3 -c \
    "import json,sys; ms=[m['name'] for m in json.load(sys.stdin)['models']]; exit(0 if any('gemma4' in m for m in ms) else 1)" 2>/dev/null; then
    ok "gemma4 model available"
  else
    warn "gemma4 not pulled — run: ollama pull gemma4:latest"
    FAILED=1
  fi
else
  fail "ollama server not running — run: ollama serve"
fi

# opencode binary
if command -v opencode &>/dev/null; then
  ok "opencode installed ($(opencode --version 2>/dev/null || echo 'unknown version'))"
else
  fail "opencode not found — install from https://opencode.ai"
fi

# python3
if command -v python3 &>/dev/null; then
  ok "python3 available ($(python3 --version))"
else
  fail "python3 not found"
fi

# pytest
if /opt/homebrew/bin/pytest --version &>/dev/null 2>&1; then
  ok "pytest available"
elif python3 -m pytest --version &>/dev/null 2>&1; then
  ok "pytest available"
else
  warn "pytest not found — installing..."
  pip3 install pytest --break-system-packages --quiet && ok "pytest installed" || fail "pytest install failed"
fi

# Stop early if hard prereqs missing
if [[ $FAILED -eq 1 ]]; then
  echo -e "\n${RED}Fix the issues above, then re-run setup.sh${NC}"
  exit 1
fi

# ── 2. Configure opencode ─────────────────────────────────────────────────────
section "Configuring opencode"

mkdir -p "$OPENCODE_CONFIG_DIR"

# Install @ai-sdk/openai-compatible if not present
if [[ -d "$OPENCODE_CONFIG_DIR/node_modules/@ai-sdk/openai-compatible" ]]; then
  ok "@ai-sdk/openai-compatible already installed"
else
  echo "  Installing @ai-sdk/openai-compatible..."
  (cd "$OPENCODE_CONFIG_DIR" && npm install @ai-sdk/openai-compatible --silent) \
    && ok "@ai-sdk/openai-compatible installed" \
    || { fail "npm install failed"; exit 1; }
fi

# Write opencode.jsonc (overwrite — always authoritative)
cat > "$OPENCODE_CONFIG" <<'JSON'
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": {
        "baseURL": "http://localhost:11434/v1"
      },
      "models": {
        "gemma4:latest": {
          "name": "Gemma 4 (local)"
        }
      }
    }
  },
  "model": "ollama/gemma4:latest"
}
JSON
ok "opencode.jsonc written"

# ── 3. Smoke test opencode → gemma4 ──────────────────────────────────────────
section "Smoke testing opencode + gemma4"

echo "  Sending test prompt (may take 15-30s)..."
SMOKE=$(opencode run -m ollama/gemma4:latest "Reply with exactly: CONDUCTOR_OK" 2>/dev/null || true)
if echo "$SMOKE" | grep -q "CONDUCTOR_OK"; then
  ok "opencode → gemma4 round-trip works"
else
  warn "opencode smoke test returned unexpected output: ${SMOKE:0:80}"
  warn "Harness will still work via direct ollama API — continuing"
fi

# ── 4. Conductor test suite ───────────────────────────────────────────────────
section "Running conductor test suite"

cd "$CONDUCTOR_DIR"
PYTEST_BIN="/opt/homebrew/bin/pytest"
[[ -x "$PYTEST_BIN" ]] || PYTEST_BIN="python3 -m pytest"

if $PYTEST_BIN -q 2>&1; then
  ok "All conductor tests pass"
else
  fail "Some tests failed — check output above"
  exit 1
fi

# ── 5. Write session awareness (CLAUDE.md) ───────────────────────────────────
section "Installing session awareness"

CLAUDE_DIR="$HOME/.claude"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
mkdir -p "$CLAUDE_DIR"

# Write the conductor block (idempotent — replace conductor section if exists)
CONDUCTOR_BLOCK="## Local Multi-Agent Harness (conductor)

A local harness exists at \`$CONDUCTOR_DIR\` for offloading small tasks to gemma4 (local model via ollama). Use it proactively — it saves cost and context on mechanical work.

### When to use

| Use conductor (gemma4) | Stay with Claude |
|---|---|
| Code edit in ≤2 files, single function scope | Cross-file refactors |
| Generate boilerplate / stubs from a clear spec | Research / web tasks |
| Write a test for a known function | Ambiguous or large-context tasks |
| Rename, reformat, add docstrings | Architecture decisions |

Route to gemma4 when estimated context ≤ 8k tokens and task type is \`code_edit\`, \`code_gen\`, or \`test_write\`.

### How to delegate

\`\`\`bash
bash $CONDUCTOR_DIR/harness/gemma4_delegate.sh <absolute-workdir> \"<task>\" <file>
\`\`\`

### How to route

\`\`\`bash
cd $CONDUCTOR_DIR && python3 -m harness.router '{\"id\":\"t1\",\"description\":\"<task>\",\"type\":\"<code_edit|code_gen|test_write>\",\"files\":[\"<path>\"],\"estimated_tokens\":<N>}'
\`\`\`

### How to evaluate

\`\`\`bash
cd $CONDUCTOR_DIR && python3 -m harness.evaluator '{\"subtask\":{\"id\":\"t1\",\"description\":\"<task>\",\"type\":\"<type>\",\"files\":[\"<path>\"],\"estimated_tokens\":<N>},\"agent\":\"gemma4\",\"changed_files\":[\"<path>\"],\"output\":\"<output>\"}'
\`\`\`

Score < 70/100 → trigger healer: ask user to choose Strategy A (shrink), B (re-prompt), or C (escalate to Claude).

### Verification contract

Always read the diff after gemma4 completes. Confirm: (1) syntactically valid, (2) scoped to requested files only, (3) no test regressions. Never declare a gemma4 subtask done without verification.

### Session stats

\`\`\`bash
bash $CONDUCTOR_DIR/harness/stats.sh
\`\`\`"

if [[ -f "$CLAUDE_MD" ]]; then
  # Remove old conductor block if present, then append fresh one
  python3 - "$CLAUDE_MD" <<PYEOF
import sys, re
path = sys.argv[1]
text = open(path).read()
# Strip existing conductor section (from ## Local Multi-Agent to next ##-level heading or EOF)
cleaned = re.sub(r'\n## Local Multi-Agent Harness \(conductor\).*?(?=\n## |\Z)', '', text, flags=re.DOTALL)
open(path, 'w').write(cleaned.rstrip() + '\n')
PYEOF
  printf '\n%s\n' "$CONDUCTOR_BLOCK" >> "$CLAUDE_MD"
  ok "~/.claude/CLAUDE.md updated with conductor harness at $CONDUCTOR_DIR"
else
  printf '# Global Claude Instructions\n\n%s\n' "$CONDUCTOR_BLOCK" > "$CLAUDE_MD"
  ok "~/.claude/CLAUDE.md created with conductor harness"
fi

# ── 6. Capability profiles check ─────────────────────────────────────────────
section "Checking capability profiles"

PROFILES="$CONDUCTOR_DIR/harness/capability_profiles.json"
if [[ -f "$PROFILES" ]]; then
  MAX_TOK=$(python3 -c "import json; d=json.load(open('$PROFILES')); print(d['gemma4']['max_reliable_tokens'])")
  ok "Profiles exist — gemma4 max_reliable_tokens: ${MAX_TOK}"
  if [[ "$MAX_TOK" -eq 8000 ]]; then
    warn "Profiles still at default (8000) — benchmark not run yet"
    warn "Run: cd $CONDUCTOR_DIR && python3 gemma4-bench/bench.py"
    warn "(Takes 15-30 min. Sets real token limits + accuracy scores.)"
  fi
else
  fail "capability_profiles.json missing"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILED -eq 0 ]]; then
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${GREEN}  Conductor harness ready.${NC}"
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
  echo "  Harness:   $CONDUCTOR_DIR"
  echo "  Delegate:  bash $CONDUCTOR_DIR/harness/gemma4_delegate.sh <workdir> <task> <file>"
  echo "  Router:    python3 -m harness.router '<subtask_json>'"
  echo "  Evaluator: python3 -m harness.evaluator '<eval_json>'"
  echo ""
  echo "  Next: run the benchmark to calibrate real thresholds:"
  echo "    cd $CONDUCTOR_DIR && python3 gemma4-bench/bench.py"
else
  echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${RED}  Setup incomplete — fix errors above and re-run.${NC}"
  echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  exit 1
fi
