import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Literal


class TaskType(str, Enum):
    CODE_EDIT = "code_edit"
    CODE_GEN = "code_gen"
    RESEARCH = "research"
    CROSS_FILE_REFACTOR = "cross_file_refactor"  # multi-file → always routed to Claude
    TEST_WRITE = "test_write"
    REFACTOR = "refactor"  # single-file / bounded refactor → eligible for makers
    SIGNATURE_CHANGE = "signature_change"
    PERF = "perf"


class AgentType(str, Enum):
    GEMMA4 = "gemma4"
    CLAUDE_AGENT = "claude_agent"
    CLAUDE_INLINE = "claude_inline"


@dataclass
class SubTask:
    id: str
    description: str
    type: TaskType
    files: list[str]
    estimated_tokens: int
    dependencies: list[str] = field(default_factory=list)
    assigned_agent: Optional[AgentType] = None
    sensitivity: Literal["low", "high"] = "low"
    writes_files: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    logical_deps: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    subtask_id: str
    agent: str          # was AgentType — widened to str; AgentType values still work
    score: int
    syntax_score: int
    test_score: int
    scope_score: int
    semantic_score: int
    details: str
    changed_files: list[str] = field(default_factory=list)


@dataclass
class CapabilityProfile:
    max_reliable_tokens: int
    accuracy_by_type: dict[str, float]
    session_failures: int = 0
    retry_budget: int = 3
    last_updated: float = field(default_factory=time.time)
    decay_per_day: float = 0.98  # accuracy drifts this fraction per day toward 0.5


@dataclass
class ProviderConfig:
    name: str
    type: str           # "ollama" | "openai_compat"
    model: str
    base_url: str
    cost_per_1k_tokens: float
    tier: str
    api_key_env: str = ""
