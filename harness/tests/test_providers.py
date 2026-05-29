import json
import pytest
from harness.models import ProviderConfig


def test_provider_config_fields():
    p = ProviderConfig(
        name="deepseek",
        type="openai_compat",
        model="deepseek-coder",
        base_url="https://api.deepseek.com/v1",
        cost_per_1k_tokens=0.0014,
        tier="cloud_cheap",
        api_key_env="DEEPSEEK_API_KEY",
    )
    assert p.name == "deepseek"
    assert p.api_key_env == "DEEPSEEK_API_KEY"


def test_provider_config_api_key_env_defaults_empty():
    p = ProviderConfig("gemma4", "ollama", "gemma4:latest", "http://localhost:11434", 0.0, "local")
    assert p.api_key_env == ""


def test_load_providers_returns_all_entries(tmp_path):
    from harness.providers import load_providers
    cfg = tmp_path / "providers.json"
    cfg.write_text(json.dumps({
        "gemma4": {"type": "ollama", "model": "gemma4:latest",
                   "base_url": "http://localhost:11434", "cost_per_1k_tokens": 0.0, "tier": "local"},
        "deepseek": {"type": "openai_compat", "model": "deepseek-coder",
                     "base_url": "https://api.deepseek.com/v1", "cost_per_1k_tokens": 0.0014,
                     "tier": "cloud_cheap", "api_key_env": "DEEPSEEK_API_KEY"},
    }))
    providers = load_providers(cfg)
    assert set(providers.keys()) == {"gemma4", "deepseek"}
    assert providers["gemma4"].type == "ollama"
    assert providers["deepseek"].api_key_env == "DEEPSEEK_API_KEY"


def test_load_providers_sets_name_from_key(tmp_path):
    from harness.providers import load_providers
    cfg = tmp_path / "providers.json"
    cfg.write_text(json.dumps({
        "nim": {"type": "openai_compat", "model": "nvidia/llama3", "base_url": "http://x",
                "cost_per_1k_tokens": 0.001, "tier": "cloud_cheap"}
    }))
    providers = load_providers(cfg)
    assert providers["nim"].name == "nim"


def test_load_providers_strips_underscore_keys(tmp_path):
    from harness.providers import load_providers
    cfg = tmp_path / "providers.json"
    cfg.write_text(json.dumps({
        "test": {"type": "openai_compat", "model": "m", "base_url": "http://x",
                 "cost_per_1k_tokens": 0.1, "tier": "cloud_cheap",
                 "_note": "should be ignored"}
    }))
    providers = load_providers(cfg)
    assert "test" in providers  # no crash from _note field
