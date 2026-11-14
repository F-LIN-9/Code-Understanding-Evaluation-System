# -*- coding: utf-8 -*-
"""演示数据：示例代码、已审核测评、学生作答记录。

使系统首次启动即可看到完整流程（提交—生成—审核—作答—评分—统计），
而不是面对空数据库。可重复执行：已存在演示代码时直接跳过。
"""
from . import db
from . import generator
from . import scoring
from .samples import SAMPLES


def _insert_code(student_id, s):
    return db.x("""INSERT INTO codes(student_id,course,title,language,source,knowledge_points,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (student_id, s["course"], s["title"], s["language"], s["source"],
                 s["kp"], db.now()))


def _insert_assessment(code, teacher_id, mode="class", limit=20,
                       approve_all=True, drop_types=()):
    qs, gen, model = generator.generate(code["source"], code["language"],
                                        code["knowledge_points"])
    qs = [q for q in qs if q["type"] not in drop_types]
    aid = db.x("""INSERT INTO assessments(code_id,title,mode,time_limit,status,generator,model,
                  created_by,created_at,published_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
               (code["id"], "%s · 代码理解测评" % code["title"], mode, limit,
                "reviewing", gen, model, teacher_id, db.now(), ""))
    for i, q in enumerate(qs, start=1):
        db.x("""INSERT INTO questions(assessment_id,seq,type,difficulty,stem,code_ref,options,
                answer,rubric,points,status,source,model) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (aid, i, q["type"], q["difficulty"], q["stem"], q["code_ref"], q["options"],
              q["answer"], q["rubric"], q["points"],
              "approved" if approve_all else "pending", q["source"], q["model"]))
    if approve_all:
        db.x("UPDATE assessments SET status='published', published_at=? WHERE id=?",
             (db.now(), aid))
    return aid


COVERAGE = {"explain": 0.8, "trace": 0.6, "diagnose": 0.4, "modify": 0.35}


def _answer_text(question, plan):
    """按给定覆盖比例造一份学生作答：选项题按比例答对，开放题覆盖部分要点。"""
    rubric = scoring.load_rubric(question.get("rubric"))
    options = scoring.load_options(question.get("options"))
    if options:
        if plan >= 0.7:
            return question.get("answer")
        for o in options:
            if o["key"] != question.get("answer"):
                return o["key"]
    if not rubric:
        return "先看输入，再按循环处理数据，最后返回结果。"
    k = max(1, min(len(rubric), int(round(len(rubric) * plan))))
    parts = []
    for r in rubric[:k]:
        ks = [x for x in (r.get("keywords") or []) if x]
        if ks:
            parts.append(ks[0])
    return "我的理解是：" + "；".join(parts) + "。然后得到结果并返回。"


def seed_demo(force=False):
    if db.q1("SELECT id FROM codes LIMIT 1") and not force:
        return False
    teacher = db.q1("SELECT * FROM users WHERE role='teacher' ORDER BY id LIMIT 1")
    students = db.q("SELECT * FROM users WHERE role='student' ORDER BY id")
    if not teacher or not students:
        return False

    created = []
    for i, s in enumerate(SAMPLES):
        stu = students[i % len(students)]
        cid = _insert_code(stu["id"], s)
        created.append((cid, stu))

    cid, stu = created[0]
    code = db.q1("SELECT * FROM codes WHERE id=?", (cid,))
    aid = _insert_assessment(code, teacher["id"], mode="class", limit=20, approve_all=True)
    qs = db.q("SELECT * FROM questions WHERE assessment_id=? ORDER BY seq", (aid,))
    total = sum(q["points"] for q in qs)
    tid = db.x("INSERT INTO attempts(assessment_id,student_id,started_at,submitted_at,status,score,max_score)"
               " VALUES(?,?,?,?,?,?,?)",
               (aid, stu["id"], db.now(), db.now(), "scored", 0, total))
    got = 0.0
    for q in qs:
        plan = COVERAGE.get(q["type"], 0.5)
        resp = _answer_text(q, plan)
        ev = scoring.evaluate_answer(q, resp, use_llm=False)
        db.x("""INSERT INTO answers(attempt_id,question_id,response,auto_score,ai_score,
                final_score,feedback,point_hits) VALUES(?,?,?,?,?,?,?,?)""",
             (tid, q["id"], resp, ev["score"], ev["score"], ev["score"], ev["feedback"],
              "[]"))
        got += ev["score"]
    db.x("UPDATE attempts SET score=? WHERE id=?", (round(got, 2), tid))

    if len(created) > 1:
        cid2, _ = created[1]
        code2 = db.q1("SELECT * FROM codes WHERE id=?", (cid2,))
        _insert_assessment(code2, teacher["id"], mode="self", limit=30, approve_all=True)

    if len(created) > 2:
        cid3, _ = created[2]
        code3 = db.q1("SELECT * FROM codes WHERE id=?", (cid3,))
        _insert_assessment(code3, teacher["id"], mode="class", limit=25,
                           approve_all=False)
    db.log(teacher, "seed_demo", "db", None, "写入演示数据")
    return True


if __name__ == "__main__":
    from . import db
    db.init_db()
    db.seed()
    ok = seed_demo(force=True)
    print("演示数据已写入" if ok else "演示数据已存在")