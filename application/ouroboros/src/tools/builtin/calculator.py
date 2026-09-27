import ast
import logging
import operator

from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expression: str) -> int | float:
    """AST-whitelist-based expression evaluation that avoids eval injection."""

    def _eval(node: ast.AST) -> int | float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            return _BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _BIN_OPS:
            return _BIN_OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"unsupported expression: {expression}")

    return _eval(ast.parse(expression, mode="eval"))


class CalculatorTool(BaseTool):
    id = "tool_calculator"
    name = "calculator"
    description = "Evaluate a math expression, supporting + - * / and parentheses"
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": 'Math expression, e.g. "3*8+100"',
            }
        },
        "required": ["expression"],
    }

    async def run(self, expression: str) -> ToolResult:
        try:
            result = _safe_eval(expression)
            return ToolResult(success=True, output=str(result))
        except Exception as exc:  # noqa: BLE001
            logger.warning("calculator eval failed: %s", exc)
            return ToolResult(success=False, output="", error=str(exc))
