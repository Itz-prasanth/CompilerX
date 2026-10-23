"""Random valid-program generator: one abstract program rendered as C, C++, Java or Python."""
from __future__ import annotations
import random
from typing import List, Tuple

NAMES = ["total", "count", "value", "result", "index", "sum", "temp", "limit", "price", "tax", "score", "width",
         "height", "size", "step", "rate", "alpha", "beta", "gamma", "delta", "speed", "level", "offset", "bonus"]
OPS = ["+", "-", "*"]
CMP = ["<", ">", "<=", ">=", "==", "!="]


class _W:
    def __init__(self, lang, unit, allman):
        self.lang, self.unit, self.allman = lang, unit, allman
        self.out: List[str] = []; self.lvl = 0

    def line(self, text=""):
        self.out.append((self.unit * self.lvl + text) if text else "")

    def open(self, header):
        if self.lang == "python":
            self.line(header + ":"); self.lvl += 1
        elif self.allman:
            self.line(header); self.line("{"); self.lvl += 1
        else:
            self.line(header + " {"); self.lvl += 1

    def close(self, tail=""):
        self.lvl -= 1
        if self.lang != "python":
            self.line("}" + tail)


class ProgramGenerator:
    def __init__(self, lang: str, seed: int):
        self.lang = lang
        self.r = random.Random(seed)
        self.w = _W(lang, self.r.choice(["    ", "    ", "  "]), lang != "python" and self.r.random() < 0.3)
        self.names = NAMES[:]; self.r.shuffle(self.names)
        self.funcs: List[Tuple[str, int]] = []

    # ---- helpers
    def nm(self):
        return self.names.pop() if self.names else f"v{self.r.randint(100, 999)}"

    def expr(self, vs, d=0):
        r = self.r
        if d >= 2 or r.random() < 0.35:
            return r.choice(vs) if vs and r.random() < 0.7 else str(r.randint(0, 99))
        a, b = self.expr(vs, d + 1), self.expr(vs, d + 1)
        e = f"{a} {r.choice(OPS)} {b}"
        return f"({e})" if d and r.random() < 0.5 else e

    def cond(self, vs):
        r = self.r
        c = f"{r.choice(vs)} {r.choice(CMP)} {self.expr(vs, 1)}"
        if r.random() < 0.25:
            c += (" and " if self.lang == "python" else " && ") + f"{r.choice(vs)} {r.choice(CMP)} {r.randint(0, 50)}"
        return c

    def semi(self):
        return "" if self.lang == "python" else ";"

    def printer(self, v):
        L = self.lang
        return {"c": f'printf("%d\\n", {v});', "cpp": f"cout << {v} << endl;",
                "java": f"System.out.println({v});", "python": f"print({v})"}[L]

    def decl(self, name, e):
        t = "" if self.lang == "python" else "int "
        return f"{t}{name} = {e}{self.semi()}"

    # ---- statements
    def stmts(self, vs, depth, n):
        r, w = self.r, self.w
        for _ in range(n):
            k = r.random()
            if r.random() < 0.10:
                w.line()
            if r.random() < 0.08:
                w.line(("# " if self.lang == "python" else "// ") + r.choice(["update", "compute", "check", "adjust"]))
            if k < 0.28 or not vs:
                nm = self.nm(); w.line(self.decl(nm, self.expr(vs))); vs.append(nm)
            elif k < 0.42:
                v = r.choice(vs); op = r.choice(["=", "+=", "-="])
                w.line(f"{v} {op} {self.expr(vs)}{self.semi()}")
            elif k < 0.55:
                w.line(self.printer(r.choice(vs)))
            elif k < 0.65 and self.funcs:
                f, ar = r.choice(self.funcs); nm = self.nm()
                args = ", ".join(self.expr(vs, 1) for _ in range(ar))
                w.line(self.decl(nm, f"{f}({args})")); vs.append(nm)
            elif depth < 2 and k < 0.80:
                w.open(f"if ({self.cond(vs)})" if self.lang != "python" else f"if {self.cond(vs)}")
                self.stmts(list(vs), depth + 1, r.randint(1, 3))
                if r.random() < 0.4:
                    w.close(); w.open("else")
                    self.stmts(list(vs), depth + 1, r.randint(1, 2))
                w.close()
            elif depth < 2 and k < 0.90:
                i = "ijk"[depth]
                if self.lang == "python":
                    w.open(f"for {i} in range({r.randint(2, 9)})")
                else:
                    w.open(f"for (int {i} = 0; {i} < {r.randint(2, 9)}; {i}++)")
                self.stmts(vs + [i], depth + 1, r.randint(1, 3)); w.close()
            elif depth < 2:
                c = self.nm(); w.line(self.decl(c, str(r.randint(0, 3)))); vs.append(c)
                w.open(f"while ({c} < {r.randint(4, 9)})" if self.lang != "python" else f"while {c} < {r.randint(4, 9)}")
                self.stmts(list(vs), depth + 1, r.randint(1, 2))
                w.line(f"{c} += 1{self.semi()}"); w.close()
            else:
                w.line(self.printer(r.choice(vs)))

    def function(self, idx):
        r, w = self.r, self.w
        ar = r.randint(1, 3); ps = ["a", "b", "c"][:ar]; name = f"calc{idx}"
        if self.lang == "python":
            w.open(f"def {name}({', '.join(ps)})")
        elif self.lang == "java":
            w.open(f"static int {name}({', '.join('int ' + p for p in ps)})")
        else:
            w.open(f"int {name}({', '.join('int ' + p for p in ps)})")
        vs = list(ps)
        self.stmts(vs, 1, r.randint(2, 4))
        w.line(f"return {self.expr(vs)}{self.semi()}")
        w.close(); w.line()
        self.funcs.append((name, ar))

    def generate(self) -> str:
        r, w, L = self.r, self.w, self.lang
        if L == "c":
            w.line("#include <stdio.h>"); w.line()
        elif L == "cpp":
            w.line("#include <iostream>"); w.line("using namespace std;"); w.line()
        if L == "java":
            w.open("public class Main"); w.line()
        for i in range(r.randint(1, 3)):
            self.function(i)
        if L == "python":
            w.open("def main()")
        elif L == "java":
            w.open("public static void main(String[] args)")
        else:
            w.open("int main()")
        vs: List[str] = []
        self.stmts(vs, 1, r.randint(4, 8))
        if not vs:
            vs.append("0")
        if L in ("c", "cpp"):
            w.line("return 0;")
        w.close()
        if L == "java":
            w.close()
        if L == "python":
            w.line(); w.out.append('main()')
        return "\n".join(w.out) + "\n"
