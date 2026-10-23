from tests.helpers import INVALID
from compiler_engine.languages.registry import get_adapter
from compiler_engine.parser.analysis import analyze
from compiler_engine.localization import rules
from compiler_engine.localization.candidates import generate_candidates
from compiler_engine.patches.generator import patches_for_line, apply_edits, suggest, validate_patch
from compiler_engine.pipeline import DiagnosisEngine

SEMI = INVALID["c"][0]


def _diag(lang, src):
    return get_adapter(lang).check(src).first_error()


def test_rule_localization_finds_earlier_line_for_missing_semicolon():
    d = _diag("c", SEMI); a = analyze("c", SEMI)
    r = rules.rank(a, d)
    assert d.line == 3 and r[0]["line"] == 2 and r[0]["evidence"]


def test_rule_ranking_is_sorted_and_normalised():
    d = _diag("c", SEMI); r = rules.rank(analyze("c", SEMI), d)
    assert [x["score"] for x in r] == sorted((x["score"] for x in r), reverse=True)
    assert abs(sum(x["score"] for x in r) - 1) < 0.01


def test_rule_localization_missing_paren_and_colon():
    s = "int main() {\n    int a = 3;\n    int b = (a + 2;\n    int c = b * 2;\n    return c;\n}\n"
    d = _diag("c", s); assert rules.rank(analyze("c", s), d)[0]["line"] == 3
    p = "x = 3\nif x > 2\n    print(x)\n"
    d = _diag("python", p); assert rules.rank(analyze("python", p), d)[0]["line"] == 2


def test_rule_localization_missing_close_brace_blank_line():
    s = "int f(int a) {\n    if (a > 1) {\n        a = 2;\n\n    return a;\n}\n\nint main() {\n    return f(1);\n}\n"
    d = _diag("c", s); a = analyze("c", s)
    assert 4 in [x["line"] for x in rules.rank(a, d)[:2]]


def test_candidates_cover_reported_line_and_never_exceed_it():
    d = _diag("c", SEMI); a = analyze("c", SEMI); c = generate_candidates(a, d)
    assert d.line in c and max(c) == d.line and min(c) >= 1


def test_patch_missing_semicolon_validates_and_leaves_original_untouched():
    d = _diag("c", SEMI); a = analyze("c", SEMI); ad = get_adapter("c")
    res = suggest(ad, a, d, [2])
    assert res["best"].validation["status"] == "fixed"
    assert apply_edits(SEMI, res["best"].edits).split("\n")[1].endswith("100;")
    assert a.source == SEMI                      # original string unchanged


def test_wrong_patch_is_reported_not_fixed():
    d = _diag("c", SEMI); a = analyze("c", SEMI); ad = get_adapter("c")
    ps = patches_for_line(a, d, 4)               # patches on an unrelated line
    for p in ps:
        assert validate_patch(ad, SEMI, p, d)["status"] != "fixed"


def test_patch_python_colon_and_indent():
    ad = get_adapter("python")
    s = "x = 3\nif x > 2\n    print(x)\n"; d = _diag("python", s)
    assert suggest(ad, analyze("python", s), d, [2])["best"].validation["status"] == "fixed"
    s2 = "def f(x):\nreturn x + 1\n\nprint(f(2))\n"; d2 = _diag("python", s2)
    assert suggest(ad, analyze("python", s2), d2, [2])["best"].validation["status"] == "fixed"


def test_patch_java_semicolon_and_cpp_paren():
    for lang in ("java", "cpp"):
        s, truth = INVALID[lang]; d = _diag(lang, s)
        r = suggest(get_adapter(lang), analyze(lang, s), d, [truth])
        assert r["best"] and r["best"].validation["status"] == "fixed", (lang, r["best"] and r["best"].description)


def test_pipeline_end_to_end_without_ml():
    r = DiagnosisEngine().diagnose("c", SEMI)
    assert r["status"] == "syntax_error" and r["root_cause_line"] == 2 and r["reported"]["line"] == 3
    assert r["patch"]["validation"]["status"] == "fixed" and "line 2" in r["explanation"]
    assert r["strategies"]["ml"]["unavailable"]


def test_pipeline_valid_and_semantic_inputs():
    e = DiagnosisEngine()
    assert e.diagnose("python", "print(1)\n")["status"] == "ok"
    r = e.diagnose("java", "public class Main {\n    public static void main(String[] a) {\n        int x = y;\n    }\n}\n")
    assert r["status"] == "non_syntax_error"
