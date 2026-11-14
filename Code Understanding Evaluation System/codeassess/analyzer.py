# -*- coding: utf-8 -*-
"""代码结构分析：抽取函数、循环、分支、返回、复杂度等，作为出题上下文。

Python 使用标准库 ast 精确分析；Java / C / C++ 使用轻量正则启发式，
足以支撑"针对具体行号提问"的原型需求。
"""
import ast
import re
from dataclasses import dataclass, field


@dataclass
class Func:
    name: str
    args: list
    start: int
    end: int
    doc: str = ""
    returns: int = 0
    loops: int = 0


@dataclass
class Facts:
    language: str
    source: str
    lines: list
    funcs: list = field(default_factory=list)
    classes: list = field(default_factory=list)
    loop_lines: list = field(default_factory=list)
    cond_lines: list = field(default_factory=list)
    return_lines: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    max_depth: int = 0
    complexity: str = "O(1)"
    flags: dict = field(default_factory=dict)

    def line(self, n):
        return self.lines[n - 1] if 1 <= n <= len(self.lines) else ""

    def snippet(self, a, b=None, max_lines=14):
        b = b or a
        b = min(b, len(self.lines))
        a = max(1, a)
        if b - a + 1 > max_lines:
            b = a + max_lines - 1
        out = []
        for i in range(a, b + 1):
            out.append("%4d | %s" % (i, self.lines[i - 1]))
        return "\n".join(out)

    def has(self, key):
        return bool(self.flags.get(key))


PY_KEYWORDS = {"if", "for", "while", "return", "def", "class", "import", "from",
               "try", "except", "with", "else", "elif"}


def analyze(source, language="python"):
    language = (language or "python").lower()
    src = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = src.split("\n")
    facts = Facts(language=language, source=src, lines=lines)
    if language.startswith("py"):
        try:
            _analyze_python(src, facts)
        except SyntaxError:
            _analyze_generic(lines, facts)
        facts.flags["syntax_ok"] = _syntax_ok(src) if language.startswith("py") else True
    else:
        _analyze_generic(lines, facts)
        facts.flags["syntax_ok"] = True
    _complexity(facts)
    return facts


def _syntax_ok(src):
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def _analyze_python(src, facts):
    tree = ast.parse(src)
    lines = facts.lines

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            doc = (ast.get_docstring(node) or "").strip().split("\n")[0]
            facts.funcs.append(Func(
                name=node.name, args=args,
                start=node.lineno, end=getattr(node, "end_lineno", node.lineno),
                doc=doc,
                returns=sum(1 for n in ast.walk(node) if isinstance(n, ast.Return)),
                loops=sum(1 for n in ast.walk(node)
                          if isinstance(n, (ast.For, ast.While, ast.AsyncFor)))))
        elif isinstance(node, ast.ClassDef):
            facts.classes.append(node.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                facts.imports.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            facts.imports.append(node.module or "")
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            facts.loop_lines.append((node.lineno, "for"))
            facts.flags.setdefault("for_ranges", []).append(
                _range_info(node, lines))
        elif isinstance(node, ast.While):
            facts.loop_lines.append((node.lineno, "while"))
        elif isinstance(node, ast.If):
            facts.cond_lines.append((node.lineno, lines[node.lineno - 1].strip()))
        elif isinstance(node, ast.Return):
            expr = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            facts.return_lines.append((node.lineno, expr))
        elif isinstance(node, ast.Call):
            fn = _call_name(node.func)
            if fn:
                facts.calls.append(fn)

    facts.funcs.sort(key=lambda f: f.start)
    _mark_flags(tree, facts)
    _loop_depth(tree, facts)


def _range_info(node, lines):
    """解析 for ... in range(...) / literal 序列，用于生成"循环次数"题。"""
    info = {"line": node.lineno, "target": "", "kind": "", "count": None,
            "items": None}
    try:
        if isinstance(node.target, ast.Name):
            info["target"] = node.target.id
    except Exception:
        pass
    it = node.iter
    if (isinstance(it, ast.Call) and isinstance(it.func, ast.Name)
            and it.func.id == "range"):
        info["kind"] = "range"
        args = []
        for a in it.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, int):
                args.append(a.value)
            else:
                return info
        if len(args) == 1:
            info["count"] = args[0]
        elif len(args) == 2:
            info["count"] = max(0, args[1] - args[0])
        elif len(args) == 3 and args[2] != 0:
            info["count"] = max(0, len(range(args[0], args[1], args[2])))
    elif isinstance(it, (ast.List, ast.Tuple, ast.Set)):
        if all(isinstance(e, ast.Constant) for e in it.elts):
            info["kind"] = "literal"
            info["items"] = [e.value for e in it.elts]
            info["count"] = len(it.elts)
    elif isinstance(it, (ast.Name, ast.Attribute)):
        info["kind"] = "iterable"
        info["items"] = ast.unparse(it)[:40] if hasattr(ast, "unparse") else ""
    return info


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _mark_flags(tree, facts):
    fl = facts.flags
    fl["has_index"] = False
    fl["has_div"] = False
    fl["has_recursion"] = False
    fl["has_mutable_default"] = False
    fl["has_while"] = False
    func_names = {f.name for f in facts.funcs}
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            fl["has_index"] = True
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            fl["has_div"] = True
        if isinstance(node, ast.While):
            fl["has_while"] = True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(isinstance(d, (ast.List, ast.Dict, ast.Set)) for d in node.args.defaults):
                fl["has_mutable_default"] = True
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and _call_name(n.func) == node.name:
                    fl["has_recursion"] = True
    fl["has_index"] = fl["has_index"] or fl["has_recursion"]
    fl["func_names"] = sorted(func_names)


