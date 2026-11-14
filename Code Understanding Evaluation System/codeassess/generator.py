# -*- coding: utf-8 -*-
"""测评题目生成：优先调用大模型，失败或离线时使用本地规则引擎。

每道题都绑定到具体代码位置（行号 + 片段），并给出参考答案与评分要点，
教师审核通过后才会进入测评。
"""
import json
import random
import re

from . import llm
from .analyzer import analyze

TYPES = [
    ("explain", "代码解释"),
    ("trace", "执行过程"),
    ("diagnose", "错误诊断"),
    ("modify", "局部修改"),
]
TYPE_NAME = dict(TYPES)

GENERIC_DISTRACTORS = [
    "声明一个新的变量并初始化为 0",
    "输出中间结果，便于调试",
    "提前结束整个程序",
    "跳过本次循环，进入下一次迭代",
    "定义一个新的函数",
    "捕获并处理可能出现的异常",
    "把字符串转换为整数",
]


def _rotate_put(stem, correct, distractors, seed=0):
    """把正确选项放到由题干长度决定的位置，返回 (options, answer_key)。"""
    pool = []
    for d in [correct] + distractors:
        if d and d not in pool:
            pool.append(d)
    for g in GENERIC_DISTRACTORS:
        if len(pool) >= 4:
            break
        if g not in pool:
            pool.append(g)
    pool = pool[:4]
    pos = (len(stem) + seed) % 4
    rest = [p for p in pool if p != correct]
    options = rest[:pos] + [correct] + rest[pos:]
    keys = ["A", "B", "C", "D"]
    opts = [{"key": k, "text": t} for k, t in zip(keys, options)]
    return opts, keys[options.index(correct)]


def _q(qtype, difficulty, stem, points, code_ref="", options=None, answer="",
       rubric=None, source="rule", model=""):
    return {
        "type": qtype,
        "difficulty": difficulty,
        "stem": stem,
        "code_ref": code_ref,
        "options": json.dumps(options, ensure_ascii=False) if options else "",
        "answer": answer,
        "rubric": json.dumps(rubric or [], ensure_ascii=False),
        "points": points,
        "source": source,
        "model": model,
    }


def _rubric(*points):
    """points: (说明, [关键词], 权重)"""
    out = []
    for p, kws, w in points:
        out.append({"point": p, "keywords": kws, "weight": w})
    return out


def _main_func(facts):
    if not facts.funcs:
        return None
    return max(facts.funcs, key=lambda f: (f.end - f.start, f.loops, f.returns))


def _key_line(facts, f):
    """选一条有代表性的语句：优先 return，其次循环，最后函数首行。"""
    if facts.return_lines:
        ln, _ = facts.return_lines[0]
        return ln
    if facts.loop_lines:
        return facts.loop_lines[0][0]
    return f.start if f else 1


def _loop_info(facts):
    for info in facts.flags.get("for_ranges", []) or []:
        if info.get("count") is not None:
            return info
    return None


