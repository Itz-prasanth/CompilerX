"""Framework-independent API core. Both the stdlib server and the FastAPI app are thin wrappers over this."""
from __future__ import annotations
import json, logging, os, threading, time, uuid
from typing import Dict, List, Optional
from compiler_engine.common.diagnostic import LANGUAGES
from compiler_engine.common.process import netns_available
from compiler_engine.languages.registry import all_adapters, get_adapter
from compiler_engine.languages.base import UnsafeSourceError
from compiler_engine.patches.generator import Edit, Patch, apply_edits, validate_patch
from compiler_engine.pipeline import DiagnosisEngine
from compiler_engine.parser.analysis import analyze
from ml_engine.ranker import MLRanker, DEFAULT_MODEL
from .db import Store

log = logging.getLogger("compilerx.service")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_STDIN = 10_000


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message); self.status = status; self.message = message


def _need(body: dict, key: str, typ=str):
    if not isinstance(body, dict) or key not in body:
        raise ApiError(422, f"missing field: {key}")
    if not isinstance(body[key], typ):
        raise ApiError(422, f"field {key!r} must be {typ.__name__}")
    return body[key]


def _lang(body):
    l = _need(body, "language")
    if l not in LANGUAGES:
        raise ApiError(422, f"unsupported language {l!r}; choose one of {list(LANGUAGES)}")
    return l


