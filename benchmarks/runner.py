"""Benchmark: conventional vs rule-based vs ML localisation on the SAME held-out samples,
plus (Phase 4) a bounded, real-compiler-validated comparison that adds the counterfactual
evidence-enhanced ranking (strategy D) on a smaller subset - see counterfactual_eval()."""
from __future__ import annotations
import argparse, json, math, os, time
from collections import defaultdict
from typing import Dict, List
from compiler_engine.common.diagnostic import Diagnostic, LANGUAGES
from compiler_engine.languages.registry import get_adapter
from compiler_engine.parser.analysis import analyze
from compiler_engine.localization import rules
from compiler_engine.localization.candidates import generate_candidates
from compiler_engine.patches.generator import suggest
from compiler_engine.counterfactual import evaluate_candidates, rank as cf_rank
from ml_engine.dataset_generator import load
from ml_engine.ranker import MLRanker, DEFAULT_MODEL

STRATS = ("conventional", "rule", "ml")


def wilson(k, n, z=1.96):
    if n == 0:
        return [0.0, 0.0]
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 4), round(min(1, c + h), 4)]


def sign_test_p(a_only, b_only):
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def _summ(rows, strat):
    n = len(rows)
    if not n:
        return {"n": 0}
    t1 = t3 = 0; mrr = 0.0; err = 0.0
    for r in rows:
        rk = r["ranks"][strat]; t = r["truth"]
        t1 += rk[0] == t; t3 += t in rk[:3]
        mrr += 1 / (rk.index(t) + 1) if t in rk else 0
        err += abs(rk[0] - t)
    return {"n": n, "top1": round(t1 / n, 4), "top1_ci95": wilson(t1, n), "top3": round(t3 / n, 4),
            "mrr": round(mrr / n, 4), "mean_abs_line_error": round(err / n, 3)}


