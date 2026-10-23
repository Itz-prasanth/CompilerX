"""End-to-end diagnosis: compile -> classify -> candidates -> rule + ML ranking -> patches -> explanation."""
from __future__ import annotations
import hashlib
from typing import Dict, Optional
from .languages.registry import get_adapter
from .parser.analysis import analyze
from .localization import rules
from .localization.candidates import generate_candidates
from .patches.generator import suggest
from .recovery.explain import explain
from .languages.base import UnsafeSourceError
from . import counterfactual as cf


class DiagnosisEngine:
    def __init__(self, ranker=None):
        self.ranker = ranker

    def diagnose(self, language: str, source: str, validate: bool = True, top_k: int = 5,
                 counterfactual: bool = False, cf_max_lines: int = 6, cf_patches_per_line: int = 3) -> Dict:
        adapter = get_adapter(language)
        res = adapter.check(source)
        out: Dict = {"language": language, "source_sha256": hashlib.sha256(source.encode()).hexdigest()[:16],
                     "compile": res.to_dict(), "status": "ok"}
        if res.toolchain_missing:
            out["status"] = "toolchain_missing"; return out
        if res.ok:
            return out
        diag = res.first_error()
        if diag is None:
            out["status"] = "checker_failed"; return out
        out["original"] = diag.to_dict()
        out["reported"] = {"line": diag.line, "column": diag.column, "message": diag.message}
        out["category"] = diag.category
        if not diag.is_syntax:
            out["status"] = "non_syntax_error"
            out["note"] = "The first error is not a syntax error (e.g. type/symbol error); root-cause localisation targets syntax errors."
            return out
        out["status"] = "syntax_error"
        a = analyze(language, source)
        cands = generate_candidates(a, diag)
        rule_rank = rules.rank(a, diag, cands)
        ml_rank = None; ml_note = None
        if self.ranker is not None and self.ranker.available:
            ml_rank = self.ranker.rank(a, diag, cands)
        else:
            ml_note = (self.ranker.error if self.ranker is not None else "no model loaded")
        pref = (self.ranker.bundle.get("preferred_strategy", "ml") if (self.ranker and self.ranker.available) else "rule")
        primary = ml_rank if (pref == "ml" and ml_rank) else rule_rank
        strategy = "ml" if primary is ml_rank and ml_rank else "rule"
        root = primary[0]["line"]
        out["strategies"] = {
            "conventional": {"root_cause_line": diag.line, "candidates": [{"line": diag.line, "score": 1.0}]},
            "rule": {"root_cause_line": rule_rank[0]["line"], "candidates": rule_rank[:top_k]},
            "ml": ({"root_cause_line": ml_rank[0]["line"], "candidates": ml_rank[:top_k]} if ml_rank else {"unavailable": ml_note}),
        }
        out["primary_strategy"] = strategy
        out["root_cause_line"] = root
        out["candidates"] = primary[:top_k]
        out["agreement"] = bool(ml_rank) and ml_rank[0]["line"] == rule_rank[0]["line"]
        if counterfactual:
            # Strategy D (Phase 3/4): fold real-compiler evidence into rule+ML ranking. Opt-in
            # and bounded (cf_max_lines/cf_patches_per_line) because, unlike rule/ML scoring,
            # this compiles candidate patches - callers that don't ask for it pay nothing extra.
            ordered = [c["line"] for c in rule_rank]
            for c in (ml_rank or []):
                if c["line"] not in ordered:
                    ordered.append(c["line"])
            ordered = ordered[:cf_max_lines]
            ev = cf.evaluate_candidates(adapter, a, diag, ordered, max_lines=cf_max_lines, patches_per_line=cf_patches_per_line)
            out["strategies"]["counterfactual"] = cf.rank(ordered, rule_rank, ml_rank, ev, diag.line, top_k=top_k)
        patch = None
        if validate:
            order = []
            for r in primary[:3] + rule_rank[:2] + (ml_rank or [])[:2]:
                if r["line"] not in order:
                    order.append(r["line"])
            s = suggest(adapter, a, diag, order[:4])
            out["patch_attempts"] = [p.to_dict() for p in s["attempts"]]
            if s["best"] is not None:
                patch = s["best"].to_dict()
                out["patch"] = patch
        out["explanation"] = explain(a, diag, root, primary[0].get("evidence", []), patch, strategy)
        return out
