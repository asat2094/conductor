from harness.optimizer.base import OptimizeConfig
from harness.optimizer.guard import is_protected, restore_protected


def test_protected_by_role():
    cfg = OptimizeConfig()
    assert is_protected({"role": "system", "content": "x"}, cfg) is True
    assert is_protected({"role": "user", "content": "x" * 1000}, cfg) is False


def test_protected_by_tag():
    cfg = OptimizeConfig()
    assert is_protected({"role": "user", "content": "code __gate_evidence__ here"}, cfg) is True


def test_protected_when_below_min_tokens():
    cfg = OptimizeConfig(min_tokens=100)
    assert is_protected({"role": "user", "content": "short"}, cfg) is True


def test_restore_protected_overwrites_backend_changes_on_protected_slots():
    cfg = OptimizeConfig()
    original = [
        {"role": "system", "content": "S" * 400},
        {"role": "user", "content": "U" * 4000},
    ]
    backend_out = [
        {"role": "system", "content": "MANGLED"},
        {"role": "user", "content": "compressed-u"},
    ]
    fixed = restore_protected(original, backend_out, cfg)
    assert fixed[0]["content"] == "S" * 400
    assert fixed[1]["content"] == "compressed-u"


def test_restore_protected_falls_back_to_original_on_length_mismatch():
    cfg = OptimizeConfig()
    original = [{"role": "user", "content": "U" * 400}]
    backend_out = []
    assert restore_protected(original, backend_out, cfg) is original
