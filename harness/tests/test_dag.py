import pytest
from harness.dag import build_edges, topo_waves, writes_overlap, DagCycleError


def _b(uid, produces=None, consumes=None, logical_deps=None, writes=None):
    return {
        "id": uid,
        "contract": {"produces": produces or [], "consumes": consumes or []},
        "logical_deps": logical_deps or [],
        "writes_files": writes or [],
    }


def test_build_edges_links_consumer_to_producer():
    briefs = [_b("a", produces=["sym"]), _b("b", consumes=["sym"])]
    deps = build_edges(briefs)
    assert deps["b"] == {"a"}
    assert deps["a"] == set()


def test_build_edges_includes_logical_deps():
    briefs = [_b("a"), _b("b", logical_deps=["a"])]
    deps = build_edges(briefs)
    assert deps["b"] == {"a"}


def test_build_edges_ignores_self_produced_symbol():
    briefs = [_b("a", produces=["sym"], consumes=["sym"])]
    assert build_edges(briefs)["a"] == set()


def test_topo_waves_orders_producer_before_consumer():
    briefs = [_b("b", consumes=["sym"]), _b("a", produces=["sym"])]
    waves = topo_waves(build_edges(briefs))
    assert waves == [["a"], ["b"]]


def test_topo_waves_groups_independent_units_in_one_wave():
    briefs = [_b("a"), _b("b")]
    waves = topo_waves(build_edges(briefs))
    assert len(waves) == 1
    assert sorted(waves[0]) == ["a", "b"]


def test_topo_waves_raises_on_cycle():
    briefs = [_b("a", produces=["x"], consumes=["y"]), _b("b", produces=["y"], consumes=["x"])]
    with pytest.raises(DagCycleError):
        topo_waves(build_edges(briefs))


def test_writes_overlap_detects_shared_file():
    assert writes_overlap(_b("a", writes=["f.py"]), _b("b", writes=["f.py"])) is True
    assert writes_overlap(_b("a", writes=["f.py"]), _b("b", writes=["g.py"])) is False
