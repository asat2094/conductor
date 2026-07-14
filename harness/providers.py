import json
from pathlib import Path

from harness.models import ProviderConfig

_DEFAULT_PATH = Path(__file__).parent / "providers.json"


def load_providers(path: Path = _DEFAULT_PATH) -> dict[str, ProviderConfig]:
    data = json.loads(path.read_text())
    result = {}
    for name, cfg in data.items():
        clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
        result[name] = ProviderConfig(name=name, **clean)
    return result
