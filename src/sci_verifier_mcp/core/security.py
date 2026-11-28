"""AST security and execution safety guards."""

import ast
import concurrent.futures
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class ExecutionTimeoutError(TimeoutError):
    """Raised when a symbolic or numerical check exceeds its wall-clock guard."""

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

    def __init__(
        self,
        extra_allowed_funcs: set[str] | None = None,
        extra_allowed_nodes: tuple[type[ast.AST], ...] = (),
    ):
        self.allowed_funcs = ALLOWED_MATH_FUNCTIONS | (extra_allowed_funcs or set())
        self.allowed_nodes = ALLOWED_AST_NODES + extra_allowed_nodes

    def generic_visit(self, node: ast.AST) -> Any:
        if not isinstance(node, self.allowed_nodes):
            raise ValueError(
                f"Disallowed AST element '{type(node).__name__}'. Only elementary math expressions are permitted."
            )
        super().generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct named function calls (e.g. sin(x)) are allowed.")
        if node.func.id not in self.allowed_funcs:
            raise ValueError(
                f"Function '{node.func.id}' is not in the permitted mathematical function list."
            )
        super().generic_visit(node)


def validate_safe_math_ast(
    expr_str: str,
    extra_allowed_funcs: set[str] | None = None,
    extra_allowed_nodes: tuple[type[ast.AST], ...] = (),
) -> None:
    """Parse and validate that an expression contains only safe mathematical nodes.
    
    Raises ValueError if expression contains unsafe or non-mathematical constructs.
    """
    try:
        tree = ast.parse(expr_str, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Syntax error in expression: {e}") from e

    visitor = ASTSecurityVisitor(
        extra_allowed_funcs=extra_allowed_funcs,
        extra_allowed_nodes=extra_allowed_nodes,
    )
    visitor.visit(tree)


def run_with_timeout(
    fn: Callable[..., T],
    timeout_seconds: float,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute a callable under a strict wall-clock timeout guard."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise ExecutionTimeoutError(
            f"Operation exceeded wall-clock timeout of {timeout_seconds:.1f}s."
        ) from exc
    finally:
        executor.shutdown(wait=False)
