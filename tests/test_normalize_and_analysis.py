from compiler_engine.common.normalize import classify
from compiler_engine.parser.lexer import tokenize
from compiler_engine.parser.analysis import analyze


def test_classify_gnu():
    assert classify("c", "expected ',' or ';' before 'int'")[:2] == ("missing_semicolon", ";")
    assert classify("cpp", "expected ')' before ';' token")[:2] == ("missing_paren", ")")
    assert classify("c", "expected declaration or statement at end of input")[0] == "missing_brace"
    assert classify("c", "expected expression before '/' token")[0] == "incomplete_expression"


def test_classify_java_python():
    assert classify("java", "';' expected")[:2] == ("missing_semicolon", ";")
    assert classify("java", "reached end of file while parsing")[0] == "missing_brace"
    assert classify("java", "cannot find symbol")[2] is False          # semantic, not syntax
    assert classify("python", "expected ':'")[0] == "missing_colon"
    assert classify("python", "'(' was never closed")[0] == "missing_paren"
    assert classify("python", "unindent does not match any outer indentation level")[0] == "indentation"


def test_lexer_positions_and_strings():
    t = tokenize("c", 'int x = 5; // c\nchar *s = "a;b";\n')
    texts = [(x.text, x.line, x.col) for x in t]
    assert ("int", 1, 1) in texts and ('"a;b"', 2, 11) in texts
    assert not any(x.text == "c" for x in t)           # comment skipped


def test_lexer_tolerates_garbage():
    assert tokenize("c", 'int x = "unterminated\nint y;') and tokenize("python", "x = '''abc")


def test_delimiter_depth_and_unmatched_braces():
    a = analyze("c", "int f() {\n  if (x) {\n    y(\n  }\n}\n")
    assert a.lines[2].paren_net == 1 and a.global_paren == 1 and a.unmatched_braces == []
    b = analyze("c", "int f() {\n  if (x) {\n    y();\n\n}\n")
    assert b.unmatched_braces == [1]
