from types import SimpleNamespace
from harness.evalkit.graders import (
    SyntaxGrader, KeywordGrader, OracleGrader, CompositeGrader, Grader,
)


def _task(language="python"):
    return SimpleNamespace(language=language, task_type="code_gen")


def test_syntax_grader_valid_python():
    g = SyntaxGrader()
    assert g.grade("def f():\n    return 1\n", _task()) == 100


def test_syntax_grader_invalid_python():
    g = SyntaxGrader()
    assert g.grade("def f(:\n  return\n", _task()) == 0


def test_syntax_grader_empty_is_zero():
    assert SyntaxGrader().grade("   ", _task()) == 0


def test_syntax_grader_language_agnostic_via_injection():
    # injected check ignores language -> proves grader doesn't hardcode Python
    g = SyntaxGrader(syntax_check=lambda out, lang: lang == "rust")
    assert g.grade("fn main(){}", _task(language="rust")) == 100
    assert g.grade("fn main(){}", _task(language="python")) == 0


def test_keyword_grader_fraction():
    g = KeywordGrader(["validate_input", "def"])
    assert g.grade("def validate_input(d): pass", _task()) == 100
    assert g.grade("def other(): pass", _task()) == 50
    assert g.grade("nothing", _task()) == 0


def test_keyword_grader_empty_keywords_is_full():
    assert KeywordGrader([]).grade("anything", _task()) == 100


def test_oracle_grader_pass_and_fail():
    g = OracleGrader(cmd_for=lambda p: f"check {p}", runner=lambda cmd: 0)
    assert g.grade("code", _task()) == 100
    g_fail = OracleGrader(cmd_for=lambda p: f"check {p}", runner=lambda cmd: 1)
    assert g_fail.grade("code", _task()) == 0


def test_oracle_grader_empty_is_zero_without_running():
    calls = []
    g = OracleGrader(cmd_for=lambda p: "x", runner=lambda cmd: calls.append(cmd) or 0)
    assert g.grade("", _task()) == 0
    assert calls == []


def test_composite_weighted_average():
    hi = SimpleNamespace(grade=lambda o, t: 100)
    lo = SimpleNamespace(grade=lambda o, t: 0)
    g = CompositeGrader([(hi, 3.0), (lo, 1.0)])
    assert g.grade("x", _task()) == 75      # (100*3 + 0*1)/4


def test_builtins_satisfy_grader_protocol():
    assert isinstance(SyntaxGrader(), Grader)
    assert isinstance(KeywordGrader(["x"]), Grader)


# --- GatedGrader (syntax gates keyword) ---

def test_gated_grader_zero_when_gate_fails():
    from harness.evalkit.graders import GatedGrader
    gate = SimpleNamespace(grade=lambda o, t: 0)
    scorer = SimpleNamespace(grade=lambda o, t: 100)
    assert GatedGrader(gate, scorer).grade("x", _task()) == 0


def test_gated_grader_scorer_when_gate_passes():
    from harness.evalkit.graders import GatedGrader
    gate = SimpleNamespace(grade=lambda o, t: 100)
    scorer = SimpleNamespace(grade=lambda o, t: 60)
    assert GatedGrader(gate, scorer).grade("x", _task()) == 60


def test_gated_syntax_blocks_keyword_on_invalid_code():
    from harness.evalkit.graders import GatedGrader
    g = GatedGrader(SyntaxGrader(), KeywordGrader(["validate_input"]))
    # keyword present BUT syntax broken -> 0, not a partial score
    assert g.grade("def validate_input(d)\n  return notclosed(", _task()) == 0
    assert g.grade("def validate_input(d):\n    return 1\n", _task()) == 100
