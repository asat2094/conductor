#!/usr/bin/env bash
# conductor/harness/stats.sh
# Show delegation stats across all sessions, or for a specific session.
# Usage: stats.sh [session_id]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ "${1:-}" != "" ]]; then
  python3 -m harness.session_stats --session "$1"
else
  cd "$SCRIPT_DIR/.." && python3 -m harness.session_stats
fi
