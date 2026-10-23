"""Executed in a throw-away subprocess: parses (never runs) a file with CPython's real compiler."""
import sys, json
path = sys.argv[1]
src = open(path, encoding="utf-8", errors="replace").read()
try:
    compile(src, "main.py", "exec", dont_inherit=True)
    print(json.dumps({"ok": True}))
except SyntaxError as e:
    print(json.dumps({"ok": False, "line": e.lineno or 1, "col": e.offset or 0,
                      "msg": e.msg, "type": type(e).__name__}))
except Exception as e:  # e.g. ValueError for null bytes, RecursionError, MemoryError
    print(json.dumps({"ok": False, "line": 1, "col": 0, "msg": f"{type(e).__name__}: {e}", "type": "Other"}))
