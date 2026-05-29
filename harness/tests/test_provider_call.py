import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from harness.models import ProviderConfig


def _ollama_provider():
    return ProviderConfig("gemma4", "ollama", "gemma4:latest",
                          "http://localhost:11434", 0.0, "local")


def _openai_provider():
    return ProviderConfig("deepseek", "openai_compat", "deepseek-coder",
                          "https://api.deepseek.com/v1", 0.0014, "cloud_cheap", "DEEPSEEK_API_KEY")


def _fake_urlopen(response_text: str):
    payload = json.dumps({"response": response_text}).encode()
    mock = MagicMock()
    mock.read.return_value = payload
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def test_ollama_extracts_code_and_writes_file(tmp_path):
    from harness.provider_call import run
    (tmp_path / "f.py").write_text("x = 1")
    with patch("urllib.request.urlopen", return_value=_fake_urlopen("```python\ny = 2\n```")):
        _, code = run(_ollama_provider(), str(tmp_path), "update x to y", ["f.py"])
    assert code == "y = 2\n"
    assert (tmp_path / "f.py").read_text() == "y = 2\n"


def test_ollama_returns_none_when_no_code_block(tmp_path):
    from harness.provider_call import run
    (tmp_path / "f.py").write_text("x = 1")
    with patch("urllib.request.urlopen", return_value=_fake_urlopen("Sorry, I cannot help.")):
        _, code = run(_ollama_provider(), str(tmp_path), "update x", ["f.py"])
    assert code is None


def test_ollama_raises_rate_limit_on_429(tmp_path):
    from harness.provider_call import run, RateLimitError
    (tmp_path / "f.py").write_text("x = 1")
    err = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RateLimitError):
            run(_ollama_provider(), str(tmp_path), "task", ["f.py"])


def test_ollama_raises_provider_error_on_500(tmp_path):
    from harness.provider_call import run, ProviderError
    (tmp_path / "f.py").write_text("x = 1")
    err = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(ProviderError):
            run(_ollama_provider(), str(tmp_path), "task", ["f.py"])


def test_openai_compat_extracts_code_and_writes_file(tmp_path):
    from harness.provider_call import run
    (tmp_path / "f.py").write_text("x = 1")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = "```python\ny = 2\n```"
    with patch("openai.OpenAI", return_value=mock_client):
        _, code = run(_openai_provider(), str(tmp_path), "update x", ["f.py"])
    assert code == "y = 2\n"
    assert (tmp_path / "f.py").read_text() == "y = 2\n"


def test_openai_compat_raises_rate_limit_on_429(tmp_path):
    import openai as _openai
    from harness.provider_call import run, RateLimitError
    (tmp_path / "f.py").write_text("x = 1")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _openai.RateLimitError(
        "rate limit", response=MagicMock(status_code=429), body={}
    )
    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(RateLimitError):
            run(_openai_provider(), str(tmp_path), "task", ["f.py"])


def test_openai_compat_raises_provider_error_on_api_error(tmp_path):
    import openai as _openai
    from harness.provider_call import run, ProviderError
    (tmp_path / "f.py").write_text("x = 1")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _openai.APIConnectionError(request=MagicMock())
    with patch("openai.OpenAI", return_value=mock_client):
        with pytest.raises(ProviderError):
            run(_openai_provider(), str(tmp_path), "task", ["f.py"])


def test_run_creates_new_file_when_not_exists(tmp_path):
    from harness.provider_call import run
    # f.py does NOT exist
    with patch("urllib.request.urlopen", return_value=_fake_urlopen("```python\ny = 2\n```")):
        _, code = run(_ollama_provider(), str(tmp_path), "create f.py", ["f.py"])
    assert code == "y = 2\n"
    assert (tmp_path / "f.py").exists()
