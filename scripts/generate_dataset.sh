#!/bin/sh
# Reproducible synthetic dataset (needs gcc, g++, JDK/javac, python3). ~10 min on one core.
cd "$(dirname "$0")/.." && python3 -m ml_engine.dataset_generator --out data/dataset --programs-per-lang "${1:-150}" --variants 6 --seed 7
