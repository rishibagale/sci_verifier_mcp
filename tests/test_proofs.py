"""Unit tests for Lean 4 proof verification and Cadabra2 tensor simplifier."""

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.proofs.lean_runner import verify_lean4_proof
from sci_verifier_mcp.proofs.tensor_simplifier import simplify_tensor_expr


def test_lean_cheat_tactics_detection():
    cheat_code_sorry = r"""
    theorem FermatLastTheorem : \forall n > 2, \not \exists x y z, x^n + y^n = z^n := by
      sorry
    """
    res = verify_lean4_proof(cheat_code_sorry)
    assert res.status == VerificationStatus.FAILED
    assert "unproven placeholder" in res.summary.lower()

    cheat_code_admit = "theorem trivial_proof : True := by admit"
    res2 = verify_lean4_proof(cheat_code_admit)
    assert res2.status == VerificationStatus.FAILED


def test_lean_axiom_rejection():
    axiom_code = """
    axiom Falsehood : 0 = 1
    theorem invalid_claim : 0 = 1 := Falsehood
    """
    res = verify_lean4_proof(axiom_code)
    assert res.status == VerificationStatus.FAILED
    assert "axiom" in res.summary.lower()


def test_lean_unavailable_or_sandboxed():
    # Valid trivial theorem code
    code = "theorem self_id (p : Prop) : p -> p := fun hp => hp"
    res = verify_lean4_proof(code)
    # If Lean is installed locally, it will verify; if not, it must return UNAVAILABLE without crashing!
    assert res.status in (VerificationStatus.VERIFIED, VerificationStatus.UNAVAILABLE)


def test_cadabra_unavailable_fallback():
    res = simplify_tensor_expr("R_{a b c d} R^{a b c d}")
    assert res.status in (VerificationStatus.UNAVAILABLE, VerificationStatus.PARTIAL_MATCH, VerificationStatus.VERIFIED)
    if res.status == VerificationStatus.UNAVAILABLE:
        assert "Cadabra2" in res.summary
        assert "https://cadabra.science" in res.details["help"]
