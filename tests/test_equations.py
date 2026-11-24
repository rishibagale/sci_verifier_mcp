"""Unit tests for symbolic and numerical equation equivalence."""

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.equations.equivalence import check_equation_equivalence


def test_identical_expressions():
    res = check_equation_equivalence("x + 1", "x + 1", format="sympy")
    assert res.status == VerificationStatus.VERIFIED
    assert "Identical" in res.summary


def test_symbolic_polynomial_equivalence():
    res = check_equation_equivalence("(x + y)**2", "x**2 + 2*x*y + y**2", format="sympy")
    assert res.status == VerificationStatus.VERIFIED


def test_trig_identity_latex():
    # \sin^2(x) + \cos^2(x) = 1
    res = check_equation_equivalence(r"\sin^2(x) + \cos^2(x)", "1", format="latex")
    assert res.status == VerificationStatus.VERIFIED


def test_broken_algebra_counterexample():
    # Sign error: (x - y)^2 != x^2 - 2xy - y^2
    res = check_equation_equivalence("(x - y)**2", "x**2 - 2*x*y - y**2", format="sympy")
    assert res.status == VerificationStatus.FAILED
    assert "counterexample" in res.details
    assert "sample_point" in res.details["counterexample"]
    assert "absolute_difference" in res.details["counterexample"]


def test_latex_parsing_error_diagnostic():
    # Malformed LaTeX with unmatched brackets
    res = check_equation_equivalence(r"\frac{x}{", "x", format="latex")
    assert res.status == VerificationStatus.ERROR
    assert "LaTeX parsing failed" in res.summary


def test_constant_expressions_inequality():
    res = check_equation_equivalence("2 + 2", "5", format="sympy")
    assert res.status == VerificationStatus.FAILED
    assert "Constant expressions are not equal" in res.summary
