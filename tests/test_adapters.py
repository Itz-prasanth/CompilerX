from tests.helpers import VALID, INVALID
from compiler_engine.languages.registry import get_adapter, all_adapters
from compiler_engine.languages.base import UnsafeSourceError, validate_source
from compiler_engine.languages.gnu import GnuAdapter
from compiler_engine.common.process import run_limited
import tempfile


def _valid(lang):
    r = get_adapter(lang).check(VALID[lang]); assert r.ok and not r.errors, r.raw_output


def _invalid(lang):
    src, _ = INVALID[lang]
    r = get_adapter(lang).check(src)
    assert not r.ok and r.first_error() is not None
    d = r.first_error(); assert d.line >= 1 and d.message and d.is_syntax


def test_valid_c(): _valid("c")
def test_valid_cpp(): _valid("cpp")
def test_valid_java(): _valid("java")
def test_valid_python(): _valid("python")
def test_invalid_c(): _invalid("c")
def test_invalid_cpp(): _invalid("cpp")
def test_invalid_java(): _invalid("java")
def test_invalid_python(): _invalid("python")


def test_toolchains_report_available():
    for l, a in all_adapters().items():
        assert a.toolchain().available, l


def test_c_reports_next_line_for_missing_semicolon():
    d = get_adapter("c").check(INVALID["c"][0]).first_error()
    assert d.line == 3 and d.category == "missing_semicolon" and d.expected == ";"


def test_missing_toolchain_is_reported_not_crashed():
    class Fake(GnuAdapter):
        language = "c"; compiler = "definitely-not-a-compiler-xyz"; filename = "m.c"
    r = Fake().check("int main(){}")
    assert r.toolchain_missing and not r.ok


def test_timeout_is_enforced():
    d = tempfile.mkdtemp()
    r = run_limited(["sleep", "5"], cwd=d, timeout=0.5)
    assert r.timed_out and r.duration_ms < 3000


def test_output_limit_is_enforced():
    d = tempfile.mkdtemp()
    r = run_limited(["python3", "-c", "print('x'*10**6)"], cwd=d, timeout=5, max_output=1000)
    assert len(r.stdout) <= 1000 and r.output_truncated


def test_dangerous_include_rejected():
    for src in ('#include "/etc/passwd"\nint main(){}', '#include "../../x.h"\nint main(){}'):
        try:
            get_adapter("c").check(src); assert False, "should reject"
        except UnsafeSourceError:
            pass


def test_oversize_and_nul_source_rejected():
    for bad in ("x" * 300_000, "a\x00b"):
        try:
            validate_source(bad); assert False
        except UnsafeSourceError:
            pass


def test_python_check_never_executes_code():
    import os
    marker = os.path.join(tempfile.mkdtemp(), "pwned")
    r = get_adapter("python").check(f"open({marker!r}, 'w').write('x')\n")
    assert r.ok and not os.path.exists(marker)


def test_java_batch_matches_single():
    ad = get_adapter("java")
    batch = ad.check_many([VALID["java"], INVALID["java"][0]])
    assert batch[0].ok and not batch[1].ok and batch[1].first_error().line == ad.check(INVALID["java"][0]).first_error().line
