from harness.optimizer_wiring import is_paid_reader, optimize_for_reader


def test_is_paid_reader():
    assert is_paid_reader({"backend": "claude_cli", "model": "opus"}) is True
    assert is_paid_reader({"backend": "ollama", "model": "gemma4"}) is False


def test_free_reader_passes_through_unchanged():
    msgs = [{"role": "assistant", "content": "this is really just basically it " * 30}]
    out = optimize_for_reader(msgs, {"backend": "ollama", "model": "g"})
    assert out == msgs   # free reader -> no compression


def test_paid_reader_compresses():
    msgs = [{"role": "assistant", "content": "this is really just basically the answer " * 30}]
    out = optimize_for_reader(msgs, {"backend": "claude_cli", "model": "haiku"}, backend="caveman", min_tokens=0)
    assert "basically" not in out[0]["content"]   # caveman trimmed it for the paid reader


def test_paid_reader_protects_system_message():
    msgs = [
        {"role": "system", "content": "really important instructions " * 30},
        {"role": "assistant", "content": "really just basically " * 30},
    ]
    out = optimize_for_reader(msgs, {"backend": "claude_cli", "model": "opus"}, backend="caveman", min_tokens=0)
    assert out[0]["content"] == msgs[0]["content"]   # system protected (guard)
