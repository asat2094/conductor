import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskType(str, Enum):
    CODE_EDIT = "code_edit"
    CODE_GEN = "code_gen"
    RESEARCH = "research"
    CROSS_FILE_REFACTOR = "cross_file_refactor"
    TEST_WRITE = "test_write"


class AgentType(str, Enum):
    GEMMA4 = "gemma4"
    CLAUDE_AGENT = "claude_agent"


@dataclass
class SubTask:
    id: str
    description: str
    type: TaskType
    files: list[str]
    estimated_tokens: int
    dependencies: list[str] = field(default_factory=list)
    assigned_agent: Optional[AgentType] = None


@dataclass
class EvalResult:
    subtask_id: str
    agent: AgentType
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
