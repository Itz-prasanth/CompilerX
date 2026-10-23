"""Error-tolerant lexer for C, C++, Java and Python source (used for analysis, not for compiling)."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List

C_KEYWORDS = {"if", "else", "for", "while", "do", "switch", "case", "default", "return", "break", "continue",
              "goto", "struct", "union", "enum", "typedef", "sizeof", "static", "const", "extern", "void",
              "int", "char", "short", "long", "float", "double", "signed", "unsigned", "class", "public",
              "private", "protected", "new", "delete", "namespace", "using", "template", "typename", "try",
              "catch", "throw", "bool", "auto", "final", "abstract", "interface", "package", "import",
              "boolean", "byte", "extends", "implements", "this", "super", "throws", "instanceof", "var", "string"}
PY_KEYWORDS = {"if", "elif", "else", "for", "while", "def", "class", "return", "import", "from", "as", "try",
               "except", "finally", "with", "lambda", "pass", "break", "continue", "in", "not", "and", "or",
               "is", "None", "True", "False", "yield", "raise", "global", "nonlocal", "assert", "del", "async", "await"}
TYPE_KEYWORDS = {"int", "char", "short", "long", "float", "double", "void", "bool", "boolean", "byte", "unsigned",
                 "signed", "string", "auto", "var", "def", "class", "struct", "static", "const", "final", "public",
                 "private", "protected"}
CONTROL_KEYWORDS = {"if", "elif", "else", "for", "while", "do", "switch", "try", "catch", "except", "finally", "with"}
BINARY_OPS = {"+", "-", "*", "/", "%", "=", "==", "!=", "<", ">", "<=", ">=", "&&", "||", "&", "|", "^", "<<", ">>",
              "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=", "?", "and", "or", "in", "not", "is"}


@dataclass
class Token:
    kind: str      # keyword ident number string op punct preproc other
    text: str
    line: int
    col: int       # 1-based
    end_line: int


_NUM = r"0[xX][0-9a-fA-F]+[uUlL]*|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?[fFuUlLdD]*"
_OPS = r"->|\+\+|--|<<=|>>=|<<|>>|<=|>=|==|!=|&&|\|\||\+=|-=|\*=|/=|%=|&=|\|=|\^=|::|\.\.\.|[-+*/%=<>!&|^~?.@$`\\]"

_C = re.compile(r"""
 (?P<ws>[ \t\r\f\v]+) | (?P<nl>\n)
|(?P<lc>//[^\n]*) | (?P<bc>/\*.*?\*/)
|(?P<str>"(?:\\.|[^"\\\n])*"?) | (?P<chr>'(?:\\.|[^'\\\n])*'?)
|(?P<num>%s) | (?P<id>[A-Za-z_][\w]*)
|(?P<op>%s) | (?P<punct>[(){}\[\];,:]) | (?P<other>.)
""" % (_NUM, _OPS), re.X | re.S)

_PY = re.compile(r'''
 (?P<ws>[ \t\r\f\v]+) | (?P<nl>\n) | (?P<lc>\#[^\n]*)
|(?P<str>(?i:[rbfu]{0,2})(?:"""(?:\\.|[^\\])*?(?:"""|\Z)|\'\'\'(?:\\.|[^\\])*?(?:\'\'\'|\Z)|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?))
|(?P<num>%s) | (?P<id>[A-Za-z_][\w]*)
|(?P<op>%s) | (?P<punct>[(){}\[\];,:]) | (?P<other>.)
''' % (_NUM, _OPS), re.X | re.S)


def tokenize(language: str, src: str) -> List[Token]:
    rx = _PY if language == "python" else _C
    kws = PY_KEYWORDS if language == "python" else C_KEYWORDS
    toks: List[Token] = []
    pos, line, line_start = 0, 1, 0
    n = len(src)
    at_line_start = True
    while pos < n:
        # preprocessor line (C/C++ only)
        if language in ("c", "cpp") and at_line_start:
            m = re.compile(r"[ \t]*#").match(src, pos)
            if m:
                end = pos
                while True:
                    e = src.find("\n", end)
                    if e == -1:
                        e = n; break
                    if src[e - 1] == "\\":
                        end = e + 1; continue
                    break
                text = src[pos:e]
                toks.append(Token("preproc", text.strip(), line, pos - line_start + 1 + (len(text) - len(text.lstrip())), line + text.count("\n")))
                line += text.count("\n"); pos = e; at_line_start = False
                continue
        m = rx.match(src, pos)
        kind = m.lastgroup; text = m.group()
        col = pos - line_start + 1
        nl_count = text.count("\n")
        if kind == "nl":
            line += 1; line_start = pos + 1; at_line_start = True
        elif kind == "ws":
            pass
        elif kind in ("lc", "bc"):
            if nl_count:
                line += nl_count; line_start = pos + text.rfind("\n") + 1
            at_line_start = False if kind == "lc" else at_line_start and False
        else:
            if kind == "id":
                k = "keyword" if text in kws else "ident"
            elif kind in ("chr", "str"):
                k = "string"
            elif kind == "num":
                k = "number"
            else:
                k = kind
            toks.append(Token(k, text, line, col, line + nl_count))
            if nl_count:
                line += nl_count; line_start = pos + text.rfind("\n") + 1
            at_line_start = False
        pos = m.end()
    return toks
