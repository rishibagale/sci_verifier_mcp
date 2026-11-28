"""SMT inequality, domain constraint, and logical claim verification using Z3."""

import ast
from typing import Any

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    z3 = None
    Z3_AVAILABLE = False

from sci_verifier_mcp.core.schemas import VerificationResult, VerificationStatus


def ast_to_z3(node: ast.AST, z3_vars: dict[str, Any]) -> Any:
    """Convert a safe AST expression into a Z3 arithmetic/boolean expression."""
    if isinstance(node, ast.Expression):
        return ast_to_z3(node.body, z3_vars)

    elif isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return z3.BoolVal(node.value)
        elif isinstance(node.value, int):
            return z3.IntVal(node.value)
        elif isinstance(node.value, float):
            return z3.RealVal(node.value)
        else:
            raise ValueError(f"Unsupported constant value: {node.value!r}")

    elif isinstance(node, ast.Name):
        if node.id in z3_vars:
            return z3_vars[node.id]
        raise ValueError(f"Undeclared variable '{node.id}' in expression.")

    elif isinstance(node, ast.UnaryOp):
        operand = ast_to_z3(node.operand, z3_vars)
        if isinstance(node.op, ast.USub):
            return -operand
        elif isinstance(node.op, ast.UAdd):
            return operand
        elif isinstance(node.op, ast.Not):
            return z3.Not(operand)
        raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")

    elif isinstance(node, ast.BinOp):
        left = ast_to_z3(node.left, z3_vars)
        right = ast_to_z3(node.right, z3_vars)
        if isinstance(node.op, ast.Add):
            return left + right
        elif isinstance(node.op, ast.Sub):
            return left - right
        elif isinstance(node.op, ast.Mult):
            return left * right
        elif isinstance(node.op, ast.Div):
            return left / right
        elif isinstance(node.op, ast.Pow):
            return left ** right
        raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")

    elif isinstance(node, ast.Compare):
        left = ast_to_z3(node.left, z3_vars)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("Chained comparisons are not supported; use explicit logical 'and'.")
        op = node.ops[0]
        right = ast_to_z3(node.comparators[0], z3_vars)

        if isinstance(op, ast.Eq):
            return left == right
        elif isinstance(op, ast.NotEq):
            return left != right
        elif isinstance(op, ast.Lt):
            return left < right
        elif isinstance(op, ast.LtE):
            return left <= right
        elif isinstance(op, ast.Gt):
            return left > right
        elif isinstance(op, ast.GtE):
            return left >= right
        raise ValueError(f"Unsupported comparison operator: {type(op).__name__}")

    elif isinstance(node, ast.BoolOp):
        values = [ast_to_z3(v, z3_vars) for v in node.values]
        if isinstance(node.op, ast.And):
            return z3.And(*values)
        elif isinstance(node.op, ast.Or):
            return z3.Or(*values)
        raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")

    raise ValueError(f"Unsupported AST node type: {type(node).__name__}")


def parse_safe_expr_to_z3(expr_str: str, z3_vars: dict[str, Any]) -> Any:
    """Safely parse a string into a Z3 expression via AST."""
    tree = ast.parse(expr_str.strip(), mode="eval")
    return ast_to_z3(tree, z3_vars)


