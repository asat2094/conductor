"""
Graders — the mechanical rating primitives (evalkit, ADR-0042).

A Grader turns one model output into an OBJECTIVE 0-100 score. Every built-in is
deterministic: syntax via the production LanguageAdapter (ADR-0035, language-agnostic),
keyword presence, or a held-out oracle command. NO model judges output (Law 1/2) — the
same mechanical basis the live gate uses, so calibration measures what production decides on.

Graders are attached to EvalTasks; CompositeGrader weights several into one score.
"""
from typing import Callable, Optional, Protocol, runtime_checkable

# language -> source extension for the syntax check's temp file
_EXT = {"python": ".py", "javascript": ".js", "typescript": ".ts", "go": ".go"}


@runtime_checkable
class Grader(Protocol):
    def grade(self, output: str, task: "object") -> int:
        """Return an objective score in [0, 100] for `output` against `task`."""
        ...


class SyntaxGrader:
    """100 iff the output parses in the task's language, else 0. Empty output -> 0 (a refusal).
    Delegates to LanguageAdapter.check_syntax via a temp file (reuses the production oracle)."""

    def __init__(self, *, syntax_check: Optional[Callable[[str, str], bool]] = None):
        self._check = syntax_check or _default_syntax_check

    def grade(self, output: str, task) -> int:
        if not output or not output.strip():
            return 0
        return 100 if self._check(output, getattr(task, "language", "python")) else 0


class KeywordGrader:
    """Fraction of required keywords present, scaled to 100. Cheap presence check
    (e.g. the function name a code_gen task must define)."""

    def __init__(self, keywords: list[str]):
        self.keywords = keywords

    def grade(self, output: str, task) -> int:
        if not self.keywords:
            return 100
        hits = sum(1 for k in self.keywords if k in (output or ""))
        return round(100 * hits / len(self.keywords))


class OracleGrader:
    """100 iff a held-out assertion command passes against the output, else 0 (the strongest,
    'does it actually work' signal). Writes output to a temp file and runs `cmd_for(path)`;
    rc == 0 -> pass. Runner injectable so tests need no subprocess. Empty output -> 0."""

    def __init__(self, cmd_for: Callable[[str], str], *,
                 runner: Optional[Callable[[str], int]] = None, ext: str = ".py"):
        self.cmd_for = cmd_for
        self.ext = ext
        self._run = runner or _default_cmd_runner

    def grade(self, output: str, task) -> int:
        if not output or not output.strip():
            return 0
        import tempfile
        import os
        fd, path = tempfile.mkstemp(suffix=self.ext)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(output)
            return 100 if self._run(self.cmd_for(path)) == 0 else 0
        finally:
            os.unlink(path)


class GatedGrader:
    """A hard prerequisite gate + a soft scorer: if `gate` scores 0, the result is 0; otherwise
    return `scorer`'s score. Use when a signal must not partially offset a failed prerequisite
    (e.g. syntax must hold before a keyword match counts) — unlike CompositeGrader's average."""

    def __init__(self, gate: "Grader", scorer: "Grader"):
        self.gate = gate
        self.scorer = scorer

    def grade(self, output: str, task) -> int:
        return self.scorer.grade(output, task) if self.gate.grade(output, task) > 0 else 0


class CompositeGrader:
    """Weighted average of sub-graders -> one 0-100 score. Weights need not sum to 1
    (normalized internally). This is how a task combines syntax + keyword/oracle signals."""

    def __init__(self, graded: list[tuple[Grader, float]]):
        self.graded = graded

    def grade(self, output: str, task) -> int:
        total_w = sum(w for _, w in self.graded) or 1.0
        return round(sum(g.grade(output, task) * w for g, w in self.graded) / total_w)


# --- default mechanical IO (injectable above) ------------------------------------------------

def _default_syntax_check(output: str, language: str) -> bool:
    import tempfile
    import os
    from harness.lang.base import resolve
    adapter = resolve(language)
    fd, path = tempfile.mkstemp(suffix=_EXT.get(language, ".txt"))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(output)
        return adapter.check_syntax(path)
    finally:
        os.unlink(path)


def _default_cmd_runner(cmd: str) -> int:
    import subprocess
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, timeout=60).returncode
    except Exception:
        return 1
