from harness.codegraph_adapter import dependency_edges


def test_returns_empty_when_no_query_fn():
    assert dependency_edges(["a.py"], ".", query_fn=None) == {}


def test_uses_query_fn_when_provided():
    def fake(files, workdir):
        return {"foo": ["bar"]}
    assert dependency_edges(["a.py"], ".", query_fn=fake) == {"foo": ["bar"]}


def test_degrades_to_empty_on_query_error():
    def boom(files, workdir):
        raise RuntimeError("MCP down")
    assert dependency_edges(["a.py"], ".", query_fn=boom) == {}
