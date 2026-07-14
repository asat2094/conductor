import pytest
from harness.sensitivity import allowed_for_sensitivity, enforce, SensitivityViolation, ExposureAudit


def test_high_sensitivity_blocks_third_party_cloud():
    assert allowed_for_sensitivity({"backend": "openai_compat", "model": "x"}, "high") is False


def test_high_sensitivity_allows_local_and_claude():
    assert allowed_for_sensitivity({"backend": "ollama", "model": "gemma4"}, "high") is True
    assert allowed_for_sensitivity({"backend": "claude_cli", "model": "opus"}, "high") is True


def test_low_sensitivity_allows_anything():
    assert allowed_for_sensitivity({"backend": "openai_compat", "model": "x"}, "low") is True


def test_enforce_raises_on_violation():
    with pytest.raises(SensitivityViolation):
        enforce({"backend": "openai_compat", "model": "x"}, "high")


def test_enforce_returns_spec_when_allowed():
    spec = {"backend": "ollama", "model": "g"}
    assert enforce(spec, "high") == spec


def test_exposure_audit_hashes_never_stores_raw():
    a = ExposureAudit()
    a.record("openrouter", "secret source code here")
    e = a.entries[0]
    assert e["provider"] == "openrouter"
    assert "secret" not in str(e)          # raw never stored
    assert e["nbytes"] == len("secret source code here")
    assert len(e["hash"]) == 16
