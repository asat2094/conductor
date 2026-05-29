"""
parallel_cli.py — shell-accessible interface for delegate_parallel.

Usage:
    python3 -m harness.parallel_cli <workdir> <tasks_json> [--diff] [--workers N]

tasks_json is a JSON array of {"task": str, "file": str} objects.

Example:
    python3 -m harness.parallel_cli /my/project '[
        {"task": "Add docstring to parse_order", "file": "orders.py"},
        {"task": "Add type hints to validate",   "file": "validators.py"}
    ]' --workers 2

Output: JSON array of results to stdout.
Each result: {"file": str, "success": bool, "output": str, "healer_strategy": str|null}
Exit code: 0 if all succeeded, 1 if any failed.
"""
import json
import sys


def main() -> int:
    args = sys.argv[1:]
    diff_mode = "--diff" in args
    args = [a for a in args if a != "--diff"]

    workers = 3
    if "--workers" in args:
        idx = args.index("--workers")
        workers = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    if len(args) < 2:
        print(
            "Usage: python3 -m harness.parallel_cli <workdir> <tasks_json> [--diff] [--workers N]",
            file=sys.stderr,
        )
        return 1

    workdir, tasks_raw = args[0], args[1]
    tasks = json.loads(tasks_raw)

    from harness.parallel_delegate import delegate_parallel
    results = delegate_parallel(workdir, tasks, max_workers=workers, diff_mode=diff_mode)
    print(json.dumps(results, indent=2))

    failed = sum(1 for r in results if not r["success"])
    if failed:
        print(f"\n[parallel_cli] {failed}/{len(results)} tasks failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
