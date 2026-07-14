from harness.lang.python_adapter import PythonAdapter
from harness.lang.base import LanguageAdapter, resolve


def test_is_language_adapter():
    assert isinstance(PythonAdapter(), LanguageAdapter)


def test_registered_as_python():
    assert resolve("python").name == "python"


def test_check_syntax_valid(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("def f():\n    return 1\n")
    assert PythonAdapter().check_syntax(str(f)) is True


def test_check_syntax_invalid(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def f(:\n")
    assert PythonAdapter().check_syntax(str(f)) is False


def test_check_syntax_non_python_file():
    # Non-.py file should not block
    assert PythonAdapter().check_syntax("readme.md") is True


def test_check_syntax_missing_file():
    # Missing file should not block
    assert PythonAdapter().check_syntax("/nonexistent/file.py") is True


def test_is_test_file():
    a = PythonAdapter()
    assert a.is_test_file("tests/test_x.py") is True
    assert a.is_test_file("test_x.py") is True
    assert a.is_test_file("x_test.py") is True
    assert a.is_test_file("x.py") is False


def test_discover_test_cmd():
    a = PythonAdapter()
    cmd = a.discover_test_cmd(["x.py", "test_x.py"])
    assert cmd is not None
    assert "pytest" in cmd
    assert "test_x.py" in cmd


def test_discover_test_cmd_no_tests():
    a = PythonAdapter()
    assert a.discover_test_cmd(["x.py"]) is None


def test_discover_test_cmd_multiple_tests():
    a = PythonAdapter()
    cmd = a.discover_test_cmd(["test_a.py", "test_b.py", "x.py"])
    assert cmd is not None
    assert "test_a.py" in cmd
    assert "test_b.py" in cmd


def test_run_tests_uses_injected_runner():
    a = PythonAdapter()
    rc, out = a.run_tests("pytest", ".", runner=lambda cmd, wd: (0, "passed"))
    assert rc == 0 and "passed" in out


def test_run_tests_default_runner(tmp_path):
    # Create a simple test file
    test_file = tmp_path / "test_simple.py"
    test_file.write_text("def test_ok():\n    assert True\n")

    a = PythonAdapter()
    rc, out = a.run_tests("python3 -m pytest test_simple.py -q", str(tmp_path))
    # Should succeed or fail gracefully
    assert isinstance(rc, int)
    assert isinstance(out, str)


def test_extract_signatures(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def foo(a, b):\n    return a\n\nclass Bar:\n    pass\n")
    sigs = PythonAdapter().extract_signatures(str(f))
    assert any("foo" in s for s in sigs)
    assert any("Bar" in s for s in sigs)


def test_extract_signatures_with_methods(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("class MyClass:\n    def method(self):\n        pass\n\ndef standalone():\n    pass\n")
    sigs = PythonAdapter().extract_signatures(str(f))
    # Should extract top-level def and class
    assert any("standalone" in s for s in sigs)
    assert any("MyClass" in s for s in sigs)


def test_extract_signatures_empty_file(tmp_path):
    f = tmp_path / "empty.py"
    f.write_text("")
    sigs = PythonAdapter().extract_signatures(str(f))
    assert sigs == []


def test_extract_signatures_syntax_error(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def f(:\n")
    sigs = PythonAdapter().extract_signatures(str(f))
    assert sigs == []


def test_mutate_delegates():
    muts = PythonAdapter().mutate("def f(x):\n    return x == 1\n")
    assert isinstance(muts, list)
    assert len(muts) >= 1


def test_mutate_returns_tuples():
    muts = PythonAdapter().mutate("def f(x):\n    return x == 1\n")
    for mut in muts:
        assert isinstance(mut, tuple)
        assert len(mut) == 2
        assert isinstance(mut[0], str)  # operator name
        assert isinstance(mut[1], str)  # mutated source


def test_lint_cmd():
    a = PythonAdapter()
    cmd = a.lint_cmd(["x.py"])
    assert cmd is not None
    assert "ruff" in cmd
    assert "x.py" in cmd


def test_lint_cmd_multiple_files():
    a = PythonAdapter()
    cmd = a.lint_cmd(["x.py", "y.py"])
    assert cmd is not None
    assert "ruff" in cmd
    assert "x.py" in cmd
    assert "y.py" in cmd


def test_format_check_cmd():
    a = PythonAdapter()
    cmd = a.format_check_cmd(["x.py"])
    assert cmd is not None
    assert "black" in cmd
    assert "x.py" in cmd


def test_format_check_cmd_multiple_files():
    a = PythonAdapter()
    cmd = a.format_check_cmd(["x.py", "y.py"])
    assert cmd is not None
    assert "black" in cmd
    assert "x.py" in cmd
    assert "y.py" in cmd


def test_verify_dependency_valid():
    a = PythonAdapter()
    # Should delegate to deps_check and return a status
    result = a.verify_dependency("requests")
    assert result in ["ok", "unresolvable", "unverified", "invalid"]


def test_verify_dependency_invalid_name():
    a = PythonAdapter()
    # Invalid name should short-circuit without network call
    result = a.verify_dependency("foo/bar")
    assert result == "invalid"


def test_verify_dependency_delegates():
    # Test that verify_dependency rejects invalid names without network
    result = PythonAdapter().verify_dependency("../evil")
    assert result == "invalid"


def test_name_property():
    a = PythonAdapter()
    assert a.name == "python"


def test_extensions_property():
    a = PythonAdapter()
    assert a.extensions == (".py",)
