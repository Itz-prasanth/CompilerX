# CompilerX-AI benchmark report

Generated 2026-10-20T18:50:53Z - held-out **test** split: **489** corrupted programs from **85** original programs never used for training. Candidate recall (true line inside the candidate window): 98.8%.

## Overall (top-1 = the strategy's first-ranked line is the injected-corruption line)

| Strategy | Top-1 (95% CI) | Top-3 | MRR | Mean abs. line error |
|---|---|---|---|---|
| conventional | 87.3% (84.1%-90.0%) | 87.3% | 0.873 | 0.94 |
| rule | 92.8% (90.2%-94.8%) | 94.1% | 0.940 | 0.76 |
| ml | 97.1% (95.2%-98.3%) | 98.8% | 0.980 | 0.03 |

Conventional reporting emits one line, so its top-3 equals its top-1.

## Per language (top-1)

| Language | n | conventional | rule | ml |
|---|---|---|---|---|
| c | 135 | 77.0% | 87.4% | 92.6% |
| cpp | 107 | 87.8% | 92.5% | 98.1% |
| java | 143 | 88.8% | 94.4% | 98.6% |
| python | 104 | 98.1% | 98.1% | 100.0% |

## Per injected corruption (top-1)

| Corruption | n | conventional | rule | ml |
|---|---|---|---|---|
| incomplete_expression | 62 | 100.0% | 100.0% | 100.0% |
| indentation | 12 | 83.3% | 83.3% | 100.0% |
| malformed_declaration | 67 | 100.0% | 100.0% | 100.0% |
| missing_brace | 39 | 0.0% | 41.0% | 64.1% |
| missing_colon | 13 | 100.0% | 100.0% | 100.0% |
| missing_comma | 50 | 100.0% | 100.0% | 100.0% |
| missing_paren | 66 | 100.0% | 92.4% | 100.0% |
| missing_semicolon | 47 | 55.3% | 100.0% | 100.0% |
| unexpected_operator | 66 | 100.0% | 100.0% | 100.0% |
| unexpected_token | 67 | 100.0% | 92.5% | 100.0% |

## Error-type classification (compiler message -> category vs injected category)

- c: 77.0% (n=135)
- ALL: 68.7% (n=489)
- cpp: 87.8% (n=107)
- java: 58.0% (n=143)
- python: 52.9% (n=104)

## Paired comparisons (top-1, exact two-sided sign test on discordant pairs)

- ml_vs_conventional: ml_only_correct=48, conventional_only_correct=0, p=7.11e-15
- ml_vs_rule: ml_only_correct=21, rule_only_correct=0, p=9.54e-07
- rule_vs_conventional: rule_only_correct=37, conventional_only_correct=10, p=9.85e-05

## Suggestion correctness (patch at the strategy's top-1 line makes the file compile; first 10 test samples per language)

- conventional: 27/40 = 67.5%
- rule: 31/40 = 77.5%
- ml: 32/40 = 80.0%

## Strategy D - counterfactual evidence-enhanced ranking (same 10-per-language compile-validated subset as above, n=40; NOT the full held-out split, because this is the one strategy that actually compiles candidate patches)

| Metric | Value |
|---|---|
| Top-1 | 92.5% |
| Top-3 | 97.5% |
| MRR | 0.942 |
| Verified repair rate (some candidate patch compiles) | 80.0% |
| False-correction rate (a compiling patch, but at the wrong line) | 9.4% |
| Avg. validation time / sample | 2055 ms |

_A compiling candidate patch is evidence it is **a** valid fix, not proof it is **the** original mistake - see false-correction rate above._

## Hand-written corpus (n=18; qualitative - too small for statistics)

| Strategy | Top-1 |
|---|---|
| conventional | 88.9% |
| rule | 88.9% |
| ml | 94.4% |

## How far the compiler's reported line is from the real mistake

| |reported - true| (lines) | count |
|---|---|
| 0 | 427 |
| 1 | 34 |
| 2 | 7 |
| 3 | 1 |
| 4 | 1 |
| 6+ | 19 |
