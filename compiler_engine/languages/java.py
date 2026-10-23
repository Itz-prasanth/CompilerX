"""Java adapter: uses `javac` if present, else the JDK compiler module through `java -m`."""
from __future__ import annotations
import os, re, shutil
from typing import List, Optional
from ..common.diagnostic import CheckResult, Diagnostic, ToolchainStatus
from ..common.process import run_limited
from .base import LanguageAdapter, validate_source, tmpdir, rmtree

_JAVA_DIAG = re.compile(r"^(?P<file>[^:\n]+\.java):(?P<line>\d+): (?P<sev>error|warning): (?P<msg>.*)$")
_JVM_FAST = ["-XX:+UseSerialGC", "-XX:TieredStopAtLevel=1", "-Xshare:auto", "-Xmx512m"]


def _javac_cmd() -> Optional[List[str]]:
    jc = shutil.which("javac")
    if jc:
        return [jc]
    j = shutil.which("java")
    if j:
        return [j, *_JVM_FAST, "-m", "jdk.compiler/com.sun.tools.javac.Main"]
    return None


def _parse(text: str, language="java"):
    """Return [(file, Diagnostic)]; column comes from the caret line javac prints."""
    lines = text.splitlines(); out = []
    for i, ln in enumerate(lines):
        m = _JAVA_DIAG.match(ln)
        if m:
            col = 0
            if i + 2 < len(lines) and lines[i + 2].strip() == "^":
                col = lines[i + 2].index("^") + 1
            out.append((m["file"], Diagnostic(language, int(m["line"]), col, m["msg"],
                                              "error" if m["sev"] == "error" else "warning", raw=ln)))
    return out


class JavaAdapter(LanguageAdapter):
    language = "java"; extension = ".java"; display = "Java (javac)"

    def toolchain(self) -> ToolchainStatus:
        cmd = _javac_cmd()
        if not cmd:
            return ToolchainStatus("java", False, "javac", "", "neither javac nor java found")
        r = run_limited([cmd[0], "-version"], cwd="/tmp", timeout=10, mem_mb=None)
        mode = "javac" if cmd[0].endswith("javac") else "java -m jdk.compiler"
        txt = (r.stderr or r.stdout).strip().splitlines()
        return ToolchainStatus("java", True, mode, txt[0] if txt else "")

    @staticmethod
    def _class_name(source: str) -> str:
        m = re.search(r"\bpublic\s+(?:final\s+|abstract\s+)*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)", source)
        return m.group(1) if m else "Main"

    def check(self, source: str, timeout: float = 30.0) -> CheckResult:
        validate_source(source)
        cmd = _javac_cmd()
        if not cmd:
            return CheckResult("java", False, [], "javac not found", "javac", toolchain_missing=True)
        d = tmpdir()
        try:
            name = self._class_name(source)
            with open(os.path.join(d, name + ".java"), "w") as f:
                f.write(source)
            r = run_limited([*cmd, "-proc:none", "-Xmaxerrs", "20", "-Xlint:none", "-d", d, name + ".java"],
                            cwd=d, timeout=timeout, cpu_seconds=int(timeout), mem_mb=None)
        finally:
            rmtree(d)
        diags = [dg for _, dg in _parse(r.stderr)]
        self._finish(diags)
        ok = r.returncode == 0 and not any(x.severity == "error" for x in diags) and not r.timed_out
        return CheckResult("java", ok, diags, r.stderr, cmd[0], r.duration_ms, r.timed_out)

    def check_many(self, sources: List[str], timeout: float = 300.0) -> List[CheckResult]:
        """One JVM for many files (dataset generation). Each source is renamed to class C<i>."""
        cmd = _javac_cmd()
        if not cmd:
            return [CheckResult("java", False, [], "javac not found", "javac", toolchain_missing=True) for _ in sources]
        d = tmpdir()
        try:
            names = []
            for i, s in enumerate(sources):
                validate_source(s)
                n = f"C{i}"; names.append(n)
                s2 = re.sub(r"\b(public\s+)?class\s+Main\b", lambda m: (m.group(1) or "") + f"class {n}", s, count=1)
                with open(os.path.join(d, n + ".java"), "w") as f:
                    f.write(s2)
            r = run_limited([*cmd, "-proc:none", "-Xmaxerrs", "1000000", "-Xlint:none", "-d", d,
                             *[n + ".java" for n in names]], cwd=d, timeout=timeout,
                            cpu_seconds=int(timeout), mem_mb=None, max_output=64_000_000)
        finally:
            rmtree(d)
        per = {n: [] for n in names}
        for fname, dg in _parse(r.stderr):
            per.setdefault(fname[:-5], []).append(dg)
        results = []
        for n in names:
            dg = self._finish(per.get(n, []))
            ok = not any(x.severity == "error" for x in dg)
            results.append(CheckResult("java", ok, dg, "", "javac(batch)", r.duration_ms // max(1, len(names)), r.timed_out))
        return results

    def build_and_run(self, source: str, stdin: str, timeout: float) -> dict:
        validate_source(source)
        cmd = _javac_cmd(); j = shutil.which("java")
        if not cmd or not j:
            return {"stage": "toolchain", "ok": False, "stderr": "java toolchain not found"}
        d = tmpdir()
        try:
            name = self._class_name(source)
            with open(os.path.join(d, name + ".java"), "w") as f:
                f.write(source)
            c = run_limited([*cmd, "-proc:none", "-d", d, name + ".java"], cwd=d, timeout=60, cpu_seconds=60, mem_mb=None)
            if c.returncode != 0:
                return {"stage": "compile", "ok": False, "stderr": c.stderr, "isolation": c.isolation}
            r = run_limited([j, *_JVM_FAST, "-Xmx128m", "-cp", d, name], cwd=d, timeout=timeout, stdin=stdin,
                            cpu_seconds=int(timeout) + 2, mem_mb=None)
            return {"stage": "run", "ok": r.returncode == 0 and not r.timed_out, "returncode": r.returncode,
                    "stdout": r.stdout, "stderr": r.stderr, "timed_out": r.timed_out,
                    "output_truncated": r.output_truncated, "duration_ms": r.duration_ms, "isolation": r.isolation}
        finally:
            rmtree(d)
