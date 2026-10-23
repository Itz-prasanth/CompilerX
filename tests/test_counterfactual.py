"""Counterfactual Repair Lab (Phase 2/3/4): validation pipeline + evidence ranking.

Mirrors the style of tests/test_localization_and_patches.py and tests/test_adapters.py -
plain functions, no fixtures, real adapters wherever the scenario doesn't need a fake."""
from tests.helpers import INVALID
from compiler_engine.languages.registry import get_adapter
from compiler_engine.languages.gnu import GnuAdapter
from compiler_engine.common.diagnostic import CheckResult, Diagnostic
from compiler_engine.parser.analysis import analyze
from compiler_engine.localization import rules
from compiler_engine.localization.candidates import generate_candidates
from compiler_engine.patches.generator import patches_for_line
from compiler_engine.counterfactual.evaluator import evaluate_patch, evaluate_candidates, PatchEvidence, LineEvidence
from compiler_engine.counterfactual.evidence_ranker import rank as cf_rank
from compiler_engine.pipeline import DiagnosisEngine

SEMI = INVALID["c"][0]      # "int main() {\n    int price = 100\n    int tax = 18;\n    return 0;\n}\n" ; truth line 2


def _diag(lang, src):
    return get_adapter(lang).check(src).first_error()


# ---------------------------------------------------------------- evaluate_patch / evaluate_candidates


def test_evaluate_candidates_finds_the_real_fix_and_leaves_source_untouched():
    a = analyze("c", SEMI); d = _diag("c", SEMI); ad = get_adapter("c")
    cands = generate_candidates(a, d)
    ordered = [c["line"] for c in rules.rank(a, d, cands)]
    ev = evaluate_candidates(ad, a, d, ordered, max_lines=5, patches_per_line=3)
    by_line = {e.line: e for e in ev}
    assert by_line[2].verified and by_line[2].best.status == "fixed"
    assert a.source == SEMI                                  # the original string is never mutated


def test_wrong_candidate_lines_are_reported_not_fixed():
    """Validating patches at an unrelated line never fabricates a 'fixed' result."""
    a = analyze("c", SEMI); d = _diag("c", SEMI); ad = get_adapter("c")
    ev = evaluate_candidates(ad, a, d, [4], max_lines=1, patches_per_line=6)
    assert len(ev) == 1 and not ev[0].verified
    for attempt in ev[0].attempts:
        assert attempt.status != "fixed"


def test_edit_size_is_measured():
    a = analyze("c", SEMI); d = _diag("c", SEMI); ad = get_adapter("c")
    p = patches_for_line(a, d, 2, limit=1)[0]            # "Add ';' at the end of line 2"
    ev = evaluate_patch(ad, a.source, p, [], d)
    assert ev.status == "fixed" and ev.edit_size_chars == 1 and ev.edit_size_lines == 1
    assert ev.edits and ev.edits[0]["insert"] == ";"


def test_remaining_and_new_diagnostics_are_tracked():
    a = analyze("c", SEMI); d = _diag("c", SEMI); ad = get_adapter("c")
    baseline = [e.to_dict() for e in ad.check(SEMI).errors]
    p = patches_for_line(a, d, 2, limit=1)[0]
    ev = evaluate_patch(ad, a.source, p, baseline, d)
    assert ev.status == "fixed"
    assert len(ev.resolved_diagnostics) == len(baseline) and not ev.new_diagnostics


# ---------------------------------------------------------------- missing toolchain / timeouts


def test_missing_toolchain_is_handled_not_crashed():
    class Fake(GnuAdapter):
        language = "c"; compiler = "definitely-not-a-compiler-xyz"; filename = "m.c"
    a = analyze("c", SEMI); d = _diag("c", SEMI)
    ev = evaluate_candidates(Fake(), a, d, [1, 2, 3], max_lines=3, patches_per_line=2)
    assert len(ev) == 3
    assert all(not e.verified and e.best is None for e in ev)


class _TimedOutAdapter:
    """Minimal stand-in whose check() always reports a timeout, without actually waiting -
    exercises the same code path a real `sleep 5`-style hang would, deterministically."""
    language = "c"

    def check(self, source, timeout=8.0):
        return CheckResult(language="c", ok=False, diagnostics=[], raw_output="", tool="fake",
                            duration_ms=int(timeout * 1000), timed_out=True, toolchain_missing=False)


