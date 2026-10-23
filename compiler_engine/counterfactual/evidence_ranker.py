"""Phase 3 - combine the existing rule-based score, the existing ML score (when available),
and counterfactual compile-validation evidence into one ranked candidate list.

This is an explicit, documented heuristic combination - NOT a calibrated probability:

    prior      = mean of whichever of {rule_score, ml_score} are available for that line
                 (each already in [0,1], produced by the existing rule/ML strategies this
                 module does not modify); if neither ranker scored the line, falls back to
                 a 1/(1+distance-from-reported-line) proximity prior, same shape as rules.py
                 uses before any evidence exists.
    tier_bonus = 1.0 if the best validated patch at that line makes the file compile with
                 zero errors ("fixed"), 0.4 if it only moves the next error strictly later
                 ("improved" - the original mistake is gone even if something else remains),
                 0 otherwise (no compiling patch was found at that line, or validation was
                 not possible - e.g. the toolchain is missing).
    composite  = prior + tier_bonus                      (NOT renormalised to sum to 1: a
                 softmax here would manufacture false precision over a combination that is
                 fundamentally a heuristic, not a trained estimator)
    score      = composite / max(composite over candidates)     (0..1, display scaling ONLY
                 - explicitly not a probability; callers must not present it as one)

A patch that compiles is evidence the candidate line COULD be edited into working code, not
proof it is the line the programmer actually got wrong - unrelated single-token deletions can
sometimes make code compile too. So when more than one candidate line reaches "fixed", this
module does not silently pick a winner: it sets `ambiguous=True` and lists every verified
line in `verified_lines`, and ties within `composite` are broken only by proximity to the
reported line (closer first) for a stable, explainable order - never invented confidence.
"""
from __future__ import annotations
from typing import Dict, List, Optional

from .evaluator import LineEvidence

_TIER_BONUS = {"fixed": 1.0, "improved": 0.4, "not_fixed": 0.0, "unvalidated": 0.0}


def rank(lines: List[int], rule_candidates: List[Dict], ml_candidates: Optional[List[Dict]],
         evidence: List[LineEvidence], reported_line: int, top_k: int = 5) -> Dict:
    rule_by_line = {c["line"]: c["score"] for c in rule_candidates}
    ml_by_line = {c["line"]: c["score"] for c in ml_candidates} if ml_candidates else {}
    ev_by_line = {e.line: e for e in evidence}

    rows = []
    for ln in lines:
        priors = [s for s in (rule_by_line.get(ln), ml_by_line.get(ln)) if s is not None]
        prior = (sum(priors) / len(priors)) if priors else 1.0 / (1 + abs(reported_line - ln))
        e = ev_by_line.get(ln)
        status = e.best.status if (e and e.best) else "unvalidated"
        checked = bool(e and e.attempts)
        bonus = _TIER_BONUS[status]
        composite = prior + bonus

        notes: List[str] = []
        if checked:
            n_fixed = sum(1 for att in e.attempts if att.status == "fixed")
            if status == "fixed":
                notes.append(f"a candidate patch at this line compiles cleanly ({n_fixed}/{len(e.attempts)} tried patches fixed it)")
            elif status == "improved":
                notes.append("a candidate patch removes the original error but a later error remains")
            elif status == "unvalidated":
                notes.append("validation unavailable (toolchain missing)")
            else:
                notes.append(f"{len(e.attempts)} candidate patch(es) tried here; none compiled")
        else:
            notes.append("not validated (outside the validation budget for this request)")

        rows.append({
            "line": ln, "prior": round(prior, 4), "status": status, "verified": status == "fixed",
            "checked": checked, "composite": round(composite, 4), "evidence": notes,
            "patch": e.best.to_dict() if (e and e.best) else None,
            "strategy": "counterfactual",
        })

    max_composite = max((r["composite"] for r in rows), default=1.0) or 1.0
    for r in rows:
        r["score"] = round(r["composite"] / max_composite, 4)
    rows.sort(key=lambda r: (-r["composite"], abs(reported_line - r["line"])))

    verified_lines = [r["line"] for r in rows if r["verified"]]
    return {
        "root_cause_line": rows[0]["line"] if rows else None,
        "candidates": rows[:top_k],
        "ambiguous": len(verified_lines) > 1,
        "verified_lines": verified_lines,
        "note": ("multiple candidate lines each produce a compiling patch - compiling is evidence of A valid "
                 "fix, not proof of THE original mistake; inspect the alternatives before accepting one")
                if len(verified_lines) > 1 else None,
    }
