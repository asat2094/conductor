#!/usr/bin/env bash
# gitai-commit-metric.sh — git-ai AI Productivity Metrics Collector
#
# Architecture: Two-phase execution triggered by post-commit git hook.
# Replaces commit-metric.sh — same patterns, different data source (git-ai instead of Cursor DB).
#
# Phase 1 ("start") — Runs synchronously in the hook (fast, <50ms):
#   1. Checks if this is a normal commit (skips rebase/merge/cherry-pick).
#   2. Gets the latest commit hash from git.
#   3. Writes commit info to a temp file.
#   4. Spawns itself as "continue" in a detached background process.
#
# Phase 2 ("continue") — Runs in background:
#   1. Polls for git-ai authorship note (exponential backoff, 30s max).
#   2. On match: extracts data from git-ai, computes metrics, sends to API.
#   3. On timeout: calls /error endpoint, attempts partial send.
#   4. Retries failed requests from previous runs.
#
# Dependencies: bash 4+, jq, curl, git, git-ai

set -euo pipefail

# ============================================================
# Dependency check
# ============================================================

check_dependencies() {
  mkdir -p ~/bin

  # Detect CPU architecture (Intel vs Apple Silicon)
  ARCH=$(uname -m)
  if [[ "$ARCH" == "arm64" ]]; then
    JQ_URL="https://github.com/stedolan/jq/releases/latest/download/jq-macos-arm64"
  elif [[ "$ARCH" == "x86_64" ]]; then
    JQ_URL="https://github.com/stedolan/jq/releases/latest/download/jq-osx-amd64"
  else
    log_warn "Unsupported architecture: $ARCH"
    return 1
  fi

  # Download jq if not installed
  if ! command -v jq >/dev/null 2>&1; then
    curl -fsSL -o ~/bin/jq "$JQ_URL"
    chmod +x ~/bin/jq
  fi

  # Add to PATH
  export PATH="$HOME/bin:$PATH"

  # Check git-ai (exit gracefully if not installed — script is a no-op without it)
  if ! command -v git-ai >/dev/null 2>&1; then
    log_warn "git-ai not found, exiting (no-op on machines without git-ai)"
    return 1
  fi

  # These should always be present on macOS/Linux
  local missing=()
  for cmd in curl git; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing+=("$cmd")
    fi
  done
  if [ ${#missing[@]} -gt 0 ]; then
    log_warn "Missing required dependencies: ${missing[*]}"
    return 1
  fi
}
# check_dependencies is called from main after parsing the command

# ============================================================
# Configuration
# ============================================================

# API endpoint to send commit metrics
API_ENDPOINT="https://cursor-server.meeshogcp.in/api/v1/add-gitai-commit-metrics"

# Error API endpoint (called on polling timeout)
ERROR_API_ENDPOINT="https://cursor-server.meeshogcp.in/api/v1/error"

# Set to true to skip API call and only save locally (for testing)
DRY_RUN=false

# Polling configuration (exponential backoff for git-ai authorship note)
POLL_INITIAL_DELAY_MS=500
POLL_MAX_DELAY_MS=8000
POLL_MAX_WAIT_S=30

# API retry configuration
API_MAX_ATTEMPTS=3
API_INITIAL_RETRY_DELAY_MS=1000
API_MAX_RETRY_DELAY_MS=5000

# Failed requests queue configuration
MAX_FAILED_BATCH_SIZE=500  # Each commit payload ~1-1.5KB (no message text); 500 entries ≈ 500-750KB, well within 2MB API limit

# Storage paths (relative to $HOME)
FAILED_COMMITS_FILE=".cursor-metrics/gitai-commit-metric/failed.json"
METRICS_OUTPUT_DIR=".cursor-metrics/gitai-commit-metric/data"
TEMP_DIR=".cursor-metrics/gitai-commit-metric/tmp"
LOG_DIR_RELATIVE=".cursor-metrics/gitai-commit-metric/logs"
REBASE_MAP_FILE=".cursor-metrics/gitai-commit-metric/rebase-map.json"

# ============================================================
# Logging
# ============================================================

LOG_FILE=""

setup_logging() {
  local log_dir="${HOME}/${LOG_DIR_RELATIVE}"
  mkdir -p "$log_dir" 2>/dev/null || true
  LOG_FILE="${log_dir}/commit-metric.log"
}

# logWarn writes a timestamped warning to the log file with [gitai-commit-metric] prefix.
# Falls back to stderr if the log file is not available.
log_warn() {
  local fmt_str="$1"; shift
  local msg
  # shellcheck disable=SC2059
  msg=$(printf "$fmt_str" "$@")
  local line
  line="[gitai-commit-metric] $(date -u +"%Y-%m-%dT%H:%M:%S%z") ${msg}"
  if [ -n "$LOG_FILE" ]; then
    echo "$line" >> "$LOG_FILE" 2>/dev/null || echo "$line" >&2
  else
    echo "$line" >&2
  fi
}

# ============================================================
# Utility functions
# ============================================================

# min_val returns the smaller of two integers
min_val() {
  local a=$1 b=$2
  if [ "$a" -lt "$b" ]; then echo "$a"; else echo "$b"; fi
}

# sleep_ms sleeps for N milliseconds
sleep_ms() {
  local ms=$1
  local secs
  secs=$(awk "BEGIN { printf \"%.3f\", $ms / 1000 }")
  sleep "$secs"
}

# ============================================================
# Temp file helpers
# ============================================================

# write_temp_file writes commit info to a temp JSON file for the background process.
# Prints the file path.
write_temp_file() {
  local commit_data="$1"
  local dir="${HOME}/${TEMP_DIR}"
  mkdir -p "$dir"

  local commit_hash
  commit_hash=$(echo "$commit_data" | jq -r '.commitHash // "unknown"')
  local timestamp_ns
  timestamp_ns=$(date +%s%N 2>/dev/null || echo "$(date +%s)000000000")
  local file_name="${commit_hash}_${timestamp_ns}.json"
  local file_path="${dir}/${file_name}"

  echo "$commit_data" > "$file_path"
  echo "$file_path"
}

# ============================================================
# Git helpers
# ============================================================

# getGitEmail retrieves the user's email from git config
get_git_email() {
  local email
  email=$(git config --get user.email 2>/dev/null || true)
  if [ -z "$email" ]; then
    email=$(git config --global --get user.email 2>/dev/null || true)
  fi
  echo "$email"
}

# epochMsToUTCString converts epoch milliseconds to UTC string with ms precision.
# Output format: "2006-01-02T15:04:05.000Z"
epoch_ms_to_utc_string() {
  local epoch_ms="$1"
  if [ -z "$epoch_ms" ] || [ "$epoch_ms" = "0" ] || [ "$epoch_ms" = "null" ]; then
    date -u +"%Y-%m-%dT%H:%M:%S.000Z"
    return
  fi

  local seconds=$(( epoch_ms / 1000 ))
  local millis=$(( epoch_ms % 1000 ))
  local millis_padded
  millis_padded=$(printf "%03d" "$millis")

  local formatted
  # GNU date
  if formatted=$(date -u -d "@${seconds}" +"%Y-%m-%dT%H:%M:%S" 2>/dev/null); then
    echo "${formatted}.${millis_padded}Z"
  # BSD/macOS date
  elif formatted=$(date -u -r "${seconds}" +"%Y-%m-%dT%H:%M:%S" 2>/dev/null); then
    echo "${formatted}.${millis_padded}Z"
  else
    date -u +"%Y-%m-%dT%H:%M:%S.000Z"
  fi
}

# toUTCString parses any time string (e.g., git's ISO 8601 with timezone) and
# converts it to UTC with ms precision. Returns empty string on parse failure.
to_utc_string() {
  local ts="$1"
  if [ -z "$ts" ]; then
    echo ""
    return
  fi

  local parsed
  # GNU date: handles "+05:30" colon timezone natively
  if parsed=$(date -u -d "$ts" +"%Y-%m-%dT%H:%M:%S.000Z" 2>/dev/null); then
    echo "$parsed"
    return
  fi

  # BSD/macOS date: %z expects "+0530" not "+05:30", so strip the colon
  # from the timezone offset before parsing.
  # "2026-02-15T01:26:12+05:30" -> "2026-02-15T01:26:12+0530"
  local ts_nocolon="$ts"
  if [[ "$ts" =~ ^(.+)([+-][0-9]{2}):([0-9]{2})$ ]]; then
    ts_nocolon="${BASH_REMATCH[1]}${BASH_REMATCH[2]}${BASH_REMATCH[3]}"
  fi
  if parsed=$(date -u -jf "%Y-%m-%dT%H:%M:%S%z" "$ts_nocolon" +"%Y-%m-%dT%H:%M:%S.000Z" 2>/dev/null); then
    echo "$parsed"
    return
  fi

  # Return as-is if unparseable
  echo "$ts"
}

# is_normal_commit returns 0 for normal commits, 1 for rebase/merge/cherry-pick.
# For rebase and cherry-pick, records the original→replayed hash mapping before skipping.
is_normal_commit() {
  local git_dir
  git_dir=$(git rev-parse --git-dir 2>/dev/null) || return 1

  # Skip during rebase (interactive or non-interactive)
  if [ -d "${git_dir}/rebase-merge" ] || [ -d "${git_dir}/rebase-apply" ]; then
    local original_hash=""
    if [ -d "${git_dir}/rebase-merge" ] && [ -f "${git_dir}/rebase-merge/done" ]; then
      original_hash=$(tail -1 "${git_dir}/rebase-merge/done" 2>/dev/null | awk '{print $2}')
    fi
    if [ -z "$original_hash" ] && [ -f "${git_dir}/rebase-apply/original-commit" ]; then
      original_hash=$(cat "${git_dir}/rebase-apply/original-commit" 2>/dev/null | tr -d '[:space:]')
    fi
    [ -n "$original_hash" ] && record_commit_hash_mapping "$original_hash"
    return 1
  fi

  # Skip during cherry-pick (CHERRY_PICK_HEAD exists until post-commit cleanup)
  if [ -f "${git_dir}/CHERRY_PICK_HEAD" ]; then
    local original_hash
    original_hash=$(cat "${git_dir}/CHERRY_PICK_HEAD" 2>/dev/null | tr -d '[:space:]')
    [ -n "$original_hash" ] && record_commit_hash_mapping "$original_hash"
    return 1
  fi

  # Skip merge commits (HEAD has more than 1 parent)
  if git rev-parse HEAD^2 >/dev/null 2>&1; then
    return 1
  fi

  return 0
}

# record_commit_hash_mapping saves replayed_hash→original_hash mapping.
# Used by rebase and cherry-pick to track which original commit was replayed.
# Stored at ~/<REBASE_MAP_FILE> as a JSON object keyed by replayed hash.
record_commit_hash_mapping() {
  local original_hash="$1"

  # Resolve short hash to full hash
  local full_hash
  full_hash=$(git rev-parse "$original_hash" 2>/dev/null) || full_hash="$original_hash"
  original_hash="$full_hash"

  local replayed_hash
  replayed_hash=$(git rev-parse HEAD 2>/dev/null) || return 0

  local repo_path
  repo_path=$(git rev-parse --show-toplevel 2>/dev/null) || return 0
  local repo_name
  repo_name=$(get_repo_name_from_path "$repo_path")
  local git_dir
  git_dir=$(git -C "$repo_path" rev-parse --git-dir 2>/dev/null) || return 0
  local branch_name=""
  if [ -f "${git_dir}/rebase-merge/head-name" ]; then
    branch_name=$(cat "${git_dir}/rebase-merge/head-name" 2>/dev/null | sed 's|^refs/heads/||')
  elif [ -f "${git_dir}/rebase-apply/head-name" ]; then
    branch_name=$(cat "${git_dir}/rebase-apply/head-name" 2>/dev/null | sed 's|^refs/heads/||')
  fi
  if [ -z "$branch_name" ]; then
    branch_name=$(git -C "$repo_path" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  fi

  local map_file="${HOME}/${REBASE_MAP_FILE}"
  mkdir -p "$(dirname "$map_file")" 2>/dev/null || true

  local current_map="{}"
  if [ -f "$map_file" ]; then
    current_map=$(cat "$map_file" 2>/dev/null) || current_map="{}"
    if ! echo "$current_map" | jq empty 2>/dev/null; then
      current_map="{}"
    fi
  fi

  current_map=$(echo "$current_map" | jq \
    --arg replayed "$replayed_hash" \
    --arg orig "$original_hash" \
    --arg repo "$repo_name" \
    --arg branch "$branch_name" \
    '. + {($replayed): {original: $orig, repo: $repo, branch: $branch}}')

  echo "$current_map" | jq '.' > "$map_file" 2>/dev/null || true

  log_warn "commit mapping recorded: %s → %s (%s)" "$replayed_hash" "$original_hash" "$repo_name"
}

# getRepoNameFromPath tries git remote origin URL first, falls back to basename.
get_repo_name_from_path() {
  local root_path="$1"

  local url
  url=$(git -C "$root_path" remote get-url origin 2>/dev/null || true)
  if [ -n "$url" ]; then
    local name
    name=$(parse_repo_name_from_url "$url")
    if [ -n "$name" ]; then
      echo "$name"
      return
    fi
  fi

  basename "$root_path"
}

# parseRepoNameFromURL extracts "org/repo" from a git remote URL.
parse_repo_name_from_url() {
  local raw_url="$1"

  # SSH: git@github.com:org/repo.git
  if [[ "$raw_url" == git@* ]]; then
    local after_colon="${raw_url#*:}"
    after_colon="${after_colon%.git}"
    echo "$after_colon"
    return
  fi

  # HTTPS: https://github.com/org/repo.git
  raw_url="${raw_url%.git}"
  local second_last last
  last=$(basename "$raw_url")
  second_last=$(basename "$(dirname "$raw_url")")
  if [ -n "$second_last" ] && [ -n "$last" ]; then
    echo "${second_last}/${last}"
    return
  fi
}

# ============================================================
# Local metrics storage
# ============================================================

# saveMetricsLocally saves the commit metrics to a local JSON file.
# Path: ~/<metricsOutputDir>/<commitHash>.json
save_metrics_locally() {
  local request_json="$1"

  local dir="${HOME}/${METRICS_OUTPUT_DIR}"
  mkdir -p "$dir"

  local commit_hash
  commit_hash=$(echo "$request_json" | jq -r '.commit_hash // "unknown"')
  local file_path="${dir}/${commit_hash}.json"

  # Idempotent — skip if already written
  if [ -f "$file_path" ]; then
    printf "Metrics already saved locally: %s\n" "$file_path"
    return 0
  fi

  echo "$request_json" | jq '.' > "$file_path"
  printf "Metrics saved locally: %s\n" "$file_path"
}

# ============================================================
# Failed requests persistence
# ============================================================

get_failed_commits_path() {
  echo "${HOME}/${FAILED_COMMITS_FILE}"
}

# load_failed_commits reads previously failed commits from the cache file.
# Concurrency is handled by the caller via acquire_lock.
load_failed_commits() {
  local path
  path=$(get_failed_commits_path)
  if [ ! -f "$path" ]; then
    echo "[]"
    return
  fi

  local data
  data=$(cat "$path" 2>/dev/null || true)

  if [ -n "$data" ] && echo "$data" | jq empty 2>/dev/null; then
    echo "$data"
  else
    echo "[]"
  fi
}

# saveFailedCommits writes the failed batch to the cache file.
# Pass empty or "[]" to clear the file (on success).
# Enforces MAX_FAILED_BATCH_SIZE — discards oldest on overflow.
save_failed_commits() {
  local commits_json="$1"
  local path
  path=$(get_failed_commits_path)

  if [ -z "$commits_json" ] || [ "$commits_json" = "[]" ] || [ "$commits_json" = "null" ]; then
    rm -f "$path" 2>/dev/null || true
    return
  fi

  # Enforce max size — discard oldest on overflow
  local count
  count=$(echo "$commits_json" | jq 'length')
  if [ "$count" -gt "$MAX_FAILED_BATCH_SIZE" ]; then
    local overflow=$(( count - MAX_FAILED_BATCH_SIZE ))
    log_warn "failed.json overflow (%d > %d); discarding %d oldest" \
      "$count" "$MAX_FAILED_BATCH_SIZE" "$overflow"
    commits_json=$(echo "$commits_json" | jq ".[${overflow}:]")
  fi

  mkdir -p "$(dirname "$path")" 2>/dev/null || true
  echo "$commits_json" | jq '.' > "$path" 2>/dev/null || true
}

# ============================================================
# Lock helpers
# ============================================================

CONTINUE_LOCK_DIR="${HOME}/.cursor-metrics/gitai-commit-metric/continue.lock"

acquire_lock() {
  local lock_dir="$1"
  mkdir -p "$(dirname "$lock_dir")" 2>/dev/null || true

  local poll_ms=500
  local stale_threshold_s=120
  local max_wait_s=180
  local start_time
  start_time=$(date +%s)

  while ! mkdir "$lock_dir" 2>/dev/null; do
    local now
    now=$(date +%s)

    if [ $(( now - start_time )) -gt "$max_wait_s" ]; then
      log_warn "lock wait exceeded %ds, force-removing: %s" "$max_wait_s" "$lock_dir"
      rmdir "$lock_dir" 2>/dev/null || true
      continue
    fi

    if [ -d "$lock_dir" ]; then
      local lock_mtime
      if lock_mtime=$(stat -f "%m" "$lock_dir" 2>/dev/null) ||
         lock_mtime=$(stat -c "%Y" "$lock_dir" 2>/dev/null); then
        if [ $(( now - lock_mtime )) -gt "$stale_threshold_s" ]; then
          log_warn "removing stale lock (age > %ds): %s" "$stale_threshold_s" "$lock_dir"
          rmdir "$lock_dir" 2>/dev/null || true
          continue
        fi
      fi
    fi
    sleep_ms "$poll_ms"
  done
}

release_lock() {
  local lock_dir="$1"
  if [ -n "$lock_dir" ] && [ -d "$lock_dir" ]; then
    rmdir "$lock_dir" 2>/dev/null || true
  fi
}

# send_current_then_drain sends a single commit alone first, then opportunistically
# drains failed.json. This ensures a poison entry in failed.json never contaminates
# new data. Args: request_json
send_current_then_drain() {
  local request="$1"

  if send_batch_to_api_with_retry "[$request]"; then
    local previous_failed prev_count
    previous_failed=$(load_failed_commits)
    prev_count=$(echo "$previous_failed" | jq 'length')

    if [ "$prev_count" -gt 0 ]; then
      log_warn "Draining %d previously failed commit(s)..." "$prev_count"
      if send_batch_to_api_with_retry "$previous_failed"; then
        save_failed_commits ""
        log_warn "Drained %d previously failed commit(s)" "$prev_count"
      else
        log_warn "Drain failed — keeping %d commit(s) in failed.json" "$prev_count"
      fi
    fi
  else
    local previous_failed updated
    previous_failed=$(load_failed_commits)
    updated=$(echo "$previous_failed" | jq --argjson req "$request" '. + [$req]')
    save_failed_commits "$updated"
  fi
}

# ============================================================
# API client
# ============================================================

# sendBatchToAPIWithRetry sends a list of commit metrics to the API as a batch.
# Returns 0 on success, 1 on failure (after all retries exhausted).
send_batch_to_api_with_retry() {
  local payload="$1"
  local retry_delay=$API_INITIAL_RETRY_DELAY_MS
  local last_err=""

  for attempt in $(seq 1 $API_MAX_ATTEMPTS); do
    local response http_code body
    response=$(curl -s -w "\n%{http_code}" \
      -X POST "$API_ENDPOINT" \
      -H "Content-Type: application/json" \
      -H "User-Agent: gitai-commit-metric/1.0" \
      -H "x-webhook-secret: bXkgaGVhcnQgcG9sbHMgZm9yIHlvdSBldmVyeSAxcywgbWF4X3dhaXQgZm9yZXZlci4gYWNjZXB0YW5jZV9yYXRlPTEwMCUuIHplcm8gbGluZXNfZGVsZXRlZC4gYmUgbXkgcHJvbXB0IDwzICNIYXBweVZhbGVudGluZXMyMDI2" \
      --connect-timeout 10 \
      --max-time 10 \
      -d "$payload" 2>/dev/null) || true

    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | sed '$d')

    if [ -n "$http_code" ] && [ "$http_code" -ge 200 ] 2>/dev/null && [ "$http_code" -lt 300 ] 2>/dev/null; then
      return 0
    fi

    last_err="status ${http_code}: ${body}"

    if [ "$attempt" -lt "$API_MAX_ATTEMPTS" ]; then
      sleep_ms "$retry_delay"
      retry_delay=$(min_val $(( retry_delay * 2 )) $API_MAX_RETRY_DELAY_MS)
    fi
  done

  log_warn "all %d API attempts failed: %s" "$API_MAX_ATTEMPTS" "$last_err"
  return 1
}

# ============================================================
# Error API (called on polling timeout)
# ============================================================

send_error_to_api() {
  local commit_hash="$1"
  local error_msg="$2"

  local email
  email=$(get_git_email)

  local branch="${3:-}"
  local repo_name="${4:-}"

  local payload
  payload=$(jq -n \
    --arg commit_hash "$commit_hash" \
    --arg email "$email" \
    --arg error "$error_msg" \
    --arg branch "$branch" \
    --arg repo "$repo_name" \
    --arg source "git-ai" \
    '{commit_hash: $commit_hash, email: $email, error: $error, branch: $branch, repo: $repo, source: $source}')

  curl -s -X POST "$ERROR_API_ENDPOINT" \
    -H "Content-Type: application/json" \
    -H "User-Agent: gitai-commit-metric/1.0" \
    -H "x-webhook-secret: bXkgaGVhcnQgcG9sbHMgZm9yIHlvdSBldmVyeSAxcywgbWF4X3dhaXQgZm9yZXZlci4gYWNjZXB0YW5jZV9yYXRlPTEwMCUuIHplcm8gbGluZXNfZGVsZXRlZC4gYmUgbXkgcHJvbXB0IDwzICNIYXBweVZhbGVudGluZXMyMDI2" \
    --connect-timeout 10 \
    --max-time 10 \
    -d "$payload" 2>/dev/null || true
}

# ============================================================
# Polling (exponential backoff for git-ai authorship note)
# ============================================================

# poll_for_authorship_note polls until git-ai's authorship note exists for the commit.
# Uses exponential backoff: 500ms → 1s → 2s → 4s -> 8s (cap), 30s deadline.
# Returns 0 on success, 1 on timeout.
poll_for_authorship_note() {
  local commit_hash="$1"
  local repo_path="$2"
  local delay_ms=$POLL_INITIAL_DELAY_MS
  local deadline=$(( $(date +%s) + POLL_MAX_WAIT_S ))

  while true; do
    # Check if authorship note exists
    if git -C "$repo_path" notes --ref=ai show "$commit_hash" >/dev/null 2>&1; then
      return 0  # success
    fi

    # Check deadline
    if [ "$(date +%s)" -ge "$deadline" ]; then
      return 1  # timeout
    fi

    # Wait with exponential backoff
    sleep_ms "$delay_ms"
    delay_ms=$(min_val $(( delay_ms * 2 )) $POLL_MAX_DELAY_MS)
  done
}

# ============================================================
# Data extraction
# ============================================================

# extract_commit_stats runs git-ai stats and returns the JSON.
# Sets STATS_JSON global. Returns 0 on success, 1 on failure.
extract_commit_stats() {
  local commit_hash="$1"
  local repo_path="$2"

  STATS_JSON=$(git -C "$repo_path" ai stats "$commit_hash" --json 2>/dev/null) || true

  if [ -z "$STATS_JSON" ] || ! echo "$STATS_JSON" | jq empty 2>/dev/null; then
    log_warn "git-ai stats failed or returned invalid JSON for %s" "$commit_hash"
    STATS_JSON=""
    return 1
  fi
  return 0
}

# extract_notes_metadata parses the JSON metadata from the git-ai authorship note.
# The note format is: attestation text + "---" separator + JSON metadata.
# Sets NOTES_JSON global. Returns 0 on success, 1 on failure.
extract_notes_metadata() {
  local commit_hash="$1"
  local repo_path="$2"

  NOTES_JSON=$(git -C "$repo_path" notes --ref=ai show "$commit_hash" 2>/dev/null \
    | sed -n '/^---$/,$p' | tail -n +2) || true

  if [ -z "$NOTES_JSON" ] || ! echo "$NOTES_JSON" | jq empty 2>/dev/null; then
    log_warn "failed to parse authorship note JSON for %s" "$commit_hash"
    NOTES_JSON=""
    return 1
  fi
  return 0
}

# validate_schema_version checks the schema version in the notes JSON.
# Non-blocking: logs a warning if schema doesn't match authorship/3.x but never fails.
validate_schema_version() {
  local notes_json="$1"
  if [ -z "$notes_json" ]; then
    return 0
  fi

  local schema_version
  schema_version=$(echo "$notes_json" | jq -r '.schema_version // "unknown"')
  if [[ "$schema_version" != authorship/3.* ]]; then
    log_warn "Unexpected schema_version: %s (expected authorship/3.x). Parsing may be inaccurate." "$schema_version"
  fi
}

# ============================================================
# Metric computation
# ============================================================

# compute_prompt_metrics extracts prompt-level counts from the notes JSON.
# Sets global variable: TOTAL_ACCEPTED_LINES.
compute_prompt_metrics() {
  local notes_json="$1"

  if [ -z "$notes_json" ]; then
    TOTAL_ACCEPTED_LINES="null"
    return
  fi

  TOTAL_ACCEPTED_LINES=$(echo "$notes_json" | jq '
    [.prompts[].accepted_lines // 0] | add // 0
  ')
}

# extract_transcript_metrics reads Claude Code transcript JSONL files for all sessions
# in this commit, counts user prompts in the time window [parent_ts, commit_ts] on the
# commit's branch, and captures permission_mode.
# Sets globals: TRANSCRIPT_PROMPT_COUNT, PERMISSION_MODE.
extract_transcript_metrics() {
  local notes_json="$1"
  local repo_path="$2"
  local parent_ts="$3"    # ISO-8601 UTC e.g. 2026-03-30T05:56:59.000Z
  local commit_ts="$4"    # ISO-8601 UTC
  local branch_name="$5"  # only count prompts on this branch

  TRANSCRIPT_PROMPT_COUNT="null"
  PERMISSION_MODE="null"

  if [ -z "$notes_json" ] || [ -z "$repo_path" ] || [ -z "$parent_ts" ] || [ -z "$commit_ts" ]; then
    return
  fi

  # Derive ~/.claude/projects/<project-dir> from repo_path
  local project_dir
  project_dir=$(echo "$repo_path" | tr '/' '-')
  local projects_base="$HOME/.claude/projects/${project_dir}"

  if [ ! -d "$projects_base" ]; then
    log_warn "transcript projects dir not found: %s" "$projects_base"
    return
  fi

  # Extract unique session IDs from notes
  local session_ids
  session_ids=$(echo "$notes_json" | jq -r '[.prompts[].agent_id.id] | unique[]' 2>/dev/null || true)

  if [ -z "$session_ids" ]; then
    log_warn "no session IDs found in notes"
    return
  fi

  local total_prompts=0
  local permission_mode=""

  while IFS= read -r session_id; do
    local transcript="$projects_base/${session_id}.jsonl"
    [ -f "$transcript" ] || continue

    # Stream transcript through jq — strip ms from timestamps for lexicographic UTC comparison.
    # Outputs "1,<permissionMode>" per matching prompt.
    local session_count=0 pm_first=""
    while IFS=',' read -r _ pm; do
      session_count=$(( session_count + 1 ))
      [ -z "$pm_first" ] && [ -n "$pm" ] && pm_first="$pm"
    done < <(jq -r \
        --arg parent_ts "$parent_ts" \
        --arg commit_ts "$commit_ts" \
        --arg branch    "$branch_name" \
        'select(
          type == "object" and
          .type == "user" and
          (.timestamp | type) == "string" and
          ((.timestamp | gsub("\\.[0-9]+Z$"; "Z")) > $parent_ts) and
          ((.timestamp | gsub("\\.[0-9]+Z$"; "Z")) <= $commit_ts) and
          (.message.content | type) == "string" and
          (.message.content | length) > 0 and
          (if $branch != "" then .gitBranch == $branch else true end)
        ) | "1,\(.permissionMode // "")"
      ' "$transcript" 2>/dev/null)

    total_prompts=$(( total_prompts + session_count ))
    [ -z "$permission_mode" ] && [ -n "$pm_first" ] && permission_mode="$pm_first"
  done <<< "$session_ids"

  [ "$total_prompts" -gt 0 ] && TRANSCRIPT_PROMPT_COUNT="$total_prompts" || TRANSCRIPT_PROMPT_COUNT="null"
  PERMISSION_MODE="${permission_mode:-}"

  log_info "transcript metrics: total_prompts=%s permission_mode=%s" \
    "$TRANSCRIPT_PROMPT_COUNT" "$PERMISSION_MODE"
}

# compute_metrics calculates the 3 metrics via jq (floats, 1 decimal, null on div-by-zero).
# rework_rate = (total_ai_additions - ai_accepted) / total_ai_additions * 100
#   = % of AI-suggested lines that were discarded or modified before commit.
# Accepts numeric values (may be "null" string for null JSON).
# Returns a JSON object with ai_percent, ai_lines_per_prompt, rework_rate.
compute_metrics() {
  local ai_additions="$1"
  local git_diff_added_lines="$2"
  local prompt_count="$3"
  local total_ai_additions="$4"

  local metrics
  metrics=$(jq -n \
    --argjson ai "${ai_additions:-0}" \
    --argjson diff "${git_diff_added_lines:-0}" \
    --argjson prompts "${prompt_count:-null}" \
    --argjson total "${total_ai_additions:-null}" \
    '{
      ai_percent:          (if ($diff | type) == "number" and $diff > 0 then ($ai / $diff * 100 * 10 | round / 10) else null end),
      ai_lines_per_prompt: (if ($prompts | type) == "number" and $prompts > 0 then ($ai / $prompts * 10 | round / 10) else null end),
      rework_rate:         (if ($total | type) == "number" and $total > 0 then (($total - $ai) / $total * 100 * 10 | round / 10) else null end)
    }')

  # Warn on negative rework (should not happen — indicates git-ai bug)
  local rework_rate
  rework_rate=$(echo "$metrics" | jq '.rework_rate // empty')
  if [ -n "$rework_rate" ] && [ "$rework_rate" != "null" ]; then
    local is_negative
    is_negative=$(echo "$rework_rate" | jq '. < 0')
    if [ "$is_negative" = "true" ]; then
      log_warn "Negative rework rate detected (%s%%) — possible git-ai data inconsistency" "$rework_rate"
    fi
  fi

  echo "$metrics"
}

# ============================================================
# Payload builders
# ============================================================

# build_model_breakdown extracts tool_model_breakdown from CommitStats JSON.
build_model_breakdown() {
  local stats_json="$1"
  if [ -z "$stats_json" ]; then
    echo "{}"
    return
  fi
  echo "$stats_json" | jq '.tool_model_breakdown // {} | map_values(del(.time_waiting_for_ai))'
}

# build_sessions builds the sessions array from the notes JSON prompt records.
# Includes messages_url if transcript is stored remotely (CAS), or inline messages array.
build_sessions() {
  local notes_json="$1"
  if [ -z "$notes_json" ]; then
    echo "[]"
    return
  fi

  echo "$notes_json" | jq '
    [.prompts | to_entries[] | {
      session_id: .value.agent_id.id,
      tool: .value.agent_id.tool,
      model: .value.agent_id.model,
      accepted_lines: (.value.accepted_lines // 0),
      overridden_lines: (.value.overriden_lines // 0),
      total_additions: (.value.total_additions // 0),
      total_deletions: (.value.total_deletions // 0),
    }]
  '
}

# build_file_type_breakdown groups additions by file extension from git diff --numstat.
build_file_type_breakdown() {
  local commit_hash="$1"
  local repo_path="$2"

  local numstat
  numstat=$(git -C "$repo_path" diff --numstat "${commit_hash}^" "$commit_hash" 2>/dev/null) || true

  if [ -z "$numstat" ]; then
    echo "{}"
    return
  fi

  echo "$numstat" | jq -R -s '
    [split("\n")[] | select(length > 0) | split("\t") |
      select(length >= 3) |
      { ext: (.[2] | split(".") | if length > 1 then "." + last else "(none)" end),
        added: (.[0] | tonumber? // 0) }
    ] | group_by(.ext) | map({
      key: .[0].ext,
      value: { total_additions: ([.[].added] | add) }
    }) | from_entries
  '
}

# ============================================================
# Convert to request
# ============================================================

# convert_to_request assembles the full API payload JSON from extracted data.
convert_to_request() {
  local commit_hash="$1"
  local repo_name="$2"
  local repo_path="$3"
  local branch_name="$4"
  local stats_json="$5"
  local notes_json="$6"
  local metrics_json="$7"
  local model_breakdown="$8"
  local sessions="$9"
  local file_type_breakdown="${10}"

  # Get user email from git config
  local email
  email=$(get_git_email)
  if [ -z "$email" ]; then
    log_warn "could not determine git user email"
    return 1
  fi

  # Get commit timestamp from git
  local timestamp_str=""
  if [ -n "$commit_hash" ]; then
    local git_ts
    git_ts=$(git -C "$repo_path" log -1 --format="%aI" "$commit_hash" 2>/dev/null || true)
    if [ -n "$git_ts" ]; then
      timestamp_str=$(to_utc_string "$git_ts")
    fi
  fi

  # Get parent commit timestamp from git
  local parent_timestamp=""
  if [ -n "$commit_hash" ]; then
    local parent_ts
    parent_ts=$(git -C "$repo_path" log -1 --format="%aI" "${commit_hash}~1" 2>/dev/null || true)
    if [ -n "$parent_ts" ]; then
      parent_timestamp=$(to_utc_string "$parent_ts")
    else
      parent_timestamp="$timestamp_str"
    fi
  fi

  # Extract raw fields from stats JSON (default to 0 or null)
  local ai_additions ai_accepted mixed_additions human_additions
  local git_diff_added_lines git_diff_deleted_lines
  local total_ai_additions total_ai_deletions

  if [ -n "$stats_json" ]; then
    ai_additions=$(echo "$stats_json" | jq '.ai_additions // 0')
    ai_accepted=$(echo "$stats_json" | jq '.ai_accepted // 0')
    mixed_additions=$(echo "$stats_json" | jq '.mixed_additions // 0')
    human_additions=$(echo "$stats_json" | jq '.human_additions // 0')
    git_diff_added_lines=$(echo "$stats_json" | jq '.git_diff_added_lines // 0')
    git_diff_deleted_lines=$(echo "$stats_json" | jq '.git_diff_deleted_lines // 0')
    total_ai_additions=$(echo "$stats_json" | jq '.total_ai_additions // 0')
    total_ai_deletions=$(echo "$stats_json" | jq '.total_ai_deletions // 0')
  else
    ai_additions=0 ai_accepted=0 mixed_additions=0 human_additions=0
    git_diff_added_lines=0 git_diff_deleted_lines=0
    total_ai_additions=0 total_ai_deletions=0
  fi

  # Extract prompt-level fields (may be "null" if notes unavailable)
  local total_accepted_lines
  total_accepted_lines="${TOTAL_ACCEPTED_LINES:-null}"

  # Transcript-derived fields
  local total_prompts permission_mode
  total_prompts="${TRANSCRIPT_PROMPT_COUNT:-null}"
  permission_mode="${PERMISSION_MODE:-null}"

  # Assemble full payload
  jq -n \
    --arg email "$email" \
    --arg commit_hash "$commit_hash" \
    --arg timestamp "$timestamp_str" \
    --arg parent_commit_timestamp "$parent_timestamp" \
    --arg repo "$repo_name" \
    --arg branch "$branch_name" \
    --argjson ai_additions "$ai_additions" \
    --argjson ai_accepted "$ai_accepted" \
    --argjson mixed_additions "$mixed_additions" \
    --argjson human_additions "$human_additions" \
    --argjson git_diff_added_lines "$git_diff_added_lines" \
    --argjson git_diff_deleted_lines "$git_diff_deleted_lines" \
    --argjson total_ai_additions "$total_ai_additions" \
    --argjson total_ai_deletions "$total_ai_deletions" \
    --argjson total_accepted_lines "$total_accepted_lines" \
    --argjson total_prompts "$total_prompts" \
    --arg     permission_mode "$permission_mode" \
    --argjson metrics "$metrics_json" \
    --argjson model_breakdown "$model_breakdown" \
    --argjson sessions "$sessions" \
    --argjson file_type_breakdown "$file_type_breakdown" \
    '{
      email: $email,
      commit_hash: $commit_hash,
      timestamp: $timestamp,
      parent_commit_timestamp: $parent_commit_timestamp,
      repo: $repo,
      branch: $branch,

      ai_additions: $ai_additions,
      ai_accepted: $ai_accepted,
      mixed_additions: $mixed_additions,
      human_additions: $human_additions,
      git_diff_added_lines: $git_diff_added_lines,
      git_diff_deleted_lines: $git_diff_deleted_lines,
      total_ai_additions: $total_ai_additions,
      total_ai_deletions: $total_ai_deletions,

      total_accepted_lines: $total_accepted_lines,

      total_prompts: $total_prompts,
      permission_mode: (if $permission_mode != "" then $permission_mode else null end),

      ai_percent: $metrics.ai_percent,
      rework_rate: $metrics.rework_rate,
      ai_lines_per_prompt: $metrics.ai_lines_per_prompt,

      model_breakdown: $model_breakdown,
      sessions: $sessions,
      file_type_breakdown: $file_type_breakdown,
      metadata: null
    }'
}

# ============================================================
# Phase 1: start — runs synchronously in the post-commit hook (fast)
# ============================================================

run_start() {
  # Skip non-normal commits (rebase, merge)
  if ! is_normal_commit; then
    log_warn "skipping non-normal commit (rebase or merge)"
    return 0
  fi

  # Get the latest commit hash from git (HEAD is the new commit in post-commit)
  local commit_hash
  commit_hash=$(git rev-parse HEAD 2>/dev/null) || {
    log_warn "failed to get HEAD commit hash"
    return 1
  }

  # Get repo path and derive repo name
  local repo_path
  repo_path=$(git rev-parse --show-toplevel 2>/dev/null) || {
    log_warn "failed to get repo toplevel path"
    return 1
  }

  local repo_name
  repo_name=$(get_repo_name_from_path "$repo_path")

  # Write temp file with commit info for the background process
  local temp_data
  temp_data=$(jq -n \
    --arg commitHash "$commit_hash" \
    --arg repoName "$repo_name" \
    --arg repoPath "$repo_path" \
    '{commitHash: $commitHash, repoName: $repoName, repoPath: $repoPath}')

  local temp_file_path
  temp_file_path=$(write_temp_file "$temp_data")

  # Spawn "continue" as a detached background process
  local self_path
  self_path=$(realpath "$0" 2>/dev/null || echo "$0")
  local continue_log_dir="${HOME}/${LOG_DIR_RELATIVE}"
  mkdir -p "$continue_log_dir" 2>/dev/null || true
  local continue_log="${continue_log_dir}/continue.log"

  nohup bash "$self_path" continue "$temp_file_path" </dev/null >>/dev/null 2>>"$continue_log" &
  disown 2>/dev/null || true
}

# ============================================================
# Phase 2: continue — runs in background (slow work)
# ============================================================

run_continue() {
  local temp_file_path="$1"

  if [ ! -f "$temp_file_path" ]; then
    log_warn "temp file not found: %s" "$temp_file_path"
    return 1
  fi

  # Read temp file and delete immediately
  local temp_data
  temp_data=$(cat "$temp_file_path")
  rm -f "$temp_file_path"

  if ! echo "$temp_data" | jq empty 2>/dev/null; then
    log_warn "parse temp data: invalid JSON"
    return 1
  fi

  local commit_hash repo_name repo_path
  commit_hash=$(echo "$temp_data" | jq -r '.commitHash')
  repo_name=$(echo "$temp_data" | jq -r '.repoName')
  repo_path=$(echo "$temp_data" | jq -r '.repoPath')

  local branch_name
  branch_name=$(git -C "$repo_path" rev-parse --abbrev-ref HEAD 2>/dev/null || true)

  # ---- Error reporting trap: call error API on ANY unhandled failure ----
  # This ensures the backend knows when metrics couldn't be collected for a commit,
  # regardless of the failure reason (git-ai crash, parse error, jq failure, etc.)
  trap '
    local exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
      send_error_to_api "${commit_hash:-unknown}" "continue_failed_exit_${exit_code}" "${branch_name:-}" "${repo_name:-}" 2>/dev/null || true
      log_warn "run_continue failed (exit %d), error reported to API" "$exit_code" 2>/dev/null || true
    fi
  ' ERR

  # ---- Poll for git-ai authorship note ----
  log_warn "polling for authorship note %s (max %ds, exponential backoff)..." \
    "$commit_hash" "$POLL_MAX_WAIT_S"

  if ! poll_for_authorship_note "$commit_hash" "$repo_path"; then
    log_warn "polling timeout: authorship note for %s not found within %ds" \
      "$commit_hash" "$POLL_MAX_WAIT_S"
    send_error_to_api "$commit_hash" "gitai_polling_timeout" "$branch_name" "$repo_name"
    return 1
  fi

  log_warn "authorship note found for %s, extracting data..." "$commit_hash"

  # ---- Extract data from git-ai ----
  STATS_JSON=""
  NOTES_JSON=""

  if ! extract_commit_stats "$commit_hash" "$repo_path"; then
    log_warn "git-ai stats extraction failed for %s" "$commit_hash"
    send_error_to_api "$commit_hash" "stats_extraction_failed" "$branch_name" "$repo_name"
    return 1
  fi

  if ! extract_notes_metadata "$commit_hash" "$repo_path"; then
    log_warn "notes metadata extraction failed for %s" "$commit_hash"
    send_error_to_api "$commit_hash" "notes_extraction_failed" "$branch_name" "$repo_name"
    return 1
  fi

  # Validate schema version (non-blocking warning only)
  validate_schema_version "$NOTES_JSON"

  # ---- Compute prompt-level metrics from notes ----
  compute_prompt_metrics "$NOTES_JSON"

  # ---- Compute transcript metrics (time-windowed prompt count, code-change prompts, permission_mode) ----
  local commit_ts parent_ts
  local commit_epoch parent_epoch
  commit_epoch=$(git -C "$repo_path" log -1 --format="%at" "$commit_hash" 2>/dev/null || echo "0")
  parent_epoch=$(git -C "$repo_path" log -1 --format="%at" "${commit_hash}~1" 2>/dev/null || echo "0")
  # Convert epoch → ISO UTC string — macOS uses -r, Linux uses -d @
  commit_ts=$(date -u -r "$commit_epoch" "+%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
              date -u -d  "@$commit_epoch" "+%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || true)
  parent_ts=$(date -u -r "$parent_epoch" "+%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || \
              date -u -d  "@$parent_epoch" "+%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || true)
  extract_transcript_metrics "$NOTES_JSON" "$repo_path" "$parent_ts" "$commit_ts" "$branch_name"

  # ---- Compute metrics ----
  local ai_additions git_diff_added_lines total_ai_additions
  ai_additions=$(echo "$STATS_JSON" | jq '.ai_additions // 0')
  git_diff_added_lines=$(echo "$STATS_JSON" | jq '.git_diff_added_lines // 0')
  total_ai_additions=$(echo "$STATS_JSON" | jq '.total_ai_additions // 0')

  local metrics_json
  metrics_json=$(compute_metrics "$ai_additions" "$git_diff_added_lines" "$TRANSCRIPT_PROMPT_COUNT" "$total_ai_additions")

  # ---- Build payload components ----
  local model_breakdown sessions file_type_breakdown
  model_breakdown=$(build_model_breakdown "$STATS_JSON")
  sessions=$(build_sessions "$NOTES_JSON")
  file_type_breakdown=$(build_file_type_breakdown "$commit_hash" "$repo_path")

  # ---- Assemble full request ----
  local request
  request=$(convert_to_request \
    "$commit_hash" "$repo_name" "$repo_path" "$branch_name" \
    "$STATS_JSON" "$NOTES_JSON" "$metrics_json" \
    "$model_breakdown" "$sessions" "$file_type_breakdown")

  if [ -z "$request" ]; then
    log_warn "convert to request failed for commit %s" "$commit_hash"
    return 1
  fi

  if [ "$DRY_RUN" = true ]; then
    save_metrics_locally "$request"
    return 0
  fi

  # ---- Send to API with retry queue ----
  # Serialise access to failed.json so concurrent continue processes
  # don't overwrite each other's data.
  acquire_lock "$CONTINUE_LOCK_DIR"
  trap 'release_lock "$CONTINUE_LOCK_DIR"' EXIT

  log_warn "Sending current commit %s to API..." "$commit_hash"
  send_current_then_drain "$request"

  trap - EXIT
  release_lock "$CONTINUE_LOCK_DIR"

  return 0
}

# ============================================================
# Main
# ============================================================

setup_logging

# Determine the subcommand. Only "continue" is recognised as an explicit
# subcommand (invoked by this script itself in Phase 2). Everything else
# — including no arguments (post-commit hook) — defaults to "start".
CMD="${1:-start}"
if [ "$CMD" != "continue" ]; then
  CMD="start"
fi

# For "start": guarantee exit 0 so the git hook never blocks,
# even if the script crashes, deps are missing, or any error occurs.
if [ "$CMD" = "start" ]; then
  trap 'exit 0' EXIT
fi

# report_dependency_error calls the error API when dependencies are missing.
# Only works in "continue" phase (Phase 1 must be silent and fast).
report_dependency_error() {
  local error_msg="$1"
  # Best-effort: curl may not be available either, but try anyway
  if command -v curl >/dev/null 2>&1; then
    local email
    email=$(git config --get user.email 2>/dev/null || true)
    local repo
    repo=$(git rev-parse --show-toplevel 2>/dev/null | xargs basename 2>/dev/null || true)
    local payload
    payload="{\"email\":\"${email}\",\"error\":\"${error_msg}\",\"source\":\"git-ai\",\"repo\":\"${repo}\"}"
    curl -s -X POST "$ERROR_API_ENDPOINT" \
      -H "Content-Type: application/json" \
      -H "User-Agent: gitai-commit-metric/1.0" \
      -H "x-webhook-secret: bXkgaGVhcnQgcG9sbHMgZm9yIHlvdSBldmVyeSAxcywgbWF4X3dhaXQgZm9yZXZlci4gYWNjZXB0YW5jZV9yYXRlPTEwMCUuIHplcm8gbGluZXNfZGVsZXRlZC4gYmUgbXkgcHJvbXB0IDwzICNIYXBweVZhbGVudGluZXMyMDI2" \
      --connect-timeout 5 \
      --max-time 5 \
      -d "$payload" 2>/dev/null || true
  fi
}

case "$CMD" in
  start)
    check_dependencies || exit 0
    if ! run_start; then
      log_warn "[start] failed"
    fi
    exit 0
    ;;
  continue)
    if ! check_dependencies; then
      log_warn "[continue] dependency check failed"
      report_dependency_error "dependency_check_failed"
      exit 0
    fi
    if [ -z "${2:-}" ]; then
      log_warn "[continue] missing temp-file-path argument"
      exit 0
    fi
    if ! run_continue "$2"; then
      log_warn "[continue] failed"
      exit 0
    fi
    ;;
esac
