import importlib.util
from pathlib import Path

BENCH = Path(__file__).resolve().parents[2] / "gemma4-bench" / "bench.py"


def _load_bench():
    spec = importlib.util.spec_from_file_location("bench", BENCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_no_hardcoded_foreign_paths():
    text = BENCH.read_text()
    assert "/Users/ankitatiwari" not in text


def test_resolve_sources_env_override(tmp_path, monkeypatch):
    f = tmp_path / "sample.py"
    f.write_text("def x():\n    return 1\n")
    monkeypatch.setenv("CONDUCTOR_BENCH_SOURCES", str(f))
    mod = _load_bench()
    sources = mod.resolve_sources()
    assert any("def x()" in s for s in sources)


def test_resolve_sources_falls_back_to_synthetic(monkeypatch):
    monkeypatch.delenv("CONDUCTOR_BENCH_SOURCES", raising=False)
    mod = _load_bench()
    sources = mod.resolve_sources(candidates=[])  # no real files
    assert sources and all(isinstance(s, str) for s in sources)
