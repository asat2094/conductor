from harness.style_gate import style_gate


class _Adapter:
    def __init__(self, lint=None, fmt=None):
        self._lint = lint
        self._fmt = fmt

    def lint_cmd(self, files):
        return self._lint

    def format_check_cmd(self, files):
        return self._fmt


def test_no_tooling_skips_clean():
    passed, ev, status = style_gate(_Adapter(), ["x.py"], ".", runner=lambda c, w: (0, ""))
    assert passed is True and status == "no-style-tooling"


def test_lint_pass_and_format_pass():
    a = _Adapter(lint="ruff check x.py", fmt="black --check x.py")
    passed, ev, status = style_gate(a, ["x.py"], ".", runner=lambda c, w: (0, "ok"))
    assert passed is True and status == "checked"


def test_lint_failure_fails_gate_with_evidence():
    a = _Adapter(lint="ruff check x.py")
    def runner(c, w):
        return (1, "x.py:3 E501 line too long")
    passed, ev, status = style_gate(a, ["x.py"], ".", runner=runner)
    assert passed is False
    assert "E501" in ev or "ruff" in ev.lower()


def test_format_failure_fails_gate():
    a = _Adapter(fmt="black --check x.py")
    def runner(c, w):
        return (1, "would reformat x.py")
    passed, ev, status = style_gate(a, ["x.py"], ".", runner=runner)
    assert passed is False


def test_only_one_tool_present():
    a = _Adapter(lint="eslint a.js")   # format None
    passed, ev, status = style_gate(a, ["a.js"], ".", runner=lambda c, w: (0, ""))
    assert passed is True and status == "checked"
