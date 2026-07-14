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
    atomicity: str = "wave",
    best_of_n: Optional[Callable[[dict], int]] = None,
    confidence: Any = None,
    judge: Optional[Callable[[Any], bool]] = None,
    judge_quota: Any = None,
    judge_model: Optional[str] = None,
    webhook_post: Optional[Callable[[dict], Any]] = None,
    tdd_gates: bool = False,
    extra_gates_for: Optional[Callable[[Any], list]] = None,
    cost_ceiling: Any = None,
    checkpoint_path: Optional[str] = None,
    codegraph: bool = False,
    probes: bool = False,
    **maker_kw: Any,
):
    """One-call live build: onboard repo -> decompose -> verify -> per-wave dispatch through REAL
    makers, with LIVE progress tracking (ADR-0023). Returns (DagRunResult, TrackerStore).

    Onboarding (ADR-0037): detects the repo's language and resolves its LanguageAdapter (ADR-0035),
    so gates/style use the right per-language block. `style=True` enables the repo-native style gate
    (ADR-0036) — the repo's own lint/format as a mechanical gate (default off to keep runs clean when
    tooling isn't installed). `merge_queue`/`failure_mode`/`resume_from` thread the ADR-0028/0029
    integration. progress streams a live PM view; progress_path feeds an external PM tool (JSONL).
    Harness-derived (NFR-TRACK-1) — sinks report, never change a verdict.
    `atomicity` (ADR-0041): 'wave' (default, per-wave landing) | 'dag' (whole-or-nothing). `best_of_n`
    (ADR-0040) + `confidence` (ADR-0039) thread through to run_dag; `confidence` should be the SAME
    ConfidenceStore passed to orchestrate's rank_providers to close the routing feedback loop. `judge`
    (ADR-0038) opt-in enables the inconclusive-only tiebreak in the gate (needs no-test units to signal
    in_loop_green=None)."""
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
    if webhook_post is not None:                       # ADR-0023 external-PM sink
        from harness.progress import webhook_sink
        store.add_sink(webhook_sink(webhook_post))

    # Onboard: detect language -> adapter (ADR-0037/0035). Used for the style gate (+ future per-lang gates).
    profile = profile_repo(workdir)
    adapter = resolve_adapter(profile.language)

    # ADR-0032 spec-completeness probes: ADVISORY — annotate briefs with edge/prohibition hints
    # for the maker's context; never gates, never mutates the caller's list.
    if probes:
        from harness.spec_probes import annotate_brief
        briefs = [annotate_brief(b) for b in briefs]

    # ADR-0022/REQ-D9 codegraph: live edges for verify + per-wave re-verify. Degrade-clean —
    # a missing codegraph CLI yields {} and the verifier reports 'unverified', never blocks.
    reverify = None
    if codegraph:
        from harness.codegraph_live import make_codegraph_query
        from harness.verify import verify_decomposition
        _qf = make_codegraph_query()
        _files = sorted({f for b in briefs for f in b.get("files", [])})
        if edges is None:
            edges = _qf(_files, workdir)
        def reverify(by_id, accepted):
            return verify_decomposition(list(by_id.values()), edges=_qf(_files, workdir))

    # ADR-0038 judge wiring: real author identities (author-separation must compare actual
    # models, not placeholders) + ONE shared per-DAG quota (~10% of units, min 1).
    if judge is not None:
        import math
        from harness.judge import JudgeQuota
        from harness.role_policy import resolve_model, model_id
        from harness.tracker import UnitState
        judge_id = judge_model or model_id(resolve_model("judge", policy=policy))
        if judge_quota is None:
            judge_quota = JudgeQuota(limit=max(1, math.ceil(0.10 * len(briefs))))

        def _impl_id_for(subtask):
            # MUST mirror LiveMaker.make's resolution exactly: high-sensitivity units get a
            # bumped-tier maker, so author-separation must compare against the BUMPED identity —
            # a stale unbumped id could let the judge accept its own output under a custom policy.
            stakes = maker_kw.get("high_stakes", False) or getattr(subtask, "sensitivity", "low") == "high"
            return model_id(resolve_model("impl_author", policy=policy, high_stakes=stakes))

    def gate_spec_for(subtask):
        spec = default_gate_spec_for(subtask)
        spec.workdir = workdir
        # ADR-0017 ↔ ADR-0026: stakes are unified with the maker's resolution — a high-stakes
        # maker config or a high-sensitivity unit both make the held-out oracle mandatory.
        # This also structurally closes the judge path for any bumped-tier unit (the judge only
        # fires when high_stakes is False), so author-separation can never see a stale identity.
        if maker_kw.get("high_stakes", False) or getattr(subtask, "sensitivity", "low") == "high":
            spec.high_stakes = True
        if style:
            spec.style_adapter = adapter   # ADR-0036 repo-native style gate
        if tdd_gates:                      # ADR-0030 git-RED commit-order gate (opt-in)
            from harness.gate_stages import git_red_stage
            spec.extra_gates.append(("git_red", git_red_stage(workdir)))
        if extra_gates_for is not None:    # ADR-0008/0010 mutation / characterization, per-unit
            spec.extra_gates.extend(extra_gates_for(subtask))
        if judge is not None:              # ADR-0038 inconclusive-only judge tiebreak (opt-in)
            spec.judge = judge
            spec.judge_quota = judge_quota
            spec.impl_author = _impl_id_for(subtask)   # per-unit: reflects high-stakes tier bump
            spec.judge_model = judge_id
            uid = getattr(subtask, "id", "?")
            spec.judge_logger = lambda decision, reason, _u=uid: store.record(
                _u, UnitState.JUDGE_TIEBREAK, decision=decision, reason=reason)
        return spec

    proc = make_live_processor(policy=policy, gate_spec_for=gate_spec_for,
                               max_attempts=max_attempts, **maker_kw)
    result = run_dag(briefs, workdir=workdir, process_unit=proc, tracker=store, edges=edges,
                     merge_queue=merge_queue, failure_mode=failure_mode, resume_from=resume_from,
                     atomicity=atomicity, best_of_n=best_of_n, confidence=confidence,
                     reverify=reverify, cost_ceiling=cost_ceiling, checkpoint_path=checkpoint_path)
    return result, store


__all__ = ["make_live_processor", "build_live", "build_report"]
