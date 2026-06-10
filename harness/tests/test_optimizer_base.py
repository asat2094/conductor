from harness.optimizer.base import OptimizeConfig, OptimizeResult, count_tokens


def test_config_defaults_to_null_backend():
    cfg = OptimizeConfig()
    assert cfg.backend == "null"
    assert cfg.min_tokens == 250
    assert "system" in cfg.protect_roles


def test_count_tokens_sums_message_content_char_quarter():
    msgs = [{"role": "user", "content": "a" * 40}]
    assert count_tokens(msgs) == 10


def test_count_tokens_ignores_non_string_content():
    msgs = [{"role": "user", "content": None}, {"role": "user"}]
    assert count_tokens(msgs) == 0


def test_optimize_result_holds_metrics():
    r = OptimizeResult(messages=[], tokens_before=100, tokens_after=40, tokens_saved=60, backend="x")
    assert r.tokens_saved == 60 and r.backend == "x"
