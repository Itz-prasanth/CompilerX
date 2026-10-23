"""Minimal single-edit patch candidates for a given line, validated against a temporary copy."""
from __future__ import annotations
import difflib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from ..common.diagnostic import Diagnostic
from ..parser.analysis import SourceAnalysis, LineInfo, looks_complete, needs_colon
from ..parser.lexer import BINARY_OPS

STRAY_CHARS = {"@", "`", "$", "?", "!", "#", "\\"}


@dataclass
class Edit:
    offset: int
    delete: int
    insert: str


@dataclass
class Patch:
    template: str
    description: str
    line: int
    edits: List[Edit]
    diff: str = ""
    validation: Optional[Dict] = None

    def to_dict(self):
        d = asdict(self); return d


def apply_edits(source: str, edits: List[Edit]) -> str:
    out = source
    for e in sorted(edits, key=lambda e: -e.offset):
        out = out[:e.offset] + e.insert + out[e.offset + e.delete:]
    return out


def _offsets(source: str) -> List[int]:
    offs, p = [], 0
    for ln in source.split("\n"):
        offs.append(p); p += len(ln) + 1
    return offs


def _mk(source, template, desc, line, edits):
    new = apply_edits(source, edits)
    diff = "".join(difflib.unified_diff(source.splitlines(True), new.splitlines(True), "original", "patched", n=1))
    return Patch(template, desc, line, edits, diff)


def _end_off(offs, t):           # offset just after token t (single-line tokens only)
    return offs[t.line - 1] + t.col - 1 + len(t.text)


def _start_off(offs, t):
    return offs[t.line - 1] + t.col - 1


ORDER = {
    "missing_semicolon": ["semicolon", "close_paren", "comma", "delete_token"],
    "missing_paren": ["close_paren", "delete_token", "semicolon", "comma"],
    "missing_brace": ["close_brace", "semicolon"],
    "missing_comma": ["comma", "close_paren", "semicolon"],
    "missing_colon": ["colon", "close_paren"],
    "indentation": ["indent"],
    "incomplete_expression": ["drop_operator", "delete_token"],
    "unexpected_token": ["delete_token", "drop_operator", "semicolon", "close_paren"],
    "malformed_declaration": ["delete_token", "drop_operator"],
}
ALL = ["semicolon", "close_paren", "close_brace", "comma", "colon", "indent", "drop_operator", "delete_token"]


