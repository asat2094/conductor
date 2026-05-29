"""
parallel_delegate.py — dispatch multiple independent gemma4 tasks concurrently.

Usage:
    from harness.parallel_delegate import delegate_parallel

    results = delegate_parallel(
        workdir="/path/to/project",
        tasks=[
            {"task": "Add docstring to parse_order", "file": "orders.py"},
            {"task": "Add type hints to validate",   "file": "validators.py"},
        ],
    )
    # → [{"file": "orders.py", "success": True, "output": "..."}, ...]

Results are returned in the same order as input tasks.
Only use for truly independent tasks (no file dependencies between them).
"""
import concurrent.futures
from harness.gemma4_call import run as _gemma4_run


def delegate_parallel(
    workdir: str,
    tasks: list[dict],
    max_workers: int = 3,
    diff_mode: bool = False,
) -> list[dict]:
    def _run_one(task: dict) -> dict:
        response, extracted = _gemma4_run(
            workdir, task["task"], [task["file"]], diff_mode=diff_mode
        )
        return {
            "file": task["file"],
            "success": extracted is not None,
            "output": response,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_run_one, t) for t in tasks]
        results = []
        for future, task in zip(futures, tasks):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"file": task["file"], "success": False, "output": str(exc)})
    return results
