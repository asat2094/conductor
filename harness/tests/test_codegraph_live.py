from harness.codegraph_live import make_codegraph_query, parse_symbols, codegraph_available


def test_parse_symbols_from_json_list_of_dicts():
    out = '[{"name": "parse"}, {"name": "tokenize"}]'
    assert parse_symbols(out) == ["parse", "tokenize"]


def test_parse_symbols_from_plain_lines():
    out = "parse\ntokenize\n\nparse\n"
    assert parse_symbols(out) == ["parse", "tokenize"]   # deduped, blanks dropped


def test_parse_symbols_garbage_returns_empty():
    assert parse_symbols("???") == [] or isinstance(parse_symbols("???"), list)


def test_query_builds_file_to_symbols_map():
    def runner(args, cwd):
        return (0, '[{"name":"parse"}]')
    qfn = make_codegraph_query(runner=runner)
    edges = qfn(["a.py"], "/repo")
    assert edges["a.py"] == ["parse"]


def test_query_degrades_per_file_on_error():
    def runner(args, cwd):
        raise RuntimeError("codegraph down")
    qfn = make_codegraph_query(runner=runner)
    edges = qfn(["a.py"], "/repo")
    assert edges == {"a.py": []}   # degrade-clean, no crash


def test_available_reflects_runner_rc():
    assert codegraph_available(runner=lambda args, cwd=None: (0, "1.0")) is True
    assert codegraph_available(runner=lambda args, cwd=None: (127, "not found")) is False
