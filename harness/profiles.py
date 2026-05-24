import json
from pathlib import Path
from harness.models import CapabilityProfile

_DEFAULT_PATH = Path(__file__).parent / "capability_profiles.json"


def load_profiles(path: Path = _DEFAULT_PATH) -> dict[str, CapabilityProfile]:
    data = json.loads(path.read_text())
    return {k: CapabilityProfile(**v) for k, v in data.items()}


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