def build_z3_formula(claim: dict[str, Any], z3_vars: dict[str, Any]) -> Any:
    """Recursively build a Z3 boolean formula from a structured claim dictionary."""
    if not isinstance(claim, dict):
        raise ValueError("Claim must be a dictionary.")

    op = claim.get("op", "").lower()

    if op in ("<", "<=", ">", ">=", "==", "!="):
        left_val = claim.get("left")
        right_val = claim.get("right")
        if left_val is None or right_val is None:
            raise ValueError(f"Comparison '{op}' requires both 'left' and 'right' arguments.")

        left_z3 = parse_safe_expr_to_z3(str(left_val), z3_vars) if isinstance(left_val, (str, int, float)) else build_z3_formula(left_val, z3_vars)
        right_z3 = parse_safe_expr_to_z3(str(right_val), z3_vars) if isinstance(right_val, (str, int, float)) else build_z3_formula(right_val, z3_vars)

        cmp_ops = {
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        return cmp_ops[op](left_z3, right_z3)

    elif op == "implies":
        premise = claim.get("premise")
        conclusion = claim.get("conclusion")
        if premise is None or conclusion is None:
            raise ValueError("'implies' requires both 'premise' and 'conclusion'.")
        p_z3 = parse_safe_expr_to_z3(str(premise), z3_vars) if isinstance(premise, str) else build_z3_formula(premise, z3_vars)
        c_z3 = parse_safe_expr_to_z3(str(conclusion), z3_vars) if isinstance(conclusion, str) else build_z3_formula(conclusion, z3_vars)
        return z3.Implies(p_z3, c_z3)

    elif op == "and":
        args = claim.get("args", [])
        z3_args = [
            parse_safe_expr_to_z3(str(a), z3_vars) if isinstance(a, str) else build_z3_formula(a, z3_vars)
            for a in args
        ]
        return z3.And(*z3_args)

    elif op == "or":
        args = claim.get("args", [])
        z3_args = [
            parse_safe_expr_to_z3(str(a), z3_vars) if isinstance(a, str) else build_z3_formula(a, z3_vars)
            for a in args
        ]
        return z3.Or(*z3_args)

    elif op == "not":
        arg = claim.get("arg")
        if arg is None:
            raise ValueError("'not' requires an 'arg' argument.")
        arg_z3 = parse_safe_expr_to_z3(str(arg), z3_vars) if isinstance(arg, str) else build_z3_formula(arg, z3_vars)
        return z3.Not(arg_z3)

    elif "expr" in claim:
        return parse_safe_expr_to_z3(claim["expr"], z3_vars)

    raise ValueError(f"Unknown or unsupported claim operator '{op}'.")


def check_smt_claim(
    claim: dict[str, Any],
    variables: dict[str, str],
    timeout_ms: int = 5000
) -> VerificationResult:
    """Prove or refute a mathematical/logical claim using Z3 via safe AST parsing."""
    if not Z3_AVAILABLE or z3 is None:
        return VerificationResult(
            status=VerificationStatus.UNAVAILABLE,
            summary="Z3 theorem prover is not installed on this system.",
            details={"help": "Install z3-solver via: pip install z3-solver"}
        )

    # 1. Instantiate Z3 variables based on declared types
    z3_vars: dict[str, Any] = {}
    for var_name, var_type in variables.items():
        vtype = var_type.lower()
        if vtype in ("real", "float"):
            z3_vars[var_name] = z3.Real(var_name)
        elif vtype in ("int", "integer"):
            z3_vars[var_name] = z3.Int(var_name)
        elif vtype in ("bool", "boolean"):
            z3_vars[var_name] = z3.Bool(var_name)
        else:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                summary=f"Unknown variable type '{var_type}' for variable '{var_name}'. Supported: real, int, bool.",
                details={"variable": var_name, "type": var_type}
            )

    # 2. Build formula
    try:
        formula = build_z3_formula(claim, z3_vars)
    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.ERROR,
            summary=f"Failed to build SMT formula from claim: {e}",
            details={"error": str(e), "claim": claim}
        )

    # 3. Setup solver with timeout
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)

    # To verify that the claim holds universally, we check if its negation is UNSAT
    solver.add(z3.Not(formula))
    check_result = solver.check()

    if check_result == z3.unsat:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            summary="Claim holds universally across the declared domain (negation is UNSAT).",
            details={"claim": claim, "variables": variables}
        )

    elif check_result == z3.sat:
        model = solver.model()
        counterexample: dict[str, str] = {}
        for k, v in z3_vars.items():
            val = model.eval(v, model_completion=True)
            counterexample[k] = str(val)

        return VerificationResult(
            status=VerificationStatus.FAILED,
            summary="Claim refuted. Found concrete counterexample model.",
            details={
                "counterexample": counterexample,
                "claim": claim,
                "variables": variables,
            }
        )

    elif check_result == z3.unknown:
        reason = solver.reason_unknown()
        if "timeout" in reason.lower():
            return VerificationResult(
                status=VerificationStatus.TIMEOUT,
                summary=f"SMT solver timed out after {timeout_ms}ms.",
                details={"reason": reason, "claim": claim}
            )
        return VerificationResult(
            status=VerificationStatus.PARTIAL_MATCH,
            summary=f"SMT solver returned unknown: {reason}",
            details={"reason": reason, "claim": claim}
        )

    return VerificationResult(
        status=VerificationStatus.ERROR,
        summary="Unexpected solver outcome.",
        details={"result": str(check_result)}
    )
