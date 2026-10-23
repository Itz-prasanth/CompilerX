"""Candidate root-cause line generation around a reported error."""
from __future__ import annotations
from typing import List
from ..common.diagnostic import Diagnostic
from ..parser.analysis import SourceAnalysis

WINDOW = 20


def generate_candidates(a: SourceAnalysis, diag: Diagnostic, window: int = WINDOW) -> List[int]:
    """All lines in [reported-window, reported] (clamped). Blank lines are kept: a deleted '}' leaves one."""
    n = len(a.lines)
    rep = min(max(diag.line, 1), n)
    if diag.category == "missing_brace":      # unbalanced braces surface at EOF: search the whole file
        window = max(window, 200)
    lo = max(1, rep - window)
    return list(range(lo, rep + 1))
