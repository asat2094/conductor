#!/usr/bin/env bash
# Usage: gemma4_delegate.sh <workdir> <task_description> <file1> [file2 ...]
#
# Reads files, sends content + task to gemma4 via ollama, extracts first
# fenced code block from response, writes it back to <file1>.
# Prints raw response to stdout. Logs to stderr.

set -euo pipefail

WORKDIR="${1:?workdir required}"
TASK="${2:?task description required}"
shift 2
FILES=("$@")

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "Error: at least one file required" >&2
  exit 1
fi

# Delegate to Python for safe prompt building + ollama API call
python3 "$(dirname "$0")/gemma4_call.py" "$WORKDIR" "$TASK" "${FILES[@]}"
