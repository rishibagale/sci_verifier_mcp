"""ODE/PDE candidate solution and boundary-condition verification using SymPy."""

import ast
import random
import re
from typing import Any

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from sci_verifier_mcp.core import config
from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.core.security import ExecutionTimeoutError, run_with_timeout, validate_safe_math_ast

TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)


def _normalize_prime_notation(text: str, dep_var: str, indep_vars: list[str]) -> str:
    """Convert prime shorthand like y'(x) or y''(x) into Derivative(y(x), x, n) when 1D."""
    if len(indep_vars) != 1:
        return text
    var = indep_vars[0]
    pattern = re.compile(rf"\b{re.escape(dep_var)}('+)(?:\(\s*([^()]+?)\s*\))?")

    def repl(m: re.Match[str]) -> str:
        order = len(m.group(1))
        arg = m.group(2) or var
        if order == 1:
            return f"Derivative({dep_var}({arg}), {var})"
        return f"Derivative({dep_var}({arg}), ({var}, {order}))"

    return pattern.sub(repl, text)


def _safe_parse_ode_expr(
    expr_str: str,
    dep_var: str,
    indep_vars: list[str],
    extra_funcs: set[str] | None = None
) -> sympy.Expr:
    """Safely parse a differential expression with AST whitelist validation."""
    normalized = _normalize_prime_notation(expr_str.strip(), dep_var, indep_vars)
    allowed = {"Derivative", "diff", dep_var} | (extra_funcs or set())
    validate_safe_math_ast(normalized, extra_allowed_funcs=allowed, extra_allowed_nodes=(ast.Tuple,))

    local_dict: dict[str, Any] = {
        "Derivative": sympy.Derivative,
        "diff": sympy.diff,
        dep_var: sympy.Function(dep_var),
    }
    for v in indep_vars:
        local_dict[v] = sympy.Symbol(v)

    return parse_expr(normalized, local_dict=local_dict, transformations=TRANSFORMATIONS)


