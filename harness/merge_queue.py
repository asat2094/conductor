"""
Single-writer merge queue with DAG-level atomicity.

ADR references: ADR-0004 (single-writer integration branch),
                ADR-0012 (ff-only promotion gate).
REQ references:  REQ-I1 (one unit merged at a time),
                 REQ-I2 (disposable integration branch),
                 REQ-I4 (fast-forward to target only when whole-DAG assembly check is green).

Design summary
--------------
Accepted units are merged one-at-a-time onto a disposable integration branch
and the FULL suite re-runs after each merge.  This catches seam drift that a
per-unit gate would miss.

The build is ATOMIC at the DAG level:
  * fast-forward to the target branch ONLY if every unit merged AND the
    whole-DAG assembly check is green;
  * any permanent failure aborts and discards the integration branch.

All git / test I/O is delegated to injected callables so the implementation
can be tested without a real git repository.
"""

from dataclasses import dataclass
from typing import Callable, Optional, Tuple


@dataclass
class MergeResult:
    """Result returned by :meth:`MergeQueue.submit`."""

    unit_id: str
    merged: bool
    suite_passed: bool
    detail: str


class MergeQueue:
    """Single-writer merge queue (ADR-0004 / REQ-I1).

    Parameters
    ----------
    suite_runner:
        Callable ``() -> (passed: bool, detail: str)``.  Runs the full test
        suite against the current integration branch state.
    merger:
        Optional callable ``(unit_id: str) -> (ok: bool, detail: str)``.
        Rebases / applies the named unit onto the integration branch.  Defaults
        to a no-op that always returns ``(True, "")``.
    """

    def __init__(
        self,
        *,
        suite_runner: Callable[[], Tuple[bool, str]],
        merger: Optional[Callable[[str], Tuple[bool, str]]] = None,
    ) -> None:
        self._suite_runner = suite_runner
        self._merger: Callable[[str], Tuple[bool, str]] = merger if merger is not None else lambda _u: (True, "")
        self._failed: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def failed(self) -> bool:
        """True if any :meth:`submit` call has failed."""
        return self._failed

    def submit(self, unit_id: str) -> MergeResult:
        """Merge *unit_id* onto the integration branch and run the full suite.

        Implements REQ-I1 (one unit at a time) and REQ-I2 (disposable
        integration branch — the caller is responsible for branch lifecycle;
        this queue only tracks outcomes).

        Returns a :class:`MergeResult`.  ``merged`` is ``True`` only when both
        the merge step AND the suite pass.  A failed submit permanently marks
        the queue as :attr:`failed`.
        """
        # 1. Apply the unit (rebase / cherry-pick / patch).
        merge_ok, merge_detail = self._merger(unit_id)
        if not merge_ok:
            self._failed = True
            return MergeResult(
                unit_id=unit_id,
                merged=False,
                suite_passed=False,
                detail=merge_detail,
            )

        # 2. Run the full suite to detect seam drift (REQ-I2).
        suite_passed, suite_detail = self._suite_runner()
        if not suite_passed:
            self._failed = True
            return MergeResult(
                unit_id=unit_id,
                merged=False,
                suite_passed=False,
                detail=suite_detail,
            )

        return MergeResult(
            unit_id=unit_id,
            merged=True,
            suite_passed=True,
            detail=suite_detail,
        )

    def finalize(self, assembly_ok: bool = True) -> str:
        """Decide the fate of the integration branch.

        Implements ADR-0012 / REQ-I4: fast-forward to the target branch ONLY
        if every unit merged successfully AND the whole-DAG assembly check is
        green.  Any failure discards the integration branch.

        Parameters
        ----------
        assembly_ok:
            Result of the whole-DAG assembly check (e.g. linking, integration
            smoke test) that runs after all units have been merged.

        Returns
        -------
        ``"ff_to_target"`` — promote the integration branch (fast-forward).
        ``"discard"``       — abort and throw away the integration branch.
        """
        if not self._failed and assembly_ok:
            return "ff_to_target"
        return "discard"
