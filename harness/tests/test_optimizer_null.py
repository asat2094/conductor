from harness.optimizer.base import OptimizeConfig
from harness.optimizer.backends.null import NullCompressor


def test_null_is_always_available():
    assert NullCompressor().available() is True


def test_null_returns_messages_unchanged_with_equal_token_counts():
    msgs = [{"role": "user", "content": "x" * 40}]
    r = NullCompressor().optimize(msgs, OptimizeConfig())
    assert r.messages is msgs
    assert r.tokens_before == r.tokens_after == 10
    assert r.tokens_saved == 0
    assert r.backend == "null"


def test_null_retrieve_returns_none():
    assert NullCompressor().retrieve("any") is None
