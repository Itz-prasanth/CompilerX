"""Human-readable explanations assembled from the actual evidence (no canned per-example text)."""
from __future__ import annotations
from typing import Dict, List, Optional
from ..common.diagnostic import Diagnostic
from ..parser.analysis import SourceAnalysis

_WHAT = {
    "missing_semicolon": "a statement is missing its terminating ';'",
    "missing_paren": "an opening bracket is never closed",
    "missing_brace": "a block is not closed with '}'",
    "missing_comma": "two items in a list are not separated by ','",
    "missing_colon": "a block header is missing its ':'",
    "indentation": "the indentation does not match the surrounding block",
    "incomplete_expression": "an expression is incomplete (an operand is missing)",
    "unexpected_token": "an unexpected token was inserted or a token is misplaced",
    "malformed_declaration": "a declaration is malformed",
    "unknown": "the code could not be classified",
}


def explain(a: SourceAnalysis, diag: Diagnostic, root_line: int, evidence: List[str], patch: Optional[Dict],
            strategy: str) -> str:
    snippet = a.lines[root_line - 1].text.strip() if 1 <= root_line <= len(a.lines) else ""
    parts = [f"The compiler reported `{diag.message}` at line {diag.line}" +
             (f", column {diag.column}" if diag.column else "") + "."]
    if root_line != diag.line:
        gap = diag.line - root_line
        parts.append(f"The most probable origin is line {root_line} (`{snippet}`), {abs(gap)} line"
                     f"{'s' if abs(gap) != 1 else ''} {'earlier' if gap > 0 else 'later'}: {_WHAT.get(diag.category, _WHAT['unknown'])}. "
                     "The parser could only notice the problem after reading further tokens.")
    else:
        parts.append(f"The reported line looks like the real origin: {_WHAT.get(diag.category, _WHAT['unknown'])}.")
    if evidence:
        parts.append("Evidence: " + "; ".join(evidence) + ".")
    parts.append(f"(Ranked by the {'ML model' if strategy == 'ml' else 'rule-based engine'}; this is a probable cause, not a proof.)")
    if patch:
        v = (patch.get("validation") or {}).get("status")
        verdict = {"fixed": "compiles cleanly after the patch", "improved": "removes this error but another error remains",
                   "not_fixed": "does not remove the error", "unvalidated": "could not be validated (toolchain missing)"}.get(v, "was not validated")
        parts.append(f"Suggested fix: {patch['description']} — the patched copy {verdict}.")
    else:
        parts.append("No automatic correction was found; inspect the highlighted line manually.")
    return " ".join(parts)
