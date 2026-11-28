"""Dimensional analysis verification using Pint supporting SI and natural units."""

import contextlib

import pint
import sympy
from sympy.parsing.sympy_parser import implicit_multiplication_application, parse_expr, standard_transformations

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus
from sci_verifier_mcp.core.security import validate_safe_math_ast

# Initialize Pint UnitRegistry
ureg: pint.UnitRegistry = pint.UnitRegistry()
# Define materials science custom units if not present
with contextlib.suppress(Exception):
    ureg.define("atom = count = atoms")

TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)


def get_term_dimensionality(
    node: sympy.Expr,
    unit_map: dict[str, pint.Unit],
    ureg: pint.UnitRegistry
) -> dict[str, int]:
    """Recursively calculate the dimensionality dictionary of a SymPy expression node."""
    if isinstance(node, sympy.Symbol):
        if node.name in unit_map:
            u = unit_map[node.name]
            return {
                str(k): int(v.real) if isinstance(v, complex) else int(float(v))
                for k, v in u.dimensionality.items()
            }
        else:
            # Dimensionless symbol if not specified
            return {}

    elif isinstance(node, (sympy.Number, sympy.Integer, sympy.Float, sympy.Rational)):
        return {}

    elif isinstance(node, sympy.Mul):
        total_dim: dict[str, int] = {}
        for factor in node.args:
            factor_dim = get_term_dimensionality(factor, unit_map, ureg)
            for k, v in factor_dim.items():
                total_dim[k] = total_dim.get(k, 0) + v
        return {k: v for k, v in total_dim.items() if v != 0}

    elif isinstance(node, sympy.Pow):
        base, exp = node.args
        base_dim = get_term_dimensionality(base, unit_map, ureg)
        if isinstance(exp, (sympy.Integer, sympy.Rational, int, float)):
            exp_val = float(exp)
            scaled = {k: int(round(v * exp_val)) for k, v in base_dim.items()}
            return {k: v for k, v in scaled.items() if v != 0}
        return base_dim

    elif isinstance(node, sympy.Add):
        # All terms in an addition must have identical dimensions
        first_dim = get_term_dimensionality(node.args[0], unit_map, ureg)
        for term in node.args[1:]:
            term_dim = get_term_dimensionality(term, unit_map, ureg)
            if term_dim != first_dim:
                raise ValueError(
                    f"Additive dimensional inconsistency: term '{node.args[0]}' has dimension {first_dim} "
                    f"while term '{term}' has dimension {term_dim}"
                )
        return first_dim

    elif isinstance(node, sympy.Function):
        # Standard transcendental functions require dimensionless arguments and return dimensionless values
        return {}

    return {}


def compute_natural_dimension(dim_dict: dict[str, int]) -> int:
    """Calculate the net energy/mass scaling exponent in natural units (hbar = c = k_B = 1).
    
    [L] = [T] = [M]^-1 => Net mass dimension D = [mass] - [length] - [time] + [temperature].
    """
    m = dim_dict.get("[mass]", 0)
    length = dim_dict.get("[length]", 0)
    t = dim_dict.get("[time]", 0)
    temp = dim_dict.get("[temperature]", 0)
    return m - length - t + temp


def check_dimensional_analysis(
    equation: str,
    symbol_units: dict[str, str],
    unit_system: str = "SI"
) -> VerificationResult:
    """Verify dimensional consistency across all additive terms and both sides of an equation."""
    clean_eq = equation.strip()
    if "=" not in clean_eq:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Equation must contain an '=' sign dividing LHS and RHS.",
            details={"input": equation}
        )

    parts = clean_eq.split("=")
    if len(parts) != 2:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary="Only single-equality equations (LHS = RHS) are currently supported.",
            details={"input": equation}
        )

    lhs_str, rhs_str = parts[0].strip(), parts[1].strip()

    # Parse and validate symbol units
    unit_map: dict[str, pint.Unit] = {}
    for sym, u_str in symbol_units.items():
        try:
            unit_map[sym] = ureg.parse_units(u_str)
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Failed to parse unit '{u_str}' for symbol '{sym}': {e}",
                details={"symbol": sym, "unit": u_str, "error": str(e)}
            )

    # Validate AST safety
    try:
        validate_safe_math_ast(lhs_str)
        validate_safe_math_ast(rhs_str)
    except ValueError as e:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Mathematical expression security validation failed: {e}",
            details={"error": str(e)}
        )

    # Parse expressions into SymPy trees with symbol variables to prevent shadowing SymPy constants (e.g. E, S)
    local_symbols = {sym: sympy.Symbol(sym) for sym in symbol_units}
    try:
        lhs_node = parse_expr(lhs_str, local_dict=local_symbols, transformations=TRANSFORMATIONS)
        rhs_node = parse_expr(rhs_str, local_dict=local_symbols, transformations=TRANSFORMATIONS)
    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Expression parsing error: {e}",
            details={"error": str(e)}
        )

    # Compute LHS and RHS dimensionalities
    try:
        lhs_dim = get_term_dimensionality(lhs_node, unit_map, ureg)
    except ValueError as e:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Dimensional mismatch inside LHS additive terms: {e}",
            details={"side": "lhs", "error": str(e)}
        )

    try:
        rhs_dim = get_term_dimensionality(rhs_node, unit_map, ureg)
    except ValueError as e:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary=f"Dimensional mismatch inside RHS additive terms: {e}",
            details={"side": "rhs", "error": str(e)}
        )

    # Format dimensions for human readability
    lhs_dim_str = " * ".join(f"{k}^{v}" if v != 1 else k for k, v in sorted(lhs_dim.items())) or "[dimensionless]"
    rhs_dim_str = " * ".join(f"{k}^{v}" if v != 1 else k for k, v in sorted(rhs_dim.items())) or "[dimensionless]"

    if unit_system.upper() == "SI":
        if lhs_dim == rhs_dim:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                summary=f"Dimensionally consistent in SI units (dimension: {lhs_dim_str}).",
                details={
                    "unit_system": "SI",
                    "lhs_dimension": lhs_dim,
                    "rhs_dimension": rhs_dim,
                    "dimension_str": lhs_dim_str,
                }
            )
        else:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                summary=f"Dimensional mismatch: LHS has dimension {lhs_dim_str} while RHS has dimension {rhs_dim_str}.",
                details={
                    "unit_system": "SI",
                    "lhs_dimension": lhs_dim,
                    "rhs_dimension": rhs_dim,
                }
            )

    elif unit_system.lower() in ("natural", "natural_units"):
        lhs_nat = compute_natural_dimension(lhs_dim)
        rhs_nat = compute_natural_dimension(rhs_dim)

        if lhs_nat == rhs_nat:
            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                summary=f"Dimensionally consistent in natural units (hbar = c = 1, energy/mass dimension D = {lhs_nat}).",
                details={
                    "unit_system": "natural",
                    "energy_mass_dimension": lhs_nat,
                    "lhs_si_dimension": lhs_dim,
                    "rhs_si_dimension": rhs_dim,
                }
            )
        else:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                summary=(
                    f"Dimensional mismatch in natural units (hbar = c = 1): "
                    f"LHS has energy dimension D = {lhs_nat} while RHS has D = {rhs_nat}."
                ),
                details={
                    "unit_system": "natural",
                    "lhs_natural_dimension": lhs_nat,
                    "rhs_natural_dimension": rhs_nat,
                    "lhs_si_dimension": lhs_dim,
                    "rhs_si_dimension": rhs_dim,
                }
            )

    else:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Unsupported unit system '{unit_system}'. Choose 'SI' or 'natural'.",
            details={"unit_system": unit_system}
        )
