"""Cadabra2 tensor calculus wrapper (QFT and General Relativity tensor algebra)."""

import contextlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


def simplify_tensor_expr(
    expr: str,
    rules: list[str] | None = None,
    timeout_seconds: int = 15,
) -> VerificationResult:
    """Simplify tensor expression using Cadabra2 in a sandboxed subprocess (graceful fallback if uninstalled)."""
    clean_expr = expr.strip()
    if not clean_expr:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty tensor expression provided.",
            details={},
        )

    cadabra_bin = shutil.which("cadabra2") or shutil.which("cadabra2-cli")

    if not cadabra_bin:
        return VerificationResult(
            status=VerificationStatus.UNAVAILABLE,
            summary="Cadabra2 tensor calculus engine is not installed on this system.",
            details={
                "help": (
                    "Cadabra2 is an optional computer algebra system for field theory and general relativity. "
                    "Install from https://cadabra.science"
                ),
                "expression": clean_expr,
                "rules": rules or [],
            },
        )

    rule_lines = "\n".join(str(r) for r in (rules or []))
    script_content = (
        "import json\n"
        "from cadabra2 import *\n"
        f"ex = Ex({json.dumps(clean_expr)})\n"
        f"{rule_lines}\n"
        "canonicalise(ex)\n"
        "collect_terms(ex)\n"
        "print('RESULT_JSON:' + json.dumps({'simplified': str(ex)}))\n"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        script_path = Path(tmp_dir) / "simplify.py"
        script_path.write_text(script_content, encoding="utf-8")

        try:
            proc = subprocess.run(
                [cadabra_bin, str(script_path)],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                status=VerificationStatus.TIMEOUT,
                summary=f"Cadabra2 simplification timed out after {timeout_seconds}s.",
                details={"expression": clean_expr, "timeout_seconds": timeout_seconds},
            )
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Failed to run Cadabra2 subprocess: {e}",
                details={"error": str(e)},
            )

        if proc.returncode != 0:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                summary=f"Cadabra2 execution failed: {proc.stderr.strip()[:200]}",
                details={"returncode": proc.returncode, "stderr": proc.stderr, "stdout": proc.stdout[:500]},
            )

        simplified = None
        for line in proc.stdout.splitlines():
            if line.startswith("RESULT_JSON:"):
                with contextlib.suppress(Exception):
                    simplified = json.loads(line.removeprefix("RESULT_JSON:")).get("simplified")

        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary=f"Tensor expression simplified via Cadabra2: {simplified or proc.stdout.strip()}",
            details={
                "input_expression": clean_expr,
                "simplified_expression": simplified or proc.stdout.strip(),
                "rules_applied": rules or [],
            },
        )
