"""Sandboxed Lean 4 formal proof verification with lake env lean, cheat detection, and goal extraction."""

import contextlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus

CHEAT_TACTICS_REGEX = re.compile(r"\b(sorry|admit)\b", re.IGNORECASE)
AXIOM_DECLARATION_REGEX = re.compile(r"\baxiom\s+([A-Za-z0-9_]+)", re.MULTILINE)


def scan_for_cheat_tactics(lean_code: str, allow_axioms: bool = False) -> list[str]:
    """Scan Lean source code for placeholder tactics and axiom declarations."""
    cheats = []
    for match in CHEAT_TACTICS_REGEX.finditer(lean_code):
        cheats.append(f"Unproven placeholder '{match.group(1)}' at index {match.start()}")

    if not allow_axioms:
        for match in AXIOM_DECLARATION_REGEX.finditer(lean_code):
            cheats.append(f"Undeclared axiom assertion '{match.group(1)}' at index {match.start()}")

    return cheats


def _extract_goal_states(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract unsolved tactic goal states from Lean 4 compiler diagnostics."""
    goals: list[dict[str, Any]] = []
    for diag in diagnostics:
        msg = str(diag.get("message", ""))
        if "unsolved goals" in msg.lower() or "⊢" in msg or "|-" in msg:
            goals.append({
                "line": diag.get("line"),
                "column": diag.get("column"),
                "goal_state": msg.strip(),
            })
    return goals


def verify_lean4_proof(
    lean_code: str,
    timeout_seconds: int = config.DEFAULT_LEAN_TIMEOUT,
    allow_axioms: bool = False,
    project_dir: str | None = None,
) -> VerificationResult:
    """Verify formal Lean 4 proof via lake env lean or lean in an isolated sandbox."""
    clean_code = lean_code.strip()
    if not clean_code:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty Lean 4 code provided.",
            details={}
        )

    # 1. Scan for cheat tactics (sorry, admit, axiom)
    cheats = scan_for_cheat_tactics(clean_code, allow_axioms=allow_axioms)
    if cheats:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=(
                f"Proof rejected: contains {len(cheats)} unproven placeholder(s) or axiom(s) "
                f"({', '.join(cheats[:2])})."
            ),
            details={"cheats_detected": cheats, "input_code": clean_code}
        )

    # 2. Check if Lean 4 compiler or Lake is installed
    lean_bin = shutil.which("lean")
    lake_bin = shutil.which("lake")

    if not lean_bin and not lake_bin:
        return VerificationResult(
            status=VerificationStatus.UNAVAILABLE,
            summary="Lean 4 compiler ('lean' or 'lake') is not installed on this system.",
            details={
                "help": (
                    "To verify Lean 4 proofs, install elan and Lean 4 by following: "
                    "https://leanprover-community.github.io/get_started.html"
                ),
                "required_binaries": ["lean", "lake"],
            }
        )

    # 3. Determine execution mode: Lake project environment vs isolated tempdir
    use_lake_project = False
    cwd_path: Path | None = None
    if project_dir:
        p = Path(project_dir)
        if not p.is_dir():
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Specified Lean project_dir does not exist: '{project_dir}'.",
                details={"project_dir": project_dir}
            )
        has_lakefile = (p / "lakefile.lean").exists() or (p / "lakefile.toml").exists()
        if has_lakefile and lake_bin:
            use_lake_project = True
            cwd_path = p

    tmp_dir_ctx = None
    tmp_lean_file: Path | None = None
    try:
        if use_lake_project and cwd_path is not None and lake_bin:
            # Create a temporary file inside the project directory and clean up afterward
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".lean",
                prefix="_sci_verifier_",
                dir=str(cwd_path),
                delete=False,
                encoding="utf-8",
            ) as fd:
                fd.write(clean_code)
                tmp_lean_file = Path(fd.name)
            cmd = [lake_bin, "env", "lean", "--json", str(tmp_lean_file)]
            run_cwd = str(cwd_path)
        else:
            tmp_dir_ctx = tempfile.TemporaryDirectory()
            tmp_path = Path(tmp_dir_ctx.name)
            tmp_lean_file = tmp_path / "Verification.lean"
            tmp_lean_file.write_text(clean_code, encoding="utf-8")
            cmd = [lean_bin, "--json", str(tmp_lean_file)] if lean_bin else [lake_bin or "lake", "env", "lean", "--json", str(tmp_lean_file)]
            run_cwd = tmp_dir_ctx.name

        try:
            proc = subprocess.run(
                cmd,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                status=VerificationStatus.TIMEOUT,
                summary=f"Lean 4 verification timed out after {timeout_seconds}s.",
                details={"timeout_seconds": timeout_seconds}
            )
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Failed to execute Lean subprocess: {e}",
                details={"error": str(e)}
            )
    finally:
        if use_lake_project and tmp_lean_file is not None and tmp_lean_file.exists():
            with contextlib.suppress(Exception):
                tmp_lean_file.unlink()
        if tmp_dir_ctx is not None:
            tmp_dir_ctx.cleanup()

    # 4. Parse JSON compiler output and tactic goal states
    diagnostics: list[dict[str, Any]] = []
    has_error = False

    for line in proc.stdout.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        try:
            diag = json.loads(line_str)
            severity = diag.get("severity", "info")
            pos = diag.get("pos", {})
            msg = diag.get("data", "")
            if severity == "error":
                has_error = True
            diagnostics.append({
                "line": pos.get("line"),
                "column": pos.get("column"),
                "severity": severity,
                "message": msg,
            })
        except Exception:
            pass

    goal_states = _extract_goal_states(diagnostics)

    if proc.returncode != 0 or has_error:
        err_summary = proc.stderr.strip() or (
            diagnostics[0]["message"] if diagnostics else "Lean compiler reported errors."
        )
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Formal proof verification failed: {str(err_summary)[:200]}",
            details={
                "returncode": proc.returncode,
                "execution_mode": "lake_env_lean" if use_lake_project else "lean_standalone",
                "diagnostics": diagnostics,
                "goal_states": goal_states,
                "stderr": proc.stderr,
                "stdout": proc.stdout[:1000],
            }
        )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary="Formal proof verified successfully by Lean 4 compiler (0 errors).",
        details={
            "execution_mode": "lake_env_lean" if use_lake_project else "lean_standalone",
            "diagnostics": diagnostics,
            "goal_states": goal_states,
            "lines_verified": len(clean_code.splitlines()),
        }
    )