def test_timeout_is_handled_not_crashed():
    a = analyze("c", SEMI); d = _diag("c", SEMI)
    p = patches_for_line(a, d, 2, limit=1)[0]
    ev = evaluate_patch(_TimedOutAdapter(), a.source, p, [], d)
    assert ev.timed_out and ev.status in ("not_fixed", "unvalidated")

    ev2 = evaluate_candidates(_TimedOutAdapter(), a, d, [1, 2], max_lines=2, patches_per_line=2)
    assert len(ev2) == 2 and all(not e.verified for e in ev2)


# ---------------------------------------------------------------- evidence_ranker: ambiguity, ties


def _fixed(line):
    return LineEvidence(line=line, verified=True,
                         best=PatchEvidence(line=line, template="t", description="d", diff="", status="fixed",
                                             compiled=True, remaining_original_error=False, remaining_error_count=0),
                         attempts=[])


def _not_fixed(line):
    return LineEvidence(line=line, verified=False,
                         best=PatchEvidence(line=line, template="t", description="d", diff="", status="not_fixed",
                                             compiled=False, remaining_original_error=True, remaining_error_count=1),
                         attempts=[])


def test_ambiguous_when_multiple_candidates_compile():
    """Two different lines each produce a compiling patch - the ranker must say so (and
    list both) instead of silently picking a winner and presenting it as certain."""
    lines = [2, 3, 4]
    rule_cands = [{"line": 2, "score": 0.5}, {"line": 3, "score": 0.3}, {"line": 4, "score": 0.2}]
    ev = [_fixed(2), _not_fixed(3), _fixed(4)]
    out = cf_rank(lines, rule_cands, None, ev, reported_line=4)
    assert out["ambiguous"] is True
    assert set(out["verified_lines"]) == {2, 4}
    assert out["note"] is not None


def test_not_ambiguous_with_a_single_verified_candidate():
    lines = [2, 3]
    rule_cands = [{"line": 2, "score": 0.7}, {"line": 3, "score": 0.3}]
    ev = [_fixed(2), _not_fixed(3)]
    out = cf_rank(lines, rule_cands, None, ev, reported_line=3)
    assert out["ambiguous"] is False and out["verified_lines"] == [2] and out["root_cause_line"] == 2
    assert out["note"] is None


def test_unvalidated_lines_never_rank_above_a_verified_fix():
    """A candidate nobody could check (e.g. outside the validation budget) must not
    outrank one that is actually proven to compile."""
    lines = [2, 5]
    rule_cands = [{"line": 2, "score": 0.4}, {"line": 5, "score": 0.6}]
    ev = [_fixed(2)]                       # line 5 was never validated at all
    out = cf_rank(lines, rule_cands, None, ev, reported_line=2)
    assert out["candidates"][0]["line"] == 2 and out["candidates"][0]["verified"]


def test_scores_are_not_fabricated_probabilities():
    """Scores are a bounded [0,1] display scaling, not a softmax - they need not sum to 1."""
    lines = [2, 3, 4]
    rule_cands = [{"line": n, "score": 0.33} for n in lines]
    ev = [_fixed(2), _not_fixed(3), _not_fixed(4)]
    out = cf_rank(lines, rule_cands, None, ev, reported_line=2)
    total = sum(c["score"] for c in out["candidates"])
    assert total > 1.0 + 1e-6 or total < 1.0 - 1e-6 or len(out["candidates"]) == 1


# ---------------------------------------------------------------- pipeline integration


def test_pipeline_counterfactual_is_opt_in_and_matches_truth():
    base = DiagnosisEngine().diagnose("c", SEMI)
    assert "counterfactual" not in base["strategies"]        # default behaviour is unchanged

    r = DiagnosisEngine().diagnose("c", SEMI, counterfactual=True, cf_max_lines=5, cf_patches_per_line=3)
    cf = r["strategies"]["counterfactual"]
    assert cf["root_cause_line"] == 2 and 2 in cf["verified_lines"]
    assert r["root_cause_line"] == 2                         # existing rule/ML selection is untouched


def test_pipeline_counterfactual_survives_missing_toolchain():
    """Diagnosing with counterfactual=True must not crash even when nothing can compile -
    it should just come back with no verified candidates."""
    import compiler_engine.pipeline as pipeline_mod

    class FakeC(GnuAdapter):
        language = "c"; compiler = "definitely-not-a-compiler-xyz"; filename = "m.c"

    real_get_adapter = pipeline_mod.get_adapter
    pipeline_mod.get_adapter = lambda lang: FakeC() if lang == "c" else real_get_adapter(lang)
    try:
        r = DiagnosisEngine().diagnose("c", SEMI, counterfactual=True)
    finally:
        pipeline_mod.get_adapter = real_get_adapter
    assert r["status"] == "toolchain_missing"
