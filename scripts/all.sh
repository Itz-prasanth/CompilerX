#!/bin/sh
# Full reproduction: dataset -> train -> benchmark -> tests
set -e
cd "$(dirname "$0")/.."
sh scripts/generate_dataset.sh && sh scripts/train_model.sh && sh scripts/run_benchmark.sh && python3 scripts/run_tests.py
