"""
orchestrate.py — multi-provider orchestrator.

Single task:
    from harness.orchestrate import orchestrate, EscalateToClaudeError
    result = orchestrate(subtask, workdir="/path")  # raises EscalateToClaudeError if all fail

Parallel tasks (shared provider busy pool):
    results = orchestrate_parallel(subtasks, workdir="/path")
    # list of EvalResult; EscalateToClaudeError instances mark escalations
"""
from __future__ import annotations

import concurrent.futures
import os
import threading
from pathlib import Path

from harness.evaluator import evaluate
from harness.healer import auto_heal
from harness.models import EvalResult, SubTask
from harness.profiles import load_profiles, save_profiles, update_accuracy
from harness.provider_call import ProviderError, RateLimitError, run as provider_run
from harness.providers import load_providers
from harness.router import rank_providers
from harness.session_stats import log_delegation, update_score
from harness.tokens import estimate_tokens

_SESSION_ID = os.environ.get("CONDUCTOR_SESSION_ID", "default")


class EscalateToClaudeError(Exception):
    def __init__(self, subtask: SubTask) -> None:
        self.subtask = subtask
        super().__init__(f"All providers exhausted for subtask {subtask.id!r}")


def _record(subtask: SubTask, provider_name: str, result: EvalResult, profiles: dict) -> None:
    update_accuracy(profiles, provider_name, subtask.type.value, result.score)
    save_profiles(profiles)
    update_score(result.subtask_id, result.score)
    log_delegation(
        session_id=_SESSION_ID,
        task_id=result.subtask_id,
        task_type=subtask.type.value,
        agent=provider_name,
        estimated_tokens=subtask.estimated_tokens,
        score=result.score,
    )


def orchestrate(
    subtask: SubTask,
    workdir: str = ".",
    providers: dict | None = None,
    profiles: dict | None = None,
    diff_mode: bool = False,
    _busy: set | None = None,
    _busy_lock: threading.Lock | None = None,
) -> EvalResult:
    """
    Try ranked providers in order until one scores >= 70.
    Falls back on RateLimitError, ProviderError, or healer strategy C.
    Raises EscalateToClaudeError when all non-Claude providers are exhausted.
    Updates provider profiles after every task (incremental scoring).
    """
    if providers is None:
        providers = load_providers()
    if profiles is None:
        profiles = load_profiles()
    if not subtask.estimated_tokens:
        subtask.estimated_tokens = estimate_tokens(subtask.files, workdir)

    busy = _busy if _busy is not None else set()
    lock = _busy_lock or threading.Lock()

    with lock:
        ranked = rank_providers(subtask, providers, profiles, busy)

    for provider_name in ranked:
        if provider_name == "claude_agent":
            raise EscalateToClaudeError(subtask)

        with lock:
            busy.add(provider_name)

        try:
            response, code = provider_run(
                providers[provider_name], workdir, subtask.description, subtask.files,
                diff_mode=diff_mode,
            )
        except (RateLimitError, ProviderError):
            continue
        finally:
            with lock:
                busy.discard(provider_name)

        if code is None:
            continue

        changed = [str(Path(workdir) / f) for f in subtask.files]
        result = evaluate(subtask, provider_name, changed, response)
        _record(subtask, provider_name, result, profiles)

        if result.score >= 70:
            return result

        healed, strategy = auto_heal(
            subtask, result, profiles, workdir,
            delegate_fn=lambda w, t, f, _pn=provider_name: provider_run(
                providers[_pn], w, t, f, diff_mode=diff_mode
            ),
            evaluate_fn=evaluate,
        )
        if strategy != "C" and healed is not None:
            _record(subtask, provider_name, healed, profiles)
            return healed

    raise EscalateToClaudeError(subtask)


def orchestrate_parallel(
    subtasks: list[SubTask],
    workdir: str = ".",
    providers: dict | None = None,
    profiles: dict | None = None,
    diff_mode: bool = False,
    max_wait_seconds: int = 30,
) -> list[EvalResult | EscalateToClaudeError]:
    """
    Dispatch multiple subtasks concurrently, sharing the provider busy pool.
    Returns results in input order.
    Items that raise EscalateToClaudeError are returned as exception instances.
    """
    if providers is None:
        providers = load_providers()
    if profiles is None:
        profiles = load_profiles()

    busy: set[str] = set()
    lock = threading.Lock()

    def _run_one(st: SubTask) -> EvalResult | EscalateToClaudeError:
        try:
            return orchestrate(st, workdir, providers, profiles, diff_mode,
                               _busy=busy, _busy_lock=lock)
        except EscalateToClaudeError as e:
            return e

    max_workers = max(len(providers), 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_run_one, st) for st in subtasks]
        return [f.result(timeout=max_wait_seconds) for f in futures]
