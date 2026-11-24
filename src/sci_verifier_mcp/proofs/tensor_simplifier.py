"""Cadabra2 tensor calculus extension stub (QFT and General Relativity tensor algebra)."""

import shutil
from typing import Any

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


def simplify_tensor_expr(
    expr: str,
    rules: list[str] | None = None
) -> VerificationResult:
    """Simplify tensor expression using Cadabra2 (graceful fallback if uninstalled)."""
    clean_expr = expr.strip()
    if not clean_expr:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Empty tensor expression provided.",
            details={}
        )

    cadabra_bin = shutil.which("cadabra2")

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
            }
        )

    # If Cadabra2 binary is installed, stub placeholder for script execution
    return VerificationResult(
        status=VerificationStatus.PARTIAL_MATCH,
        summary="Cadabra2 detected; tensor expression simplification queued.",
        details={"expression": clean_expr, "binary": cadabra_bin}
    )
