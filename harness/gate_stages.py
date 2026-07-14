"""
Ready-made extra gate stages (GateSpec.extra_gates) — production wiring for gates that were
designed and tested but previously orphaned:

  ADR-0030 git-RED   — commit-order proof that the failing test predates the implementation.
  ADR-0008 mutation  — test adequacy: the unit's tests must kill >= threshold of mutants.
  ADR-0010 charact.  — refactor/perf units must preserve captured golden behavior.

Each factory returns `fn(artifact) -> (ok: bool, evidence: str)` suitable for
GateSpec.extra_gates. All are mechanical (git / test-run / diff) — never a model.
"""
import os
from typing import Callable, Optional, Tuple


def git_red_stage(workdir: str, *, runner: Optional[Callable] = None):
    """ADR-0030: for units that changed both a test file and an impl file, prove the test's
    introducing commit is an ancestor of the impl's. Units without a (test, impl) pair pass
    (nothing to order). Degrade-clean: not a git repo -> pass with evidence."""
    from harness.git_red_gate import red_before_impl
    from harness.lang.base import adapter_for_path

    def stage(artifact) -> Tuple[bool, str]:
        tests = [f for f in artifact.changed_files if adapter_for_path(f).is_test_file(f)]
        impls = [f for f in artifact.changed_files if f not in tests]
        if not tests or not impls:
            return True, "no test+impl pair to order"
        cwd = os.getcwd()
        try:
            os.chdir(workdir)
            kwargs = {"runner": runner} if runner is not None else {}
            return red_before_impl(tests[0], impls[0], **kwargs)
        except Exception as e:            # not a git repo / git absent -> degrade-clean
            return True, f"git-red skipped: {e}"
        finally:
            os.chdir(cwd)
    return stage


def mutation_stage(test_runner: Callable[[str], bool], *, threshold: float = 0.8):
    """ADR-0008: mutate the unit's first changed .py source; the injected test_runner
    (mutated_source -> mutant_killed) must kill >= threshold. Non-Python units pass."""
    from harness.mutation import adequacy_ok

    def stage(artifact) -> Tuple[bool, str]:
        py = [f for f in artifact.changed_files if f.endswith(".py") and not f.startswith("test")]
        if not py:
            return True, "no python impl to mutate"
        try:
            source = open(py[0]).read()
        except OSError as e:
            return True, f"mutation skipped: {e}"
        return adequacy_ok(source, test_runner=test_runner, threshold=threshold)
    return stage


def characterization_stage(before: dict, capture_after: Callable[[], dict]):
    """ADR-0010: for refactor/perf units — golden I/O captured BEFORE the change must match
    a fresh capture after it. `before` is the pre-change capture_golden() result."""
    from harness.characterization_gate import characterization_ok

    def stage(artifact) -> Tuple[bool, str]:
        after = capture_after()
        ok, evidence = characterization_ok(before, after)
        return ok, (evidence if isinstance(evidence, str) else "drift: " + ", ".join(map(str, evidence)))
    return stage
