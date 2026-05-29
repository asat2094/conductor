"""
provider_call.py — unified model caller.

run(provider, workdir, task, files, diff_mode=False) -> (response_text, code_or_none)

Raises:
    RateLimitError  — HTTP 429 or openai.RateLimitError
    ProviderError   — any other call failure (timeout, 5xx, connection refused)
"""
from __future__ import annotations

import json as _json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from harness.gemma4_call import apply_patch, extract_code_block, extract_diff_block
from harness.models import ProviderConfig


class RateLimitError(Exception):
    pass


class ProviderError(Exception):
    pass


def _build_prompt(workdir: str, task: str, files: list[str], diff_mode: bool = False) -> str:
    root = Path(workdir)
    target = files[0]
    target_exists = (root / target).exists()
    sections = [task, ""]
    for f in files:
        path = root / f
        if path.exists():
            sections.append(f"--- FILE: {f} ---")
            sections.append(path.read_text())
            sections.append("")
    if diff_mode and target_exists:
        sections.append(
            f"Output ONLY a unified diff (--- {target}\n+++ {target}) "
            "of the changes inside a single fenced diff block. No explanation, no other text."
        )
    elif target_exists:
        sections.append(
            f"Output ONLY the complete modified version of {target} "
            "inside a single fenced code block. No explanation, no other text."
        )
    else:
        sections.append(
            f"Output ONLY the complete contents of the new file {target} "
            "inside a single fenced code block. No explanation, no other text."
        )
    return "\n".join(sections)


def _run_ollama(
    provider: ProviderConfig, workdir: str, task: str, files: list[str], diff_mode: bool = False
) -> tuple[str, str | None]:
    root = Path(workdir)
    target = root / files[0]
    target_exists = target.exists()
    prompt = _build_prompt(workdir, task, files, diff_mode)
    url = provider.base_url.rstrip("/") + "/api/generate"
    payload = _json.dumps({"model": provider.model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    print(f"[{provider.name}] Calling ollama ({provider.model})...", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = _json.loads(resp.read())
        text = data.get("response", "")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimitError(f"{provider.name}: rate limited") from e
        raise ProviderError(f"{provider.name}: HTTP {e.code}") from e
    except Exception as e:
        raise ProviderError(f"{provider.name}: {e}") from e

    if diff_mode and target_exists:
        diff = extract_diff_block(text)
        if diff and apply_patch(diff, target):
            print(f"[{provider.name}] Patch applied to {target}", file=sys.stderr)
            return text, diff
        print(f"\n[{provider.name}] WARNING: diff failed — falling back to full rewrite.", file=sys.stderr)
        return _run_ollama(provider, workdir, task, files, diff_mode=False)

    code = extract_code_block(text)
    if not code:
        print(f"\n[{provider.name}] WARNING: no code block in response.", file=sys.stderr)
        return text, None
    target.write_text(code)
    print(f"[{provider.name}] Written to {target}", file=sys.stderr)
    return text, code


def _run_openai_compat(
    provider: ProviderConfig, workdir: str, task: str, files: list[str], diff_mode: bool = False
) -> tuple[str, str | None]:
    try:
        import openai
    except ImportError:
        raise ProviderError(f"{provider.name}: openai package required — run: pip install openai")

    root = Path(workdir)
    target = root / files[0]
    target_exists = target.exists()
    api_key = os.environ.get(provider.api_key_env, "no-key") if provider.api_key_env else "no-key"
    client = openai.OpenAI(base_url=provider.base_url, api_key=api_key)
    prompt = _build_prompt(workdir, task, files, diff_mode)
    print(f"[{provider.name}] Calling {provider.model}...", file=sys.stderr)
    try:
        resp = client.chat.completions.create(
            model=provider.model,
            messages=[{"role": "user", "content": prompt}],
            timeout=180,
        )
        text = resp.choices[0].message.content or ""
    except openai.RateLimitError as e:
        raise RateLimitError(f"{provider.name}: {e}") from e
    except Exception as e:
        raise ProviderError(f"{provider.name}: {e}") from e

    if diff_mode and target_exists:
        diff = extract_diff_block(text)
        if diff and apply_patch(diff, target):
            print(f"[{provider.name}] Patch applied to {target}", file=sys.stderr)
            return text, diff
        print(f"\n[{provider.name}] WARNING: diff failed — falling back to full rewrite.", file=sys.stderr)
        return _run_openai_compat(provider, workdir, task, files, diff_mode=False)

    code = extract_code_block(text)
    if not code:
        print(f"\n[{provider.name}] WARNING: no code block in response.", file=sys.stderr)
        return text, None
    target.write_text(code)
    print(f"[{provider.name}] Written to {target}", file=sys.stderr)
    return text, code


def run(
    provider: ProviderConfig,
    workdir: str,
    task: str,
    files: list[str],
    diff_mode: bool = False,
) -> tuple[str, str | None]:
    if provider.type == "ollama":
        return _run_ollama(provider, workdir, task, files, diff_mode)
    return _run_openai_compat(provider, workdir, task, files, diff_mode)
