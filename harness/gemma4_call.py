#!/usr/bin/env python3
"""
gemma4_call.py <workdir> <task> <file1> [file2 ...] [--diff]

Reads files from workdir, builds prompt, calls gemma4 via ollama REST API,
extracts first fenced code block (or unified diff in --diff mode), writes to file1.
Prints full response to stdout. Logs status to stderr.

--diff: asks gemma4 for a unified diff instead of full file; applies with `patch(1)`.
        If patch(1) is missing or the diff apply fails, automatically falls back to
        a full file rewrite (re-calls gemma4 without --diff). A warning is logged.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:latest"


def call_ollama(prompt: str) -> str:
    import urllib.request
    payload = json.dumps({"model": MODEL, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    return data.get("response", "")


def extract_code_block(text: str) -> str | None:
    m = re.search(r"```(?:python|py)?\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"```\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else None


def extract_diff_block(text: str) -> str | None:
    m = re.search(r"```(?:diff|patch)?\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Accept raw diff without fencing if it starts with ---
    if text.strip().startswith("---"):
        return text.strip()
    return None


def apply_patch(diff_text: str, target: Path) -> bool:
    try:
        result = subprocess.run(
            ["patch", str(target)],
            input=diff_text, text=True, capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run(workdir: str, task: str, files: list[str], diff_mode: bool = False) -> tuple[str, str | None]:
    """
    Call gemma4 and write the result to files[0].

    Returns (response_text, extracted_code_or_diff).
    extracted is None if no parseable block was found.
    """
    root = Path(workdir)
    target = root / files[0]
    target_exists = target.exists()

    sections = [task, ""]
    for f in files:
        path = root / f
        if path.exists():
            sections.append(f"--- FILE: {f} ---")
            sections.append(path.read_text())
            sections.append("")

    if diff_mode and target_exists:
        sections.append(
            f"Output ONLY a unified diff (--- {files[0]}\n+++ {files[0]}) "
            "of the changes inside a single fenced diff block. No explanation, no other text."
        )
    elif target_exists:
        sections.append(
            f"Output ONLY the complete modified version of {files[0]} "
            "inside a single fenced code block. No explanation, no other text."
        )
    else:
        sections.append(
            f"Output ONLY the complete contents of the new file {files[0]} "
            "inside a single fenced code block. No explanation, no other text."
        )

    prompt = "\n".join(sections)
    print(f"[gemma4] Calling ollama ({MODEL})...", file=sys.stderr)
    response = call_ollama(prompt)

    if diff_mode and target_exists:
        diff = extract_diff_block(response)
        if diff and apply_patch(diff, target):
            print(f"[gemma4] Patch applied to {target}", file=sys.stderr)
            return response, diff
        # Fallback: patch unavailable or failed — retry as full rewrite
        print(
            "\n[gemma4] WARNING: diff mode failed (patch missing or bad diff) — "
            "falling back to full rewrite.",
            file=sys.stderr,
        )
        return run(workdir, task, files, diff_mode=False)

    code = extract_code_block(response)
    if not code:
        print("\n[gemma4] WARNING: no code block in response — file not modified.", file=sys.stderr)
        return response, None

    target.write_text(code)
    print(f"[gemma4] Written to {target}", file=sys.stderr)
    return response, code


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: gemma4_call.py <workdir> <task> <file1> [file2 ...] [--diff]", file=sys.stderr)
        return 1

    args = sys.argv[1:]
    diff_mode = "--diff" in args
    args = [a for a in args if a != "--diff"]

    workdir, task, *files = args
    response, extracted = run(workdir, task, files, diff_mode=diff_mode)
    print(response)
    return 0 if extracted is not None else 1


if __name__ == "__main__":
    sys.exit(main())
