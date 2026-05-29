"""
parallel_delegate.py — dispatch multiple independent tasks concurrently across all providers.

Tasks are distributed across the provider pool (each provider handles one task at a time).
Fallback and healing happen inside orchestrate() per task.

Usage:
    from harness.parallel_delegate import delegate_parallel
    from harness.models import SubTask, TaskType

    results = delegate_parallel(
        workdir="/path/to/project",
        tasks=[
            {"task": "Add docstrings to parse_order",    "file": "orders.py"},
            {"task": "Add type hints to validate_email", "file": "validators.py"},
        ],
    )
    # → [{"file": "orders.py", "success": True, "score": 85, "agent": "gemma4", ...}, ...]

    # With explicit SubTask objects (for richer routing):
    results = delegate_parallel(workdir=..., tasks=[...], subtasks=[SubTask(...), ...])
"""
from __future__ import annotations

import concurrent.futures
import threading

from harness.models import SubTask, TaskType
from harness.orchestrate import EscalateToClaudeError, orchestrate
from harness.profiles import load_profiles
from harness.providers import load_providers


def delegate_parallel(
    workdir: str,
    tasks: list[dict],
    max_workers: int | None = None,
    diff_mode: bool = False,
    heal: bool = True,          # kept for API compat; orchestrate always heals
    subtasks: list[SubTask] | None = None,
) -> list[dict]:
    """
    Args:
        workdir:     Absolute path to project root.
        tasks:       List of {"task": str, "file": str}.
        max_workers: Max concurrent tasks. Defaults to number of available providers.
        diff_mode:   Pass diff_mode to each orchestrate() call.
        heal:        Retained for API compatibility. Orchestrate always heals internally.
        subtasks:    Optional SubTask objects in same order as tasks.
                     Auto-built from tasks if not provided.
    Returns:
        List of result dicts in input order:
        {"file", "success", "score", "agent", "output", "escalated", "healer_strategy"}
    """
    providers = load_providers()
    profiles = load_profiles()

    if subtasks is None:
        subtasks = [
            SubTask(
                id=f"parallel_{i}",
                description=t["task"],
                type=TaskType.CODE_EDIT,
                files=[t["file"]],
                estimated_tokens=0,
            )
            for i, t in enumerate(tasks)
        ]

    busy: set[str] = set()
    lock = threading.Lock()

    def _run_one(task: dict, subtask: SubTask) -> dict:
        try:
            result = orchestrate(
                subtask, workdir, providers, profiles, diff_mode,
                _busy=busy, _busy_lock=lock,
            )
            return {
                "file": task["file"],
                "success": result.score >= 70,
                "score": result.score,
                "agent": result.agent,
                "output": result.details,
                "escalated": False,
                "healer_strategy": None,
            }
        except EscalateToClaudeError:
            return {
                "file": task["file"],
                "success": False,
                "score": -1,
                "agent": "claude_agent",
                "output": "all providers exhausted — escalated to claude_agent",
                "escalated": True,
                "healer_strategy": "C",
            }
        except Exception as exc:
            return {
                "file": task["file"],
                "success": False,
                "score": -1,
                "agent": None,
                "output": str(exc),
                "escalated": False,
                "healer_strategy": None,
            }

    n_workers = max_workers if max_workers is not None else max(len(providers), 1)
    pairs = list(zip(tasks, subtasks))

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_run_one, t, st) for t, st in pairs]
        return [f.result() for f in futures]
