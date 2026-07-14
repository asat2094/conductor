from harness.models import SubTask, TaskType, AgentType, CapabilityProfile
from harness.router import route, cost_skip

def _profiles(failures=0, max_tokens=8000, code_edit_acc=0.85):
    return {
        "gemma4": CapabilityProfile(
            max_reliable_tokens=max_tokens,
            accuracy_by_type={"code_edit": code_edit_acc, "code_gen": 0.78, "test_write": 0.75},
            session_failures=failures,
            retry_budget=3,
        ),
        "claude_agent": CapabilityProfile(
            max_reliable_tokens=180000,
            accuracy_by_type={"code_edit": 0.95},
            session_failures=0,
            retry_budget=10,
        ),
    }

def _task(type=TaskType.CODE_EDIT, tokens=2000):
    return SubTask(id="t1", description="fix it", type=type, files=["a.py"], estimated_tokens=tokens)


def test_routes_small_code_edit_to_gemma4():
    assert route(_task(), _profiles()) == AgentType.GEMMA4

def test_routes_research_always_to_claude():
    assert route(_task(type=TaskType.RESEARCH), _profiles()) == AgentType.CLAUDE_AGENT

def test_routes_cross_file_refactor_always_to_claude():
    assert route(_task(type=TaskType.CROSS_FILE_REFACTOR), _profiles()) == AgentType.CLAUDE_AGENT

def test_routes_oversized_task_to_claude():
    assert route(_task(tokens=20000), _profiles(max_tokens=8000)) == AgentType.CLAUDE_AGENT

def test_routes_to_claude_when_failures_at_budget():
    assert route(_task(), _profiles(failures=3)) == AgentType.CLAUDE_AGENT

def test_routes_to_claude_when_accuracy_low():
    assert route(_task(), _profiles(code_edit_acc=0.65)) == AgentType.CLAUDE_AGENT


# --- rank_providers tests ---

from harness.models import ProviderConfig


def _rp_providers():
    return {
        "gemma4":   ProviderConfig("gemma4",   "ollama",        "gemma4:latest",    "http://localhost:11434",       0.0,    "local"),
        "deepseek": ProviderConfig("deepseek", "openai_compat", "deepseek-coder",   "https://api.deepseek.com/v1", 0.0014, "cloud_cheap", "DEEPSEEK_API_KEY"),
        "gemini":   ProviderConfig("gemini",   "openai_compat", "gemini-2.0-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", 0.00015, "cloud_cheap", "GEMINI_API_KEY"),
    }


def _rp_profiles():
    return {
        "gemma4":   CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.85}),
        "deepseek": CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.80}),
        "gemini":   CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.82}),
    }


def _rp_task(type=TaskType.CODE_EDIT, tokens=100):
    return SubTask("t1", "add docstring", type, ["f.py"], tokens)


def test_rank_providers_free_provider_first():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(), _rp_providers(), _rp_profiles())
    # gemma4 costs 0.0 → highest score (accuracy/cost+eps) → ranked first
    assert ranked[0] == "gemma4"
    assert ranked[-1] == "claude_agent"


def test_rank_providers_claude_always_last():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(), _rp_providers(), _rp_profiles())
    assert ranked[-1] == "claude_agent"


def test_rank_providers_skips_busy_provider():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(), _rp_providers(), _rp_profiles(), busy_providers={"gemma4"})
    assert "gemma4" not in ranked[:-1]
    assert ranked[-1] == "claude_agent"


def test_rank_providers_always_claude_for_research():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(type=TaskType.RESEARCH), _rp_providers(), _rp_profiles())
    assert ranked == ["claude_agent"]


def test_rank_providers_always_claude_for_cross_file_refactor():
    from harness.router import rank_providers
    ranked = rank_providers(_rp_task(type=TaskType.CROSS_FILE_REFACTOR), _rp_providers(), _rp_profiles())
    assert ranked == ["claude_agent"]


def test_rank_providers_skips_low_accuracy():
    from harness.router import rank_providers
    profiles = {
        "gemma4": CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.50}),
    }
    ranked = rank_providers(_rp_task(), {"gemma4": _rp_providers()["gemma4"]}, profiles)
    assert ranked == ["claude_agent"]


def test_rank_providers_skips_oversized_tasks():
    from harness.router import rank_providers
    profiles = {
        "gemma4": CapabilityProfile(max_reliable_tokens=500, accuracy_by_type={"code_edit": 0.85}),
    }
    ranked = rank_providers(_rp_task(tokens=10000), {"gemma4": _rp_providers()["gemma4"]}, profiles)
    assert ranked == ["claude_agent"]


