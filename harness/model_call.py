"""Unified model caller for Claude CLI and ollama backends."""

import json
import re
import subprocess
import urllib.request
from typing import Any, Callable, Optional


def _default_runner(args: list[str], input_text: str) -> str:
    """Default subprocess runner for claude_cli backend."""
    result = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.stdout


def _default_http(url: str, payload: dict) -> dict:
    """Default HTTP runner for ollama backend using urllib."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _openai_http(api_key: Optional[str]) -> Callable[[str, dict], dict]:
    """Default HTTP caller for openai_compat: POST chat/completions with Bearer auth."""
    def _http(url: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return _http


def call_model(
    spec: dict,
    prompt: str,
    *,
    runner: Optional[Callable[[list[str], str], str]] = None,
    http: Optional[Callable[[str, dict], dict]] = None,
) -> str:
    """Dispatch a model call based on spec['backend'].

    Args:
        spec: Dict with 'backend' and 'model' keys.
        prompt: The prompt text to send to the model.
        runner: Optional injectable subprocess runner for claude_cli.
                Signature: runner(args_list, input_text) -> stdout_str
        http: Optional injectable HTTP caller for ollama.
              Signature: http(url, payload_dict) -> response_dict

    Returns:
        The model's response as a string.

    Raises:
        ValueError: If spec['backend'] is not recognised.
    """
    backend = spec["backend"]
    model = spec["model"]

    if backend == "claude_cli":
        _runner = runner if runner is not None else _default_runner
        args = ["claude", "--print", "--model", model, "--output-format", "json"]
        stdout = _runner(args, prompt)
        return json.loads(stdout)["result"]

    if backend == "ollama":
        _http = http if http is not None else _default_http
        url = "http://localhost:11434/api/generate"
        payload = {"model": model, "prompt": prompt, "stream": False}
        resp = _http(url, payload)
        return resp["response"]

    if backend == "openai_compat":
        import os
        base_url = spec["base_url"]
        key_env = spec.get("api_key_env")
        api_key = os.environ.get(key_env) if key_env else None
        if key_env and not api_key:
            # config error -> propagates (fail loud); NEVER silently scored as a refusal.
            raise ValueError(f"missing API key env {key_env!r} for openai_compat model {model!r}")
        _http = http if http is not None else _openai_http(api_key)
        url = base_url.rstrip("/") + "/chat/completions"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        resp = _http(url, payload)
        return resp["choices"][0]["message"]["content"]

    raise ValueError(f"Unknown backend: {backend!r}")


def extract_files(text: str) -> dict[str, str]:
    """Parse file blocks of the form:

        === FILE: path/to/x.py ===
        <content lines>
        === END ===

    Returns a dict mapping path -> content (trailing newline stripped).
    Multiple blocks are supported; surrounding prose is ignored.
    """
    pattern = re.compile(
        r"=== FILE: (.+?) ===\n(.*?)\n=== END ===",
        re.DOTALL,
    )
    return {m.group(1): m.group(2) for m in pattern.finditer(text)}
