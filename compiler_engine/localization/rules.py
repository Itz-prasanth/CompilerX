"""Strategy B - deterministic, rule-based root-cause localisation (no learning, no ground truth)."""
from __future__ import annotations
from typing import Dict, List, Tuple
from ..common.diagnostic import Diagnostic
from ..parser.analysis import (SourceAnalysis, LineInfo, looks_complete, needs_colon, is_block_header)
from ..parser.lexer import BINARY_OPS
from .candidates import generate_candidates

_TERMINATORS = {";", "{", "}", ","}


def _score_line(a: SourceAnalysis, diag: Diagnostic, li: LineInfo, rep: int) -> Tuple[float, List[str]]:
    cat, exp = diag.category, diag.expected
    notes: List[str] = []
    dist = rep - li.no
    s = -0.15 * dist                       # proximity prior only; never "reported or previous line"
    if li.in_string or li.preproc or li.comment_only:
        return -99.0, ["not code"]
    if li.blank and cat != "missing_brace":
        return -99.0, ["blank"]
    last = li.last
    nxt = a.next_code(li.no)

    if cat == "missing_semicolon":
        if looks_complete(a, li):
            s += 4.0; notes.append("complete statement without terminator")
            if nxt and (nxt.first.kind in ("keyword", "ident") or nxt.first.text == "}"):
                s += 1.0; notes.append("next line starts a new statement")
        elif last is not None and last.text in _TERMINATORS:
            s -= 4.0
        if li.paren_end != 0:
            s -= 2.0
    elif cat == "missing_paren":
        if li.paren_net > 0 or li.bracket_net > 0:
            s += 4.0 + 0.5 * (li.paren_net + li.bracket_net); notes.append("line opens a bracket it never closes")
        else:
            s -= 3.0
    elif cat == "missing_brace":
        if li.blank:
            nb = a.next_nonblank(li.no)
            if li.brace_end > 0 and nb is not None and nb.indent <= li.open_indent:
                s += 5.0; notes.append("block should end here: next line dedents while a '{' is open")
            elif li.brace_end > 0:
                s += 0.5
        else:
            nb = a.next_nonblank(li.no)
            if li.brace_end > 0 and nb is not None and nb.indent <= li.open_indent and nb.indent < li.indent:
                s += 3.0; notes.append("dedent after this line while a '{' is open")
            if li.opens_unmatched_brace:
                s += 0.5
    elif cat == "missing_comma":
        if li.paren_end > 0 and last is not None and last.text not in (",", "(") and last.kind != "op":
            s += 3.0; notes.append("argument list continues on next line without comma")
        if li.no == rep:
            s += 1.5
    elif cat == "missing_colon":
        if needs_colon(a, li):
            s += 5.0; notes.append("block header lacks ':'")
        else:
            s -= 3.0
    elif cat == "indentation":
        if li.no == rep:
            s += 3.0
        prev = a.prev_code(li.no)
        if prev is not None and prev.no == li.no - 1 and prev.last is not None and prev.last.text == ":" and li.no == rep:
            s += 0.5
    elif cat == "incomplete_expression":
        if last is not None and (last.text in BINARY_OPS or last.text in ("(", ",")):
            s += 4.0; notes.append("statement ends with a dangling operator")
        if li.no == rep:
            s += 1.5
    elif cat in ("unexpected_token", "malformed_declaration", "unknown"):
        if li.no == rep:
            s += 3.0; notes.append("error token is on this line")
        if last is not None and last.text in BINARY_OPS:
            s += 1.0
        # the previous line may be an unterminated statement that swallowed this one
        if looks_complete(a, li) and li.no == rep - 1 and exp == ";":
            s += 3.0
    if li.no == rep and cat in ("missing_semicolon", "missing_paren") and diag.column and li.first is not None \
            and diag.column > li.first.col and looks_complete(a, li):
        s += 0.5; notes.append("error column is inside this line")
    return s, notes


def rank(a: SourceAnalysis, diag: Diagnostic, lines: List[int] = None) -> List[Dict]:
    rep = min(max(diag.line, 1), len(a.lines))
    lines = lines if lines is not None else generate_candidates(a, diag)
    scored = []
    for no in lines:
        sc, notes = _score_line(a, diag, a.lines[no - 1], rep)
        scored.append((sc, no, notes))
    scored.sort(key=lambda x: (-x[0], rep - x[1]))
    good = [x for x in scored if x[0] > -50]
    if not good:
        good = scored[:1]
    top = good[0][0]
    import math
    z = sum(math.exp(min(x[0] - top, 0)) for x in good)
    return [{"line": no, "score": round(math.exp(min(sc - top, 0)) / z, 4), "raw_score": round(sc, 3),
             "evidence": notes, "strategy": "rule"} for sc, no, notes in good]
