"""AST security and execution safety guards."""

import ast
from typing import Any

# Whitelisted AST node types for safe mathematical expressions
ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Constant,
    ast.Name,
    ast.Call,
    ast.Load,
)

# Whitelisted mathematical function names
ALLOWED_MATH_FUNCTIONS = {
    "sin", "cos", "tan", "cot", "sec", "csc",
    "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "exp", "log", "ln", "sqrt", "cbrt", "abs",
    "pi", "E", "I", "oo",
    "gamma", "factorial",
}


class ASTSecurityVisitor(ast.NodeVisitor):
    """Walks an AST and ensures only whitelisted safe mathematical operations exist."""

    def generic_visit(self, node: ast.AST) -> Any:
        if not isinstance(node, ALLOWED_AST_NODES):
            raise ValueError(
                f"Disallowed AST element '{type(node).__name__}'. Only elementary math expressions are permitted."
            )
        super().generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct named function calls (e.g. sin(x)) are allowed.")
        if node.func.id not in ALLOWED_MATH_FUNCTIONS:
            raise ValueError(
                f"Function '{node.func.id}' is not in the permitted mathematical function list."
            )
        super().generic_visit(node)


def validate_safe_math_ast(expr_str: str) -> None:
    """Parse and validate that an expression contains only safe mathematical nodes.
    
    Raises ValueError if expression contains unsafe or non-mathematical constructs.
    """
    try:
        tree = ast.parse(expr_str, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Syntax error in expression: {e}") from e

    visitor = ASTSecurityVisitor()
    visitor.visit(tree)
