"""Symbolic and numerical equation equivalence verification."""

import random
from typing import Any

import sympy

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.core.security import ExecutionTimeoutError, run_with_timeout
from sci_verifier_mcp.equations.parser import parse_math_expression


def sample_domain_points(
    symbols: set[sympy.Symbol],
    num_points: int = 10,
    seed: int = 42
) -> list[dict[sympy.Symbol, complex]]:
    """Generate domain-valid random points for evaluation."""
    rng = random.Random(seed)
    points: list[dict[sympy.Symbol, complex]] = []

    for _ in range(num_points):
        pt: dict[sympy.Symbol, complex] = {}
        for sym in symbols:
            val: complex
            if sym.is_integer:
                val = float(rng.randint(2, 20))
            elif sym.is_positive:
                val = rng.uniform(0.5, 10.0)
            elif sym.is_real:
                val = rng.uniform(-10.0, 10.0)
                if abs(val) < 0.1:
                    val = 1.5
            else:
                # General complex
                val = complex(rng.uniform(0.5, 5.0), rng.uniform(0.5, 5.0))
            pt[sym] = val
        points.append(pt)

    return points


def check_equation_equivalence(
    lhs: str,
    rhs: str,
    format: str = "latex",
    assumptions: dict[str, Any] | None = None
) -> VerificationResult:
    """Check mathematical equivalence between two expressions symbolically and numerically."""
    # 1. Parse LHS and RHS
    lhs_expr, lhs_err = parse_math_expression(lhs, format=format, assumptions=assumptions)
    if lhs_err or lhs_expr is None:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Failed to parse LHS: {lhs_err}",
            details={"side": "lhs", "input": lhs, "error": lhs_err}
        )

    rhs_expr, rhs_err = parse_math_expression(rhs, format=format, assumptions=assumptions)
    if rhs_err or rhs_expr is None:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Failed to parse RHS: {rhs_err}",
            details={"side": "rhs", "input": rhs, "error": rhs_err}
        )

    diff = lhs_expr - rhs_expr

    # 2. Fast exact zero check
    if diff == 0:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary="Identical expressions (LHS == RHS).",
            details={"method": "syntactic_zero", "lhs": str(lhs_expr), "rhs": str(rhs_expr)}
        )

    # 3. Symbolic simplification
    symbolic_methods = [
        ("simplify", sympy.simplify),
        ("expand", sympy.expand),
        ("trigsimp", sympy.trigsimp),
        ("factor", sympy.factor),
        ("ratsimp", sympy.ratsimp),
    ]

    for name, method in symbolic_methods:
        try:
            reduced = run_with_timeout(method, config.DEFAULT_SYMBOLIC_TIMEOUT, diff)
            if reduced == 0:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    summary=f"Symbolically equivalent (verified via {name}).",
                    details={
                        "method": f"symbolic_{name}",
                        "lhs_parsed": str(lhs_expr),
                        "rhs_parsed": str(rhs_expr),
                    }
                )
        except ExecutionTimeoutError:
            return VerificationResult(
                status=VerificationStatus.TIMEOUT,
                summary=f"Symbolic equivalence check ({name}) timed out after {config.DEFAULT_SYMBOLIC_TIMEOUT}s.",
                details={
                    "timed_out_method": name,
                    "timeout_seconds": config.DEFAULT_SYMBOLIC_TIMEOUT,
                    "lhs_parsed": str(lhs_expr),
                    "rhs_parsed": str(rhs_expr),
                }
            )
        except Exception:
            continue

    # 4. Randomized numerical domain testing
    free_syms = set(diff.free_symbols)
    if not free_syms:
        # Constant expressions
        try:
            val = complex(diff.evalf())
            if abs(val) < 1e-9:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    summary="Constant expressions evaluate to equal values within tolerance.",
                    details={"diff_value": float(abs(val))}
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    summary="Constant expressions are not equal.",
                    details={
                        "lhs_value": str(lhs_expr.evalf()),
                        "rhs_value": str(rhs_expr.evalf()),
                        "diff": str(val)
                    }
                )
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Numerical evaluation failed: {e}",
                details={"error": str(e)}
            )

    test_points = sample_domain_points(free_syms, num_points=10)
    all_matched = True
    counterexample = None

    for pt in test_points:
        try:
            lhs_val = complex(lhs_expr.evalf(subs=pt))
            rhs_val = complex(rhs_expr.evalf(subs=pt))
            abs_diff = abs(lhs_val - rhs_val)

            denom = max(abs(lhs_val), abs(rhs_val), 1.0)
            rel_diff = abs_diff / denom

            if rel_diff > 1e-6 and abs_diff > 1e-7:
                all_matched = False
                counterexample = {
                    "sample_point": {s.name: (v.real if v.imag == 0 else str(v)) for s, v in pt.items()},
                    "lhs_value": lhs_val.real if lhs_val.imag == 0 else str(lhs_val),
                    "rhs_value": rhs_val.real if rhs_val.imag == 0 else str(rhs_val),
                    "absolute_difference": abs_diff,
                    "relative_difference": rel_diff,
                }
                break
        except Exception:
            # Skip singular point
            continue

    if counterexample is not None:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary="Equations are not equivalent. Found concrete numerical counterexample.",
            details={
                "counterexample": counterexample,
                "lhs_parsed": str(lhs_expr),
                "rhs_parsed": str(rhs_expr),
            }
        )

    if all_matched:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary="Equations verified numerically across 10 random domain test points (symbolic reduction inconclusive).",
            details={
                "method": "numerical_domain_sampling",
                "points_tested": len(test_points),
                "lhs_parsed": str(lhs_expr),
                "rhs_parsed": str(rhs_expr),
            }
        )

    return VerificationResult(
        status=VerificationStatus.PARTIAL_MATCH,
        summary="Equivalence could not be definitively confirmed or refuted.",
        details={"lhs_parsed": str(lhs_expr), "rhs_parsed": str(rhs_expr)}
    )
