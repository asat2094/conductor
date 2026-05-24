#!/usr/bin/env python3
"""
gemma4_call.py <workdir> <task> <file1> [file2 ...]

Reads files from workdir, builds prompt, calls gemma4 via ollama REST API,
extracts first fenced code block, writes it back to file1.
Prints full response to stdout. Logs status to stderr.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:latest"


def call_ollama(prompt: str) -> str:
    payload = json.dumps({"model": MODEL, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    return data.get("response", "")


def extract_code_block(text: str) -> str | None:
    m = re.search(r"```(?:python|py)?\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    # fallback: bare block without language tag
    m = re.search(r"```\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else None


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: gemma4_call.py <workdir> <task> <file1> [file2 ...]", file=sys.stderr)
        return 1

    workdir = Path(sys.argv[1])
    task = sys.argv[2]
    files = sys.argv[3:]

    # Build prompt with embedded file contents
    sections = [task, ""]
    for f in files:
        path = workdir / f
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            return 1
        sections.append(f"--- FILE: {f} ---")
        sections.append(path.read_text())
        sections.append("")

    sections.append(
        f"Output ONLY the complete modified version of {files[0]} "
        "inside a single fenced code block. No explanation, no other text."
    )
    prompt = "\n".join(sections)

    print(f"[gemma4] Calling ollama ({MODEL})...", file=sys.stderr)
    response = call_ollama(prompt)
    print(response)

    code = extract_code_block(response)
    if not code:
        print("\n[gemma4] WARNING: no code block in response — file not modified.", file=sys.stderr)
        return 1

    target = workdir / files[0]
    target.write_text(code)
    print(f"[gemma4] Written to {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
