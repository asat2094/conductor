from harness.tokens import estimate_tokens, _EXT_MULTIPLIER


def test_empty_list():
    assert estimate_tokens([], ".") == 0


def test_missing_file(tmp_path):
    assert estimate_tokens(["nonexistent.py"], str(tmp_path)) == 0


def test_py_baseline(tmp_path):
    (tmp_path / "code.py").write_text("x" * 400)  # 400 chars, mult=1.0 → 100 tokens
    assert estimate_tokens(["code.py"], str(tmp_path)) == 100


def test_multiple_files(tmp_path):
    (tmp_path / "a.py").write_text("x" * 400)
    (tmp_path / "b.py").write_text("x" * 800)
    assert estimate_tokens(["a.py", "b.py"], str(tmp_path)) == 300  # 100 + 200


def test_missing_file_skipped(tmp_path):
    (tmp_path / "a.py").write_text("x" * 400)
    assert estimate_tokens(["a.py", "missing.py"], str(tmp_path)) == 100


def test_json_multiplier_higher(tmp_path):
    content = "x" * 400
    (tmp_path / "data.json").write_text(content)
    (tmp_path / "code.py").write_text(content)
    json_tokens = estimate_tokens(["data.json"], str(tmp_path))
    py_tokens = estimate_tokens(["code.py"], str(tmp_path))
    assert json_tokens > py_tokens  # JSON mult=1.4 vs py mult=1.0


def test_md_multiplier_lower(tmp_path):
    content = "x" * 400
    (tmp_path / "README.md").write_text(content)
    (tmp_path / "code.py").write_text(content)
    md_tokens = estimate_tokens(["README.md"], str(tmp_path))
    py_tokens = estimate_tokens(["code.py"], str(tmp_path))
    assert md_tokens < py_tokens  # markdown mult=0.8 vs py mult=1.0


def test_yaml_multiplier(tmp_path):
    (tmp_path / "config.yaml").write_text("x" * 400)
    result = estimate_tokens(["config.yaml"], str(tmp_path))
    expected = int(400 / 4 * _EXT_MULTIPLIER[".yaml"])
    assert result == expected


def test_unknown_extension_uses_default(tmp_path):
    (tmp_path / "data.avro").write_text("x" * 400)
    result = estimate_tokens(["data.avro"], str(tmp_path))
    assert result == 100  # default mult=1.0
