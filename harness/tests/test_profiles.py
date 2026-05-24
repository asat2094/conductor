import json
from pathlib import Path
from harness.models import CapabilityProfile
import harness.profiles as profiles_mod


def _write_tmp_profiles(tmp_path: Path) -> Path:
    data = {
        "gemma4": {
            "max_reliable_tokens": 8000,
            "accuracy_by_type": {"code_edit": 0.80},
            "session_failures": 0,
            "retry_budget": 3,
        }
    }
    p = tmp_path / "capability_profiles.json"
    p.write_text(json.dumps(data))
    return p


def test_load_profiles(tmp_path):
    path = _write_tmp_profiles(tmp_path)
    profiles = profiles_mod.load_profiles(path)
    assert "gemma4" in profiles
    assert isinstance(profiles["gemma4"], CapabilityProfile)
    assert profiles["gemma4"].max_reliable_tokens == 8000


def test_save_and_reload(tmp_path):
    path = _write_tmp_profiles(tmp_path)
    profiles = profiles_mod.load_profiles(path)
    profiles["gemma4"].session_failures = 2
    profiles_mod.save_profiles(profiles, path)
    reloaded = profiles_mod.load_profiles(path)
    assert reloaded["gemma4"].session_failures == 2


def test_update_accuracy_rolling_average(tmp_path):
    path = _write_tmp_profiles(tmp_path)
    profiles = profiles_mod.load_profiles(path)
    profiles_mod.update_accuracy(profiles, "gemma4", "code_edit", 40)
    # 0.80 * 0.7 + 0.40 * 0.3 = 0.56 + 0.12 = 0.68
    assert abs(profiles["gemma4"].accuracy_by_type["code_edit"] - 0.68) < 0.01
