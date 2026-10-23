import os, json, tempfile
from ml_engine import dataset_generator as dg
from ml_engine.corruptions import apply, KINDS
from ml_engine.program_gen import ProgramGenerator
from ml_engine.features import FEATURE_NAMES, featurize
from ml_engine.ranker import MLRanker
from ml_engine import train as tr
from benchmarks import runner
import random

_CACHE = {}


def _small_dataset():
    if "d" not in _CACHE:
        d = tempfile.mkdtemp(); _CACHE["d"] = d
        dg.build(d, programs_per_lang=14, variants_per_program=4, seed=3, languages=["c", "python"], log=lambda *_: None)
    return _CACHE["d"]


def test_generator_is_deterministic():
    assert ProgramGenerator("c", 5).generate() == ProgramGenerator("c", 5).generate()
    assert ProgramGenerator("c", 5).generate() != ProgramGenerator("c", 6).generate()


def test_corruption_preserves_line_numbers_and_changes_one_line():
    src = ProgramGenerator("c", 1).generate(); rng = random.Random(0)
    for kind in KINDS:
        r = apply("c", src, kind, rng)
        if r is None:
            continue
        bad, truth = r
        assert len(bad.split("\n")) == len(src.split("\n"))
        diff = [i + 1 for i, (x, y) in enumerate(zip(src.split("\n"), bad.split("\n"))) if x != y]
        assert diff == [truth], (kind, diff, truth)


def test_dataset_split_has_no_program_leakage_and_labels_are_sound():
    d = _small_dataset(); S = dg.load(d)
    assert S
    by_prog = {}
    for s in S:
        by_prog.setdefault(s["program_id"], set()).add(s["split"])
    assert all(len(v) == 1 for v in by_prog.values())
    for s in S:
        assert sum(c["label"] for c in s["candidates"]) <= 1
        assert all(len(c["features"]) == len(FEATURE_NAMES) for c in s["candidates"])


def test_training_saves_reloads_and_ranks():
    d = _small_dataset(); m = os.path.join(tempfile.mkdtemp(), "m.joblib")
    card = tr.train(d, m, log=lambda *_: None)
    r = MLRanker(m); assert r.available and card["validation"]["selected"] in ("random_forest", "gradient_boosting")
    s = [x for x in dg.load(d) if x["language"] == "c"][0]
    from compiler_engine.common.diagnostic import Diagnostic
    from compiler_engine.parser.analysis import analyze
    dd = Diagnostic("c", s["reported_line"], s["reported_col"], s["message"], expected=s["expected"], category=s["diag_category"])
    rk = r.rank(analyze("c", s["source"]), dd)
    assert abs(sum(x["score"] for x in rk) - 1) < 0.01
    assert rk == MLRanker(m).rank(analyze("c", s["source"]), dd)      # reload is deterministic


def test_missing_model_is_handled():
    r = MLRanker("/nonexistent/model.joblib"); assert not r.available and r.error


def test_metric_functions():
    rows = [{"truth": 3, "ranks": {"conventional": [4], "rule": [3, 4], "ml": [2, 3]}},
            {"truth": 5, "ranks": {"conventional": [5], "rule": [4, 5], "ml": [5]}}]
    assert runner._summ(rows, "conventional")["top1"] == 0.5
    assert runner._summ(rows, "rule")["top1"] == 0.5 and runner._summ(rows, "rule")["top3"] == 1.0
    assert abs(runner._summ(rows, "ml")["mrr"] - 0.75) < 1e-9
    assert runner.wilson(0, 0) == [0.0, 0.0] and 0 < runner.wilson(5, 10)[0] < 0.5 < runner.wilson(5, 10)[1] < 1
    assert runner.sign_test_p(10, 0) < 0.01 and runner.sign_test_p(3, 3) == 1.0


def test_benchmark_runs_on_small_dataset():
    d = _small_dataset(); m = os.path.join(tempfile.mkdtemp(), "m.joblib")
    tr.train(d, m, log=lambda *_: None)
    out = tempfile.mkdtemp()
    res = runner.run(d, m, split="val", suggestion_limit=2, out_dir=out, log=lambda *_: None)
    assert res["n_samples"] > 0 and set(res["overall"]) == {"conventional", "rule", "ml"}
    assert os.path.exists(os.path.join(out, "latest.json")) and "# CompilerX-AI" in runner.to_markdown(res)
    # Phase 4: strategy D (counterfactual) rides along on the same bounded, compile-validated subset
    ce = res["counterfactual_eval"]
    assert ce["n"] > 0 and 0 <= ce["top1"] <= 1 and 0 <= ce["false_correction_rate"] <= 1
    assert ce["n"] == res["suggestion_correctness"]["overall"]["rule"]["n"]       # same sample set, by construction
    assert "Strategy D" in runner.to_markdown(res)


def test_select_rows_is_deterministic_and_shared_across_eval_passes():
    rows = [{"id": f"{lang}-{i}", "language": lang} for lang in ("c", "python") for i in range(5)]
    sel1 = runner._select_rows(rows, 2); sel2 = runner._select_rows(rows, 2)
    assert [r["id"] for r in sel1] == [r["id"] for r in sel2]
    assert sum(r["language"] == "c" for r in sel1) == 2 and sum(r["language"] == "python" for r in sel1) == 2
