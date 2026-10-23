"""Python adapter: CPython's own compile() in an isolated, resource-limited subprocess."""
from __future__ import annotations
import json, os, shutil, sys
from ..common.diagnostic import CheckResult, Diagnostic, ToolchainStatus
from ..common.process import run_limited
from .base import LanguageAdapter, validate_source, tmpdir, rmtree

_HELPER = os.path.join(os.path.dirname(__file__), "_py_check.py")


class PythonAdapter(LanguageAdapter):
    language = "python"; extension = ".py"; display = "Python (CPython)"

    def _exe(self):
        return shutil.which("python3") or sys.executable

    def toolchain(self) -> ToolchainStatus:
        r = run_limited([self._exe(), "--version"], cwd="/tmp", timeout=5, mem_mb=None)
        return ToolchainStatus("python", True, self._exe(), (r.stdout or r.stderr).strip())

    def check(self, source: str, timeout: float = 10.0) -> CheckResult:
        validate_source(source)
        d = tmpdir()
        try:
            p = os.path.join(d, "main.py")
            with open(p, "w", encoding="utf-8") as f:
                f.write(source)
            r = run_limited([self._exe(), "-I", "-S", _HELPER, p], cwd=d, timeout=timeout,
                            cpu_seconds=int(timeout), mem_mb=512)
        finally:
            rmtree(d)
        try:
            info = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return CheckResult("python", False, [Diagnostic("python", 1, 0, "checker failed: " + r.stderr[:200])],
                               r.stderr, self._exe(), r.duration_ms, r.timed_out)
        if info["ok"]:
            return CheckResult("python", True, [], "", self._exe(), r.duration_ms)
        dg = Diagnostic("python", int(info["line"]), int(info["col"]), info["msg"],
                        "error", raw=f'{info["type"]}: {info["msg"]} (line {info["line"]})')
        self._finish([dg])
        return CheckResult("python", False, [dg], dg.raw, self._exe(), r.duration_ms)

    def build_and_run(self, source: str, stdin: str, timeout: float) -> dict:
        validate_source(source)
        d = tmpdir()
        try:
            with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
                f.write(source)
            r = run_limited([self._exe(), "-I", "main.py"], cwd=d, timeout=timeout, stdin=stdin,
                            cpu_seconds=int(timeout) + 1, mem_mb=256, nproc=64)
            return {"stage": "run", "ok": r.returncode == 0 and not r.timed_out, "returncode": r.returncode,
                    "stdout": r.stdout, "stderr": r.stderr, "timed_out": r.timed_out,
                    "output_truncated": r.output_truncated, "duration_ms": r.duration_ms, "isolation": r.isolation}
        finally:
            rmtree(d)
