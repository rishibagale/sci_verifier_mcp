"""Safe parsing of mathematical expressions from LaTeX and SymPy strings."""

from typing import Any

import sympy
from sympy.parsing.latex import parse_latex
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from sci_verifier_mcp.core.security import validate_safe_math_ast

TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)


def create_symbols_with_assumptions(
    symbol_names: set[str],
    assumptions: dict[str, Any] | None = None
) -> dict[str, sympy.Symbol]:
    """Instantiate SymPy symbols with specified mathematical assumptions."""
    assumptions = assumptions or {}
    symbols_dict: dict[str, sympy.Symbol] = {}

    for name in symbol_names:
        sym_assumptions: dict[str, bool] = {}
        if name in assumptions:
            val = assumptions[name]
            if isinstance(val, dict):
                sym_assumptions = {k: bool(v) for k, v in val.items()}
            elif isinstance(val, str):
                sym_assumptions = {val: True}
            elif isinstance(val, (list, tuple)):
                sym_assumptions = {str(item): True for item in val}
        symbols_dict[name] = sympy.Symbol(name, **sym_assumptions)

    return symbols_dict


def parse_math_expression(
    expr_str: str,
    format: str = "latex",
    assumptions: dict[str, Any] | None = None
) -> tuple[sympy.Expr | None, str | None]:
    """Parse a math expression string into a SymPy expression safely.
    
    Returns:
        (sympy_expr, error_message)
    """
    clean_str = expr_str.strip()
    if not clean_str:
        return None, "Empty expression provided."

    if format.lower() == "latex":
        try:
            parsed = parse_latex(clean_str)
            if assumptions:
                free_sym_names = {s.name for s in parsed.free_symbols}
                sub_map = create_symbols_with_assumptions(free_sym_names, assumptions)
                parsed = parsed.subs({sympy.Symbol(k): v for k, v in sub_map.items()})
            return parsed, None
        except Exception as e:
            return None, f"LaTeX parsing failed: {type(e).__name__}: {str(e)}"

    elif format.lower() == "sympy":
        try:
            # First pass: strict AST whitelist security validation
            validate_safe_math_ast(clean_str)
        except ValueError as e:
            return None, f"Security/Validation check failed: {str(e)}"

        try:
            # Gather symbols
            temp_expr = parse_expr(clean_str, transformations=TRANSFORMATIONS, evaluate=False)
            free_sym_names = {s.name for s in temp_expr.free_symbols}
            local_dict = create_symbols_with_assumptions(free_sym_names, assumptions)

            # Second pass: instantiate with proper symbols
            parsed = parse_expr(clean_str, local_dict=local_dict, transformations=TRANSFORMATIONS)
            return parsed, None
        except Exception as e:
            return None, f"SymPy parsing failed: {type(e).__name__}: {str(e)}"

    else:
        return None, f"Unsupported format '{format}'. Use 'latex' or 'sympy'."