def generate_by_rules(source, language="python", knowledge_points=""):
    facts = analyze(source, language)
    f = _main_func(facts)
    fname = f.name if f else "代码"
    args = f.args if f else []
    kps = [k.strip() for k in re.split(r"[,，;；、]", knowledge_points or "") if k.strip()]
    qs = []

    ln = _key_line(facts, f)
    code_line = facts.line(ln).strip()
    if facts.return_lines and facts.return_lines[0][0] == ln:
        correct = "把计算结果返回给调用者，并结束当前函数的执行"
        distractors = ["在控制台打印该表达式的值",
                       "把表达式的结果赋值给一个新的局部变量",
                       "抛出异常以中断函数执行"]
    elif facts.loop_lines and facts.loop_lines[0][0] == ln:
        it = ""
        for info in facts.flags.get("for_ranges", []) or []:
            if info["line"] == ln:
                it = info.get("items") or ("range(...)" if info["kind"] == "range" else "")
        if facts.language.startswith("py"):
            correct = "遍历%s，对每个元素重复执行循环体" % (it or "可迭代对象")
        else:
            correct = "控制循环变量按条件变化，重复执行循环体"
        distractors = ["只在条件成立时执行一次循环体",
                       "声明一个名为 %s 的变量" % (it if isinstance(it, str) and it.isidentifier() else "i"),
                       "提前跳出循环并返回结果"]
    else:
        var = re.match(r"\s*([A-Za-z_]\w*)\s*=", code_line)
        correct = ("计算右侧表达式并把结果保存到变量 %s" % var.group(1)) if var else \
            "执行该语句完成一次具体的计算或函数调用"
        distractors = ["声明一个新的函数", "结束程序运行", "跳过当前循环"]
    stem = "第 %d 行语句 `%s` 的作用是（　）。" % (ln, code_line[:60])
    opts, ans = _rotate_put(stem, correct, distractors, seed=1)
    qs.append(_q("explain", "易", stem, 8,
                 code_ref="第 %d 行" % ln, options=opts, answer=ans,
                 rubric=_rubric(("能判断该语句的功能", [correct[:8]], 1))))

    loop_desc = "遍历数据并逐个处理" if facts.loop_lines else "顺序执行若干计算"
    ret_desc = "返回处理结果" if facts.return_lines else "直接结束"
    rubric = _rubric(
        ("说明函数的输入（参数含义）", [a for a in args] + ["参数", "输入"], 1),
        ("概括关键处理步骤（循环/判断）", ["循环", "遍历", "判断", "条件"], 1),
        ("说明输出或返回值", ["返回", "输出", "结果"], 1),
        ("用自己的话概括而非照抄代码", [fname, "函数"], 0.5),
    )
    stem = ("请用自己的话说明函数 %s 的功能：它接收什么输入，经过哪些关键步骤，"
            "最后返回什么结果？" % fname)
    if kps:
        stem += "（结合知识点：%s）" % "、".join(kps)
    qs.append(_q("explain", "中", stem, 12,
                 code_ref="第 %d—%d 行" % (f.start, f.end) if f else "全文",
                 rubric=rubric, answer=("该函数%s，%s。"
                                        % (loop_desc, ret_desc))))

    info = _loop_info(facts)
    if info:
        c = info["count"]
        cand = [str(c), str(c + 1), str(max(0, c - 1)), "取决于运行时输入"]
        correct = str(c)
        distractors = [x for x in cand if x != correct]
        stem = ("第 %d 行的 for 循环（变量 %s）在代码执行时，循环体一共会被执行多少次（　）。"
                % (info["line"], info.get("target") or "i"))
        opts, ans = _rotate_put(stem, correct, distractors, seed=3)
        qs.append(_q("trace", "易", stem, 8,
                     code_ref="第 %d 行" % info["line"], options=opts, answer=ans,
                     rubric=_rubric(("能算出循环次数", [correct], 1))))
    else:
        order = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)"]
        correct = facts.complexity
        i = order.index(correct) if correct in order else 2
        distractors = []
        for delta in (-1, 1, -2, 2):
            j = i + delta
            if 0 <= j < len(order) and order[j] not in distractors:
                distractors.append(order[j])
            if len(distractors) >= 3:
                break
        for x in order:
            if len(distractors) >= 3:
                break
            if x != correct and x not in distractors:
                distractors.append(x)
        stem = "该段代码的时间复杂度最接近（　）。"
        opts, ans = _rotate_put(stem, correct, distractors, seed=3)
        qs.append(_q("trace", "中", stem, 8,
                     code_ref="第 %d—%d 行" % (f.start, f.end) if f else "全文",
                     options=opts, answer=ans,
                     rubric=_rubric(("能判断复杂度", [correct], 1))))

    a, b = (f.start, f.end) if f else (1, min(len(facts.lines), 20))
    rubric = _rubric(
        ("说明先执行哪些语句或判断", ["先", "首先", "判断", "条件"], 1),
        ("说明循环遍历的对象与次数", ["循环", "遍历", "次", "range"], 1),
        ("说明结束时的返回或输出", ["最后", "返回", "输出"], 1),
    )
    flow = []
    if facts.cond_lines:
        flow.append("先做条件判断")
    if facts.loop_lines:
        flow.append("然后进入循环遍历数据")
    flow.append("最后返回计算结果" if facts.return_lines else "最后结束函数")
    stem = ("请按执行顺序描述第 %d—%d 行的处理过程：先做什么判断、循环遍历什么、"
            "最后返回什么。" % (a, b))
    qs.append(_q("trace", "中", stem, 12, code_ref="第 %d—%d 行" % (a, b),
                 rubric=rubric,
                 answer="，".join(flow) + "。"))

    args_txt = "、".join(args) if args else "参数"
    if facts.has("has_index"):
        stem = ("当传入的数据为空（长度为 0）时，上面代码会发生什么？请说明原因，"
                "并给出避免该问题的最小改动思路。")
        answer = "访问空序列的元素会抛出 IndexError（下标越界），应先判断长度或使用空值处理。"
        rubric = _rubric(
            ("指出会抛出下标越界异常", ["IndexError", "越界", "报错", "异常"], 1),
            ("说明原因：访问了不存在的元素", ["长度", "空", "0", "不存在"], 1),
            ("给出先判断长度的修改思路", ["if", "len", "not", "判断"], 1),
        )
    elif facts.has("has_div"):
        stem = "如果参与除法运算的量取值为 0，程序会发生什么？应如何避免？"
        answer = "会抛出 ZeroDivisionError（除零错误），应在外层判断除数是否为 0。"
        rubric = _rubric(
            ("指出除零错误", ["ZeroDivisionError", "除零", "除以0", "异常"], 1),
            ("说明触发条件", ["0", "除数", "为空"], 1),
            ("给出判断除数的修改", ["if", "!=0", "==0", "判断"], 1),
        )
    elif facts.has("has_mutable_default"):
        stem = "函数的默认参数使用了列表或字典，连续多次调用会发生什么？请说明原因和正确写法。"
        answer = "默认参数只创建一次，多次调用会共享同一个对象；应使用 None 作为默认值并在函数内初始化。"
        rubric = _rubric(
            ("指出多次调用会累积共享数据", ["共享", "累积", "同一个", "多次"], 1),
            ("说明原因：默认值只求值一次", ["默认", "一次", "只创建"], 1),
            ("给出 None + 初始化的写法", ["None", "if", "初始化"], 1),
        )
    elif facts.has("has_recursion"):
        stem = "这段递归代码的终止条件是什么？如果去掉终止条件会发生什么？"
        answer = "终止条件是不再继续递归的判断分支；去掉后会无限递归，最终触发 RecursionError。"
        rubric = _rubric(
            ("指出终止条件所在分支", ["终止", "if", "条件", "返回"], 1),
            ("说明无限递归的后果", ["RecursionError", "栈溢出", "无限"], 1),
            ("说明边界输入的处理", ["0", "1", "边界"], 1),
        )
    else:
        stem = ("如果把第 %d 行的循环条件稍作改动（例如 < 改成 <=），"
                "在什么输入下结果会出错？请说明原因。" % (facts.loop_lines[0][0] if facts.loop_lines else ln))
        answer = "边界输入（最后一个元素或长度为 0 的输入）容易出错，会出现多执行一次或少执行一次。"
        rubric = _rubric(
            ("指出边界输入", ["边界", "0", "空", "最后一个"], 1),
            ("说明多执行/少执行一次的现象", ["多", "少", "一次", "越界"], 1),
            ("给出修正方式", ["改回", "条件", "<"], 1),
        )
    qs.append(_q("diagnose", "中", stem, 12,
                 code_ref="第 %d—%d 行" % (a, b), rubric=rubric, answer=answer))

    if facts.return_lines:
        if facts.language.startswith("py"):
            target = "在输入为空时直接返回 None，而不是继续执行后续计算"
        else:
            target = "在输入为空或非法时提前返回（或抛出明确的异常），而不是继续执行后续计算"
    else:
        target = "在关键计算前增加对输入的合法性检查"
    stem = ("请给出一个具体修改方案：%s。说明需要修改的位置（行号或函数名）"
            "以及要增加或改写的关键语句。" % target)
    rubric = _rubric(
        ("指出修改位置（行号或函数名）", ["行", fname], 1),
        ("写出关键判断语句", ["if", "not", "len", "==", "is None"], 1),
        ("说明修改后的返回或流程变化", ["return", "返回", "None"], 1),
    )
    qs.append(_q("modify", "难", stem, 12, code_ref="第 %d—%d 行" % (a, b),
                 rubric=rubric,
                 answer="在函数开头加入 `if not x: return None`（或对长度/None 的判断），"
                        "再执行原有逻辑。"))

    return qs


