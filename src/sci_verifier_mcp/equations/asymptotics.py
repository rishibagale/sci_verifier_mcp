"""Asymptotic and limiting-case sanity verification using SymPy limits."""

from typing import Any

import sympy

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.equations.parser import parse_math_expression


def _parse_limit_point(val: str | float | int) -> Any:
    """Safely convert limit target string ('0', 'oo', '-oo', 'pi') into a SymPy object."""
    if isinstance(val, (int, float)):
        return sympy.nsimplify(val) if isinstance(val, float) and val.is_integer() else sympy.Number(val)
    clean = str(val).strip()
    if clean in ("oo", "+oo", "inf", "+inf", r"\infty"):
        return sympy.oo
    if clean in ("-oo", "-inf", r"-\infty"):
        return -sympy.oo
    expr, err = parse_math_expression(clean, format="sympy")
    if err or expr is None:
        raise ValueError(f"Invalid limit point '{val}': {err}")
    return expr


def check_limiting_cases(
    expr: str,
    limits: dict[str, str | float | int],
    expected: dict[str, str | float | int] | None = None,
    format: str = "sympy",
    assumptions: dict[str, Any] | None = None,
) -> VerificationResult:
    """Evaluate symbolic limits across boundary regimes and compare against expected scaling/values."""
    parsed, err = parse_math_expression(expr, format=format, assumptions=assumptions)
    if err or parsed is None:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Failed to parse expression: {err}",
            details={"input": expr, "error": err}
        )

    if not limits:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Provide at least one variable limit in 'limits' (e.g. {'x': '0'}).",
            details={}
        )

    computed_limits: dict[str, str] = {}
    mismatches: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for var_name, target_raw in limits.items():
        sym = sympy.Symbol(var_name)
        matching_syms = [s for s in parsed.free_symbols if s.name == var_name]
        if matching_syms:
            sym = matching_syms[0]

        try:
            target_pt = _parse_limit_point(target_raw)
            lim_val = sympy.limit(parsed, sym, target_pt)
            computed_limits[var_name] = str(lim_val)

            if expected and var_name in expected:
                exp_raw = expected[var_name]
                exp_pt = _parse_limit_point(exp_raw)
                diff = sympy.simplify(lim_val - exp_pt)
                if diff != 0:
                    mismatches[var_name] = {
                        "target": str(target_pt),
                        "computed_limit": str(lim_val),
                        "expected_limit": str(exp_pt),
                    }
        except Exception as e:
            errors[var_name] = str(e)

    details = {
        "expression": str(parsed),
        "limits_tested": {k: str(v) for k, v in limits.items()},
        "computed_limits": computed_limits,
        "mismatches": mismatches,
        "errors": errors,
    }

    if errors and not computed_limits:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Limit evaluation failed: {errors}",
            details=details,
        )

    if mismatches:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Limiting case mismatch for variable(s): {', '.join(mismatches.keys())}.",
            details=details,
        )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary=(
            f"Evaluated {len(computed_limits)} limiting regime(s)"
            + (" and all matched expected values." if expected else ".")
        ),
        details=details,
    )
