"""
Eval tasks & suites (evalkit, ADR-0042).

An EvalTask is one bounded prompt + a mechanical grader + the context size it probes.
An EvalSuite is a named collection; every task carries an `origin` ("builtin" | "custom")
so the report can break results out by suite. default_suite() ships the standard grid;
load_suite() ingests a user's own JSON — both feed the same runner and report.
"""
import json
from dataclasses import dataclass, field
from typing import Any

from harness.evalkit.graders import (
    Grader, SyntaxGrader, KeywordGrader, OracleGrader, CompositeGrader, GatedGrader,
)

DEFAULT_CONTEXT_SIZES = [1000, 4000, 8000, 16000, 32000]

_KEYWORDS = {
    "code_edit": ['"""'],           # a docstring was added
    "code_gen": ["def validate_input"],
    "test_write": ["def test_"],
}
_INSTRUCTION = {
    "code_edit": "Add a Google-style docstring to the first function. Output ONLY the modified "
                 "function in a single ```python block.",
    "code_gen": "Write a standalone function `validate_input(d)` that returns whether dict d has a "
                "'symbol' key. Output ONLY the function in a single ```python block.",
    "test_write": "Write one pytest test for any function above. Output ONLY the test in a single "
                  "```python block.",
}


@dataclass
class EvalTask:
    id: str
    task_type: str
    language: str
    prompt: str
    grader: Grader
    context_tokens: int
    origin: str = "builtin"


@dataclass
class EvalSuite:
    name: str
    tasks: list[EvalTask] = field(default_factory=list)

    def __iter__(self):
        return iter(self.tasks)

    def __len__(self):
        return len(self.tasks)


def _synthetic_payload(target_tokens: int) -> str:
    """Portable filler (~4 chars/token) — no dependency on any host repo, so the default
    suite runs anywhere."""
    unit = "def helper_%d(x):\n    return x * 2  # sample context line\n\n"
    target_chars = target_tokens * 4
    out, i = [], 0
    n = 0
    while n < target_chars:
        s = unit % i
        out.append(s)
        n += len(s)
        i += 1
    return "".join(out)[:target_chars]


def default_suite(*, language: str = "python",
                  context_sizes: list[int] | None = None,
                  task_types: list[str] | None = None) -> EvalSuite:
    """The standard capability grid: task_type x context_size, each graded by
    SyntaxGrader (language-agnostic) + a task KeywordGrader."""
    sizes = context_sizes or DEFAULT_CONTEXT_SIZES
    types = task_types or list(_INSTRUCTION)
    tasks = []
    for ttype in types:
        for size in sizes:
            payload = _synthetic_payload(size)
            # Syntax GATES the keyword check: invalid code scores 0 even if it contains the
            # expected symbol — a keyword match must not partially offset a parse failure.
            grader = GatedGrader(SyntaxGrader(), KeywordGrader(_KEYWORDS[ttype]))
            tasks.append(EvalTask(
                id=f"{ttype}_{size}", task_type=ttype, language=language,
                prompt=f"Given this code:\n\n{payload}\n\n{_INSTRUCTION[ttype]}",
                grader=grader, context_tokens=size, origin="builtin",
            ))
    return EvalSuite(name="default", tasks=tasks)


def _build_grader(spec: dict) -> Grader:
    """Construct a grader from a JSON spec (bring-your-own suites)."""
    kind = spec.get("type", "syntax")
    if kind == "syntax":
        return SyntaxGrader()
    if kind == "keyword":
        return KeywordGrader(spec["keywords"])
    if kind == "oracle":
        tmpl = spec["cmd"]                       # e.g. "python3 {path} && ..."
        return OracleGrader(cmd_for=lambda p, _t=tmpl: _t.format(path=p),
                            ext=spec.get("ext", ".py"))
    if kind == "composite":
        return CompositeGrader([(_build_grader(s), s.get("weight", 1.0))
                                for s in spec["graders"]])
    raise ValueError(f"unknown grader type {kind!r}")


def load_suite(source: "str | list | dict", *, name: str = "custom") -> EvalSuite:
    """Load a bring-your-own suite from a JSON file path, a parsed list, or a {name, tasks} dict.
    Each task dict: {id, task_type, language, prompt, context_tokens, grader:{...}}.

    SECURITY: an oracle grader's `cmd` runs via shell (harness.evalkit.graders.OracleGrader).
    Suite JSON is a TRUSTED-OPERATOR input — never load a suite from untrusted / PR-submitted
    content, or its cmd is arbitrary code execution."""
    if isinstance(source, str):
        with open(source) as f:
            data = json.load(f)
    else:
        data = source
    if isinstance(data, dict):
        name = data.get("name", name)
        items = data["tasks"]
    else:
        items = data
    tasks = [EvalTask(
        id=t["id"], task_type=t["task_type"], language=t.get("language", "python"),
        prompt=t["prompt"], grader=_build_grader(t.get("grader", {"type": "syntax"})),
        context_tokens=t.get("context_tokens", 0), origin="custom",
    ) for t in items]
    return EvalSuite(name=name, tasks=tasks)
