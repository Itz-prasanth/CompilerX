from __future__ import annotations
import re, shutil, tempfile
from typing import List
from ..common.diagnostic import CheckResult, Diagnostic, ToolchainStatus
from ..common.normalize import classify


class UnsafeSourceError(ValueError):
    pass


MAX_SOURCE_BYTES = 200_000


def validate_source(source: str) -> None:
    if not isinstance(source, str):
        raise UnsafeSourceError("source must be a string")
    if len(source.encode("utf-8", "replace")) > MAX_SOURCE_BYTES:
        raise UnsafeSourceError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
    if "\x00" in source:
        raise UnsafeSourceError("NUL bytes are not allowed")


_INCLUDE = re.compile(r'^\s*#\s*(?:include|include_next|import)\s*[<"]([^>"]+)[>"]', re.M)


def reject_dangerous_includes(source: str) -> None:
    """Stop `#include "/etc/passwd"`-style file disclosure through compiler diagnostics."""
    for m in _INCLUDE.finditer(source):
        p = m.group(1)
        if p.startswith("/") or ".." in p.split("/") or p.startswith("~"):
            raise UnsafeSourceError(f"include path not allowed: {p}")
    if re.search(r"__has_include|\.incbin|#\s*embed", source):
        raise UnsafeSourceError("file-reading preprocessor constructs are not allowed")


class LanguageAdapter:
    language = ""
    extension = ""
    display = ""

    def toolchain(self) -> ToolchainStatus:
        raise NotImplementedError

    def check(self, source: str, timeout: float = 15.0) -> CheckResult:
        raise NotImplementedError

    def check_many(self, sources: List[str], timeout: float = 120.0) -> List[CheckResult]:
        return [self.check(s) for s in sources]

    def build_and_run(self, source: str, stdin: str, timeout: float) -> dict:
        raise NotImplementedError

    def _finish(self, diags: List[Diagnostic]) -> List[Diagnostic]:
        for d in diags:
            if d.severity == "error":
                d.category, d.expected, d.is_syntax = classify(self.language, d.message)
            else:
                d.category, d.expected, d.is_syntax = "unknown", None, False
        return diags


def tmpdir() -> str:
    return tempfile.mkdtemp(prefix="cxai_")


def rmtree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
