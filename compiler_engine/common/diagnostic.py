"""Shared diagnostic schema used by every language adapter."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Optional, List

LANGUAGES = ("c", "cpp", "java", "python")


@dataclass
class Diagnostic:
    language: str
    line: int                 # 1-based reported line
    column: int               # 1-based reported column (0 if unknown)
    message: str
    severity: str = "error"   # error | warning
    raw: str = ""
    expected: Optional[str] = None   # normalised expected token, e.g. ";"
    category: str = "unknown"        # see normalize.CATEGORIES
    is_syntax: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckResult:
    language: str
    ok: bool
    diagnostics: List[Diagnostic] = field(default_factory=list)
    raw_output: str = ""
    tool: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    toolchain_missing: bool = False

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    def first_error(self) -> Optional[Diagnostic]:
        errs = self.errors
        return errs[0] if errs else None

    def to_dict(self) -> dict:
        return {
            "language": self.language, "ok": self.ok, "tool": self.tool,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "raw_output": self.raw_output, "duration_ms": self.duration_ms,
            "timed_out": self.timed_out, "toolchain_missing": self.toolchain_missing,
        }


@dataclass
class ToolchainStatus:
    language: str
    available: bool
    tool: str
    version: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
