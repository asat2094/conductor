"""
parallel_delegate.py — dispatch multiple independent gemma4 tasks concurrently.

Usage (basic):
    from harness.parallel_delegate import delegate_parallel

    results = delegate_parallel(
        workdir="/path/to/project",
        tasks=[
            {"task": "Add docstrings to parse_order",    "file": "orders.py"},
            {"task": "Add type hints to validate_email", "file": "validators.py"},
        ],
    )
    # → [{"file": "orders.py", "success": True, "output": "...", "healer_strategy": None}, ...]

Usage (with per-task auto_heal):
    from harness.models import SubTask, TaskType
    results = delegate_parallel(
        workdir="...",
        tasks=[...],
        heal=True,
        subtasks=[SubTask(...), SubTask(...)],  # same order as tasks
    )

heal=True runs auto_heal(A→B) on any task that fails to produce code.
One task's failure does not block others.
Results returned in input order.
Only use for truly independent tasks (no shared file dependencies).
"""
import concurrent.futures
from pathlib import Path

from harness.gemma4_call import run as _gemma4_run


def delegate_parallel(
    workdir: str,
    tasks: list[dict],
    max_workers: int = 3,
    diff_mode: bool = False,
    heal: bool = False,
    subtasks: list | None = None,
) -> list[dict]:
    """
    Args:
        workdir:    Absolute path to project root.
        tasks:      List of {"task": str, "file": str}.
        max_workers: Max concurrent gemma4 calls.
        diff_mode:  Pass --diff to each call.
        heal:       If True, run auto_heal(A→B) on tasks that fail to produce code.
                    Requires `subtasks` (list[SubTask]) in the same order as tasks.
        subtasks:   SubTask objects matching tasks order, required when heal=True.
    """
    pairs = list(zip(tasks, subtasks or ([None] * len(tasks))))

    def _run_one(task: dict, subtask) -> dict:
        try:
            response, extracted = _gemma4_run(
                workdir, task["task"], [task["file"]], diff_mode=diff_mode
            )
            result = {
                "file": task["file"],
                "success": extracted is not None,
                "output": response,
                "healer_strategy": None,
            }
            if heal and not result["success"] and subtask is not None:
                result = _try_heal(task, subtask, result, workdir, diff_mode=diff_mode)
            return result
        except Exception as exc:
            return {
                "file": task["file"],
                "success": False,
                "output": str(exc),
                "healer_strategy": None,
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_run_one, t, st) for t, st in pairs]
        results = []
        for future, (task, _) in zip(futures, pairs):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({
                    "file": task["file"],
                    "success": False,
                    "output": str(exc),
                    "healer_strategy": None,
                })
    return results


def _try_heal(task: dict, subtask, base: dict, workdir: str, diff_mode: bool = False) -> dict:
    """Run auto_heal for a single failed parallel task, honouring diff_mode."""
    from harness.healer import auto_heal
    from harness.models import AgentType, EvalResult
    from harness.profiles import load_profiles

    dummy_result = EvalResult(
        subtask_id=subtask.id,
        agent=AgentType.GEMMA4,
        score=0,
        syntax_score=0, test_score=0, scope_score=0, semantic_score=0,
        details="no code block extracted",
        changed_files=[str(Path(workdir) / task["file"])],
    )
    profiles = load_profiles()
    healed, strategy = auto_heal(subtask, dummy_result, profiles, workdir, diff_mode=diff_mode)
    base["healer_strategy"] = strategy
    if healed is not None:
        base["success"] = True
        base["output"] = f"healed via strategy {strategy} (score={healed.score})"
    return base