def verify_ode_pde_solution(
    equation: str,
    candidate_solution: str,
    dependent_var: str = "y",
    independent_vars: list[str] | None = None,
    boundary_conditions: dict[str, Any] | None = None
) -> VerificationResult:
    """Verify whether a candidate expression satisfies an ODE/PDE and optional boundary conditions."""
    indep_vars = independent_vars or ["x"]
    clean_eq = equation.strip()
    clean_cand = candidate_solution.strip()

    if not clean_eq or not clean_cand:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Both 'equation' and 'candidate_solution' must be non-empty.",
            details={}
        )

    # Split equation around '=' (or treat as residual = 0)
    if "=" in clean_eq:
        parts = clean_eq.split("=")
        if len(parts) != 2:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary="Equation must contain at most one '=' sign.",
                details={"equation": clean_eq}
            )
        lhs_str, rhs_str = parts[0].strip(), parts[1].strip()
    else:
        lhs_str, rhs_str = clean_eq, "0"

    # Strip optional 'y(x) =' prefix on candidate_solution
    if "=" in clean_cand:
        cparts = clean_cand.split("=", 1)
        cand_rhs = cparts[1].strip()
    else:
        cand_rhs = clean_cand

    try:
        lhs_expr = _safe_parse_ode_expr(lhs_str, dependent_var, indep_vars)
        rhs_expr = _safe_parse_ode_expr(rhs_str, dependent_var, indep_vars)
        cand_expr = _safe_parse_ode_expr(cand_rhs, dependent_var, indep_vars)
    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Failed to parse differential equation or candidate solution: {e}",
            details={"error": str(e)}
        )

    # Substitute dependent function f(x1, ...) -> candidate expression
    indep_syms = [sympy.Symbol(v) for v in indep_vars]
    dep_call = sympy.Function(dependent_var)(*indep_syms)
    residual = (lhs_expr - rhs_expr).subs(dep_call, cand_expr).doit()

    # Check symbolic zero residual with wall-clock timeout guard
    symbolic_verified = False
    for method in (sympy.simplify, sympy.expand, sympy.trigsimp):
        try:
            if run_with_timeout(method, config.DEFAULT_SYMBOLIC_TIMEOUT, residual) == 0:
                symbolic_verified = True
                break
        except ExecutionTimeoutError:
            return VerificationResult(
                status=VerificationStatus.TIMEOUT,
                summary=f"ODE/PDE symbolic residual check timed out after {config.DEFAULT_SYMBOLIC_TIMEOUT}s.",
                details={"timeout_seconds": config.DEFAULT_SYMBOLIC_TIMEOUT}
            )
        except Exception:
            continue

    # Randomized numerical residual check if symbolic wasn't exact zero
    numerical_failure: dict[str, Any] | None = None
    if not symbolic_verified:
        free_syms = sorted(residual.free_symbols, key=lambda s: s.name)
        if not free_syms:
            try:
                val = complex(residual.evalf())
                if abs(val) < 1e-9:
                    symbolic_verified = True
                else:
                    numerical_failure = {"residual": str(val)}
            except Exception as e:
                return VerificationResult(
                    status=VerificationStatus.ERROR,
                    summary=f"Residual evaluation failed: {e}",
                    details={"error": str(e)}
                )
        else:
            rng = random.Random(42)
            tested = 0
            for _ in range(8):
                subs = {s: rng.uniform(0.5, 3.5) for s in free_syms}
                try:
                    val = complex(residual.evalf(subs=subs))
                    tested += 1
                    if abs(val) > 1e-6:
                        numerical_failure = {
                            "sample_point": {k.name: v for k, v in subs.items()},
                            "residual_value": val.real if val.imag == 0 else str(val),
                        }
                        break
                except Exception:
                    continue
            if numerical_failure is None and tested > 0:
                symbolic_verified = True

    if numerical_failure is not None or not symbolic_verified:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary="Candidate solution does NOT satisfy the differential equation.",
            details={
                "residual_expression": str(residual),
                "counterexample": numerical_failure,
            }
        )

    # Check optional boundary/initial conditions e.g. {"y(0)": 1, "y'(0)": 0}
    bc_failures: dict[str, Any] = {}
    if boundary_conditions:
        prime_bc_re = re.compile(rf"^{re.escape(dependent_var)}('+)\(\s*([^()]+)\s*\)$")
        for bc_lhs_str, bc_expected in boundary_conditions.items():
            try:
                bc_clean = str(bc_lhs_str).strip()
                prime_m = prime_bc_re.match(bc_clean)
                if prime_m and len(indep_syms) == 1:
                    order = len(prime_m.group(1))
                    pt_expr = _safe_parse_ode_expr(prime_m.group(2), dependent_var, indep_vars)
                    bc_eval = sympy.diff(cand_expr, indep_syms[0], order).subs(indep_syms[0], pt_expr)
                else:
                    bc_lhs = _safe_parse_ode_expr(bc_clean, dependent_var, indep_vars)
                    if bc_lhs.func == sympy.Function(dependent_var):
                        pt_subs = dict(zip(indep_syms, bc_lhs.args, strict=False))
                        bc_eval = cand_expr.subs(pt_subs)
                    else:
                        bc_eval = bc_lhs.subs(dep_call, cand_expr).doit()

                exp_expr = _safe_parse_ode_expr(str(bc_expected), dependent_var, indep_vars)
                bc_diff = sympy.simplify(bc_eval - exp_expr)
                if bc_diff != 0:
                    try:
                        num_diff = abs(complex(bc_diff.evalf()))
                        if num_diff > 1e-7:
                            bc_failures[bc_lhs_str] = {
                                "expected": str(exp_expr),
                                "actual": str(bc_eval),
                            }
                    except Exception:
                        bc_failures[bc_lhs_str] = {
                            "expected": str(exp_expr),
                            "actual": str(bc_eval),
                        }
            except Exception as e:
                bc_failures[bc_lhs_str] = {"error": str(e)}

    if bc_failures:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary="Candidate satisfies the differential equation, but violates boundary/initial condition(s).",
            details={
                "pde_ode_satisfied": True,
                "boundary_condition_failures": bc_failures,
            }
        )

    return VerificationResult(
        status=VerificationStatus.VERIFIED,
        summary="Candidate solution satisfies the differential equation" + (
            " and all boundary/initial conditions." if boundary_conditions else "."
        ),
        details={
            "equation": clean_eq,
            "candidate_solution": cand_rhs,
            "residual": str(sympy.simplify(residual)),
            "boundary_conditions_checked": len(boundary_conditions or {}),
        }
    )
