#!/usr/bin/env python3
"""
Benchmark gemma4 across context sizes and task types.
Writes results to gemma4-bench/bench_results.json
Updates harness/capability_profiles.json with discovered thresholds.
"""
import json
import re
import time
import ast
import urllib.request
from pathlib import Path

BENCH_DIR = Path(__file__).parent
HARNESS_DIR = BENCH_DIR.parent / "harness"
PROFILES_PATH = HARNESS_DIR / "capability_profiles.json"
RESULTS_PATH = BENCH_DIR / "bench_results.json"

SOURCE_FILES = [
    Path("/Users/ankitatiwari/Desktop/claude-playground/backtest-engine/backend/metrics/engine.py"),
    Path("/Users/ankitatiwari/Desktop/claude-playground/backtest-engine/backend/costs/engine.py"),
    Path("/Users/ankitatiwari/Desktop/claude-playground/trading-system/backend/llm/tools.py"),
]

TOKEN_TARGETS = [1000, 4000, 8000, 16000, 32000]
TASK_TYPES = ["code_edit", "code_gen", "test_write"]
TRIALS = 2


def _build_payload(target_tokens: int) -> str:
    target_chars = target_tokens * 4
    parts = []
    total = 0
    sources = [f.read_text() for f in SOURCE_FILES if f.exists()]
    if not sources:
        sources = ["def placeholder(): pass\n" * 50]
    while total < target_chars:
        for s in sources:
            parts.append(s)
            total += len(s)
            if total >= target_chars:
                break
    return "\n\n".join(parts)[:target_chars]


def _task_prompt(task_type: str, payload: str) -> str:
    # All prompts explicitly request a fenced code block — required for reliable scoring.
    prompts = {
        "code_edit": (
            f"Given this code:\n\n{payload}\n\n"
            "Add a Google-style docstring to the first function you see. "
            "Output ONLY the complete modified function inside a single ```python code block. No explanation."
        ),
        "code_gen": (
            f"Given this code context:\n\n{payload[:2000]}\n\n"
            "Write a new standalone Python function called `validate_input` that checks if a dict has a 'symbol' key. "
            "Output ONLY the function inside a single ```python code block. No explanation."
        ),
        "test_write": (
            f"Given this code:\n\n{payload[:2000]}\n\n"
            "Write one pytest test for any function you see. "
            "Output ONLY the test function inside a single ```python code block. No explanation."
        ),
    }
    return prompts[task_type]


def _extract_code_block(text: str) -> str:
    """Pull first fenced code block; fall back to full text."""
    m = re.search(r"```(?:python|py)?\n(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _score_output(raw_output: str, task_type: str) -> int:
    if not raw_output.strip():
        return 0
    code = _extract_code_block(raw_output)
    try:
        ast.parse(code)
        syntax_ok = True
    except SyntaxError:
        syntax_ok = False

    if task_type == "code_edit":
        has_docstring = '"""' in code or "'''" in code
        return 90 if (syntax_ok and has_docstring) else 50 if syntax_ok else 20

    if task_type == "code_gen":
        has_func = "def validate_input" in code
        return 90 if (syntax_ok and has_func) else 50 if has_func else 20

    if task_type == "test_write":
        has_test = "def test_" in code
        return 90 if (syntax_ok and has_test) else 50 if has_test else 20

    return 30


def _run_gemma4(prompt: str) -> tuple[str, float]:
    """Call ollama REST API directly — same path used by gemma4_delegate.sh."""
    start = time.time()
    try:
        payload = json.dumps({"model": "gemma4:latest", "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
        latency = time.time() - start
        return data.get("response", ""), latency
    except Exception:
        return "", time.time() - start


def run_benchmark() -> dict:
    results = {}
    for token_target in TOKEN_TARGETS:
        payload = _build_payload(token_target)
        actual_tokens = len(payload) // 4
        print(f"\n=== Context: ~{actual_tokens:,} tokens ===")
        for task_type in TASK_TYPES:
            prompt = _task_prompt(task_type, payload)
            scores = []
            latencies = []
            for trial in range(TRIALS):
                print(f"  {task_type} trial {trial+1}/{TRIALS}...", end=" ", flush=True)
                output, latency = _run_gemma4(prompt)
                score = _score_output(output, task_type)
                scores.append(score)
                latencies.append(latency)
                print(f"score={score} latency={latency:.1f}s")
            key = f"{actual_tokens}_{task_type}"
            results[key] = {
                "tokens": actual_tokens,
                "task_type": task_type,
                "avg_score": round(sum(scores) / len(scores), 1),
                "avg_latency": round(sum(latencies) / len(latencies), 1),
                "scores": scores,
            }
    return results


def derive_thresholds(results: dict) -> dict:
    by_type: dict[str, list] = {}
    for cell in results.values():
        t = cell["task_type"]
        by_type.setdefault(t, []).append(cell)

    thresholds = {}
    for task_type, cells in by_type.items():
        cells.sort(key=lambda c: c["tokens"])
        max_reliable = 1000
        acc_scores = {}
        for cell in cells:
            if cell["avg_score"] >= 70:
                max_reliable = cell["tokens"]
                acc_scores[task_type] = round(cell["avg_score"] / 100, 3)
        thresholds[task_type] = {
            "max_reliable_tokens": max_reliable,
            "accuracy": acc_scores.get(task_type, 0.5),
        }
    return thresholds


def update_profiles(thresholds: dict) -> None:
    profiles = json.loads(PROFILES_PATH.read_text())
    gemma = profiles["gemma4"]
    token_limits = [v["max_reliable_tokens"] for v in thresholds.values()]
    gemma["max_reliable_tokens"] = min(token_limits) if token_limits else 8000
    for task_type, data in thresholds.items():
        gemma["accuracy_by_type"][task_type] = data["accuracy"]
    gemma["session_failures"] = 0
    PROFILES_PATH.write_text(json.dumps(profiles, indent=2))
    print(f"\nUpdated {PROFILES_PATH}")


def main():
    print("Benchmarking gemma4 via opencode...")
    print(f"Trials per cell: {TRIALS}, Task types: {TASK_TYPES}")
    print(f"Token targets: {TOKEN_TARGETS}")
    results = run_benchmark()
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nRaw results saved to {RESULTS_PATH}")
    thresholds = derive_thresholds(results)
    print("\n--- Derived thresholds ---")
    for task_type, data in thresholds.items():
        print(f"  {task_type}: max_reliable_tokens={data['max_reliable_tokens']:,}  accuracy={data['accuracy']}")
    update_profiles(thresholds)
    print("\nBenchmark complete. Run: cd conductor && /opt/homebrew/bin/pytest -v")


if __name__ == "__main__":
    main()
