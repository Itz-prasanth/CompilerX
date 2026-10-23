"""Resource-limited subprocess execution (rlimits, timeout, output cap, no-network namespace)."""
from __future__ import annotations
import os, resource, shutil, signal, subprocess, tempfile, time
from dataclasses import dataclass
from typing import Optional, Sequence

_UNSHARE_OK: Optional[bool] = None


def netns_available() -> bool:
    """True if `unshare -rn` works here (private empty network namespace)."""
    global _UNSHARE_OK
    if _UNSHARE_OK is None:
        try:
            _UNSHARE_OK = bool(shutil.which("unshare")) and subprocess.run(
                ["unshare", "-rn", "true"], capture_output=True, timeout=5).returncode == 0
        except Exception:
            _UNSHARE_OK = False
    return _UNSHARE_OK


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool
    duration_ms: int
    isolation: str


def run_limited(cmd: Sequence[str], cwd: str, timeout: float = 10.0, stdin: str = "",
                max_output: int = 65536, cpu_seconds: int = 10, mem_mb: Optional[int] = 1024,
                nproc: Optional[int] = None, isolate_network: bool = True) -> ProcResult:
    """Run `cmd` with rlimits in its own session. Output goes to size-capped temp files."""
    cmd = list(cmd)
    isolation = ["rlimits", "timeout", "tempdir", "env-scrubbed"]
    if isolate_network and netns_available():
        cmd = ["unshare", "-rn", "--"] + cmd
        isolation.append("netns")

    def _preexec():
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_output + 1, max_output + 1))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if mem_mb:
            lim = mem_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
        if nproc:
            resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))

    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
           "HOME": cwd, "TMPDIR": cwd}
    out_f = tempfile.TemporaryFile(); err_f = tempfile.TemporaryFile()
    in_f = tempfile.TemporaryFile(); in_f.write(stdin.encode()); in_f.seek(0)
    start = time.monotonic(); timed_out = False
    try:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=in_f, stdout=out_f, stderr=err_f,
                             preexec_fn=_preexec)
    except FileNotFoundError as e:
        return ProcResult(127, "", str(e), False, False, 0, ",".join(isolation))
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
    dur = int((time.monotonic() - start) * 1000)

    def _read(f):
        f.seek(0, 2); size = f.tell(); f.seek(0)
        data = f.read(max_output)
        return data.decode("utf-8", "replace"), size > max_output
    so, t1 = _read(out_f); se, t2 = _read(err_f)
    for f in (out_f, err_f, in_f):
        f.close()
    return ProcResult(p.returncode if p.returncode is not None else -1, so, se, timed_out,
                      t1 or t2, dur, ",".join(isolation))
