# -*- coding: utf-8 -*-
"""根据示例代码库生成《代码理解测评案例集》Markdown。

每道题都由系统的出题引擎真实生成（与页面中生成的题目一致），
用于说明测评任务的组织方式，也可作为教师审核与课堂使用的底稿。
"""
import io
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from codeassess import generator
from codeassess.samples import SAMPLES

OUT = BASE.parent / "代码理解测评案例集.md"
TYPE_LABEL = {"explain": "代码解释", "trace": "执行过程",
              "diagnose": "错误诊断", "modify": "局部修改"}


def render_question(idx, q):
    out = []
    out.append("**题目 %d**　`%s`　难度：%s　分值：%s 分　对应位置：%s\n"
               % (idx, TYPE_LABEL[q["type"]], q["difficulty"], q["points"],
                  q["code_ref"] or "全文"))
    out.append(q["stem"] + "\n")
    opts = json.loads(q["options"]) if q["options"] else []
    if opts:
        for o in opts:
            mark = " ✅" if o["key"] == q["answer"] else ""
            out.append("- %s. %s%s" % (o["key"], o["text"], mark))
        out.append("")
        out.append("> 参考答案：%s" % q["answer"])
    else:
        out.append("> 参考答案：%s" % (q["answer"] or "（开放题，按评分要点评判）"))
        rubric = json.loads(q["rubric"]) if q["rubric"] else []
        if rubric:
            out.append(">")
            out.append("> 评分要点：")
            for r in rubric:
                out.append("> - %s（权重 %s，关键词：%s）"
                           % (r.get("point"), r.get("weight"),
                              "、".join(r.get("keywords") or [])))
    out.append("")
    return "\n".join(out)


def main():
    buf = []
    buf.append("# 代码理解测评案例集\n")
    buf.append("> 面向 AI 辅助编程的代码理解测评系统 · 案例集（v1.0）\n")
    buf.append("本案例集由系统出题引擎对 15 个典型程序生成，共 %d 道题，覆盖"
               "代码解释、执行过程、错误诊断、局部修改四类任务。实际使用时，题目需经"
               "教师逐题审核（可通过/修改/删除）后才会发布给学生。\n\n" % 0)
    buf.append("## 一、编制说明\n")
    buf.append("- **测评对象**：学生本人提交的代码，题目指向具体行号，避免脱离代码的泛泛提问。\n")
    buf.append("- **任务类型**：代码含义（解释语句/函数）、执行过程（循环次数、复杂度、执行顺序）、"
               "错误诊断（边界与典型错误）、局部修改（改哪里、怎么改）。\n")
    buf.append("- **评分方式**：选择题按选项精确判分；开放题依据评分要点中的关键词覆盖情况给出"
               "建议分，教师复核后为最终成绩。\n")
    buf.append("- **难度标注**：易（读懂即可）、中（需推演或联系课程知识点）、难（需修改与权衡）。\n\n")

    total = 0
    rows = []
    sections = []
    for i, s in enumerate(SAMPLES, start=1):
        qs, gen, model = generator.generate(s["source"], s["language"], s["kp"])
        total += len(qs)
        counts = {}
        for q in qs:
            counts[q["type"]] = counts.get(q["type"], 0) + 1
        rows.append((i, s["title"], s["language"], s["kp"], len(qs),
                     "、".join("%s%d" % (TYPE_LABEL[k], v) for k, v in counts.items())))
        body = []
        body.append("## 案例 %d：%s\n" % (i, s["title"]))
        body.append("- 课程：%s　语言：%s　知识点：%s\n" % (s["course"], s["language"], s["kp"]))
        body.append("- 题量：%d 道（%s）　满分：%d 分\n"
                    % (len(qs), "、".join("%s %d" % (TYPE_LABEL[k], v) for k, v in counts.items()),
                       sum(q["points"] for q in qs)))
        lang = {"python": "python", "java": "java", "cpp": "cpp"}.get(s["language"], "")
        body.append("\n```%s\n%s```\n" % (lang, s["source"]))
        for j, q in enumerate(qs, start=1):
            body.append(render_question(j, q))
        sections.append("\n".join(body))

    buf[2] = buf[2].replace("%d" % 0, str(total))
    buf.append("## 二、案例清单\n")
    buf.append("| 编号 | 程序 | 语言 | 知识点 | 题量 | 类型分布 |")
    buf.append("| --- | --- | --- | --- | --- | --- |")
    for r in rows:
        buf.append("| %d | %s | %s | %s | %d | %s |" % r)
    buf.append("\n合计：%d 个程序、%d 道题。\n" % (len(SAMPLES), total))
    buf.append("## 三、案例明细\n")
    buf.append("\n---\n\n".join(sections))
    buf.append("\n---\n")
    buf.append("## 四、使用建议\n")
    buf.append("1. 课堂限时测评：从案例中选取 1—2 个与学生作业相近的程序，限时 15—20 分钟作答。\n")
    buf.append("2. 个性化测评：学生在系统中提交自己的代码，由系统按同样规则出题，"
               "教师审核后使用（本案例集即该系统在示例代码上的输出）。\n")
    buf.append("3. 现场核验：对开放题得分较高的学生，要求其现场修改代码或口头解释，"
               "以核实理解程度。\n")
    buf.append("4. 教学改进：按《知识点掌握情况》统计定位薄弱环节，安排针对性练习。\n")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(buf))
    print("案例集已生成：%s（%d 个程序 / %d 道题）" % (OUT, len(SAMPLES), total))


if __name__ == "__main__":
    main()