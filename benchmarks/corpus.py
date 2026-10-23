"""Small hand-written corpus (NOT produced by the synthetic generator) with human-labelled ground truth.
truth_line = the line a human would edit to fix the mistake. Brace-deletion cases are excluded because the
'line' of a missing '}' is ambiguous when no line exists to carry it."""

CASES = [
 dict(id="c-deck", language="c", truth_line=2, source="int main() {\n    int price = 100\n    int tax = 18;\n    return 0;\n}\n"),
 dict(id="c-if-paren", language="c", truth_line=4, source='#include <stdio.h>\nint main(void) {\n    int n = 5;\n    if (n > 3 {\n        printf("big\\n");\n    }\n    return 0;\n}\n'),
 dict(id="c-struct-semi", language="c", truth_line=4, source="struct Point {\n    int x;\n    int y;\n}\n\nint main(void) {\n    struct Point p;\n    p.x = 1;\n    return 0;\n}\n"),
 dict(id="c-for-semi", language="c", truth_line=4, source="int main(void) {\n    int s = 0;\n    for (int i = 0; i < 10; i++) {\n        s += i\n    }\n    return s;\n}\n"),
 dict(id="c-decl-paren", language="c", truth_line=3, source="int main() {\n    int a = 3;\n    int b = (a + 2;\n    int c = b * 2;\n    return c;\n}\n"),
 dict(id="c-call-comma", language="c", truth_line=4, source='#include <stdio.h>\nint main(void) {\n    int a = 1, b = 2;\n    printf("%d %d\\n", a b);\n    return 0;\n}\n'),
 dict(id="cpp-class-semi", language="cpp", truth_line=5, source="#include <iostream>\nclass Counter {\npublic:\n    int n = 0;\n}\n\nint main() {\n    Counter c;\n    std::cout << c.n << std::endl;\n}\n"),
 dict(id="cpp-while-paren", language="cpp", truth_line=5, source="#include <iostream>\nint main() {\n    int i = 0;\n    int total = 0;\n    while (i < 10 {\n        total += i;\n        i++;\n    }\n    std::cout << total;\n}\n"),
 dict(id="cpp-stmt-semi", language="cpp", truth_line=4, source="#include <vector>\nint main() {\n    std::vector<int> v;\n    v.push_back(3)\n    v.push_back(4);\n    return 0;\n}\n"),
 dict(id="java-println-paren", language="java", truth_line=3, source='public class Main {\n    public static void main(String[] args) {\n        System.out.println("hi";\n    }\n}\n'),
 dict(id="java-decl-semi", language="java", truth_line=3, source="public class Main {\n    public static void main(String[] args) {\n        int x = 5\n        int y = 6;\n        System.out.println(x + y);\n    }\n}\n"),
 dict(id="java-if-paren", language="java", truth_line=4, source="public class Main {\n    public static void main(String[] args) {\n        int n = 3;\n        if (n > 2 {\n            System.out.println(n);\n        }\n    }\n}\n"),
 dict(id="py-def-colon", language="python", truth_line=1, source="def greet(name)\n    return 'hi ' + name\n\nprint(greet('x'))\n"),
 dict(id="py-call-paren", language="python", truth_line=1, source="total = max(1, 2\nprint(total)\n"),
 dict(id="py-list-comma", language="python", truth_line=3, source="items = [\n    1,\n    2\n    3,\n    4,\n]\nprint(items)\n"),
 dict(id="py-body-indent", language="python", truth_line=2, source="def f(x):\nreturn x + 1\n\nprint(f(2))\n"),
 dict(id="py-if-colon", language="python", truth_line=2, source="x = 3\nif x > 2\n    print(x)\n"),
 dict(id="py-binop", language="python", truth_line=2, source="a = 1\nb = a +\nprint(b)\n"),
]
