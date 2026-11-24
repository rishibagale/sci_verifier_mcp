"""Sandboxed Lean 4 formal proof verification with cheat detection and line diagnostics."""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

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


def verify_lean4_proof(
    lean_code: str,
    timeout_seconds: int = config.DEFAULT_LEAN_TIMEOUT,
    allow_axioms: bool = False
) -> VerificationResult:
    """Verify formal Lean 4 proof in a temporary sandbox with cheat detection and line diagnostics."""
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

    # 3. Execute in isolated temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        lean_file = tmp_path / "Verification.lean"
        lean_file.write_text(clean_code, encoding="utf-8")

        cmd = [lean_bin or "lean", "--json", str(lean_file)]

        try:
            proc = subprocess.run(
                cmd,
                cwd=tmp_dir,
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

        # Parse JSON compiler output
        diagnostics = []
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

        if proc.returncode != 0 or has_error:
            err_summary = proc.stderr.strip() or "Lean compiler reported errors."
            return VerificationResult(
                status=VerificationStatus.FAILED,
                summary=f"Formal proof verification failed: {err_summary[:200]}",
                details={
                    "returncode": proc.returncode,
                    "diagnostics": diagnostics,
                    "stderr": proc.stderr,
                    "stdout": proc.stdout[:1000],
                }
            )

        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary="Formal proof verified successfully by Lean 4 compiler (0 errors).",
            details={
                "diagnostics": diagnostics,
                "lines_verified": len(clean_code.splitlines()),
            }
        )
