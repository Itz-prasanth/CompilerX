"""Per-line structural analysis: delimiter depth, statement completeness, indentation, block stack."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .lexer import tokenize, Token, TYPE_KEYWORDS, CONTROL_KEYWORDS, BINARY_OPS

PY_HEADERS = {"if", "elif", "else", "for", "while", "def", "class", "try", "except", "finally", "with"}


@dataclass
class LineInfo:
    no: int
    text: str
    tokens: List[Token] = field(default_factory=list)
    blank: bool = False
    comment_only: bool = False
    preproc: bool = False
    in_string: bool = False        # continuation of a multi-line literal
    indent: int = 0
    paren_net: int = 0
    bracket_net: int = 0
    brace_net: int = 0
    paren_start: int = 0
    paren_end: int = 0
    bracket_end: int = 0
    brace_start: int = 0
    brace_end: int = 0
    open_indent: int = -1          # indent of innermost unmatched '{' line at line start (-1 none)
    opens_unmatched_brace: bool = False   # this line holds an '{' still unmatched at EOF

    @property
    def first(self) -> Optional[Token]:
        return self.tokens[0] if self.tokens else None

    @property
    def last(self) -> Optional[Token]:
        return self.tokens[-1] if self.tokens else None

    @property
    def code(self) -> bool:
        return bool(self.tokens) and not self.preproc


@dataclass
class SourceAnalysis:
    language: str
    source: str
    lines: List[LineInfo]
    tokens: List[Token]
    unmatched_braces: List[int]     # line numbers of unmatched '{'
    global_paren: int
    global_bracket: int

    def line(self, no: int) -> Optional[LineInfo]:
        return self.lines[no - 1] if 1 <= no <= len(self.lines) else None

    def next_code(self, no: int) -> Optional[LineInfo]:
        for i in range(no, len(self.lines)):
            if self.lines[i].code:
                return self.lines[i]
        return None

    def prev_code(self, no: int) -> Optional[LineInfo]:
        for i in range(no - 2, -1, -1):
            if self.lines[i].code:
                return self.lines[i]
        return None

    def next_nonblank(self, no: int) -> Optional[LineInfo]:
        for i in range(no, len(self.lines)):
            if not self.lines[i].blank:
                return self.lines[i]
        return None

    def token_at(self, line: int, col: int) -> Optional[Token]:
        best = None
        for t in self.tokens:
            if t.line == line and t.col <= max(col, 1):
                best = t
            elif t.line > line:
                break
        if best is not None and col > 0:
            exact = [t for t in self.tokens if t.line == line and t.col == col]
            return exact[0] if exact else best
        return best


def _indent_width(text: str) -> int:
    w = 0
    for ch in text:
        if ch == " ":
            w += 1
        elif ch == "\t":
            w += 4
        else:
            break
    return w


def analyze(language: str, source: str) -> SourceAnalysis:
    toks = tokenize(language, source)
    raw_lines = source.split("\n")
    lines = [LineInfo(i + 1, t, blank=(t.strip() == ""), indent=_indent_width(t)) for i, t in enumerate(raw_lines)]
    by_line: Dict[int, List[Token]] = {}
    for t in toks:
        by_line.setdefault(t.line, []).append(t)
        for l in range(t.line + 1, t.end_line + 1):     # multi-line literal / preproc continuation
            if 1 <= l <= len(lines):
                lines[l - 1].in_string = True
    paren = bracket = 0
    brace_stack: List[int] = []   # line numbers of '{'
    for li in lines:
        li.tokens = by_line.get(li.no, [])
        li.preproc = bool(li.tokens) and li.tokens[0].kind == "preproc"
        li.comment_only = (not li.blank) and not li.tokens and not li.in_string
        li.paren_start, li.brace_start = paren, len(brace_stack)
        li.open_indent = lines[brace_stack[-1] - 1].indent if brace_stack else -1
        if not li.preproc:
            for t in li.tokens:
                if t.kind != "punct":
                    continue
                if t.text == "(":
                    paren += 1; li.paren_net += 1
                elif t.text == ")":
                    if paren > 0:
                        paren -= 1
                    li.paren_net -= 1
                elif t.text == "[":
                    bracket += 1; li.bracket_net += 1
                elif t.text == "]":
                    if bracket > 0:
                        bracket -= 1
                    li.bracket_net -= 1
                elif t.text == "{":
                    brace_stack.append(li.no); li.brace_net += 1
                elif t.text == "}":
                    if brace_stack:
                        brace_stack.pop()
                    li.brace_net -= 1
        li.paren_end, li.bracket_end, li.brace_end = paren, bracket, len(brace_stack)
    for ln in brace_stack:
        lines[ln - 1].opens_unmatched_brace = True
    return SourceAnalysis(language, source, lines, toks, list(brace_stack), paren, bracket)


# ---------------------------------------------------------------- statement-level predicates
def is_block_header(a: SourceAnalysis, li: LineInfo) -> bool:
    f = li.first
    if not f:
        return False
    if a.language == "python":
        return f.text in PY_HEADERS
    return f.text in CONTROL_KEYWORDS and li.last.text == ")" and li.paren_end == 0


def needs_colon(a: SourceAnalysis, li: LineInfo) -> bool:
    """Python block header whose trailing ':' is absent."""
    if a.language != "python" or not li.code or li.paren_end != 0:
        return False
    f = li.first
    return f.text in PY_HEADERS and li.last.text != ":" and not (li.last.kind == "keyword" and li.last.text in ("else", "try", "finally") and False)


def looks_complete(a: SourceAnalysis, li: LineInfo) -> bool:
    """A line that ends where a statement could legally end but carries no terminator."""
    if not li.code or li.in_string or li.paren_end != 0 or li.paren_start != 0:
        return False
    last = li.last
    if a.language == "python":
        return last.text not in (":", ",", "\\") and last.kind not in ("op",) and not needs_colon(a, li)
    if last.kind in ("ident", "number", "string") or last.text in (")", "]", "++", "--") or \
            (last.kind == "keyword" and last.text in ("break", "continue", "return", "this", "super")):
        if is_block_header(a, li):
            return False
        nxt = a.next_code(li.no)
        if nxt and nxt.first.text == "{":
            return False
        return True
    return False


def last_kind(li: LineInfo) -> str:
    t = li.last
    if not t:
        return "none"
    if t.text in (";", "{", "}", ",", ":", ")", "]", "("):
        return t.text
    if t.kind in ("ident", "number", "string", "keyword"):
        return t.kind
    if t.kind == "op":
        return "op_binary" if t.text in BINARY_OPS else "op_other"
    return "other"


def first_kind(li: LineInfo) -> str:
    t = li.first
    if not t:
        return "none"
    if t.text == "}":
        return "}"
    if t.kind == "keyword":
        if t.text in TYPE_KEYWORDS:
            return "kw_type"
        if t.text in CONTROL_KEYWORDS:
            return "kw_control"
        return "kw_other"
    if t.kind == "ident":
        return "ident"
    return "other"
