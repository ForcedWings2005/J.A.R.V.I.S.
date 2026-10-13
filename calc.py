"""The calculate tool: exact arithmetic without eval().

The expression is parsed and only numbers, the operators below, a few math
functions and pi/e are allowed. Exponents and results are capped so a request
like (10**1000)**1000 cannot hang the server.
"""
import ast
import math
import operator

from tools import tool

OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "abs": abs, "round": round,
}
CONSTS = {"pi": math.pi, "e": math.e}
MAX_RESULT = 10 ** 300  # stops runaway numbers like (10**1000)**1000


class TooLarge(Exception):
    pass


def _check(value):
    if abs(value) > MAX_RESULT:
        raise TooLarge
    return value


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in CONSTS:
        return CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise TooLarge
        return _check(OPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS:
        return _check(FUNCS[node.func.id](*[_eval(a) for a in node.args]))
    raise ValueError("unsupported expression")


@tool("Evaluate a math expression exactly, for example '15 * 23 + 7' or 'sqrt(144) / 3'. Use for any arithmetic beyond trivial.",
      expression={"type": "string"})
def calculate(expression: str) -> str:
    try:
        result = _eval(ast.parse(expression, mode="eval").body)
    except ZeroDivisionError:
        return "Error: division by zero."
    except (TooLarge, OverflowError):
        return "Error: the number is too large to work with."
    except Exception:
        return "Error: could not evaluate that. Use plain numbers and operators like + - * / ** and functions like sqrt()."
    if isinstance(result, float):
        result = round(result, 10)
    return f"{expression} = {result}"
