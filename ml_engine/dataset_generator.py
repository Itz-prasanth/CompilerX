"""Reproducible synthetic dataset: valid programs -> controlled corruptions -> real compiler diagnostics."""
from __future__ import annotations
import argparse, hashlib, json, os, random, time
from typing import Dict, List
from compiler_engine.common.diagnostic import LANGUAGES
from compiler_engine.languages.registry import get_adapter
from compiler_engine.parser.analysis import analyze
from compiler_engine.localization.candidates import generate_candidates
from .corruptions import KINDS, KIND_TO_CATEGORY, apply
from .features import FEATURE_VERSION, FEATURE_NAMES, featurize
from .program_gen import ProgramGenerator


def _split_for(pid: int, seed: int) -> str:
    """Split by ORIGINAL PROGRAM (hash of program id) so no program appears in two splits."""
    h = int(hashlib.sha256(f"{seed}:{pid}".encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else "val" if h < 85 else "test"


def build(out_dir: str, programs_per_lang: int = 120, variants_per_program: int = 6, seed: int = 7,
          languages=LANGUAGES, log=print) -> Dict:
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(seed)
    samples: List[dict] = []; stats = {"programs": {}, "attempted": {}, "kept": {}, "valid_rejected": {}}
    t0 = time.time()
    for lang in languages:
        ad = get_adapter(lang)
        progs = [(pid, ProgramGenerator(lang, seed * 100003 + pid * 7 + LANGUAGES.index(lang)).generate())
                 for pid in range(programs_per_lang)]
        res = ad.check_many([p for _, p in progs]) if lang == "java" else [ad.check(p) for _, p in progs]
        valid = [(pid, p) for (pid, p), r in zip(progs, res) if r.ok]
        stats["valid_rejected"][lang] = len(progs) - len(valid)
        stats["programs"][lang] = len(valid)
        # --- corrupt
        pending = []
        for pid, p in valid:
            kinds = rng.sample(KINDS, k=len(KINDS))
            made = 0
            for kind in kinds:
                if made >= variants_per_program:
                    break
                r = apply(lang, p, kind, rng)
                if r is None:
                    continue
                pending.append((pid, p, kind, r[0], r[1])); made += 1
        stats["attempted"][lang] = len(pending)
        cres = ad.check_many([x[3] for x in pending]) if lang == "java" else [ad.check(x[3]) for x in pending]
        kept = 0
        for (pid, orig, kind, bad, truth), r in zip(pending, cres):
            diag = r.first_error()
            if r.ok or diag is None or not diag.is_syntax or r.timed_out:
                continue
            a = analyze(lang, bad)
            cand = generate_candidates(a, diag)
            feats = featurize(a, diag, cand)
            samples.append({
                "id": f"{lang}-{pid}-{kind}-{len(samples)}", "program_id": f"{lang}-{pid}", "language": lang,
                "split": _split_for(pid + 1000 * LANGUAGES.index(lang), seed),
                "corruption": kind, "true_category": KIND_TO_CATEGORY[kind], "truth_line": truth,
                "reported_line": diag.line, "reported_col": diag.column, "message": diag.message,
                "diag_category": diag.category, "expected": diag.expected,
                "original": orig, "source": bad,
                "candidates": [{"line": n, "features": f, "label": 1 if n == truth else 0} for n, f in zip(cand, feats)],
            })
            kept += 1
        stats["kept"][lang] = kept
        log(f"[{lang}] programs valid={len(valid)}/{len(progs)} corrupted kept={kept}/{len(pending)}  ({time.time()-t0:.0f}s)")
    with open(os.path.join(out_dir, "samples.jsonl"), "w") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")
    meta = {"seed": seed, "programs_per_lang": programs_per_lang, "variants_per_program": variants_per_program,
            "feature_version": FEATURE_VERSION, "feature_names": FEATURE_NAMES, "stats": stats, "n_samples": len(samples),
            "split_counts": {sp: sum(1 for s in samples if s["split"] == sp) for sp in ("train", "val", "test")},
            "split_programs": {sp: len({s["program_id"] for s in samples if s["split"] == sp}) for sp in ("train", "val", "test")}}
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def load(out_dir: str) -> List[dict]:
    with open(os.path.join(out_dir, "samples.jsonl")) as f:
        return [json.loads(l) for l in f]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/dataset"); ap.add_argument("--programs-per-lang", type=int, default=120)
    ap.add_argument("--variants", type=int, default=6); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--languages", nargs="+", default=list(LANGUAGES))
    a = ap.parse_args()
    m = build(a.out, a.programs_per_lang, a.variants, a.seed, a.languages)
    print(json.dumps({k: m[k] for k in ("n_samples", "split_counts", "split_programs", "stats")}, indent=1))
