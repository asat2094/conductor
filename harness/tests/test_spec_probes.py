from harness.spec_probes import edge_probe, prohibition_probe, annotate_brief, EDGE_CATEGORIES


def test_edge_probe_covers_all_categories():
    crit = edge_probe({"goal": "parse orders"})
    assert len(crit) == len(EDGE_CATEGORIES)
    assert any("boundary" in c.lower() for c in crit)
    assert any("parse orders" in c for c in crit)


def test_edge_probe_uses_injected_prober():
    crit = edge_probe({"goal": "g"}, prober=lambda b, cats: ["custom edge 1", "custom edge 2"])
    assert crit == ["custom edge 1", "custom edge 2"]


def test_prohibition_probe_returns_must_nots():
    p = prohibition_probe({"goal": "transfer funds"})
    assert isinstance(p, list) and len(p) >= 1
    assert any("must not" in x.lower() for x in p)


def test_annotate_brief_is_advisory_and_pure():
    brief = {"id": "u1", "goal": "parse orders"}
    out = annotate_brief(brief)
    assert "candidate_criteria" not in brief          # input not mutated
    assert "edges" in out["candidate_criteria"]
    assert "prohibitions" in out["candidate_criteria"]
    assert out["candidate_criteria"]["dismissed"] == []
    assert out["id"] == "u1"                            # original fields preserved
