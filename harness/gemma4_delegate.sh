#!/usr/bin/env bash
# Usage (single file):
#   gemma4_delegate.sh <workdir> <task_description> <file1> [file2 ...] [--diff]
#
# Usage (parallel, multiple independent tasks):
#   gemma4_delegate.sh --parallel <workdir> <tasks_json> [--diff] [--workers N]
#   tasks_json: '[{"task":"...","file":"..."},...]'
#
# Reads files, sends content + task to gemma4 via ollama, extracts first
# fenced code block from response, writes it back to <file1>.
# Prints raw response to stdout. Logs to stderr.

set -euo pipefail

SCRIPT_DIR="$(dirname "$0")"

# Route --parallel to parallel_cli.py
if [[ "${1:-}" == "--parallel" ]]; then
  shift
  exec python3 "$SCRIPT_DIR/parallel_cli.py" "$@"
fi

WORKDIR="${1:?workdir required}"
TASK="${2:?task description required}"
shift 2
FILES=("$@")

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "Error: at least one file required" >&2
  exit 1
fi

# Delegate to Python for safe prompt building + ollama API call
python3 "$SCRIPT_DIR/gemma4_call.py" "$WORKDIR" "$TASK" "${FILES[@]}"
