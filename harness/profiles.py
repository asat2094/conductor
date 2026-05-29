import json
import time
from pathlib import Path
from harness.models import CapabilityProfile

_DEFAULT_PATH = Path(__file__).parent / "capability_profiles.json"

# Accuracy drifts ~2% per day toward 0.5 (neutral) when not updated.
# After 30 days of no runs, a 0.9 score decays to ~0.87.
_DECAY_PER_DAY = 0.98
_NEUTRAL = 0.5


def apply_decay(profiles: dict[str, CapabilityProfile]) -> None:
    now = time.time()
    for profile in profiles.values():
        days = (now - profile.last_updated) / 86400
        if days < 1:
            continue
        factor = _DECAY_PER_DAY ** days
        profile.accuracy_by_type = {
            k: round(_NEUTRAL + (v - _NEUTRAL) * factor, 3)
            for k, v in profile.accuracy_by_type.items()
        }


def load_profiles(path: Path = _DEFAULT_PATH) -> dict[str, CapabilityProfile]:
    data = json.loads(path.read_text())
    profiles = {}
    for k, v in data.items():
        if "last_updated" not in v:
            v["last_updated"] = time.time()
        profiles[k] = CapabilityProfile(**v)
    apply_decay(profiles)
    return profiles


def save_profiles(profiles: dict[str, CapabilityProfile], path: Path = _DEFAULT_PATH) -> None:
    data = {k: vars(v) for k, v in profiles.items()}
    path.write_text(json.dumps(data, indent=2))


def update_accuracy(
    profiles: dict[str, CapabilityProfile],
    agent: str,
    task_type: str,
    score: int,
) -> None:
    profile = profiles[agent]
    current = profile.accuracy_by_type.get(task_type, score / 100)
    profile.accuracy_by_type[task_type] = round(current * 0.7 + (score / 100) * 0.3, 3)
    profile.last_updated = time.time()
