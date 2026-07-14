from harness.optimizer.base import OptimizeConfig
from harness.optimizer.backends.caveman import CavemanCompressor


def test_caveman_is_available():
    assert CavemanCompressor().available() is True


def test_caveman_trims_filler_and_collapses_whitespace():
    text = "The result is   basically    just the   value."
    msgs = [{"role": "assistant", "content": text}]
    r = CavemanCompressor().optimize(msgs, OptimizeConfig(min_tokens=0))
    out = r.messages[0]["content"]
    assert "basically" not in out
    assert "  " not in out
    assert r.tokens_after <= r.tokens_before
    assert "caveman" in r.transforms_applied[0]


def test_caveman_is_deterministic():
    msgs = [{"role": "assistant", "content": "This is really just a simple test."}]
    a = CavemanCompressor().optimize(msgs, OptimizeConfig(min_tokens=0)).messages
    b = CavemanCompressor().optimize(msgs, OptimizeConfig(min_tokens=0)).messages
    assert a == b


def test_caveman_preserves_message_count_and_roles():
    msgs = [{"role": "assistant", "content": "really really long " * 30}]
    r = CavemanCompressor().optimize(msgs, OptimizeConfig(min_tokens=0))
    assert len(r.messages) == 1
    assert r.messages[0]["role"] == "assistant"
