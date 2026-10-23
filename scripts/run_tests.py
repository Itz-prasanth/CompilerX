#!/usr/bin/env python3
"""Minimal runner so the suite works without pytest (it is also pytest-compatible: `pytest tests/`)."""
import glob, importlib, os, sys, time, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
want = sys.argv[1:]
passed = failed = 0; t0 = time.time(); fails = []
for f in sorted(glob.glob("tests/test_*.py")):
    if want and not any(w in f for w in want):
        continue
    mod = importlib.import_module(f[:-3].replace("/", "."))
    for name in sorted(n for n in dir(mod) if n.startswith("test_")):
        t = time.time()
        try:
            getattr(mod, name)(); passed += 1; print(f"PASS  {f}::{name}  ({time.time()-t:.1f}s)")
        except Exception:
            failed += 1; fails.append((f, name, traceback.format_exc())); print(f"FAIL  {f}::{name}")
for f, n, tb in fails:
    print("=" * 70, f"\n{f}::{n}\n{tb}")
print(f"\n{passed} passed, {failed} failed in {time.time()-t0:.0f}s")
sys.exit(1 if failed else 0)
