from harness.model_call import call_model, extract_files


def test_claude_cli_parses_result_field():
    captured = {}
    def fake_runner(args, input_text):
        captured["args"] = args
        captured["input"] = input_text
        return '{"type":"result","result":"hello from claude"}'
    out = call_model({"backend": "claude_cli", "model": "haiku"}, "say hi", runner=fake_runner)
    assert out == "hello from claude"
    assert "claude" in captured["args"][0] or captured["args"][0] == "claude"
    assert "--model" in captured["args"] and "haiku" in captured["args"]
    assert "--print" in captured["args"] or "-p" in captured["args"]


def test_ollama_returns_response_field():
    def fake_http(url, payload):
        assert "11434" in url
        assert payload["model"] == "gemma4:latest"
        assert payload["stream"] is False
        return {"response": "hello from gemma"}
    out = call_model({"backend": "ollama", "model": "gemma4:latest"}, "say hi", http=fake_http)
    assert out == "hello from gemma"


def test_unknown_backend_raises():
    import pytest
    with pytest.raises(ValueError):
        call_model({"backend": "nope", "model": "x"}, "p")


def test_extract_single_file():
    text = "prose\n=== FILE: a.py ===\ndef f():\n    return 1\n=== END ===\nmore prose"
    files = extract_files(text)
    assert set(files) == {"a.py"}
    assert files["a.py"] == "def f():\n    return 1"


def test_extract_multiple_files():
    text = "=== FILE: a.py ===\nx=1\n=== END ===\n=== FILE: b/c.py ===\ny=2\n=== END ==="
    files = extract_files(text)
    assert files == {"a.py": "x=1", "b/c.py": "y=2"}


def test_extract_none_returns_empty():
    assert extract_files("no file blocks here") == {}
