"""Built-in tools answered instantly without the LLM: calculator and "what's today's date?".

`answer_builtin()` returns a reply, or `None` when the message should go to the LLM.
"""

import ast
import math
import operator
import re
from datetime import datetime

from app.config import Calendar
from app.core.normalizer import Language, detect_language, to_ascii_digits, to_persian_digits
from app.utils.calendar import format_date

# --- Calculator ---

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_EXPONENT = 100
_MAX_MAGNITUDE = 1e18

# Only digits, operators, parentheses and spaces; must contain at least one operator.
_EXPRESSION = re.compile(r"^[\d.\s()+\-*/%^]+$")
_HAS_OPERATOR = re.compile(r"\d\s*[+\-*/%^]|\)\s*[+\-*/%^]")


class CalcError(ValueError):
    pass


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise CalcError("exponent too large")
        try:
            result = _BIN_OPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise CalcError("division by zero") from exc
        if isinstance(result, complex) or abs(result) > _MAX_MAGNITUDE:
            raise CalcError("result out of range")
        return result
    raise CalcError("unsupported expression")


def _prepare(text: str) -> str:
    text = to_ascii_digits(text).strip().rstrip("=?؟ ").strip()
    text = text.replace("×", "*").replace("÷", "/").replace("−", "-")
    return text.replace(",", "")  # thousands separators


def looks_like_math(text: str) -> bool:
    expr = _prepare(text)
    return bool(_EXPRESSION.match(expr) and _HAS_OPERATOR.search(expr))


def calculate(text: str) -> float:
    """Safely evaluate an arithmetic expression (Persian digits, ×, ÷ and ^ allowed)."""
    expr = _prepare(text).replace("^", "**")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CalcError("invalid expression") from exc
    return _eval(tree.body)


def format_number(value: float) -> str:
    """`4200000` → `4,200,000`; `0.1 + 0.2` → `0.3`."""
    if isinstance(value, float) and not value.is_integer():
        value = float(f"{value:.10g}")
    if float(value).is_integer() and not math.isinf(value):
        return f"{int(value):,}"
    return f"{value:,.10g}"


# --- Today's date ---

_DATE_QUESTION = re.compile(
    r"what(?:'s| is)?\s+(?:the\s+)?(?:date|day)(?:\s+(?:is\s+)?(?:it\s+)?today)?\s*\??$"
    r"|^(?:what\s+is\s+)?today'?s\s+date\s*\??$"
    r"|^what\s+day\s+is\s+(?:it|today)\s*\??$"
    r"|^date\s*\??$"
    r"|امروز\s*(?:چندمه|چندم\s*است|چه\s*روزیه|چه\s*روزی\s*است|چند\s*شنبه\s*(?:است|ه)?)"
    r"|^تاریخ\s*(?:امروز|چنده|امروز\s*چیه|امروز\s*چنده)",
    re.IGNORECASE,
)


def is_date_question(text: str) -> bool:
    return bool(_DATE_QUESTION.search(text.strip()))


def today_answer(now: datetime, calendar: Calendar, lang: Language) -> str:
    """Today's date in the selected calendar first, the other one in parentheses."""
    other = Calendar.GREGORIAN if calendar == Calendar.JALALI else Calendar.JALALI
    primary = format_date(now.date(), calendar, lang)
    secondary = format_date(now.date(), other, lang, weekday=False)
    if lang == "fa":
        clock = to_persian_digits(f"{now:%H:%M}")
        return f"📅 امروز <b>{primary}</b> است ({secondary})\n🕒 ساعت {clock}"
    return f"📅 Today is <b>{primary}</b> ({secondary})\n🕒 {now:%H:%M}"


def answer_builtin(text: str, now: datetime, calendar: Calendar) -> str | None:
    if looks_like_math(text):
        try:
            return f"🧮 <code>{_prepare(text)}</code> = <b>{format_number(calculate(text))}</b>"
        except CalcError as exc:
            return f"🧮 <code>{_prepare(text)}</code>: {exc}"
    if is_date_question(text):
        return today_answer(now, calendar, detect_language(text))
    return None
