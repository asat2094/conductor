from harness.verify import verify_decomposition, VerifyReport


def _b(uid, produces=None, consumes=None, files=None):
    return {"id": uid, "files": files or [], "writes_files": files or [],
            "contract": {"produces": produces or [], "consumes": consumes or []}}


def test_clean_when_no_codegraph_returns_unverified():
    briefs = [_b("a", produces=["x"]), _b("b", consumes=["x"])]
    rep = verify_decomposition(briefs, edges=None)
    assert rep.status == "unverified"
    assert rep.errors == []


def test_under_declared_edge_is_flagged_when_codegraph_present():
    briefs = [_b("a", produces=["x"], files=["a.py"]), _b("b", consumes=[], files=["b.py"])]
    edges = {"b.py": ["x"]}
    rep = verify_decomposition(briefs, edges=edges)
    assert rep.status == "verified"
    assert any("b" in e and "x" in e for e in rep.warnings + rep.errors)


def test_over_declared_consume_is_a_warning():
    briefs = [_b("a", produces=["x"], files=["a.py"]), _b("b", consumes=["x"], files=["b.py"])]
    edges = {"b.py": []}
    rep = verify_decomposition(briefs, edges=edges)
    assert any("over-declared" in w.lower() and "x" in w for w in rep.warnings)


def test_coverage_metric_present():
    briefs = [_b("a", produces=["x"], files=["a.py"]), _b("b", consumes=["x"], files=["b.py"])]
    edges = {"b.py": ["x"]}
    rep = verify_decomposition(briefs, edges=edges)
    assert 0.0 <= rep.coverage <= 1.0


def test_density_signal_flags_dense_graph():
    briefs = [
        _b("a", produces=["pa"], consumes=["pb", "pc"]),
        _b("b", produces=["pb"], consumes=["pa", "pc"]),
        _b("c", produces=["pc"], consumes=["pa", "pb"]),
    ]
    rep = verify_decomposition(briefs, edges=None)
    assert rep.dense is True
