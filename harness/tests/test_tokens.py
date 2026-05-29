from harness.tokens import estimate_tokens


def test_empty_list():
    assert estimate_tokens([], ".") == 0


def test_missing_file(tmp_path):
    assert estimate_tokens(["nonexistent.py"], str(tmp_path)) == 0


def test_existing_file(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("x" * 400)  # 400 chars → 100 tokens
    assert estimate_tokens(["code.py"], str(tmp_path)) == 100


def test_multiple_files(tmp_path):
    (tmp_path / "a.py").write_text("x" * 400)
    (tmp_path / "b.py").write_text("x" * 800)
    result = estimate_tokens(["a.py", "b.py"], str(tmp_path))
    assert result == 300  # 100 + 200


def test_missing_file_skipped(tmp_path):
    (tmp_path / "a.py").write_text("x" * 400)
    result = estimate_tokens(["a.py", "missing.py"], str(tmp_path))
    assert result == 100
