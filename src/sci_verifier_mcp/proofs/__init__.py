"""Formal proof and tensor algebra verification."""

from sci_verifier_mcp.proofs.lean_runner import verify_lean4_proof
from sci_verifier_mcp.proofs.tensor_simplifier import simplify_tensor_expr

__all__ = [
    "verify_lean4_proof",
    "simplify_tensor_expr",
]