PROMPT_SYSTEM = (
    "你是一名计算机课程助教，负责根据学生提交的代码出《代码理解》测评题。"
    "题目必须紧扣给定的具体行号与代码片段，不能泛泛考察语法常识。"
    "只输出 JSON。"
)

PROMPT_USER = """请阅读下面的学生代码，围绕四个方面出 6 道测评题：
1. explain（代码解释）：解释关键语句或函数的作用；
2. trace（执行过程）：推演变量、循环次数、执行顺序或输出；
3. diagnose（错误诊断）：边界条件、典型错误及其后果；
4. modify（局部修改）：按要求做局部修改，说明改哪里、怎么改。

要求：
- 每题给出 type、difficulty（易/中/难）、stem、code_ref（如"第 12 行"）、points；
- 选择题给出 options（4 个，形如 [{{"key":"A","text":"..."}}]）和 answer（选项字母）；
- 开放题给出 rubric：评分要点数组，每项含 point（要点）、keywords（关键词数组）、weight（权重）；
- 选择题 8 分，开放题 12 分；
- 不要编造代码里不存在的函数名或行号。

课程知识点：{kps}
代码语言：{lang}
代码（行号见左侧）：
{code}

输出 JSON：{{"questions": [ ... ]}}"""


def _format_code(source, language):
    lines = source.replace("\r\n", "\n").split("\n")
    return "\n".join("%3d | %s" % (i + 1, l) for i, l in enumerate(lines))


