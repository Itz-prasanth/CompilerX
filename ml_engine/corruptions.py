"""Controlled single-line syntax corruptions with a recorded ground-truth line (numbering is preserved)."""
from __future__ import annotations
import random
from typing import Optional, Tuple, List
from compiler_engine.parser.lexer import tokenize, BINARY_OPS

KINDS = ["missing_semicolon", "missing_paren", "missing_brace", "missing_comma", "missing_colon",
         "unexpected_token", "unexpected_operator", "incomplete_expression", "malformed_declaration",
         "indentation"]
# Map corruption kind -> shared category vocabulary (for classification accuracy)
KIND_TO_CATEGORY = {"missing_semicolon": "missing_semicolon", "missing_paren": "missing_paren",
                    "missing_brace": "missing_brace", "missing_comma": "missing_comma",
                    "missing_colon": "missing_colon", "unexpected_token": "unexpected_token",
                    "unexpected_operator": "incomplete_expression", "incomplete_expression": "incomplete_expression",
                    "malformed_declaration": "malformed_declaration", "indentation": "indentation"}
STRAY = {"c": [")", "]", "@", "`", "}"], "cpp": [")", "]", "@", "`", "}"],
         "java": [")", "]", "}", "#", "`"], "python": [")", "]", "}", "$", "?", "!"]}
DUP_OPS = {"c": ["/", "&&", "||", "==", "<"], "cpp": ["/", "&&", "||", "==", "<"],
           "java": ["/", "&&", "||", "==", "<"], "python": ["/", "%", "==", "<"]}
TYPES = {"int", "double", "float", "char", "long"}


def _toks_by_line(lang, src):
    d = {}
    for t in tokenize(lang, src):
        d.setdefault(t.line, []).append(t)
    return d


def _set(lines, i, text):
    out = lines[:]; out[i] = text
    return "\n".join(out)


def apply(lang: str, src: str, kind: str, rng: random.Random) -> Optional[Tuple[str, int]]:
    """Return (corrupted_source, truth_line) or None if the kind is not applicable."""
    lines = src.split("\n"); tl = _toks_by_line(lang, src)
    c_like = lang != "python"
    idxs = list(range(len(lines))); rng.shuffle(idxs)

    for i in idxs:
        text, toks = lines[i], tl.get(i + 1, [])
        if not toks or toks[0].kind == "preproc":
            continue
        s = text.rstrip()
        if kind == "missing_semicolon" and c_like and s.endswith(";") and toks[0].text != "for":
            return _set(lines, i, s[:-1]), i + 1
        if kind == "missing_paren":
            ps = [t for t in toks if t.text == ")" and t.kind == "punct"]
            if ps:
                t = rng.choice(ps)
                return _set(lines, i, text[:t.col - 1] + text[t.col:]), i + 1
        if kind == "missing_brace" and c_like and s.strip() == "}":
            return _set(lines, i, ""), i + 1
        if kind == "missing_comma":
            cs = [t for t in toks if t.text == "," and t.kind == "punct"]
            if cs:
                t = rng.choice(cs)
                return _set(lines, i, text[:t.col - 1] + text[t.col:]), i + 1
        if kind == "missing_colon" and lang == "python" and s.endswith(":"):
            return _set(lines, i, s[:-1]), i + 1
        if kind == "unexpected_token" and len(toks) >= 3:
            k = rng.randrange(1, len(toks))
            t = toks[k]
            stray = rng.choice(STRAY[lang])
            return _set(lines, i, text[:t.col - 1] + stray + " " + text[t.col - 1:]), i + 1
        if kind == "unexpected_operator":
            ops = [t for t in toks if t.text in ("+", "-", "*") and t.kind == "op"]
            if ops:
                t = rng.choice(ops); ins = rng.choice(DUP_OPS[lang])
                e = t.col - 1 + len(t.text)
                return _set(lines, i, text[:e] + " " + ins + text[e:]), i + 1
        if kind == "incomplete_expression" and toks[0].text not in ("for", "if", "while", "elif", "return", "def"):
            if c_like and not s.endswith(";"):
                continue
            if not c_like and s.endswith(":"):
                continue
            ops = [t for t in toks if t.kind == "op" and t.text in BINARY_OPS and t.text != "?"]
            if ops:
                t = ops[-1]; e = t.col - 1 + len(t.text)
                tail = ";" if c_like else ""
                return _set(lines, i, text[:e] + " " + tail), i + 1
        if kind == "malformed_declaration":
            if c_like and toks[0].text in TYPES and len(toks) >= 4 and toks[1].kind == "ident" and toks[2].text == "=":
                a, b = toks[1].col - 1, toks[1].col - 1 + len(toks[1].text)
                return _set(lines, i, text[:a] + text[b:].lstrip()), i + 1
            if not c_like and len(toks) >= 3 and toks[0].kind == "ident" and toks[1].text == "=" and toks[0].col == toks[0].col:
                return _set(lines, i, text[:toks[0].col - 1] + f"{rng.randint(1, 9)}" + text[toks[0].col - 1:]), i + 1
        if kind == "indentation" and lang == "python" and text.startswith(" "):
            ind = len(text) - len(text.lstrip())
            if rng.random() < 0.5 and ind >= 2:
                cut = rng.choice([1, 2]) if ind > 2 else 1
                return _set(lines, i, text[cut:]), i + 1
            return _set(lines, i, "  " + text), i + 1
    return None
