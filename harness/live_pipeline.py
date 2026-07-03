"""
Live pipeline wiring (completes the spine, ADR-0011/0024/0027). Composes the built pieces into the
real per-unit processor and a one-call live build:

    live_maker (model -> files -> diff -> in-loop test)
      wrapped by make_processor (bounded repair loop against the composed unit_gate)
      driven by run_dag (decompose -> verify -> per-wave cost_skip -> dispatch -> track)

`make_live_processor` returns a process_unit(subtask, workdir) usable as run_dag's process_unit.
`build_live` is the convenience entrypoint: decompose+verify+dispatch with REAL makers. All maker IO
(model_caller, test_runner, differ) is pass-through via **maker_kw so it stays unit-testable with fakes
and uses real Claude-CLI/ollama + pytest in production.
"""
from typing import Any, Callable, Optional

from harness.process_unit import make_processor
from harness.live_maker import make_live_maker
from harness.conductor import build, build_report, default_gate_spec_for


def make_live_processor(
    *,
    role: str = "impl_author",
    policy: Optional[dict] = None,
    gate_spec_for: Optional[Callable[[Any], Any]] = None,
    max_attempts: int = 3,
    stuck_window: int = 2,
    **maker_kw: Any,
) -> Callable[[Any, str], Any]:
    """Compose the real maker + bounded repair loop + composed unit gate into a process_unit."""
    maker = make_live_maker(role=role, policy=policy, **maker_kw)
    return make_processor(
        maker,
        gate_spec_for or default_gate_spec_for,
        max_attempts=max_attempts,
        stuck_window=stuck_window,
    )


def build_live(
    briefs: list[dict],
    workdir: str = ".",
    *,
    policy: Optional[dict] = None,
    edges: Optional[dict] = None,
    max_attempts: int = 3,
    progress: bool = True,
    progress_path: Optional[str] = None,
    db_path: str = ":memory:",
    style: bool = False,
    merge_queue: Any = None,
    failure_mode: str = "continue_on_error",
    resume_from: Optional[dict] = None,
    **maker_kw: Any,
):
    """One-call live build: onboard repo -> decompose -> verify -> per-wave dispatch through REAL
    makers, with LIVE progress tracking (ADR-0023). Returns (DagRunResult, TrackerStore).

    Onboarding (ADR-0037): detects the repo's language and resolves its LanguageAdapter (ADR-0035),
    so gates/style use the right per-language block. `style=True` enables the repo-native style gate
    (ADR-0036) — the repo's own lint/format as a mechanical gate (default off to keep runs clean when
    tooling isn't installed). `merge_queue`/`failure_mode`/`resume_from` thread the ADR-0028/0029
    integration. progress streams a live PM view; progress_path feeds an external PM tool (JSONL).
    Harness-derived (NFR-TRACK-1) — sinks report, never change a verdict."""
    from harness.run_dag import run_dag
    from harness.tracker_store import TrackerStore
    from harness.progress import live_sink, jsonl_sink
    from harness.repo_profile import profile_repo
    from harness.lang.base import resolve as resolve_adapter
    from harness.conductor import default_gate_spec_for

    store = TrackerStore(db_path)
    if progress:
        store.add_sink(live_sink())
    if progress_path:
        store.add_sink(jsonl_sink(progress_path))

    # Onboard: detect language -> adapter (ADR-0037/0035). Used for the style gate (+ future per-lang gates).
    profile = profile_repo(workdir)
    adapter = resolve_adapter(profile.language)

    def gate_spec_for(subtask):
        spec = default_gate_spec_for(subtask)
        spec.workdir = workdir
        if style:
            spec.style_adapter = adapter   # ADR-0036 repo-native style gate
        return spec

    proc = make_live_processor(policy=policy, gate_spec_for=gate_spec_for,
                               max_attempts=max_attempts, **maker_kw)
    result = run_dag(briefs, workdir=workdir, process_unit=proc, tracker=store, edges=edges,
                     merge_queue=merge_queue, failure_mode=failure_mode, resume_from=resume_from)
    return result, store


__all__ = ["make_live_processor", "build_live", "build_report"]
