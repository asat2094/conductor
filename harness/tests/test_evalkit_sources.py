"""Source-payload resolution (absorbed from the removed gemma4-bench)."""
import os
from harness.evalkit import resolve_sources, default_suite


def test_resolve_sources_env_override(tmp_path, monkeypatch):
    f = tmp_path / "sample.py"
    f.write_text("def x():\n    return 1\n")
    monkeypatch.setenv("EVALKIT_SOURCES", str(f))
    sources = resolve_sources()
    assert any("def x()" in s for s in sources)


def test_resolve_sources_candidates(tmp_path, monkeypatch):
    monkeypatch.delenv("EVALKIT_SOURCES", raising=False)
    f = tmp_path / "a.py"
    f.write_text("CONTENT_MARKER = 1\n")
    assert any("CONTENT_MARKER" in s for s in resolve_sources([str(f)]))


def test_resolve_sources_empty_when_none(monkeypatch):
    monkeypatch.delenv("EVALKIT_SOURCES", raising=False)
    assert resolve_sources(candidates=[]) == []          # -> caller uses synthetic fallback


def test_default_suite_uses_real_sources_in_payload():
    suite = default_suite(context_sizes=[1000], task_types=["code_gen"],
                          sources=["def REAL_SOURCE_FN():\n    return 42\n"])
    assert "REAL_SOURCE_FN" in suite.tasks[0].prompt


def test_default_suite_synthetic_when_no_sources():
    suite = default_suite(context_sizes=[1000], task_types=["code_gen"])
    assert len(suite.tasks[0].prompt) > 1000             # portable synthetic filler still works
