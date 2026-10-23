import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

VALID = {
    "c": '#include <stdio.h>\nint main(void) {\n    printf("ok\\n");\n    return 0;\n}\n',
    "cpp": '#include <iostream>\nint main() {\n    std::cout << "ok";\n    return 0;\n}\n',
    "java": 'public class Main {\n    public static void main(String[] a) {\n        System.out.println("ok");\n    }\n}\n',
    "python": 'def f(x):\n    return x + 1\n\nprint(f(1))\n',
}
INVALID = {   # language -> (source, true_root_line)
    "c": ("int main() {\n    int price = 100\n    int tax = 18;\n    return 0;\n}\n", 2),
    "cpp": ("#include <iostream>\nint main() {\n    int a = (1 + 2;\n    return 0;\n}\n", 3),
    "java": ("public class Main {\n    public static void main(String[] a) {\n        int x = 1\n        int y = 2;\n    }\n}\n", 3),
    "python": ("def f(x):\n    return x +\n\nprint(f(1))\n", 2),
}


def tmp():
    return tempfile.mkdtemp(prefix="cxai_test_")
