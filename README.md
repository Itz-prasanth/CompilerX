# CompilerX-AI
Multi-language compiler **error localisation, recovery & explanation**. A compiler reports where the parser *stopped*;
CompilerX-AI estimates where the mistake *began*, proposes a minimal patch, validates it on a temporary copy, and explains why.

```c
int main() {
    int price = 100        // <- real mistake (line 2)
    int tax = 18;          // <- gcc reports line 3: expected ',' or ';' before 'int'
```
Produced by the actual engine (not hard-coded): reported line 3 -> root cause line 2 -> patch "Add ';' at the end of line 2" -> validated *fixed*.

Built from scratch from `Presentation_cd_1.pdf`. The old ZIP was **not** used as a codebase (only its results markdown was glanced at; none of its numbers are used) and was left untouched.

## Status at a glance (details: docs/ACCEPTANCE.md)
| Area | Status |
|---|---|
| 4 language adapters on real toolchains (gcc, g++, javac*, CPython) | verified |
| Conventional vs rule-based vs ML localisation on the same held-out data | verified |
| Dataset generation, training, persistence/reload, inference | verified |
| Patch generation + validation on a temp copy, explicit accept | verified |
| **Counterfactual Repair Lab** (real-compiler-validated, evidence-ranked candidates) | verified -> docs/COUNTERFACTUAL_REPAIR_LAB.md |
| Benchmark on 489 held-out programs + strategy D on a 40-sample compile-validated subset | verified -> docs/BENCHMARK_REPORT.md |
| Automated tests | **62 passed, 0 failed** (`python3 scripts/run_tests.py`, also runs under `pytest tests/`) |
| stdlib HTTP API (identical endpoints) | verified live |
| **FastAPI app** `backend/fastapi_app.py` | verified live (`fastapi`/`uvicorn`/`httpx` installed and exercised via `TestClient`) |
| **React/Vite/Monaco frontend** | verified: `npm install`, `npx tsc --noEmit`, `npm run build` all succeed; built `dist/` served live and hit end to end |
| Program execution | **off by default**; not a security sandbox |

\* No `javac` binary existed here; the JDK compiler module is invoked via `java -m jdk.compiler/com.sun.tools.javac.Main` (same compiler). A `javac` on PATH is preferred automatically.

## Install & run
Needs Python 3.10+, gcc, g++, a JDK (or JRE with `jdk.compiler`), Node 18+ for the UI.
```sh
pip install -r requirements.txt
sh scripts/generate_dataset.sh     # ~10 min on 1 core -> data/dataset (3,439 samples, seed 7)  [already included]
sh scripts/train_model.sh          # ~30 s -> data/model/ranker.joblib                           [already included]
sh scripts/run_benchmark.sh        # -> docs/BENCHMARK_REPORT.md                                  [already included]
python3 scripts/run_tests.py       # or: pytest tests/
sh scripts/start.sh                # API on :8000 (FastAPI if installed, else stdlib server)
sh scripts/start_frontend.sh       # UI on http://localhost:5173
```
Execution: `COMPILERX_ENABLE_EXECUTION=1`, only inside a disposable container/VM (docs/KNOWN_LIMITATIONS.md #6).

## API
GET `/api/health /languages /samples /model/status /benchmark/results /benchmark/status /history` ·
POST `/api/compile /run /diagnose /patch/validate /patch/apply /benchmark/run /counterfactual`. `patch/apply` refuses without `"accept": true`.
`/api/counterfactual` (and `/api/diagnose` with `"counterfactual": true`) runs the Counterfactual Repair Lab - see docs/COUNTERFACTUAL_REPAIR_LAB.md.

## Layout
`compiler_engine/` adapters, lexer/analysis, rule localiser, patches, explanations, pipeline, **`counterfactual/`** (validation + evidence ranking) ·
`ml_engine/` generator, corruptions, features, train, ranker · `benchmarks/` runner + hand-written corpus ·
`backend/` service core, SQLite, stdlib + FastAPI servers · `frontend/` (incl. the Repair Lab panel) · `tests/` · `docs/`.