def _breakdown(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    return {k: {s: _summ(v, s) for s in STRATS} | {"n": len(v)} for k, v in sorted(g.items())}


def evaluate_rows(samples: List[dict], ranker: MLRanker) -> List[dict]:
    rows = []
    for s in samples:
        d = Diagnostic(s["language"], s["reported_line"], s["reported_col"], s["message"], expected=s["expected"], category=s["diag_category"])
        a = analyze(s["language"], s["source"])
        cands = generate_candidates(a, d)
        rule = [x["line"] for x in rules.rank(a, d, cands)]
        ml = [x["line"] for x in ranker.rank(a, d, cands)] if ranker.available else [d.line]
        rows.append({"id": s["id"], "language": s["language"], "corruption": s.get("corruption", "handwritten"),
                     "truth": s["truth_line"], "reported": d.line, "in_candidates": s["truth_line"] in cands,
                     "true_category": s.get("true_category"), "diag_category": s["diag_category"],
                     "ranks": {"conventional": [d.line], "rule": rule, "ml": ml},
                     "_d": d, "_a": a, "_sample": s})
    return rows


def _select_rows(rows, limit_per_lang: int) -> List[dict]:
    """Deterministic per-language sample cap shared by every compile-validated (expensive)
    benchmark pass, so suggestion_eval and counterfactual_eval score the SAME programs."""
    taken = defaultdict(int); out = []
    for r in sorted(rows, key=lambda x: x["id"]):
        if taken[r["language"]] >= limit_per_lang:
            continue
        taken[r["language"]] += 1
        out.append(r)
    return out


def suggestion_eval(rows, limit_per_lang: int, log=print) -> Dict:
    cache: Dict = {}; out = {s: {"fixed": 0, "n": 0} for s in STRATS}; per_lang = defaultdict(lambda: {s: {"fixed": 0, "n": 0} for s in STRATS})
    sel = _select_rows(rows, limit_per_lang); counts = defaultdict(int)
    for r in sel:
        lang = r["language"]; counts[lang] += 1
        ad = get_adapter(lang)
        for st in STRATS:
            ln = r["ranks"][st][0]
            key = (r["id"], ln)
            if key not in cache:
                res = suggest(ad, r["_a"], r["_d"], [ln], max_validations=6)
                cache[key] = bool(res["best"] and res["best"].validation["status"] == "fixed")
            out[st]["n"] += 1; out[st]["fixed"] += cache[key]
            per_lang[lang][st]["n"] += 1; per_lang[lang][st]["fixed"] += cache[key]
        log(f"  suggestion eval {lang} {counts[lang]}/{limit_per_lang}", )
    for st in STRATS:
        out[st]["rate"] = round(out[st]["fixed"] / max(out[st]["n"], 1), 4)
    return {"overall": out, "per_language": {k: v for k, v in per_lang.items()}, "limit_per_language": limit_per_lang}


def counterfactual_eval(rows, limit_per_lang: int, cf_max_lines: int = 5, cf_patches_per_line: int = 3, log=print) -> Dict:
    """Phase 4, strategy D: on the SAME bounded sample set as suggestion_eval (compile
    validation is expensive, so this is deliberately NOT run over the full held-out split -
    exactly the cost trade-off suggestion_eval already makes), rank candidates with
    evidence_ranker.rank() (rule+ML priors + real-compiler evidence) and report:
      - top1 / top3 / mrr           : same definitions as the no-compile strategies above
      - verified_repair_rate        : fraction of samples where SOME candidate's patch
                                       actually compiled cleanly (the system found *a*
                                       working repair, not necessarily at the true line)
      - false_correction_rate       : of those verified repairs, the fraction whose
                                       top-ranked compiling candidate is NOT the true
                                       corruption line - a compiling patch is evidence of
                                       a valid fix, not proof of the original mistake
      - avg_validation_ms           : mean wall-clock time spent compiling candidate
                                       patches, per sample
    """
    sel = _select_rows(rows, limit_per_lang)
    n = t1 = t3 = verified = false_corr = 0; mrr = 0.0; total_ms = 0.0
    per_lang = defaultdict(lambda: {"n": 0, "top1": 0, "top3": 0, "mrr": 0.0, "verified": 0, "false_corr": 0, "ms": 0.0})
    for r in sel:
        lang = r["language"]; ad = get_adapter(lang)
        lines = r["ranks"]["rule"][:cf_max_lines]
        ev = evaluate_candidates(ad, r["_a"], r["_d"], lines, max_lines=cf_max_lines, patches_per_line=cf_patches_per_line)
        rule_cands = rules.rank(r["_a"], r["_d"], lines)
        ranked = cf_rank(lines, rule_cands, None, ev, r["_d"].line, top_k=len(lines))
        order = [c["line"] for c in ranked["candidates"]]
        t = r["truth"]; pl = per_lang[lang]
        n += 1; pl["n"] += 1
        hit1 = bool(order) and order[0] == t; t1 += hit1; pl["top1"] += hit1
        hit3 = t in order[:3]; t3 += hit3; pl["top3"] += hit3
        rr = (1 / (order.index(t) + 1)) if t in order else 0.0; mrr += rr; pl["mrr"] += rr
        is_verified = bool(ranked["verified_lines"]); verified += is_verified; pl["verified"] += is_verified
        is_false = is_verified and not hit1; false_corr += is_false; pl["false_corr"] += is_false
        ms = sum(att.duration_ms for le in ev for att in le.attempts); total_ms += ms; pl["ms"] += ms
        log(f"  counterfactual eval {lang} {pl['n']}/{limit_per_lang}")

    def _rate(num, den):
        return round(num / den, 4) if den else 0.0

    out = {"n": n, "top1": _rate(t1, n), "top3": _rate(t3, n), "mrr": _rate(mrr, n),
           "verified_repair_rate": _rate(verified, n), "false_correction_rate": _rate(false_corr, verified),
           "avg_validation_ms": round(total_ms / n, 1) if n else 0.0,
           "limit_per_language": limit_per_lang, "cf_max_lines": cf_max_lines, "cf_patches_per_line": cf_patches_per_line}
    out["per_language"] = {k: {"n": v["n"], "top1": _rate(v["top1"], v["n"]), "top3": _rate(v["top3"], v["n"]),
                                "mrr": _rate(v["mrr"], v["n"]), "verified_repair_rate": _rate(v["verified"], v["n"]),
                                "false_correction_rate": _rate(v["false_corr"], v["verified"]),
                                "avg_validation_ms": round(v["ms"] / v["n"], 1) if v["n"] else 0.0}
                            for k, v in per_lang.items()}
    return out


def run(dataset_dir="data/dataset", model_path=DEFAULT_MODEL, split="test", suggestion_limit=25, out_dir="data/benchmarks", log=print) -> Dict:
    from .corpus import CASES
    t0 = time.time()
    ranker = MLRanker(model_path)
    samples = [s for s in load(dataset_dir) if s["split"] == split]
    rows = evaluate_rows(samples, ranker)
    res: Dict = {"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "split": split, "n_samples": len(rows),
                 "ml_available": ranker.available, "model": ranker.status(), "programs": len({s["program_id"] for s in samples})}
    res["candidate_recall"] = round(sum(r["in_candidates"] for r in rows) / max(len(rows), 1), 4)
    res["overall"] = {s: _summ(rows, s) for s in STRATS}
    res["by_language"] = _breakdown(rows, "language")
    res["by_corruption"] = _breakdown(rows, "corruption")
    cl = defaultdict(lambda: [0, 0])
    for r in rows:
        cl[r["language"]][1] += 1; cl[r["language"]][0] += r["true_category"] == r["diag_category"]; cl["ALL"][1] += 1; cl["ALL"][0] += r["true_category"] == r["diag_category"]
    res["classification_accuracy"] = {k: {"accuracy": round(v[0] / v[1], 4), "n": v[1]} for k, v in cl.items()}
    ok = lambda r, s: r["ranks"][s][0] == r["truth"]
    res["paired_tests"] = {}
    for a_, b_ in (("ml", "conventional"), ("ml", "rule"), ("rule", "conventional")):
        ao = sum(ok(r, a_) and not ok(r, b_) for r in rows); bo = sum(ok(r, b_) and not ok(r, a_) for r in rows)
        res["paired_tests"][f"{a_}_vs_{b_}"] = {f"{a_}_only_correct": ao, f"{b_}_only_correct": bo, "sign_test_p": sign_test_p(ao, bo)}
    drift = defaultdict(int)
    for r in rows:
        drift[min(abs(r["reported"] - r["truth"]), 6)] += 1
    res["compiler_line_drift"] = {str(k): v for k, v in sorted(drift.items())}
    log(f"localisation done on {len(rows)} samples ({time.time()-t0:.0f}s)")
    if suggestion_limit > 0:
        res["suggestion_correctness"] = suggestion_eval(rows, suggestion_limit, log=lambda *_: None)
        res["counterfactual_eval"] = counterfactual_eval(rows, suggestion_limit, log=lambda *_: None)
        log(f"counterfactual eval done on {res['counterfactual_eval']['n']} samples")
    # hand-written corpus (qualitative, small n)
    hw = []
    for c in CASES:
        ad = get_adapter(c["language"]); chk = ad.check(c["source"]); d = chk.first_error()
        if chk.ok or d is None:
            hw.append({"id": c["id"], "skipped": "source compiled cleanly or no error"}); continue
        hw.append({"id": c["id"], "language": c["language"], "message": d.message, "category": d.category, "syntax": d.is_syntax,
                   "s": dict(c, source=c["source"], expected=d.expected, reported_line=d.line, reported_col=d.column, message=d.message, diag_category=d.category, id=c["id"])})
    hrows = evaluate_rows([h["s"] for h in hw if "s" in h], ranker) if hw else []
    res["handwritten"] = {"n": len(hrows), "overall": {s: _summ(hrows, s) for s in STRATS},
                          "cases": [{"id": r["id"], "truth": r["truth"], "reported": r["reported"],
                                     "rule_top1": r["ranks"]["rule"][0], "ml_top1": r["ranks"]["ml"][0]} for r in hrows],
                          "skipped": [h for h in hw if "skipped" in h]}
    res["runtime_seconds"] = round(time.time() - t0, 1)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "latest.json")
    json.dump(res, open(path, "w"), indent=2)
    json.dump(res, open(os.path.join(out_dir, f"run_{res['created'].replace(':', '')}.json"), "w"), indent=2)
    return res


