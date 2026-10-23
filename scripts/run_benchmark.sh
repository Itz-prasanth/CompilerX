#!/bin/sh
cd "$(dirname "$0")/.." && python3 -m benchmarks.runner --suggestion-limit "${1:-25}" --report docs/BENCHMARK_REPORT.md
