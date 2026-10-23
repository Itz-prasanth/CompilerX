"""Train candidate ranking models, choose by VALIDATION top-1, persist. Test split is never touched here."""
from __future__ import annotations
import argparse, json, os, time
import numpy as np
import joblib, sklearn
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from compiler_engine.common.diagnostic import Diagnostic
from compiler_engine.parser.analysis import analyze
from compiler_engine.localization import rules
from .dataset_generator import load
from .features import FEATURE_NAMES, FEATURE_VERSION


def _xy(samples):
    X, y, groups = [], [], []
    for gi, s in enumerate(samples):
        for c in s["candidates"]:
            X.append(c["features"]); y.append(c["label"]); groups.append(gi)
    return np.array(X, dtype=float), np.array(y), np.array(groups)


def group_metrics(samples, proba, groups):
    top1 = top3 = 0; mrr = 0.0
    for gi, s in enumerate(samples):
        idx = np.where(groups == gi)[0]
        lines = [c["line"] for c in s["candidates"]]
        order = np.argsort(-proba[idx], kind="stable")
        ranked = [lines[i] for i in order]
        if s["truth_line"] in ranked:
            r = ranked.index(s["truth_line"]) + 1
            top1 += r == 1; top3 += r <= 3; mrr += 1 / r
    n = max(len(samples), 1)
    return {"top1": top1 / n, "top3": top3 / n, "mrr": mrr / n, "n": len(samples)}


def rule_top1(samples):
    ok = 0
    for s in samples:
        d = Diagnostic(s["language"], s["reported_line"], s["reported_col"], s["message"], expected=s["expected"], category=s["diag_category"])
        r = rules.rank(analyze(s["language"], s["source"]), d)
        ok += r[0]["line"] == s["truth_line"]
    return ok / max(len(samples), 1)


def train(dataset_dir="data/dataset", model_path="data/model/ranker.joblib", seed=7, log=print):
    samples = load(dataset_dir)
    meta = json.load(open(os.path.join(dataset_dir, "meta.json")))
    assert meta["feature_version"] == FEATURE_VERSION and meta["feature_names"] == FEATURE_NAMES, "dataset/feature mismatch: regenerate"
    tr = [s for s in samples if s["split"] == "train"]; va = [s for s in samples if s["split"] == "val"]
    assert not ({s["program_id"] for s in tr} & {s["program_id"] for s in va}), "program leakage between splits"
    Xtr, ytr, _ = _xy(tr); Xva, yva, gva = _xy(va)
    models = {
        "random_forest": RandomForestClassifier(n_estimators=250, min_samples_leaf=2, class_weight="balanced_subsample", n_jobs=1, random_state=seed),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.1, subsample=0.8, random_state=seed),
    }
    results, fitted = {}, {}
    for name, m in models.items():
        t0 = time.time(); m.fit(Xtr, ytr)
        results[name] = group_metrics(va, m.predict_proba(Xva)[:, 1], gva); results[name]["fit_seconds"] = round(time.time() - t0, 1)
        fitted[name] = m
        log(f"{name}: val {results[name]}")
    best = max(results, key=lambda k: (results[k]["top1"], results[k]["mrr"]))
    rv = rule_top1(va)
    bundle = {"model": fitted[best], "name": best, "feature_names": FEATURE_NAMES, "feature_version": FEATURE_VERSION,
              "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sklearn_version": sklearn.__version__,
              "validation": {"candidates": results, "selected": best, "rule_based_top1": rv},
              "n_train_samples": len(tr), "preferred_strategy": "ml" if results[best]["top1"] >= rv else "rule",
              "dataset": {"seed": meta["seed"], "n_samples": meta["n_samples"], "split_counts": meta["split_counts"]}}
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(bundle, model_path)
    imp = getattr(fitted[best], "feature_importances_", None)
    card = {k: v for k, v in bundle.items() if k != "model"}
    if imp is not None:
        card["top_features"] = [(FEATURE_NAMES[i], round(float(imp[i]), 4)) for i in np.argsort(-imp)[:12]]
    json.dump(card, open(os.path.splitext(model_path)[0] + ".card.json", "w"), indent=2)
    log(f"selected {best} (val top1={results[best]['top1']:.3f}); rule-based val top1={rv:.3f}; saved {model_path}")
    return card


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/dataset"); ap.add_argument("--model", default="data/model/ranker.joblib")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(); train(a.dataset, a.model, a.seed)