class Service:
    def __init__(self, db_path: Optional[str] = None, model_path: str = DEFAULT_MODEL, dataset_dir: Optional[str] = None):
        self.store = Store(db_path or os.environ.get("COMPILERX_DB", os.path.join(ROOT, "data", "compilerx.db")))
        self.ranker = MLRanker(model_path)
        self.model_path = model_path
        self.dataset_dir = dataset_dir or os.path.join(ROOT, "data", "dataset")
        self.engine = DiagnosisEngine(self.ranker)
        self.execution_enabled = os.environ.get("COMPILERX_ENABLE_EXECUTION", "0") == "1"
        self.jobs: Dict[str, dict] = {}

    # ------------------------------------------------------------------ info
    def health(self):
        tc = {l: a.toolchain().to_dict() for l, a in all_adapters().items()}
        return {"status": "ok", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "toolchains": tc,
                "all_toolchains_available": all(t["available"] for t in tc.values()),
                "model": {"available": self.ranker.available, "error": self.ranker.error},
                "execution": self.execution_info()}

    def execution_info(self):
        return {"enabled": self.execution_enabled,
                "isolation": "partial: rlimits, timeout, output cap, scrubbed env, temp dir" + (", network namespace" if netns_available() else "") +
                             " - NO filesystem or PID isolation; not a security sandbox",
                "how_to_enable": "set COMPILERX_ENABLE_EXECUTION=1 (only in a container/VM you are willing to lose)"}

    def languages(self):
        out = []
        for l, a in all_adapters().items():
            out.append({"id": l, "display": a.display, "extension": a.extension, "toolchain": a.toolchain().to_dict()})
        return {"languages": out}

    def samples(self):
        from benchmarks.corpus import CASES
        valid = {"c": '#include <stdio.h>\nint main(void) {\n    printf("hello\\n");\n    return 0;\n}\n',
                 "cpp": '#include <iostream>\nint main() {\n    std::cout << "hello" << std::endl;\n    return 0;\n}\n',
                 "java": 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("hello");\n    }\n}\n',
                 "python": 'print("hello")\n'}
        s = [{"id": f"{l}-valid", "language": l, "title": f"{l}: valid hello-world", "source": src} for l, src in valid.items()]
        s += [{"id": c["id"], "language": c["language"], "title": f"{c['language']}: {c['id']} (bug on line {c['truth_line']})", "source": c["source"]} for c in CASES]
        return {"samples": s}

    # ------------------------------------------------------------------ compile / run / diagnose
    def compile(self, body: dict):
        lang = _lang(body); src = _need(body, "source")
        try:
            return get_adapter(lang).check(src).to_dict()
        except UnsafeSourceError as e:
            raise ApiError(422, str(e))

    def run(self, body: dict):
        lang = _lang(body); src = _need(body, "source"); stdin = body.get("stdin", "")
        if not self.execution_enabled:
            raise ApiError(403, "execution is disabled on this server (no secure sandbox available). " + self.execution_info()["how_to_enable"])
        if not isinstance(stdin, str) or len(stdin) > MAX_STDIN:
            raise ApiError(422, "stdin must be a string of at most 10000 characters")
        timeout = min(max(float(body.get("timeout", 5)), 0.5), 10.0)
        try:
            r = get_adapter(lang).build_and_run(src, stdin, timeout)
        except (UnsafeSourceError, ValueError) as e:
            raise ApiError(422, str(e))
        r["isolation_note"] = self.execution_info()["isolation"]
        return r

    def diagnose(self, body: dict):
        lang = _lang(body); src = _need(body, "source")
        try:
            r = self.engine.diagnose(lang, src, validate=bool(body.get("validate", True)), top_k=int(body.get("top_k", 5)),
                                      counterfactual=bool(body.get("counterfactual", False)),
                                      cf_max_lines=int(body.get("cf_max_lines", 6)), cf_patches_per_line=int(body.get("cf_patches_per_line", 3)))
        except UnsafeSourceError as e:
            raise ApiError(422, str(e))
        try:
            self.store.add_history(lang, src, r)
        except Exception:
            log.exception("history write failed")
        return r

    def counterfactual(self, body: dict):
        """Counterfactual Repair Lab (Phase 2-3): full diagnosis plus the bounded,
        real-compiler-validated, evidence-ranked candidate list. A thin wrapper over
        diagnose() with counterfactual evaluation forced on, so the Lab panel sees exactly
        the same baseline diagnostics/rule/ML output as the main IDE view plus the extra
        'counterfactual' strategy - nothing is recomputed or duplicated."""
        lang = _lang(body); src = _need(body, "source")
        max_lines = int(body.get("max_lines", 6)); patches_per_line = int(body.get("patches_per_line", 3))
        if not (1 <= max_lines <= 12):
            raise ApiError(422, "max_lines must be between 1 and 12")
        if not (1 <= patches_per_line <= 6):
            raise ApiError(422, "patches_per_line must be between 1 and 6")
        try:
            r = self.engine.diagnose(lang, src, validate=bool(body.get("validate", True)), top_k=int(body.get("top_k", 5)),
                                      counterfactual=True, cf_max_lines=max_lines, cf_patches_per_line=patches_per_line)
        except UnsafeSourceError as e:
            raise ApiError(422, str(e))
        if r.get("status") != "syntax_error":
            raise ApiError(409, f"no syntax error to analyse (status={r.get('status')})")
        try:
            self.store.add_history(lang, src, r)
        except Exception:
            log.exception("history write failed")
        return r

    # ------------------------------------------------------------------ patches (never auto-applied)
    @staticmethod
    def _patch_from(body: dict, src: str) -> Patch:
        p = _need(body, "patch", dict)
        edits = p.get("edits")
        if not isinstance(edits, list) or not edits or len(edits) > 20:
            raise ApiError(422, "patch.edits must be a non-empty list (max 20)")
        es = []
        for e in edits:
            try:
                off, dele, ins = int(e["offset"]), int(e["delete"]), str(e["insert"])
            except Exception:
                raise ApiError(422, "each edit needs integer offset/delete and string insert")
            if off < 0 or dele < 0 or off + dele > len(src) or len(ins) > 1000:
                raise ApiError(422, "edit out of range")
            es.append(Edit(off, dele, ins))
        return Patch(str(p.get("template", "custom")), str(p.get("description", "")), int(p.get("line", 0)), es)

    def validate_patch(self, body: dict):
        lang = _lang(body); src = _need(body, "source")
        patch = self._patch_from(body, src)
        ad = get_adapter(lang); orig = ad.check(src).first_error()
        if orig is None:
            raise ApiError(409, "the original source has no error to fix")
        return {"validation": validate_patch(ad, src, patch, orig), "patched_source": apply_edits(src, patch.edits)}

    def apply_patch(self, body: dict):
        lang = _lang(body); src = _need(body, "source")
        if body.get("accept") is not True:
            raise ApiError(400, "patch not applied: the user must explicitly accept (accept: true)")
        patch = self._patch_from(body, src)
        new = apply_edits(src, patch.edits)
        r = get_adapter(lang).check(new)
        return {"source": new, "revalidation": {"ok": r.ok, "errors": [d.to_dict() for d in r.errors][:5]}}

    # ------------------------------------------------------------------ model / benchmark / history
    def model_status(self):
        st = self.ranker.status()
        card = os.path.splitext(self.model_path)[0] + ".card.json"
        if os.path.exists(card):
            st["card"] = json.load(open(card))
        return st

    def benchmark_results(self):
        r = self.store.latest_benchmark()
        if r is None:
            p = os.path.join(ROOT, "data", "benchmarks", "latest.json")
            if os.path.exists(p):
                r = json.load(open(p))
        return {"available": r is not None, "results": r}

    def benchmark_start(self, body: dict):
        if any(j["state"] == "running" for j in self.jobs.values()):
            raise ApiError(409, "a benchmark is already running")
        if not os.path.exists(os.path.join(self.dataset_dir, "samples.jsonl")):
            raise ApiError(409, "no dataset found - run scripts/generate_dataset.sh first")
        limit = int(body.get("suggestion_limit", 10)); split = body.get("split", "test")
        if split not in ("train", "val", "test"):
            raise ApiError(422, "split must be train|val|test")
        jid = uuid.uuid4().hex[:8]; self.jobs[jid] = {"id": jid, "state": "running", "started": time.time()}

        def work():
            try:
                from benchmarks.runner import run
                res = run(self.dataset_dir, self.model_path, split, limit, out_dir=os.path.join(ROOT, "data", "benchmarks"), log=lambda *_: None)
                self.store.add_benchmark(res); self.jobs[jid].update(state="done", finished=time.time())
            except Exception as e:
                log.exception("benchmark failed"); self.jobs[jid].update(state="failed", error=f"{type(e).__name__}: {e}")
        threading.Thread(target=work, daemon=True).start()
        return self.jobs[jid]

    def benchmark_status(self, job_id: Optional[str] = None):
        if job_id:
            if job_id not in self.jobs:
                raise ApiError(404, "unknown job")
            return self.jobs[job_id]
        return {"jobs": list(self.jobs.values())}

    def history(self, limit=50):
        return {"history": self.store.history(max(1, min(int(limit), 500)))}
