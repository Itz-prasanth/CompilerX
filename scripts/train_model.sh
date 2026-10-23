#!/bin/sh
cd "$(dirname "$0")/.." && python3 -m ml_engine.train --dataset data/dataset --model data/model/ranker.joblib
