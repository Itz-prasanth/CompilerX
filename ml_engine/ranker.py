"""Inference wrapper around the persisted scikit-learn ranking model."""
from __future__ import annotations
import logging
import os
from typing import Dict, List, Optional
from compiler_engine.common.diagnostic import Diagnostic
from compiler_engine.localization.candidates import generate_candidates
from compiler_engine.parser.analysis import SourceAnalysis
from .features import FEATURE_NAMES, FEATURE_VERSION, featurize

DEFAULT_MODEL = os.environ.get("COMPILERX_MODEL", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "model", "ranker.joblib"))

log = logging.getLogger("compilerx.ml_engine.ranker")


class MLRanker:
    def __init__(self, path: str = DEFAULT_MODEL):
        self.path = path; self.bundle: Optional[dict] = None; self.error: Optional[str] = None
        self.load()

    def load(self):
        try:
            import joblib
            import sklearn
            if not os.path.exists(self.path):
                self.error = "model file not found - run scripts/train_model.sh"; return
            b = joblib.load(self.path)    # NOTE: pickle - only load models you trained yourself
            if b.get("feature_version") != FEATURE_VERSION or b.get("feature_names") != FEATURE_NAMES:
                self.error = "model/feature version mismatch - retrain"; return
            trained_with = b.get("sklearn_version")
            if trained_with and trained_with != sklearn.__version__:
                # Not fatal by itself (the load above already succeeded), but scikit-learn
                # does not guarantee pickle compatibility across versions, so a mismatch
                # here is the leading indicator the NEXT retrain/redeploy will break
                # unpickling (e.g. "ModuleNotFoundError: No module named '_loss'" for
                # GradientBoostingClassifier). Surface it loudly instead of staying quiet.
                log.warning(
                    "ml_ranker.sklearn_version_mismatch model trained with %s, running %s - retrain via scripts/train_model.sh to keep this in sync",
                    trained_with, sklearn.__version__,
                    extra={"extra_fields": {"trained_with": trained_with, "running": sklearn.__version__, "model_path": self.path}},
                )
            self.bundle = b; self.error = None
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            # Log the full traceback for debugging; self.error stays a short message so
            # the API response (pipeline.py's "unavailable: <ml_note>") doesn't leak a
            # multi-line stack trace to clients. Rule-based ranking is unaffected -
            # DiagnosisEngine.diagnose() falls back to it whenever self.available is False.
            log.exception(
                "ml_ranker.load_failed path=%s", self.path,
                extra={"extra_fields": {"model_path": self.path, "error": self.error}},
            )

    @property
    def available(self) -> bool:
        return self.bundle is not None

    def rank(self, a: SourceAnalysis, diag: Diagnostic, lines: Optional[List[int]] = None) -> List[Dict]:
        if not self.available:
            raise RuntimeError(self.error or "model unavailable")
        lines = lines if lines is not None else generate_candidates(a, diag)
        X = featurize(a, diag, lines)
        p = self.bundle["model"].predict_proba(X)[:, 1]
        tot = float(sum(p)) or 1.0
        out = [{"line": n, "score": round(float(s) / tot, 4), "probability": round(float(s), 4), "evidence": [], "strategy": "ml"}
               for n, s in zip(lines, p)]
        out.sort(key=lambda d: (-d["score"], diag.line - d["line"]))
        return out

    def status(self) -> Dict:
        if not self.available:
            return {"available": False, "path": self.path, "error": self.error}
        b = self.bundle
        return {"available": True, "path": self.path, "model": b["name"], "trained_at": b["trained_at"],
                "validation": b["validation"], "n_train_samples": b["n_train_samples"],
                "n_features": len(b["feature_names"]), "sklearn_version": b["sklearn_version"],
                "preferred_strategy": b.get("preferred_strategy", "ml"), "dataset": b.get("dataset")}
