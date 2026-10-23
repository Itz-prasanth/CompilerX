"""Phase 2 - bounded counterfactual candidate-correction validation.

For each candidate root-cause line, this module generates the same minimal single-edit
patches the existing "Suggested patch" feature uses (patches.generator.patches_for_line),
applies each to a TEMPORARY in-memory copy of the source, and compiles that copy with the
real language adapter. The result is structured evidence (compiled or not, which original
diagnostics disappeared, which new ones appeared, how big the edit was, how long it took)
- never a bare "it compiles" flag, and never the user's own source.

Safety: compiling a candidate is exactly `LanguageAdapter.check(source, timeout=...)`, the
same call every other strategy already uses. It writes to a fresh temporary directory
(base.tmpdir()/rmtree(), per-adapter), enforces the adapter's own timeout and output-size
limits (compiler_engine.common.process.run_limited), and never executes the program -
`check()` only ever invokes the compiler/parser, never `build_and_run`. The ORIGINAL source
string is only ever read (`a.source`); `apply_edits` returns a new string, so there is
nothing to accidentally write back.
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from ..common.diagnostic import Diagnostic
from ..parser.analysis import SourceAnalysis
from ..patches.generator import Patch, apply_edits, patches_for_line

log = logging.getLogger("compilerx.counterfactual")

DEFAULT_TIMEOUT = 8.0
MAX_CANDIDATE_LINES = 8          # bound on how many candidate lines get compiled at all
MAX_PATCHES_PER_LINE = 4         # bound on patch templates tried per line
MAX_TOTAL_VALIDATIONS = 24       # hard cap on total compiler invocations per request

_STATUS_RANK = {"fixed": 3, "improved": 2, "not_fixed": 1, "unvalidated": 0}


@dataclass
class PatchEvidence:
    """Counterfactual-validation evidence for ONE candidate patch at one line.

    `edits` is carried along (not just `diff`) so a client that accepts a Lab candidate can
    POST it straight to the existing /api/patch/apply endpoint without re-deriving it."""
    line: int
    template: str
    description: str
    diff: str
    status: str                        # fixed | improved | not_fixed | unvalidated
    compiled: bool                     # True iff the patched copy compiled with 0 errors
    remaining_original_error: bool     # True iff the original (line, category, message) is still reported
    remaining_error_count: int
    edits: List[dict] = field(default_factory=list)
    new_diagnostics: List[dict] = field(default_factory=list)       # errors present after, absent before
    resolved_diagnostics: List[dict] = field(default_factory=list)  # errors present before, absent after
    edit_size_chars: int = 0
    edit_size_lines: int = 0
    timed_out: bool = False
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LineEvidence:
    """Best counterfactual evidence found across the patches tried at one candidate line."""
    line: int
    verified: bool                      # True iff at least one patch at this line compiles cleanly
    best: Optional[PatchEvidence]
    attempts: List[PatchEvidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"line": self.line, "verified": self.verified,
                "best": self.best.to_dict() if self.best else None,
                "attempts": [a.to_dict() for a in self.attempts]}


def _diag_key(d: dict) -> tuple:
    return (d.get("line"), d.get("category"), d.get("message"))


def _edit_extent(source: str, edits) -> "tuple[int, int]":
    """(characters touched, distinct source lines touched) - a cheap, honest size proxy.

    Not a diff-minimality claim; just how much text the edit set rewrites, used only to
    prefer smaller corrections among otherwise-tied candidates (Phase 3)."""
    chars = sum(max(len(e.insert), e.delete) for e in edits)
    lines = set()
    for e in edits:
        start_line = source.count("\n", 0, e.offset)
        end_line = source.count("\n", 0, e.offset + e.delete) if e.delete else start_line
        end_line += e.insert.count("\n")          # a multi-line insertion (e.g. a new '}' line) touches more lines
        lines.update(range(start_line, end_line + 1))
    return chars, len(lines)


def evaluate_patch(adapter, source: str, patch: Patch, baseline_diags: List[dict], orig: Diagnostic,
                    timeout: float = DEFAULT_TIMEOUT) -> PatchEvidence:
    """Apply `patch` to a COPY of `source` (the real `source` string is untouched - Python
    strings are immutable and `apply_edits` returns a new one) and compile that copy."""
    t0 = time.time()
    patched = apply_edits(source, patch.edits)
    r = adapter.check(patched, timeout=timeout)
    dur_ms = int((time.time() - t0) * 1000)
    errs = r.errors
    after = [d.to_dict() for d in errs]
    base_keys = {_diag_key(d) for d in baseline_diags}
    after_keys = {_diag_key(d) for d in after}
    new_diags = [d for d in after if _diag_key(d) not in base_keys]
    resolved = [d for d in baseline_diags if _diag_key(d) not in after_keys]
    orig_key = (orig.line, orig.category, orig.message)
    remaining_original = any(_diag_key(d) == orig_key for d in after)

    if r.toolchain_missing:
        status = "unvalidated"
    elif r.ok:
        status = "fixed"
    elif errs and errs[0].line > orig.line:
        status = "improved"           # the original error is gone; a later error remains
    else:
        status = "not_fixed"

    chars, lines_touched = _edit_extent(source, patch.edits)
    return PatchEvidence(
        line=patch.line, template=patch.template, description=patch.description, diff=patch.diff,
        status=status, compiled=r.ok, remaining_original_error=remaining_original,
        remaining_error_count=len(errs), edits=[asdict(e) for e in patch.edits],
        new_diagnostics=new_diags, resolved_diagnostics=resolved,
        edit_size_chars=chars, edit_size_lines=lines_touched, timed_out=r.timed_out, duration_ms=dur_ms,
    )


def evaluate_candidates(adapter, a: SourceAnalysis, diag: Diagnostic, lines: List[int],
                         max_lines: int = MAX_CANDIDATE_LINES, patches_per_line: int = MAX_PATCHES_PER_LINE,
                         max_total: int = MAX_TOTAL_VALIDATIONS, timeout: float = DEFAULT_TIMEOUT) -> List[LineEvidence]:
    """Validate patch candidates at each of `lines` (already ordered by the caller - callers
    should pass their most-plausible lines first, since validation is bounded). Never raises
    on a missing toolchain or a failed compile - those become `unvalidated`/`not_fixed`
    evidence, and rule/ML ranking still works even when nothing here could be validated."""
    try:
        baseline = adapter.check(a.source, timeout=timeout)
    except Exception:
        log.exception("counterfactual.baseline_check_failed")
        return [LineEvidence(line=ln, verified=False, best=None, attempts=[]) for ln in lines[:max_lines]]

    bounded_lines = lines[:max_lines]
    if baseline.toolchain_missing:
        return [LineEvidence(line=ln, verified=False, best=None, attempts=[]) for ln in bounded_lines]

    baseline_diags = [d.to_dict() for d in baseline.errors]
    out: List[LineEvidence] = []
    total = 0
    for ln in bounded_lines:
        attempts: List[PatchEvidence] = []
        if not (1 <= ln <= len(a.lines)):
            out.append(LineEvidence(line=ln, verified=False, best=None, attempts=[]))
            continue
        for p in patches_for_line(a, diag, ln, limit=patches_per_line):
            if total >= max_total:
                break
            try:
                ev = evaluate_patch(adapter, a.source, p, baseline_diags, diag, timeout=timeout)
            except Exception as e:
                log.exception("counterfactual.patch_validation_failed line=%s", ln)
                ev = PatchEvidence(line=p.line, template=p.template, description=p.description, diff=p.diff,
                                    status="unvalidated", compiled=False, remaining_original_error=True,
                                    remaining_error_count=-1, timed_out=False, duration_ms=0)
            attempts.append(ev)
            total += 1
        best = max(attempts, key=lambda e: (_STATUS_RANK[e.status], -e.edit_size_chars)) if attempts else None
        out.append(LineEvidence(line=ln, verified=bool(best and best.status == "fixed"), best=best, attempts=attempts))
        if total >= max_total:
            break
    # lines beyond the budget still appear in the result, unvalidated, so callers can display
    # "not checked" rather than silently dropping candidates.
    for ln in lines[len(out):max_lines]:
        out.append(LineEvidence(line=ln, verified=False, best=None, attempts=[]))
    return out
