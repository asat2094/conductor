import ast
import subprocess
from pathlib import Path

from harness.models import AgentType, EvalResult, SubTask


def check_syntax(files: list[str]) -> int:
    for f in files:
        path = Path(f)
        if path.suffix == ".py" and path.exists():
            try:
                ast.parse(path.read_text())
            except SyntaxError:
                return 0
    return 25


def _has_test_file(files: list[str]) -> bool:
    for f in files:
        p = Path(f)
        test_candidates = [
            p.parent / f"test_{p.name}",
            p.parent.parent / "tests" / f"test_{p.name}",
            p.parent / "tests" / f"test_{p.name}",
        ]
        if any(c.exists() for c in test_candidates):
            return True
    return False


def _run_tests(files: list[str]) -> int:
    if not _has_test_file(files):
        return 20  # partial credit — no tests exist, not agent's fault
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "--tb=no", "-q"] + files,
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return 35
        if "no tests ran" in result.stdout or result.stdout.strip() == "":
            return 20
        return 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0


def _basenames(paths: list[str]) -> set[str]:
    return {Path(p).name for p in paths}


def check_scope(changed: list[str], requested: list[str]) -> int:
    extra = _basenames(changed) - _basenames(requested)
    if not extra:
        return 20
    if len(extra) == 1:
        return 10
    return 0


def _word_overlap_score(text: str, description: str) -> int:
    desc_words = set(description.lower().split())
    if not desc_words:
        return 10
    overlap = len(desc_words & set(text.lower().split())) / len(desc_words)
    return int(overlap * 20)


def estimate_semantic(output: str, description: str, changed_files: list[str] | None = None) -> int:
    score = _word_overlap_score(output, description)
    # For short outputs (summaries), also score against file content and take the best
    if len(output.split()) < 30 and changed_files:
        for f in changed_files:
            p = Path(f)
            if p.exists() and p.suffix == ".py":
                score = max(score, _word_overlap_score(p.read_text(), description))
    return score


def evaluate(
    subtask: SubTask,
    agent: AgentType,
    changed_files: list[str],
    output: str,
) -> EvalResult:
    syntax = check_syntax(changed_files)
    tests = _run_tests(changed_files)
    scope = check_scope(changed_files, subtask.files)
    semantic = estimate_semantic(output, subtask.description, changed_files)
    total = syntax + tests + scope + semantic

    return EvalResult(
        subtask_id=subtask.id,
        agent=agent,
        score=total,
        syntax_score=syntax,
        test_score=tests,
        scope_score=scope,
        semantic_score=semantic,
        details=f"syntax={syntax}/25 tests={tests}/35 scope={scope}/20 semantic={semantic}/20",
        changed_files=changed_files,
    )


if __name__ == "__main__":
    import json
    import sys

    from harness.models import TaskType
    from harness.profiles import load_profiles
    from harness.session_stats import update_score

    auto_heal_flag = "--auto-heal" in sys.argv
    argv_clean = [a for a in sys.argv[1:] if a != "--auto-heal"]

    data = json.loads(argv_clean[0])
    st = data["subtask"]
    st["type"] = TaskType(st["type"])
    subtask = SubTask(**st)
    agent = AgentType(data["agent"])
    changed = data["changed_files"]
    output = data["output"]
    workdir = data.get("workdir", ".")

    result = evaluate(subtask, agent, changed, output)
    update_score(subtask.id, result.score)

    if auto_heal_flag and result.score < 70:
        from harness.healer import auto_heal
        profiles = load_profiles()
        healed_result, strategy = auto_heal(subtask, result, profiles, workdir)
        if healed_result is not None:
            update_score(healed_result.subtask_id, healed_result.score)
            out = vars(healed_result)
            out["healer_strategy"] = strategy
            print(json.dumps(out))
            sys.exit(0)
        else:
            out = vars(result)
            out["healer_strategy"] = "C"
            out["healer_note"] = "Both A and B failed — escalate to claude_agent."
            print(json.dumps(out))
            sys.exit(2)

    print(json.dumps(vars(result)))
