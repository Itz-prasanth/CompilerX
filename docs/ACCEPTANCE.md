# Acceptance results (what was actually executed, 2026-10-15; updated 2026-10-20/21 for the Counterfactual Repair Lab)
| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | New codebase independent of old ZIP | PASS | built in `compilerx-ai/`; ZIP never unpacked (only its results .md read to /tmp) |
| 2 | Functioning web interface | PASS | `npm install && npx tsc --noEmit && npm run build` all succeed; built `frontend/dist` served live by `backend/simple_server.py` and exercised end to end (health check, diagnose, counterfactual) |
| 3 | Real compile/validation for C, C++, Java, Python | PASS | gcc 13.3, g++ 13.3, OpenJDK 21 compiler module, CPython 3.12 |
| 4 | Real diagnostics from toolchains | PASS | `tests/test_adapters.py`, live `/api/diagnose` |
| 5 | Probable root-cause localisation | PASS | deck example: reported 3 -> root 2 in all four strategies (conventional/rule/ML/counterfactual); benchmark below |
| 6 | Three independent strategies, same cases | PASS | `benchmarks/runner.py` |
| 6b | Counterfactual Repair Lab (4th, evidence-based strategy) | PASS | `compiler_engine/counterfactual/`, `/api/counterfactual`, benchmarked as "strategy D" - see docs/COUNTERFACTUAL_REPAIR_LAB.md and BENCHMARK_REPORT.md |
| 7 | Trained, loadable ML model | PASS | GB, val top-1 98.7%; reload determinism tested |
| 8 | Suggested corrections with validation | PASS | 82/100 (ML), 78 (rule), 74 (compiler line) fixed on 25 test samples/language (original run); re-verified with the current model |
| 9 | Reproducible benchmark | PASS (see limitation 9) | scripts + seeds; test split: conventional 87.3%, rule 92.8%, ML 97.1% top-1; strategy D 92.5% top-1 on a 40-sample compile-validated subset (see limitation 11) |
| 10 | Measured test results | PASS | **62** passed, 0 failed (`scripts/run_tests.py`, up from 48 - 14 new counterfactual tests); also verified under `pytest tests/` (pytest installed and run directly) |
| 11 | Documented install/startup | PASS | README |
| 12 | FastAPI server | PASS | `fastapi`, `uvicorn`, `pydantic`, `httpx` installed; exercised live via `TestClient` (`/api/health`, `/api/model/status`, `/api/diagnose`, `/api/counterfactual`) |
| 13 | Secure execution | **DISABLED BY DEFAULT** | no secure sandbox available; enabled path functionally tested (run, timeout) but is not a security boundary. The Counterfactual Repair Lab never executes submitted programs either - it only ever calls `adapter.check()` (compile/parse), never `build_and_run()` |
