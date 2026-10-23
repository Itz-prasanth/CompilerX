# Architecture
| Layer | Code | Responsibility |
|---|---|---|
| A Developer interface | `frontend/src` | Monaco IDE: language select, samples, open/save/reset, compile/run/diagnose, terminal, reported (red) + root-cause (amber) decorations, rule-vs-ML candidate tables, patch diff + accept/reject, history, benchmark dashboard, toolchain/model status |
| B Compiler integration | `compiler_engine/languages/` | one adapter per language -> common `Diagnostic`. gcc/g++ `-fsyntax-only`; javac; CPython `compile()` in an isolated subprocess (parsed, never executed) |
| C Source analysis | `compiler_engine/parser/` | tolerant lexer; per-line delimiter depth, indentation, unmatched-brace stack, statement-completeness predicates |
| D Diagnostic engine | `common/normalize.py`, `localization/`, `recovery/`, `pipeline.py` | message -> category/expected token; candidate lines; rule ranking; ML ranking; explanation |
| E Correction engine | `compiler_engine/patches/` | template edits on ranked lines, each validated on a temp copy; the user must accept |
| F ML engine | `ml_engine/` | program generator, controlled corruptions, 105 features, RF vs GB chosen on validation, persistence, ranker |
| G Benchmark & persistence | `benchmarks/`, `backend/db.py` | shared held-out corpus, metrics, SQLite history + runs |
| H Counterfactual Repair Lab | `compiler_engine/counterfactual/` | opt-in 4th strategy: compiles candidate patches for real (reusing B/E), records structured pass/fail evidence, combines it with D's rule/ML scores into one ranked, documented (non-probabilistic) list - see docs/COUNTERFACTUAL_REPAIR_LAB.md |

Flow: `source -> adapter.check -> first syntax Diagnostic -> analyze -> candidates [reported-20, reported] (whole file for brace errors) -> rules.rank + MLRanker.rank -> patches_for_line -> adapter.check(patched copy) -> explanation`.
Strategies: **conventional** = reported line; **rule** = deterministic heuristics (no learning); **ML** = GradientBoosting probability per candidate line, normalised per diagnostic;
**counterfactual** (opt-in, `counterfactual=True`) = rule/ML priors + real-compiler verification bonus per candidate line, via `compiler_engine/counterfactual/`.
The primary strategy shown to the user is whichever scored higher on *validation* (stored in the model card) - counterfactual evidence is additional context, not currently part of that selection (see docs/COUNTERFACTUAL_REPAIR_LAB.md).
