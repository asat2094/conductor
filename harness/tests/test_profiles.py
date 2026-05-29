import json
import time
from pathlib import Path
from harness.models import CapabilityProfile
import harness.profiles as profiles_mod


def _write_tmp_profiles(tmp_path: Path, last_updated: float | None = None) -> Path:
    data = {
        "gemma4": {
            "max_reliable_tokens": 8000,
            "accuracy_by_type": {"code_edit": 0.80},
            "session_failures": 0,
            "retry_budget": 3,
        }
    }
    if last_updated is not None:
        data["gemma4"]["last_updated"] = last_updated
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


def test_update_accuracy_sets_last_updated(tmp_path):
    before = time.time()
    path = _write_tmp_profiles(tmp_path)
    profiles = profiles_mod.load_profiles(path)
    profiles_mod.update_accuracy(profiles, "gemma4", "code_edit", 90)
    assert profiles["gemma4"].last_updated >= before


def test_decay_stale_profile(tmp_path):
    stale_ts = time.time() - 30 * 86400  # 30 days ago
    path = _write_tmp_profiles(tmp_path, last_updated=stale_ts)
    profiles = profiles_mod.load_profiles(path)
    # 30-day decay: 0.5 + (0.8 - 0.5) * 0.98**30 ≈ 0.666
    accuracy = profiles["gemma4"].accuracy_by_type["code_edit"]
    assert accuracy < 0.80
    assert accuracy > 0.50  # still above neutral


def test_no_decay_fresh_profile(tmp_path):
    path = _write_tmp_profiles(tmp_path, last_updated=time.time())
    profiles = profiles_mod.load_profiles(path)
    accuracy = profiles["gemma4"].accuracy_by_type["code_edit"]
    assert abs(accuracy - 0.80) < 0.01  # no change within same day


def test_missing_last_updated_in_json(tmp_path):
    path = _write_tmp_profiles(tmp_path)  # no last_updated in JSON
    profiles = profiles_mod.load_profiles(path)
    assert profiles["gemma4"].last_updated > 0  # gets defaulted to now
