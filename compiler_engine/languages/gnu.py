"""GCC / G++ adapter shared by C and C++."""
from __future__ import annotations
import os, re, shutil
from typing import List
from ..common.diagnostic import CheckResult, Diagnostic, ToolchainStatus
from ..common.process import run_limited
from .base import LanguageAdapter, validate_source, reject_dangerous_includes, tmpdir, rmtree

_DIAG = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?P<sev>fatal error|error|warning): (?P<msg>.*)$")


class GnuAdapter(LanguageAdapter):
    compiler = "gcc"
    std = "-std=c11"
    filename = "main.c"

    def toolchain(self) -> ToolchainStatus:
        exe = shutil.which(self.compiler)
        if not exe:
            return ToolchainStatus(self.language, False, self.compiler, "", f"{self.compiler} not found on PATH")
        r = run_limited([exe, "--version"], cwd="/tmp", timeout=5, mem_mb=None)
        return ToolchainStatus(self.language, True, exe, (r.stdout.splitlines() or [""])[0])

    def _flags(self):
        return [self.std, "-fno-diagnostics-color", "-fno-diagnostics-show-caret", "-fmax-errors=10"]

    def check(self, source: str, timeout: float = 15.0) -> CheckResult:
        validate_source(source); reject_dangerous_includes(source)
        exe = shutil.which(self.compiler)
        if not exe:
            return CheckResult(self.language, False, [], f"{self.compiler} not found", self.compiler,
                               toolchain_missing=True)
        d = tmpdir()
        try:
            with open(os.path.join(d, self.filename), "w") as f:
                f.write(source)
            r = run_limited([exe, "-fsyntax-only", *self._flags(), self.filename], cwd=d,
                            timeout=timeout, cpu_seconds=int(timeout), mem_mb=1024)
        finally:
            rmtree(d)
        text = r.stderr
        diags: List[Diagnostic] = []
        for ln in text.splitlines():
            m = _DIAG.match(ln)
            if not m:
                continue
            sev = "error" if "error" in m["sev"] else "warning"
            diags.append(Diagnostic(self.language, int(m["line"]), int(m["col"] or 0), m["msg"], sev, raw=ln))
        self._finish(diags)
        ok = r.returncode == 0 and not any(x.severity == "error" for x in diags) and not r.timed_out
        return CheckResult(self.language, ok, diags, text, exe, r.duration_ms, r.timed_out)

    def build_and_run(self, source: str, stdin: str, timeout: float) -> dict:
        validate_source(source); reject_dangerous_includes(source)
        if re.search(r"\b(__asm__|asm)\b", source):
            raise ValueError("inline assembly is not allowed in execution mode")
        exe = shutil.which(self.compiler)
        if not exe:
            return {"stage": "toolchain", "ok": False, "stderr": f"{self.compiler} not found"}
        d = tmpdir()
        try:
            with open(os.path.join(d, self.filename), "w") as f:
                f.write(source)
            c = run_limited([exe, *self._flags(), self.filename, "-o", "prog"], cwd=d, timeout=30, cpu_seconds=30)
            if c.returncode != 0:
                return {"stage": "compile", "ok": False, "stderr": c.stderr, "isolation": c.isolation}
            r = run_limited([os.path.join(d, "prog")], cwd=d, timeout=timeout, stdin=stdin,
                            cpu_seconds=int(timeout) + 1, mem_mb=256, nproc=64)
            return {"stage": "run", "ok": r.returncode == 0 and not r.timed_out, "returncode": r.returncode,
                    "stdout": r.stdout, "stderr": r.stderr, "timed_out": r.timed_out,
                    "output_truncated": r.output_truncated, "duration_ms": r.duration_ms,
                    "isolation": r.isolation}
        finally:
            rmtree(d)
