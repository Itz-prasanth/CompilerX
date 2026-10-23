"""Candidate-line feature extraction (F1-F8 of the deck, expanded). Shared by training and inference."""
from __future__ import annotations
from typing import List, Tuple
from compiler_engine.common.diagnostic import Diagnostic, LANGUAGES
from compiler_engine.common.normalize import CATEGORIES
from compiler_engine.parser.analysis import (SourceAnalysis, LineInfo, looks_complete, needs_colon,
                                             is_block_header, last_kind, first_kind)

FEATURE_VERSION = 2
_EXPECT = (";", ")", "]", "}", "{", ",", ":")
_FOUND = ("ident", "keyword", "number", "string", "op", "punct", "none", "other")
_LAST = (";", "{", "}", ",", ":", ")", "]", "(", "ident", "number", "string", "keyword", "op_binary",
         "op_other", "none", "other")
_FIRST = ("kw_type", "kw_control", "kw_other", "ident", "}", "other", "none")
_PREVLAST = (";", "{", "}", ",", ":", "other", "none")


class _FV:
    def __init__(self):
        self.names: List[str] = []; self.vals: List[float] = []

    def add(self, name, v):
        self.names.append(name); self.vals.append(float(v))

    def onehot(self, name, choices, v):
        for c in choices:
            self.add(f"{name}={c}", 1.0 if v == c else 0.0)


def _expected_bucket(e):
    if e is None:
        return "none"
    return e if e in _EXPECT else "other"


def _prev_bucket(li):
    k = last_kind(li) if li else "none"
    return k if k in _PREVLAST else ("none" if k == "none" else "other")


def _extract(a: SourceAnalysis, diag: Diagnostic, line_no: int) -> _FV:
    fv = _FV()
    rep = min(max(diag.line, 1), len(a.lines))
    rl = a.lines[rep - 1]
    li = a.lines[line_no - 1]
    # ---- group features (same for every candidate of this diagnostic)
    fv.onehot("lang", LANGUAGES, diag.language)
    fv.onehot("expected", _EXPECT + ("other", "none"), _expected_bucket(diag.expected))
    fv.onehot("category", CATEGORIES, diag.category)
    tok = a.token_at(diag.line, diag.column)
    fv.onehot("found", _FOUND, (tok.kind if tok and tok.kind in _FOUND else "other") if tok else "none")
    fv.add("found_is_type_kw", 1 if tok and tok.kind == "keyword" and first_kind(LineInfo(0, "", [tok])) == "kw_type" else 0)
    last_code = max((l.no for l in a.lines if l.code), default=1)
    msg = diag.message.lower()
    fv.add("reported_at_eof", 1 if ("end of input" in msg or "end of file" in msg or rep >= last_code) else 0)
    fv.add("rep_paren_start", rl.paren_start); fv.add("rep_brace_start", rl.brace_start)
    fv.add("global_unmatched_brace", len(a.unmatched_braces)); fv.add("global_paren", a.global_paren)
    fv.add("global_bracket", a.global_bracket)
    fv.add("rep_col_at_line_start", 1 if (rl.first is not None and diag.column and diag.column <= rl.first.col) else 0)
    fv.add("rep_indent", rl.indent)
    # ---- candidate features
    nxt_code = a.next_code(li.no); prv_code = a.prev_code(li.no); nxt_nb = a.next_nonblank(li.no)
    fv.add("F1_dist", rep - li.no)
    fv.add("code_lines_between", sum(1 for l in a.lines[li.no:rep] if l.code))
    fv.add("is_reported", 1 if li.no == rep else 0)
    fv.add("blank", 1 if li.blank else 0); fv.add("comment_only", 1 if li.comment_only else 0)
    fv.add("preproc", 1 if li.preproc else 0); fv.add("in_string", 1 if li.in_string else 0)
    fv.onehot("last_kind", _LAST, last_kind(li))
    fv.onehot("first_kind", _FIRST, first_kind(li))
    fv.add("ntok", len(li.tokens))
    fv.add("paren_net", li.paren_net); fv.add("bracket_net", li.bracket_net); fv.add("brace_net", li.brace_net)   # F5
    fv.add("paren_end", li.paren_end); fv.add("bracket_end", li.bracket_end)
    fv.add("brace_start", li.brace_start); fv.add("brace_end", li.brace_end)
    fv.add("F6_looks_complete", 1 if looks_complete(a, li) else 0)                                  # F6
    fv.add("needs_colon", 1 if needs_colon(a, li) else 0)
    fv.add("is_block_header", 1 if (li.code and is_block_header(a, li)) else 0)
    fv.onehot("next_first", _FIRST, first_kind(nxt_code) if nxt_code else "none")                   # F8
    fv.onehot("prev_last", _PREVLAST, _prev_bucket(prv_code))
    fv.add("indent", li.indent)
    nb_ind = nxt_nb.indent if nxt_nb else li.indent
    fv.add("indent_minus_next", li.indent - nb_ind)
    fv.add("indent_minus_prev", li.indent - (prv_code.indent if prv_code else li.indent))
    fv.add("indent_minus_rep", li.indent - rl.indent)
    exp = diag.expected
    fv.add("ends_with_expected", 1 if (exp and li.last is not None and li.last.text == exp) else 0)
    fv.add("opens_unmatched_brace", 1 if li.opens_unmatched_brace else 0)
    fv.add("open_indent", li.open_indent)
    fv.add("next_indent_minus_open", (nb_ind - li.open_indent) if li.brace_end > 0 else 0)
    fv.add("dedent_while_open", 1 if (li.brace_end > 0 and nxt_nb is not None and nb_ind <= li.open_indent) else 0)
    fv.add("line_len", len(li.text.strip()))
    return fv


def feature_names() -> List[str]:
    from compiler_engine.parser.analysis import analyze
    a = analyze("c", "int main() {\n  return 0;\n}\n")
    d = Diagnostic("c", 2, 3, "x", expected=";", category="missing_semicolon")
    return _extract(a, d, 1).names


FEATURE_NAMES = feature_names()


def candidate_features(a: SourceAnalysis, diag: Diagnostic, line_no: int) -> List[float]:
    return _extract(a, diag, line_no).vals


def featurize(a: SourceAnalysis, diag: Diagnostic, lines: List[int]) -> List[List[float]]:
    return [candidate_features(a, diag, n) for n in lines]
