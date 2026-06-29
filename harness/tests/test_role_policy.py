from harness.role_policy import resolve_model, ROLE_DEFAULTS, TIERS


def test_defaults_cover_all_roles():
    for role in ("decomposer", "test_author", "impl_author", "verifier", "checker"):
        spec = resolve_model(role)
        assert "backend" in spec


def test_impl_author_defaults_to_cheap_local():
    spec = resolve_model("impl_author")
    assert spec["backend"] == "ollama"   # cheap grunt work -> local gemma4


def test_decomposer_is_high_capability():
    spec = resolve_model("decomposer")
    assert spec["backend"] == "claude_cli"
    assert spec["model"] == "opus"


def test_high_stakes_bumps_impl_author_up():
    low = resolve_model("impl_author", high_stakes=False)
    high = resolve_model("impl_author", high_stakes=True)
    assert high != low                      # high-stakes escalates off cheap local
    assert high["backend"] == "claude_cli"  # bumped to a Claude tier


def test_unknown_role_falls_back_to_checker_tier():
    spec = resolve_model("totally_unknown_role")
    assert "backend" in spec   # never crashes; returns a safe default


def test_explicit_policy_override():
    custom = {"impl_author": {"backend": "claude_cli", "model": "sonnet"}}
    spec = resolve_model("impl_author", policy=custom)
    assert spec == {"backend": "claude_cli", "model": "sonnet"}