def test_rank_providers_prefers_cheaper_at_equal_accuracy():
    from harness.router import rank_providers
    # gemini cheaper than deepseek, equal accuracy
    profiles = {
        "deepseek": CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.80}),
        "gemini":   CapabilityProfile(max_reliable_tokens=32000, accuracy_by_type={"code_edit": 0.80}),
    }
    providers = {k: _rp_providers()[k] for k in ("deepseek", "gemini")}
    ranked = rank_providers(_rp_task(), providers, profiles)
    assert ranked[0] == "gemini"  # cheaper: 0.00015 vs 0.0014


# --- ADR-0039 confidence-scored routing ---

def test_rank_providers_live_confidence_skips_cold_streak_model():
    from harness.router import rank_providers
    from harness.confidence import ConfidenceStore
    # gemma4 is free -> normally first. A cold streak drops its live score below 0.70 -> skipped.
    conf = ConfidenceStore()
    for _ in range(12):
        conf.update("gemma4", "code_edit", passed=False, seed=0.85)
    ranked = rank_providers(_rp_task(), _rp_providers(), _rp_profiles(), confidence=conf)
    assert "gemma4" not in ranked[:-1]          # dropped by live confidence, not profile
    assert ranked[-1] == "claude_agent"


def test_rank_providers_confidence_none_matches_static():
    from harness.router import rank_providers
    a = rank_providers(_rp_task(), _rp_providers(), _rp_profiles())
    b = rank_providers(_rp_task(), _rp_providers(), _rp_profiles(), confidence=None)
    assert a == b                               # backward-compat: no store -> identical


def test_rank_providers_cold_start_confidence_keeps_static_order():
    from harness.router import rank_providers
    from harness.confidence import ConfidenceStore
    conf = ConfidenceStore()                    # empty -> seeds == profile accuracy
    ranked = rank_providers(_rp_task(), _rp_providers(), _rp_profiles(), confidence=conf)
    assert ranked[0] == "gemma4"                # free provider still first


# --- cost_skip tests ---

def _st(tokens, ttype=TaskType.CODE_EDIT):
    return SubTask(id="t", description="d", type=ttype, files=["a.py"], estimated_tokens=tokens)


def test_cost_skip_routes_tiny_task_to_inline():
    assert cost_skip(_st(100)) == AgentType.CLAUDE_INLINE


def test_cost_skip_passes_large_task_through():
    assert cost_skip(_st(20_000)) is None  # None → fall through to rank_providers


def test_cost_skip_does_not_inline_always_claude_types():
    assert cost_skip(_st(50, ttype=TaskType.RESEARCH)) is None
    assert cost_skip(_st(50, ttype=TaskType.CROSS_FILE_REFACTOR)) is None


def test_cost_skip_inlines_new_small_task_types():
    # REFACTOR/SIGNATURE_CHANGE/PERF are maker-eligible types: tiny ones cost-skip to inline
    for tt in (TaskType.REFACTOR, TaskType.SIGNATURE_CHANGE, TaskType.PERF):
        assert cost_skip(_st(100, ttype=tt)) == AgentType.CLAUDE_INLINE


def test_cost_skip_passes_large_new_task_types_through():
    # REFACTOR/SIGNATURE_CHANGE/PERF are maker-eligible types: large ones pass through
    for tt in (TaskType.REFACTOR, TaskType.SIGNATURE_CHANGE, TaskType.PERF):
        assert cost_skip(_st(20_000, ttype=tt)) is None


# --- ADR-0017 sensitivity boundary ---

def test_rank_providers_high_sensitivity_excludes_cloud():
    from harness.router import rank_providers
    st = SubTask("t1", "edit secrets handler", TaskType.CODE_EDIT, ["s.py"], 100, sensitivity="high")
    ranked = rank_providers(st, _rp_providers(), _rp_profiles())
    # deepseek/gemini are cloud_cheap -> excluded; gemma4 (local) + trusted claude fallback only
    assert ranked == ["gemma4", "claude_agent"]


def test_rank_providers_low_sensitivity_unchanged():
    from harness.router import rank_providers
    st = SubTask("t1", "edit", TaskType.CODE_EDIT, ["s.py"], 100, sensitivity="low")
    ranked = rank_providers(st, _rp_providers(), _rp_profiles())
    assert "gemini" in ranked and "deepseek" in ranked
