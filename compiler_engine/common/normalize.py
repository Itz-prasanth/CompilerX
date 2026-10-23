"""Map raw compiler messages onto a shared (category, expected-token) vocabulary."""
from __future__ import annotations
import re
from typing import Optional, Tuple

CATEGORIES = (
    "missing_semicolon", "missing_paren", "missing_brace", "missing_comma",
    "missing_colon", "unexpected_token", "incomplete_expression",
    "malformed_declaration", "indentation", "unknown",
)
EXPECTED_TOKENS = (";", ")", "]", "}", "{", ",", ":", "other", "none")

_EXP = re.compile(r"expected '([^']+)'")


def _first_expected(msg: str) -> Optional[str]:
    m = _EXP.search(msg)
    return m.group(1) if m else None


def classify(language: str, message: str) -> Tuple[str, Optional[str], bool]:
    """Return (category, expected_token, is_syntax_error)."""
    msg = message.strip()
    low = msg.lower()
    if language in ("c", "cpp"):
        return _classify_gnu(msg, low)
    if language == "java":
        return _classify_java(msg, low)
    if language == "python":
        return _classify_python(msg, low)
    return "unknown", None, True


def _classify_gnu(msg: str, low: str):
    if "at end of input" in low:
        return "missing_brace", "}", True
    if "stray" in low:
        return "unexpected_token", None, True
    if "expected ';'" in low or "expected ',' or ';'" in low or "'asm' or '__attribute__'" in low:
        return "missing_semicolon", ";", True
    if "expected ')'" in low:
        return "missing_paren", ")", True
    if "expected ']'" in low:
        return "missing_paren", "]", True
    if "expected '}'" in low:
        return "missing_brace", "}", True
    if "expected ','" in low:
        return "missing_comma", ",", True
    if "expected ':'" in low:
        return "missing_colon", ":", True
    if "expected expression" in low or "expected primary-expression" in low:
        return "incomplete_expression", None, True
    if "expected identifier" in low or "expected declaration specifiers" in low \
            or "expected unqualified-id" in low or "does not name a type" in low:
        return "malformed_declaration", _first_expected(msg), True
    if "expected declaration or statement" in low:
        return "unexpected_token", None, True
    if "expected" in low and "before" in low:
        return "unexpected_token", _first_expected(msg), True
    if "syntax error" in low or "unknown type name" in low:
        return "unexpected_token", None, True
    return "unknown", None, False


def _classify_java(msg: str, low: str):
    if "reached end of file while parsing" in low:
        return "missing_brace", "}", True
    if low.startswith("';' expected"):
        return "missing_semicolon", ";", True
    if low.startswith("')' expected") or low.startswith("']' expected") or "')' or ',' expected" in low:
        return "missing_paren", ")", True
    if low.startswith("',' expected"):
        return "missing_comma", ",", True
    if low.startswith("':' expected") or "':' or '->' expected" in low:
        return "missing_colon", ":", True
    if "illegal start of expression" in low:
        return "incomplete_expression", None, True
    if "<identifier> expected" in low or "illegal start of type" in low:
        return "malformed_declaration", None, True
    if "class, interface, enum, or record expected" in low or "'}' expected" in low:
        return "missing_brace", "}", True
    if "not a statement" in low or "illegal character" in low or "unclosed" in low \
            or "orphaned" in low or " expected" in low:
        return "unexpected_token", None, True
    return "unknown", None, False   # semantic error (symbol, types, ...)


def _classify_python(msg: str, low: str):
    if "unindent does not match" in low or "expected an indented block" in low \
            or "unexpected indent" in low or "inconsistent use of tabs" in low:
        return "indentation", None, True
    if "expected ':'" in low:
        return "missing_colon", ":", True
    if "was never closed" in low:
        return "missing_paren", ")", True
    if "forgot a comma" in low:
        return "missing_comma", ",", True
    if "unmatched" in low:
        return "unexpected_token", None, True
    if "expected an expression" in low or "cannot assign" in low:
        return "incomplete_expression", None, True
    if "invalid decimal literal" in low or "invalid syntax" in low or "unterminated" in low \
            or "invalid character" in low or "invalid non-printable" in low:
        return "unexpected_token", None, True
    if "syntax" in low or "expected" in low:
        return "unexpected_token", None, True
    return "unknown", None, True