def patches_for_line(a: SourceAnalysis, diag: Diagnostic, line_no: int, limit: int = 8) -> List[Patch]:
    src = a.source; offs = _offsets(src)
    if not (1 <= line_no <= len(a.lines)):
        return []
    li = a.lines[line_no - 1]
    out: List[Patch] = []
    c_like = a.language != "python"
    order = ORDER.get(diag.category, []) + [t for t in ALL if t not in ORDER.get(diag.category, [])]
    last = li.last
    single_line_last = last is not None and last.end_line == last.line

    for tpl in order:
        if tpl == "semicolon" and c_like and li.code and single_line_last and last.text not in (";", "{", "}", ",", ":"):
            out.append(_mk(src, tpl, f"Add ';' at the end of line {line_no}", line_no, [Edit(_end_off(offs, last), 0, ";")]))
        elif tpl == "close_paren" and li.code and single_line_last and (li.paren_net > 0 or li.bracket_net > 0):
            ins = ")" * max(li.paren_net, 0) + "]" * max(li.bracket_net, 0)
            pos = _end_off(offs, last)
            if last.text in (";", "{", ":") and len(li.tokens) > 1:
                pos = _start_off(offs, last)
            out.append(_mk(src, tpl, f"Insert missing '{ins}' on line {line_no}", line_no, [Edit(pos, 0, ins)]))
        elif tpl == "close_brace" and c_like:
            ind = max(li.open_indent, 0) if li.brace_end > 0 else 0
            if li.blank:
                out.append(_mk(src, tpl, f"Insert missing '}}' at line {line_no}", line_no, [Edit(offs[line_no - 1], len(li.text), " " * ind + "}")]))
            elif li.code:
                out.append(_mk(src, tpl, f"Insert missing '}}' after line {line_no}", line_no,
                               [Edit(offs[line_no - 1] + len(li.text), 0, "\n" + " " * ind + "}")]))
        elif tpl == "comma" and li.code:
            depth = li.paren_start; n = 0
            toks = li.tokens
            pairs = []
            for i, t in enumerate(toks):
                if t.text in ("(", "["):
                    depth += 1
                elif t.text in (")", "]"):
                    depth = max(depth - 1, 0)
                if i + 1 < len(toks) and depth > 0 and t.end_line == t.line:
                    u = toks[i + 1]
                    left = t.kind in ("ident", "number", "string") or t.text in (")", "]")
                    right = u.kind in ("ident", "number", "string")
                    if left and right and t.kind != "keyword":
                        pairs.append(t)
            if li.no == diag.line and diag.column:
                pairs.sort(key=lambda t: abs(t.col - diag.column))
            for t in pairs[:4]:
                out.append(_mk(src, tpl, f"Insert ',' after '{t.text}' on line {line_no}", line_no, [Edit(_end_off(offs, t), 0, ",")]))
        elif tpl == "colon" and a.language == "python" and needs_colon(a, li) and single_line_last:
            out.append(_mk(src, tpl, f"Add ':' at the end of line {line_no}", line_no, [Edit(_end_off(offs, last), 0, ":")]))
        elif tpl == "indent" and a.language == "python" and li.code:
            prev = a.prev_code(line_no)
            if prev is not None:
                opts = [(prev.indent + 4 if prev.last.text == ":" else prev.indent, "match the surrounding block")]
                outer = sorted({l.indent for l in a.lines[:line_no - 1] if l.code and l.indent < li.indent}, reverse=True)
                opts += [(o, "dedent to an enclosing block") for o in outer[:2]]
                seen = set()
                for w, why in opts:
                    if w in seen or w == li.indent:
                        continue
                    seen.add(w)
                    out.append(_mk(src, tpl, f"Re-indent line {line_no} to {w} spaces ({why})", line_no,
                                   [Edit(offs[line_no - 1], len(li.text) - len(li.text.lstrip()), " " * w)]))
        elif tpl == "drop_operator" and li.code:
            toks = li.tokens
            for i in range(len(toks) - 1, -1, -1):
                t = toks[i]
                tail_ok = (i == len(toks) - 1) or (i == len(toks) - 2 and toks[-1].text == ";")
                if t.kind == "op" and t.text in BINARY_OPS and tail_ok:
                    out.append(_mk(src, tpl, f"Remove dangling operator '{t.text}' on line {line_no}", line_no,
                                   [Edit(_start_off(offs, t), len(t.text), "")]))
                    break
            # doubled operator:  a + / b  -> remove the second one
            for i in range(len(toks) - 1):
                if toks[i].kind == "op" and toks[i + 1].kind == "op" and toks[i].text in BINARY_OPS and toks[i + 1].text in BINARY_OPS:
                    t = toks[i + 1]
                    out.append(_mk(src, tpl, f"Remove extra operator '{t.text}' on line {line_no}", line_no,
                                   [Edit(_start_off(offs, t), len(t.text), "")]))
                    break
        elif tpl == "delete_token" and li.code:
            toks = [t for t in li.tokens if t.end_line == t.line]
            cands = []
            at = a.token_at(diag.line, diag.column) if li.no == diag.line else None
            if at is not None and at.line == li.no and at.kind in ("punct", "op", "other"):
                cands.append(at)
            cands += [t for t in toks if t.text in STRAY_CHARS and t not in cands]
            if li.paren_net < 0:
                cands += [t for t in toks if t.text == ")" and t not in cands][-1:]
            if li.brace_net < 0 or li.bracket_net < 0:
                cands += [t for t in toks if t.text in ("}", "]") and t not in cands][-1:]
            if li.no == diag.line:
                cands += [t for t in toks if t.text in (")", "]", "}") and t not in cands][:2]
            if c_like is False and li.first is not None:
                pass
            for t in cands[:4]:
                out.append(_mk(src, tpl, f"Delete unexpected '{t.text}' on line {line_no}", line_no,
                               [Edit(_start_off(offs, t), len(t.text), "")]))
    # de-duplicate by resulting edits
    seen, uniq = set(), []
    for p in out:
        key = tuple((e.offset, e.delete, e.insert) for e in p.edits)
        if key not in seen:
            seen.add(key); uniq.append(p)
    return uniq[:limit]


def validate_patch(adapter, source: str, patch: Patch, orig: Diagnostic) -> Dict:
    """Compile the patched COPY (the user's source is never touched)."""
    patched = apply_edits(source, patch.edits)
    r = adapter.check(patched)
    errs = r.errors
    if r.toolchain_missing:
        status = "unvalidated"
    elif r.ok:
        status = "fixed"
    elif errs and errs[0].line > orig.line:
        status = "improved"          # original error gone, a later (possibly pre-existing) error remains
    else:
        status = "not_fixed"
    return {"status": status, "remaining_errors": len(errs),
            "first_error": errs[0].to_dict() if errs else None, "timed_out": r.timed_out}


_RANK = {"fixed": 3, "improved": 2, "unvalidated": 1, "not_fixed": 0}


def suggest(adapter, a: SourceAnalysis, diag: Diagnostic, lines: List[int], max_validations: int = 8,
            patches_per_line: int = 6) -> Dict:
    """Try patches on the given lines (in order); return the best validated one plus all attempts."""
    attempts: List[Patch] = []; best: Optional[Patch] = None
    for ln in lines:
        for p in patches_for_line(a, diag, ln, limit=patches_per_line):
            if len(attempts) >= max_validations:
                break
            p.validation = validate_patch(adapter, a.source, p, diag)
            attempts.append(p)
            if best is None or _RANK[p.validation["status"]] > _RANK[best.validation["status"]]:
                best = p
            if p.validation["status"] == "fixed":
                return {"best": best, "attempts": attempts}
        if len(attempts) >= max_validations:
            break
    return {"best": best, "attempts": attempts}