def to_markdown(res: Dict) -> str:
    pct = lambda x: f"{100*x:.1f}%"
    L = ["# CompilerX-AI benchmark report", "",
         f"Generated {res['created']} - held-out **{res['split']}** split: **{res['n_samples']}** corrupted programs "
         f"from **{res['programs']}** original programs never used for training. Candidate recall (true line inside the candidate window): {pct(res['candidate_recall'])}.", "",
         "## Overall (top-1 = the strategy's first-ranked line is the injected-corruption line)", "",
         "| Strategy | Top-1 (95% CI) | Top-3 | MRR | Mean abs. line error |", "|---|---|---|---|---|"]
    for s in STRATS:
        o = res["overall"][s]
        L.append(f"| {s} | {pct(o['top1'])} ({pct(o['top1_ci95'][0])}-{pct(o['top1_ci95'][1])}) | {pct(o['top3'])} | {o['mrr']:.3f} | {o['mean_abs_line_error']:.2f} |")
    L += ["", "Conventional reporting emits one line, so its top-3 equals its top-1.", "", "## Per language (top-1)", "", "| Language | n | conventional | rule | ml |", "|---|---|---|---|---|"]
    for k, v in res["by_language"].items():
        L.append(f"| {k} | {v['n']} | " + " | ".join(pct(v[s]['top1']) for s in STRATS) + " |")
    L += ["", "## Per injected corruption (top-1)", "", "| Corruption | n | conventional | rule | ml |", "|---|---|---|---|---|"]
    for k, v in res["by_corruption"].items():
        L.append(f"| {k} | {v['n']} | " + " | ".join(pct(v[s]['top1']) for s in STRATS) + " |")
    L += ["", "## Error-type classification (compiler message -> category vs injected category)", ""]
    for k, v in res["classification_accuracy"].items():
        L.append(f"- {k}: {pct(v['accuracy'])} (n={v['n']})")
    L += ["", "## Paired comparisons (top-1, exact two-sided sign test on discordant pairs)", ""]
    for k, v in res["paired_tests"].items():
        L.append(f"- {k}: " + ", ".join(f"{a}={b}" for a, b in v.items() if a != "sign_test_p") + f", p={v['sign_test_p']:.3g}")
    if "suggestion_correctness" in res:
        sc = res["suggestion_correctness"]
        L += ["", f"## Suggestion correctness (patch at the strategy's top-1 line makes the file compile; first {sc['limit_per_language']} test samples per language)", ""]
        for s in STRATS:
            o = sc["overall"][s]; L.append(f"- {s}: {o['fixed']}/{o['n']} = {pct(o['rate'])}")
    if "counterfactual_eval" in res:
        ce = res["counterfactual_eval"]
        L += ["", f"## Strategy D - counterfactual evidence-enhanced ranking (same {ce['limit_per_language']}-per-language "
                  f"compile-validated subset as above, n={ce['n']}; NOT the full held-out split, because this is the one "
                  "strategy that actually compiles candidate patches)", "",
              "| Metric | Value |", "|---|---|",
              f"| Top-1 | {pct(ce['top1'])} |", f"| Top-3 | {pct(ce['top3'])} |", f"| MRR | {ce['mrr']:.3f} |",
              f"| Verified repair rate (some candidate patch compiles) | {pct(ce['verified_repair_rate'])} |",
              f"| False-correction rate (a compiling patch, but at the wrong line) | {pct(ce['false_correction_rate'])} |",
              f"| Avg. validation time / sample | {ce['avg_validation_ms']:.0f} ms |",
              "", "_A compiling candidate patch is evidence it is **a** valid fix, not proof it is **the** original "
                  "mistake - see false-correction rate above._"]
    hw = res["handwritten"]
    L += ["", f"## Hand-written corpus (n={hw['n']}; qualitative - too small for statistics)", "", "| Strategy | Top-1 |", "|---|---|"]
    for s in STRATS:
        L.append(f"| {s} | {pct(hw['overall'][s]['top1'])} |")
    L += ["", "## How far the compiler's reported line is from the real mistake", "", "| |reported - true| (lines) | count |", "|---|---|"]
    for k, v in res["compiler_line_drift"].items():
        L.append(f"| {k}{'+' if k == '6' else ''} | {v} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/dataset"); ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--split", default="test"); ap.add_argument("--suggestion-limit", type=int, default=25)
    ap.add_argument("--report", default="docs/BENCHMARK_REPORT.md")
    a = ap.parse_args()
    r = run(a.dataset, a.model, a.split, a.suggestion_limit)
    os.makedirs(os.path.dirname(a.report), exist_ok=True)
    open(a.report, "w").write(to_markdown(r)); print(to_markdown(r))
