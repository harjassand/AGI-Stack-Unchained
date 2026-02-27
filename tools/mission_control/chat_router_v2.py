from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from typing import Literal, Optional


@dataclass(frozen=True)
class ChatDecisionV2:
    kind: Literal["DIRECT_ANSWER", "MISSION"]
    answer_text: Optional[str]
    confidence: Optional[Literal["HIGH", "MED", "LOW"]]
    reason: str


_LEAD_INS = (
    "what is ",
    "what's ",
    "whats ",
    "calculate ",
    "compute ",
    "evaluate ",
    "answer ",
)

_SYMBOLIC_KEYWORDS = ("simplify", "factor", "solve for", "differentiate", "integrate")


def extract_arith_expr_v2(msg: str) -> Optional[str]:
    s = str(msg).strip().lower()

    while True:
        matched = False
        for phrase in _LEAD_INS:
            if s.startswith(phrase):
                s = s[len(phrase) :]
                matched = True
        if not matched:
            break

    s = re.sub(r"\bmultiplied by\b", "*", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdivided by\b", "/", s, flags=re.IGNORECASE)
    s = re.sub(r"\bplus\b", "+", s, flags=re.IGNORECASE)
    s = re.sub(r"\bminus\b", "-", s, flags=re.IGNORECASE)
    s = re.sub(r"\btimes\b", "*", s, flags=re.IGNORECASE)
    s = re.sub(r"\bover\b", "/", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<=\s)x(?=\s)", "*", s, flags=re.IGNORECASE)

    s = re.sub(r"[^0-9\+\-\*\/\(\)\.\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    if re.search(r"\d", s) is None:
        return None
    if re.search(r"[\+\-\*\/]", s) is None:
        return None

    expr = s.replace(" ", "")
    return expr


def safe_eval_arith_decimal(expr: str) -> str:
    src = str(expr).strip()
    if len(src) > 80:
        raise ValueError("arith_expr_too_long")

    tree = ast.parse(src, mode="eval")

    with localcontext() as ctx:
        ctx.prec = 50
        result = _eval_ast_decimal(tree)

    if result == result.to_integral_value():
        return str(result.to_integral_value())

    text = format(result.normalize(), "f")
    text = text.rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text


def decide_chat_route_v2(message: str) -> ChatDecisionV2:
    expr = extract_arith_expr_v2(message)
    if expr is not None:
        try:
            ans = safe_eval_arith_decimal(expr)
        except Exception as e:  # noqa: BLE001
            return ChatDecisionV2(
                kind="MISSION",
                answer_text=None,
                confidence=None,
                reason=f"arith_eval_failed:{type(e).__name__}",
            )
        return ChatDecisionV2(
            kind="DIRECT_ANSWER",
            answer_text=ans,
            confidence="HIGH",
            reason="arith_ok",
        )

    if _is_symbolic_request(message):
        if os.getenv("MC_ENABLE_SYMBOLIC") != "1":
            return ChatDecisionV2(
                kind="MISSION",
                answer_text=None,
                confidence=None,
                reason="symbolic_disabled",
            )

        symbolic_answer = _try_symbolic_answer(message)
        if symbolic_answer is not None:
            return ChatDecisionV2(
                kind="DIRECT_ANSWER",
                answer_text=symbolic_answer,
                confidence="MED",
                reason="symbolic_ok",
            )
        return ChatDecisionV2(
            kind="MISSION",
            answer_text=None,
            confidence=None,
            reason="symbolic_unresolved",
        )

    return ChatDecisionV2(kind="MISSION", answer_text=None, confidence=None, reason="no_arith_expr")


def _eval_ast_decimal(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_ast_decimal(node.body)

    if isinstance(node, ast.BinOp):
        lhs = _eval_ast_decimal(node.left)
        rhs = _eval_ast_decimal(node.right)
        if isinstance(node.op, ast.Add):
            return lhs + rhs
        if isinstance(node.op, ast.Sub):
            return lhs - rhs
        if isinstance(node.op, ast.Mult):
            return lhs * rhs
        if isinstance(node.op, ast.Div):
            if rhs == 0:
                raise ZeroDivisionError("division by zero")
            try:
                return lhs / rhs
            except (DivisionByZero, InvalidOperation) as exc:
                raise ZeroDivisionError("division by zero") from exc
        raise ValueError("unsupported_binop")

    if isinstance(node, ast.UnaryOp):
        value = _eval_ast_decimal(node.operand)
        if isinstance(node.op, ast.UAdd):
            return value
        if isinstance(node.op, ast.USub):
            return -value
        raise ValueError("unsupported_unary")

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise ValueError("bool_not_allowed")
        if isinstance(node.value, int):
            return Decimal(node.value)
        if isinstance(node.value, float):
            return Decimal(str(node.value))
        raise ValueError("unsupported_constant")

    raise ValueError(f"unsupported_node:{type(node).__name__}")


def _is_symbolic_request(message: str) -> bool:
    lowered = str(message).lower()
    return any(keyword in lowered for keyword in _SYMBOLIC_KEYWORDS)


def _sympify_expr(expr: str):
    import sympy as sp

    return sp.sympify(expr.replace("^", "**"), evaluate=True)


def _try_symbolic_answer(message: str) -> Optional[str]:
    lowered = str(message).strip().lower()
    try:
        import sympy as sp
    except Exception:
        return None

    try:
        if "simplify" in lowered:
            expr = lowered.split("simplify", 1)[1].strip()
            if expr:
                return str(sp.simplify(_sympify_expr(expr)))

        if "factor" in lowered:
            expr = lowered.split("factor", 1)[1].strip()
            if expr:
                return str(sp.factor(_sympify_expr(expr)))

        solve_match = re.search(r"solve for\s+([a-zA-Z])[:\s]+(.+)$", lowered)
        if solve_match:
            symbol = sp.Symbol(solve_match.group(1))
            expr = solve_match.group(2).strip()
            if expr:
                if "=" in expr:
                    lhs_raw, rhs_raw = expr.split("=", 1)
                    equation = sp.Eq(_sympify_expr(lhs_raw), _sympify_expr(rhs_raw))
                    solutions = sp.solve(equation, symbol, dict=False)
                else:
                    solutions = sp.solve(_sympify_expr(expr), symbol, dict=False)
                return str(solutions)

        if "differentiate" in lowered:
            expr = lowered.split("differentiate", 1)[1].strip()
            if expr:
                x = sp.Symbol("x")
                return str(sp.diff(_sympify_expr(expr), x))

        if "integrate" in lowered:
            expr = lowered.split("integrate", 1)[1].strip()
            if expr:
                x = sp.Symbol("x")
                return str(sp.integrate(_sympify_expr(expr), x))
    except Exception:
        return None

    return None
