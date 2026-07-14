from harness.lang.javascript_adapter import JavaScriptAdapter
from harness.lang.base import LanguageAdapter, resolve


def test_is_language_adapter():
    assert isinstance(JavaScriptAdapter(), LanguageAdapter)


def test_registered():
    assert resolve("javascript").name == "javascript"


def test_extensions_cover_ts_and_js():
    exts = JavaScriptAdapter().extensions
    assert ".js" in exts and ".ts" in exts and ".tsx" in exts


def test_is_test_file():
    a = JavaScriptAdapter()
    assert a.is_test_file("foo.test.js") is True
    assert a.is_test_file("foo.spec.ts") is True
    assert a.is_test_file("foo.js") is False


def test_discover_test_cmd():
    a = JavaScriptAdapter()
    assert a.discover_test_cmd(["a.js", "a.test.js"]) == "npm test"
    assert a.discover_test_cmd(["a.js"]) is None


def test_extract_signatures_regex():
    src = "export function parse(x){}\nconst run = (a) => a\nclass Engine {}\n"
    sigs = JavaScriptAdapter().extract_signatures_text(src)
    joined = " ".join(sigs)
    assert "parse" in joined and "Engine" in joined


def test_mutate_flips_strict_equality():
    muts = JavaScriptAdapter().mutate("if (a === b) return true;")
    assert any("!==" in m for _, m in muts)


def test_mutate_distinct():
    muts = JavaScriptAdapter().mutate("x === 1 && y < 2")
    srcs = [m for _, m in muts]
    assert len(srcs) == len(set(srcs)) and all(s != "x === 1 && y < 2" for s in srcs)


def test_lint_and_format():
    a = JavaScriptAdapter()
    assert "eslint" in a.lint_cmd(["a.js"])
    assert "prettier" in a.format_check_cmd(["a.js"])


def test_verify_dependency_invalid():
    assert JavaScriptAdapter().verify_dependency("bad name!") == "invalid"
    assert JavaScriptAdapter().verify_dependency("react") == "unverified"


def test_run_tests_injected_runner():
    a = JavaScriptAdapter()
    rc, out = a.run_tests("npm test", ".", runner=lambda c, w: (0, "ok"))
    assert rc == 0