def _loop_depth(tree, facts):
    best = 0

    def walk(node, depth):
        nonlocal best
        for child in ast.iter_child_nodes(node):
            d = depth + 1 if isinstance(child, (ast.For, ast.While, ast.AsyncFor)) else depth
            best = max(best, d)
            walk(child, d)

    walk(tree, 0)
    facts.max_depth = best


RE_JAVA_FUNC = re.compile(
    r"^\s*(?:public|private|protected|static|final|abstract|synchronized|\s)*"
    r"[\w<>\[\],\s]+\s+(\w+)\s*\(([^)]*)\)\s*\{?\s*$")
RE_LOOP = re.compile(r"\b(for|while|do)\b")
RE_IF = re.compile(r"\b(if|else\s+if)\b")
RE_RETURN = re.compile(r"\breturn\b")


def _analyze_generic(lines, facts):
    depth = 0
    loop_depths = []
    func_frames = []
    for i, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        m = RE_JAVA_FUNC.match(line)
        if m and m.group(1) not in PY_KEYWORDS and "=" not in line.split("(")[0]:
            params = []
            for a in m.group(2).split(","):
                tok = a.strip().split()
                if tok:
                    params.append(tok[-1].replace("[]", ""))
            fn = Func(name=m.group(1), args=params, start=i, end=i)
            facts.funcs.append(fn)
            func_frames.append((fn, depth))
        if RE_LOOP.search(line):
            facts.loop_lines.append((i, line.split()[0]))
            loop_depths.append(depth)
            facts.max_depth = max(facts.max_depth, len(loop_depths))
        if RE_IF.search(line):
            facts.cond_lines.append((i, line))
        if RE_RETURN.search(line):
            facts.return_lines.append((i, line))
        if line.startswith("import "):
            facts.imports.append(line[7:].strip().rstrip(";"))
        depth += line.count("{") - line.count("}")
        while loop_depths and depth <= loop_depths[-1]:
            loop_depths.pop()
        while func_frames and depth <= func_frames[-1][1]:
            fn, d = func_frames.pop()
            fn.end = max(fn.start, i)

    for fn, _ in func_frames:
        fn.end = len(lines)
    for idx, f in enumerate(facts.funcs):
        if f.end <= f.start:
            nxt = facts.funcs[idx + 1].start if idx + 1 < len(facts.funcs) else len(lines) + 1
            f.end = max(f.start, nxt - 1)
    facts.flags.update({"has_index": "[" in facts.source,
                        "has_div": "/" in facts.source,
                        "has_recursion": False,
                        "has_mutable_default": False,
                        "has_while": any(k.lower().startswith("while") for _, k in facts.loop_lines),
                        "func_names": sorted({f.name for f in facts.funcs})})


def _complexity(facts):
    depth = facts.max_depth
    src = facts.source
    has_sort = bool(re.search(r"(\.\s*sort\s*\(|\bsorted\s*\()", src))
    has_halving = bool(re.search(r"(//=|/\s*=\s*|>>=|i\s*=\s*i\s*//\s*2|i\s*=\s*i\s*/\s*2|mid)", src))
    if facts.flags.get("has_recursion"):
        facts.complexity = "O(n)" if depth <= 1 else "O(n²)"
    elif depth >= 2:
        facts.complexity = "O(n²)"
    elif depth == 1 and has_halving:
        facts.complexity = "O(log n)"
    elif depth == 1:
        facts.complexity = "O(n log n)" if has_sort else "O(n)"
    else:
        facts.complexity = "O(1)"