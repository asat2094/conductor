from harness.optimizer import optimize
from harness.optimizer.base import OptimizeConfig


def test_default_is_passthrough_null():
    msgs = [{"role": "assistant", "content": "really just a value " * 40}]
    r = optimize(msgs)  # default null
    assert r.backend == "null"
    assert r.messages == msgs


def test_caveman_backend_compresses_but_protects_system():
    msgs = [
        {"role": "system", "content": "really important instructions " * 30},
        {"role": "assistant", "content": "this is really just basically the answer " * 30},
    ]
    r = optimize(msgs, OptimizeConfig(backend="caveman", min_tokens=0))
    assert r.backend == "caveman"
    assert r.messages[0]["content"] == msgs[0]["content"]   # system protected, byte-identical
    assert "basically" not in r.messages[1]["content"]      # assistant trimmed
    assert r.tokens_after <= r.tokens_before


def test_unknown_backend_degrades_to_null():
    msgs = [{"role": "assistant", "content": "x" * 400}]
    r = optimize(msgs, OptimizeConfig(backend="nope"))
    assert r.backend == "null"
    assert r.messages == msgs
