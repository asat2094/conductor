"""
Git-backed MergeQueue (ADR-0041 made physical).

Until now MergeQueue's merger/suite_runner were caller-injected and per-wave landing was pure
bookkeeping. GitMergeQueue supplies the real git plumbing:

  * setup:   an integration branch (`conductor/integration`) is (re)created at the target
             branch's tip and checked out — makers write into this checkout (REQ-I2 disposable).
  * submit:  the unit's working-tree changes are committed on the integration branch
             (one commit per unit, REQ-I1 single-writer), then the repo suite re-runs.
  * promote_wave ("wave" atomicity): a fully-GREEN wave fast-forwards the TARGET branch ref to
             the integration tip (`git update-ref`) — target advances wave-by-wave, held waves
             leave it untouched (prefix rule).
  * finalize ("dag" atomicity): one fast-forward at the end iff the whole DAG is clean.

The target branch is never checked out during the build, so update-ref is a safe ff. On discard
the integration branch is left in place for inspection (disposable by name, ADR-0004).
"""
import subprocess
from typing import Callable, Optional, Tuple

from harness.merge_queue import MergeQueue

INTEGRATION_BRANCH = "conductor/integration"


def _git(args: list, workdir: str) -> Tuple[int, str]:
    r = subprocess.run(["git"] + args, cwd=workdir, capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


class GitMergeQueue(MergeQueue):
    """MergeQueue with real git integration-branch plumbing (ADR-0041)."""

    def __init__(
        self,
        workdir: str,
        target_branch: str,
        *,
        suite_cmd: Optional[str] = None,
        writes_for: Optional[Callable[[str], list]] = None,
        run: Optional[Callable[[list, str], Tuple[int, str]]] = None,
        shell: Optional[Callable[[str, str], Tuple[int, str]]] = None,
    ) -> None:
        self.workdir = workdir
        self.target = target_branch
        self.suite_cmd = suite_cmd
        # unit_id -> declared writes_files. When provided, a unit's commit stages ONLY its declared
        # files (scope guard at the merge boundary — stray/other-unit files never land). None -> add -A.
        self._writes_for = writes_for
        self._git = run if run is not None else _git
        self._shell = shell if shell is not None else self._default_shell
        # SAFETY: refuse a dirty tree. `checkout -B` carries uncommitted tracked edits onto the
        # integration branch, where the first submit() would commit them as unit work and
        # promote_wave would land them on the target — operator work shipped silently. Fail loud.
        rc, out = self._git(["status", "--porcelain"], workdir)
        if rc != 0:
            raise RuntimeError(f"not a usable git repo: {out}")
        if out.strip():
            raise RuntimeError(
                "working tree is dirty — commit or stash local changes before a conductor "
                f"merge build:\n{out.strip()}"
            )
        # (re)create the integration branch at the target's tip and check it out
        rc, out = self._git(["checkout", "-B", INTEGRATION_BRANCH, target_branch], workdir)
        if rc != 0:
            raise RuntimeError(f"integration branch setup failed: {out}")
        super().__init__(suite_runner=self._run_suite, merger=self._commit_unit)

    # -- injected plumbing -------------------------------------------------

    def _default_shell(self, cmd: str, workdir: str) -> Tuple[int, str]:
        r = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True, timeout=600)
        return r.returncode, (r.stdout or "") + (r.stderr or "")

    def _commit_unit(self, unit_id: str) -> Tuple[bool, str]:
        """One commit per accepted unit on the integration branch (REQ-I1).

        --no-verify: conductor's mechanical gates + the post-merge suite are the oracles here;
        arbitrary (possibly interactive/slow) commit hooks must not hang a headless integration
        branch. The repo's own checks still gate via style_gate + suite_cmd."""
        files = self._writes_for(unit_id) if self._writes_for is not None else None
        add_args = (["add", "--"] + list(files)) if files else ["add", "-A"]
        rc, out = self._git(add_args, self.workdir)
        if rc != 0:
            return False, out
        rc, out = self._git(["commit", "--no-verify", "--allow-empty",
                             "-m", f"conductor unit: {unit_id}"], self.workdir)
        return rc == 0, out

    def _run_suite(self) -> Tuple[bool, str]:
        """Full repo suite after each merge (seam-drift check). No suite configured -> pass
        with evidence (degrade-clean; the per-unit gate already ran)."""
        if not self.suite_cmd:
            return True, "no suite_cmd configured"
        rc, out = self._shell(self.suite_cmd, self.workdir)
        return rc == 0, out

    # -- promotion ---------------------------------------------------------

    def _ff_target(self) -> None:
        rc, sha = self._git(["rev-parse", "HEAD"], self.workdir)
        if rc != 0:
            raise RuntimeError(f"rev-parse failed: {sha}")
        rc, out = self._git(["update-ref", f"refs/heads/{self.target}", sha.strip()], self.workdir)
        if rc != 0:
            raise RuntimeError(f"target fast-forward failed: {out}")

    def promote_wave(self, assembly_ok: bool = True) -> str:
        """Per-wave atomic landing: bookkeeping via the base class, then physically
        fast-forward the target ref when the wave lands."""
        disposition = super().promote_wave(assembly_ok=assembly_ok)
        if disposition == "ff_wave":
            self._ff_target()
        return disposition

    def finalize(self, assembly_ok: bool = True) -> str:
        """DAG-atomic landing: one physical fast-forward iff the whole build is clean."""
        disposition = super().finalize(assembly_ok=assembly_ok)
        if disposition == "ff_to_target":
            self._ff_target()
        return disposition
