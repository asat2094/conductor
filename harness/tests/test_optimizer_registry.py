import pytest
from harness.optimizer import registry
from harness.optimizer.base import OptimizeConfig


class _Null:
    name = "null"
    def available(self): return True
    def optimize(self, messages, cfg): return None
    def retrieve(self, handle): return None


class _FakeUnavailable:
    name = "fake"
    def available(self): return False
    def optimize(self, messages, cfg): raise AssertionError("must not be called")
    def retrieve(self, handle): return None


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(registry._BACKENDS)
    registry._BACKENDS.clear()
    registry.register("null", lambda: _Null())
    yield
    registry._BACKENDS.clear()
    registry._BACKENDS.update(saved)


def test_resolve_returns_registered_available_backend():
    registry.register("x", lambda: _Null())
    assert registry.resolve("x").name == "null"


def test_resolve_unknown_name_degrades_to_null():
    assert registry.resolve("does_not_exist").name == "null"


def test_resolve_unavailable_backend_degrades_to_null():
    registry.register("fake", lambda: _FakeUnavailable())
    assert registry.resolve("fake").name == "null"


def test_env_override_wins(monkeypatch):
    registry.register("fake", lambda: _FakeUnavailable())
    monkeypatch.setenv("CONDUCTOR_OPTIMIZER", "fake")
    assert registry.resolve_from_config(OptimizeConfig(backend="x")).name == "null"
