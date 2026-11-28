"""Unit tests for ODE/PDE solution checking, asymptotic limits, and simulation invariants."""

from sci_verifier_mcp.core.schemas import VerificationStatus
from sci_verifier_mcp.equations.asymptotics import check_limiting_cases
from sci_verifier_mcp.equations.differential import verify_ode_pde_solution
from sci_verifier_mcp.equations.invariants import verify_simulation_invariants


def test_ode_harmonic_oscillator_with_bcs():
    res = verify_ode_pde_solution(
        equation="y''(x) + y(x) = 0",
        candidate_solution="cos(x) + 2*sin(x)",
        dependent_var="y",
        independent_vars=["x"],
        boundary_conditions={"y(0)": 1, "y'(0)": 2},
    )
    assert res.status == VerificationStatus.VERIFIED


def test_ode_wrong_ansatz_fails():
    res = verify_ode_pde_solution(
        equation="y''(x) + y(x) = 0",
        candidate_solution="exp(x)",
        dependent_var="y",
        independent_vars=["x"],
    )
    assert res.status == VerificationStatus.FAILED


def test_ode_boundary_condition_violation():
    res = verify_ode_pde_solution(
        equation="y''(x) + y(x) = 0",
        candidate_solution="cos(x)",
        dependent_var="y",
        independent_vars=["x"],
        boundary_conditions={"y(0)": 0},  # cos(0) == 1 != 0
    )
    assert res.status == VerificationStatus.FAILED
    assert "boundary" in res.summary.lower()


def test_heat_pde_solution():
    # u_t - u_xx = 0 with u(x, t) = exp(-t) * sin(x)
    res = verify_ode_pde_solution(
        equation="Derivative(u(x, t), t) - Derivative(u(x, t), (x, 2)) = 0",
        candidate_solution="exp(-t) * sin(x)",
        dependent_var="u",
        independent_vars=["x", "t"],
    )
    assert res.status == VerificationStatus.VERIFIED


def test_limiting_cases_valid_and_mismatch():
    ok = check_limiting_cases(
        expr="sin(x) / x",
        limits={"x": "0"},
        expected={"x": "1"},
    )
    assert ok.status == VerificationStatus.VERIFIED
    assert ok.details["computed_limits"]["x"] == "1"

    bad = check_limiting_cases(
        expr="1 / (1 + x)",
        limits={"x": "oo"},
        expected={"x": "1"},  # actual limit is 0
    )
    assert bad.status == VerificationStatus.FAILED
    assert "x" in bad.details["mismatches"]


def test_simulation_invariants_conservation_and_drift():
    ok = verify_simulation_invariants(
        data={"energy": [10.0, 10.0000001, 9.9999999]},
        checks=["conservation"],
        tolerance=1e-5,
    )
    assert ok.status == VerificationStatus.VERIFIED

    drifted = verify_simulation_invariants(
        data={"energy": [10.0, 10.2, 10.5]},
        checks=["conservation"],
        tolerance=1e-4,
    )
    assert drifted.status == VerificationStatus.FAILED


def test_simulation_invariants_prob_psd_and_convergence():
    prob_ok = verify_simulation_invariants(
        data=[[0.2, 0.5, 0.3], [0.1, 0.8, 0.1]],
        checks=["probability_norm"],
    )
    assert prob_ok.status == VerificationStatus.VERIFIED

    psd_bad = verify_simulation_invariants(
        data=[[1.0, 2.0], [2.0, 1.0]],  # eigenvalues 3 and -1
        checks=["psd"],
    )
    assert psd_bad.status == VerificationStatus.FAILED

    conv_ok = verify_simulation_invariants(
        data={"h": [0.1, 0.05, 0.025], "error": [0.01, 0.0025, 0.000625], "expected_order": 2.0},
        checks=["convergence_order"],
    )
    assert conv_ok.status == VerificationStatus.VERIFIED
    assert conv_ok.details["checks"]["convergence_order"]["observed_order"] == 2.0
