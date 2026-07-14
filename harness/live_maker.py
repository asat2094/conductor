"""
LiveMaker: turns a model call into written files + an in-loop test result (UnitArtifact).

All IO is injectable (model_caller, file_writer, differ, test_runner) so unit tests
need no real model or subprocess.

Public API
----------
build_prompt(subtask, feedback) -> str
make_live_maker(**kw) -> callable(subtask, workdir, feedback)
class LiveMaker
"""

import os
import subprocess
from typing import Any, Callable, Optional

from harness.model_call import call_model, extract_files
from harness.role_policy import resolve_model
from harness.unit_gate import UnitArtifact


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(subtask: Any, feedback: Optional[str]) -> str:
    """Produce a bounded instruction prompt for the given subtask.

    The prompt states: goal, files in scope, produces/consumes contract, and
    requires output as one or more FILE blocks.  On repair, it appends the
    failure feedback so the model knows what to fix.
    """
    lines = [
        "You are a code-writing assistant.  Output ONLY file blocks — no prose.",
        "",
        f"GOAL: {subtask.description}",
        "",
    ]

    if subtask.files:
        lines.append("FILES IN SCOPE:")
        for f in subtask.files:
            lines.append(f"  - {f}")
        lines.append("")

    produces = getattr(subtask, "produces", [])
    consumes = getattr(subtask, "consumes", [])

    if produces:
        lines.append("PRODUCES (must be present in output):")
        for p in produces:
            lines.append(f"  - {p}")
        lines.append("")

    if consumes:
        lines.append("CONSUMES (already available, do not redefine):")
        for c in consumes:
            lines.append(f"  - {c}")
        lines.append("")

    lines += [
        "OUTPUT FORMAT — emit exactly this structure for every file you write:",
        "=== FILE: <relative/path> ===",
        "<full file content>",
        "=== END ===",
        "",
        "Do not write anything outside these blocks.",
    ]

    if feedback is not None:
        lines += [
            "",
            "PREVIOUS ATTEMPT FAILED — fix this:",
            str(feedback),
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default IO helpers
# ---------------------------------------------------------------------------

def _default_file_writer(workdir: str, path: str, content: str) -> None:
    """Write content to workdir/path, creating parent dirs as needed."""
    full = os.path.join(workdir, path)
    os.makedirs(os.path.dirname(full) or workdir, exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)


def _default_differ(workdir: str, paths: list[str]) -> str:
    """Run git diff on the given paths inside workdir (best-effort)."""
    if not paths:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", workdir, "diff", "--"] + paths,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout
    except Exception:
        return ""


def _default_test_runner(cmd: str, workdir: str) -> tuple[int, str]:
    """Run cmd in workdir, return (returncode, combined output)."""
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# LiveMaker
# ---------------------------------------------------------------------------

class LiveMaker:
    """Resolve a model, call it, write files, run in-loop tests, return UnitArtifact."""

    def __init__(
        self,
        workdir: str,
        *,
        role: str = "impl_author",
        policy: Optional[dict] = None,
        high_stakes: bool = False,
        model_caller: Optional[Callable] = None,
        file_writer: Optional[Callable] = None,
        differ: Optional[Callable] = None,
        test_runner: Optional[Callable] = None,
        no_test_inconclusive: bool = False,
    ) -> None:
        self.workdir = workdir
        self.role = role
        self.policy = policy
        self.high_stakes = high_stakes
        # ADR-0038: when True, a unit with NO test command reports in_loop_green=None (inconclusive)
        # so the gate routes it to the judge tiebreak instead of auto-passing. Default False keeps the
        # historical "no test = partial credit" behavior.
        self.no_test_inconclusive = no_test_inconclusive

        self._model_caller = model_caller if model_caller is not None else call_model
        self._file_writer = file_writer  # None -> use default below
        self._differ = differ if differ is not None else _default_differ
        self._test_runner = test_runner if test_runner is not None else _default_test_runner

    # ------------------------------------------------------------------

    def _write_file(self, path: str, content: str) -> None:
        if self._file_writer is not None:
            self._file_writer(path, content)
        else:
            _default_file_writer(self.workdir, path, content)

    # ------------------------------------------------------------------

    def make(self, subtask: Any, feedback: Optional[str]) -> UnitArtifact:
        """Core make step: model -> file writes -> diff -> test -> UnitArtifact."""
        # 1. Resolve model spec
        spec = resolve_model(self.role, high_stakes=self.high_stakes, policy=self.policy)

        # 2. Build prompt (+ inject surrounding code so the maker matches local style/idiom, REQ-RM3)
        prompt = build_prompt(subtask, feedback)
        slices = _read_context_slices_impl(self.workdir, subtask)
        if slices:
            prompt += (
                "\n\nEXISTING CODE — match its style, naming, and conventions:\n" + slices
            )

        # 3. Call model
        raw_text = self._model_caller(spec, prompt)

        # 4. Extract FILE blocks and write them — but ONLY files the unit is allowed to write.
        #    A maker that emits a file outside its declared writes_files (e.g. rewriting its own
        #    test) is a scope leak; we drop those writes mechanically (ADR-0011/0013). When the
        #    subtask declares no writes_files, fall back to permitting all (best-effort).
        file_map = extract_files(raw_text)
        allowed = set(getattr(subtask, "writes_files", None) or [])
        changed: list[str] = []
        self.rejected_writes: list[str] = []
        for rel_path, content in file_map.items():
            if allowed and rel_path not in allowed:
                self.rejected_writes.append(rel_path)
                continue
            self._write_file(rel_path, content)
            changed.append(rel_path)

        # 5. Compute diff
        diff_text = self._differ(self.workdir, changed)

        # 6. Determine in-loop test result
        in_loop_green = self._run_in_loop_test(subtask)

        # 7. Build and return UnitArtifact
        return UnitArtifact(
            changed_files=changed,
            diff_text=diff_text,
            task_type=subtask.type.value,
            in_loop_green=in_loop_green,
            oracle_passed=None,
        )

    # ------------------------------------------------------------------

    def _run_in_loop_test(self, subtask: Any) -> Optional[bool]:
        """Determine the in-loop test command and run it.

        Priority (language-agnostic, ADR-0035):
          1. subtask.verify_cmd (if present and truthy)
          2. the per-file LanguageAdapter's discover_test_cmd (pytest / npm test / go test / ...)
          3. No test command found -> True (partial credit) by default, or None (inconclusive,
             ADR-0038) when `no_test_inconclusive` is set — routes the unit to the judge tiebreak.
        """
        verify_cmd: Optional[str] = getattr(subtask, "verify_cmd", None)
        if verify_cmd:
            rc, _ = self._test_runner(verify_cmd, self.workdir)
            return rc == 0

        # Resolve the adapter from the unit's files and ask it how to run the tests — no language
        # branching here; a Python unit gets pytest, a JS unit gets npm test, etc.
        files = list(getattr(subtask, "files", []))
        from harness.lang.base import adapter_for_path
        adapter = adapter_for_path(files[0]) if files else adapter_for_path("")
        cmd = adapter.discover_test_cmd(files, self.workdir)
        if not cmd:
            return None if self.no_test_inconclusive else True  # ADR-0038: None -> judge; else partial credit
        rc, _ = self._test_runner(cmd, self.workdir)
        return rc == 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_live_maker(**kw: Any) -> Callable[[Any, str, Optional[str]], UnitArtifact]:
    """Return a maker(subtask, workdir, feedback) callable compatible with
    harness.process_unit.make_processor.

    A new LiveMaker is constructed per call so workdir is bound at call-time.
    All **kw are forwarded to LiveMaker.__init__ (except workdir).
    """
    def maker(subtask: Any, workdir: str, feedback: Optional[str]) -> UnitArtifact:
        lm = LiveMaker(workdir, **kw)
        return lm.make(subtask, feedback)

    return maker


def _read_context_slices_impl(workdir, subtask):
    """Read the unit's declared context_slices from disk into a 'match this style' block (REQ-RM3).
    Uses harness.retrieve.slice_file. Best-effort: a missing file contributes nothing."""
    import os
    from harness.retrieve import slice_file
    out = []
    for sl in getattr(subtask, "context_slices", []) or []:
        path = os.path.join(workdir, sl["path"])
        if not os.path.exists(path):
            continue
        try:
            text = open(path).read()
        except Exception:
            continue
        sliced = slice_file(text, [(sl["start_line"], sl["end_line"])])
        out.append(f"--- {sl['path']} ---\n{sliced}")
    return "\n".join(out)
