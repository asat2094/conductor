"""
SubtaskBrief — the self-contained unit of work emitted by decomposition (REQ-D2, ADR-0011).
Shape matches docs/specs/conductor/schemas/subtask_brief.schema.json. Stdlib-only validation
(no jsonschema dependency).
"""
from dataclasses import dataclass, field

_REQUIRED = ("id", "goal", "task_type", "files", "context_slices", "contract", "verify_cmd", "exit_criteria", "sensitivity")
_VALID_TASK_TYPES = {"code_edit", "code_gen", "test_write", "refactor", "signature_change", "perf"}
_VALID_SENSITIVITY = {"low", "high"}


@dataclass
class ContextSlice:
    path: str
    start_line: int
    end_line: int


@dataclass
class Contract:
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    expected_behavior: str = ""


@dataclass
class SubtaskBrief:
    id: str
    goal: str
    task_type: str
    files: list[str]
    context_slices: list[ContextSlice]
    contract: Contract
    verify_cmd: str
    exit_criteria: str
    sensitivity: str = "low"
    writes_files: list[str] = field(default_factory=list)
    logical_deps: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "SubtaskBrief":
        c = d["contract"]
        # NOTE: schema 'roles' is intentionally not mapped in v1 — maker-role wiring lands in the pipeline plan (Plan 3).
        return cls(
            id=d["id"],
            goal=d["goal"],
            task_type=d["task_type"],
            files=list(d["files"]),
            context_slices=[ContextSlice(**s) for s in d["context_slices"]],
            contract=Contract(
                produces=list(c.get("produces", [])),
                consumes=list(c.get("consumes", [])),
                expected_behavior=c.get("expected_behavior", ""),
            ),
            verify_cmd=d["verify_cmd"],
            exit_criteria=d["exit_criteria"],
            sensitivity=d.get("sensitivity", "low"),
            writes_files=list(d.get("writes_files", [])),
            logical_deps=list(d.get("logical_deps", [])),
        )


def validate_brief(d: dict) -> list[str]:
    """Return a list of human-readable errors. Empty list == valid."""
    errors: list[str] = []
    for key in _REQUIRED:
        if key not in d:
            errors.append(f"missing required key '{key}'")
    if "task_type" in d and d["task_type"] not in _VALID_TASK_TYPES:
        errors.append(f"invalid task_type '{d['task_type']}'")
    if "sensitivity" in d and d["sensitivity"] not in _VALID_SENSITIVITY:
        errors.append(f"invalid sensitivity '{d['sensitivity']}' (must be low|high)")
    if "contract" in d:
        if not isinstance(d["contract"], dict) or "produces" not in d["contract"] or "consumes" not in d["contract"]:
            errors.append("contract must be an object with 'produces' and 'consumes'")
    return errors