def _validate(items, source, language):
    facts = analyze(source, language)
    ok = []
    for it in items or []:
        try:
            t = it.get("type")
            if t not in TYPE_NAME:
                continue
            stem = (it.get("stem") or "").strip()
            if len(stem) < 6:
                continue
            pts = float(it.get("points") or (8 if t in ("explain", "trace") and it.get("options") else 12))
            pts = max(2, min(20, pts))
            options = it.get("options") or None
            answer = (it.get("answer") or "").strip()
            rubric = it.get("rubric") or []
            if options and answer not in [o.get("key") for o in options]:
                continue
            if not options and not rubric:
                continue
            ref = (it.get("code_ref") or "").strip()
            m = re.search(r"第\s*(\d+)", ref)
            if m and not (1 <= int(m.group(1)) <= max(1, len(facts.lines))):
                continue
            ok.append(_q(t, it.get("difficulty") or "中", stem, pts,
                         code_ref=ref, options=options, answer=answer,
                         rubric=rubric, source="llm",
                         model=llm.status().get("model", "")))
        except Exception:
            continue
    return ok


def generate(source, language="python", knowledge_points="", use_llm=True):
    """返回 (questions, generator_name, model_name)。"""
    if use_llm and llm.available():
        msgs = [
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": PROMPT_USER.format(
                kps=knowledge_points or "无",
                lang=language,
                code=_format_code(source, language))},
        ]
        data = llm.chat_json(msgs, temperature=0.3)
        got = _validate((data or {}).get("questions"), source, language)
        if len(got) >= 4:
            return got, "llm", llm.status().get("model", "")
        rule = generate_by_rules(source, language, knowledge_points)
        return rule, "rule-fallback", ""
    return generate_by_rules(source, language, knowledge_points), "rule", ""