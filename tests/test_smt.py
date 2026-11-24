"""Unit tests for Z3 SMT claim verification and counterexample extraction."""

import pytest

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    z3 = None
    Z3_AVAILABLE = False

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.equations.smt import check_smt_claim


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver is not installed")
def test_valid_inequality_implication():
    # x > 0 ==> x + 1 > 1
    claim = {
        "op": "implies",
        "premise": {"op": ">", "left": "x", "right": 0},
        "conclusion": {"op": ">", "left": "x + 1", "right": 1},
    }
    vars_dict = {"x": "real"}
    res = check_smt_claim(claim, vars_dict)
    assert res.status == VerificationStatus.VERIFIED
    assert "Claim holds universally" in res.summary


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver is not installed")
def test_refuted_claim_with_counterexample():
    # Claim: for all real x, x > 0 ==> x**2 > x
    # Fails for 0 < x < 1 (e.g. x = 0.5 => x^2 = 0.25 not > 0.5)
    claim = {
        "op": "implies",
        "premise": {"op": ">", "left": "x", "right": 0},
        "conclusion": {"op": ">", "left": "x * x", "right": "x"},
    }
    vars_dict = {"x": "real"}
    res = check_smt_claim(claim, vars_dict)
    assert res.status == VerificationStatus.FAILED
    assert "counterexample" in res.details
    assert "x" in res.details["counterexample"]
    # Verify counterexample is indeed in (0, 1]
    val_str = res.details["counterexample"]["x"]
    # Z3 can return fraction e.g. "1/2" or float
    if "/" in val_str:
        num, den = val_str.split("/")
        val = float(num) / float(den)
    else:
        val = float(val_str)
    assert 0 < val <= 1


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver is not installed")
def test_integer_domain_constraint():
    # n is integer, n > 1 ==> n >= 2
    claim = {
        "op": "implies",
        "premise": {"op": ">", "left": "n", "right": 1},
        "conclusion": {"op": ">=", "left": "n", "right": 2},
    }
    vars_dict = {"n": "int"}
    res = check_smt_claim(claim, vars_dict)
    assert res.status == VerificationStatus.VERIFIED


@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver is not installed")
def test_conjunction_and_disjunction():
    # (a > 0 and b > 0) ==> (a + b > 0)
    claim = {
        "op": "implies",
        "premise": {
            "op": "and",
            "args": [
                {"op": ">", "left": "a", "right": 0},
                {"op": ">", "left": "b", "right": 0},
            ]
        },
        "conclusion": {"op": ">", "left": "a + b", "right": 0},
    }
    vars_dict = {"a": "real", "b": "real"}
    res = check_smt_claim(claim, vars_dict)
    assert res.status == VerificationStatus.VERIFIED


def test_z3_unavailable_fallback():
    if not Z3_AVAILABLE:
        res = check_smt_claim({"op": ">", "left": 1, "right": 0}, {})
        assert res.status == VerificationStatus.UNAVAILABLE
