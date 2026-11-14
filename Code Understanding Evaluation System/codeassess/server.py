# -*- coding: utf-8 -*-
"""HTTP 服务与业务接口（标准库实现，无第三方依赖）。

接口约定：所有 /api/* 返回 {"ok": true, "data": ...} 或 {"ok": false, "error": "..."}。
"""
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import db
from . import llm
from . import generator
from . import scoring
from .config import STATIC_DIR, APP_NAME

sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None

SESSIONS = {}
ROUTES = []


class ApiError(Exception):
    def __init__(self, msg, code=400):
        self.msg = msg
        self.code = code
        super().__init__(msg)


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


def need(user, role=None):
    if not user:
        raise ApiError("请先登录", 401)
    if role and user["role"] != role:
        raise ApiError("没有权限执行该操作", 403)
    return user


def user_public(u):
    return {"id": u["id"], "name": u["name"], "role": u["role"],
            "username": u["username"], "class_name": u["class_name"]}


def assessment_public(a, detail=False):
    a = dict(a)
    a["type_counts"] = {"pending": 0}
    return a


@route("POST", r"/api/login")
def api_login(ctx):
    body = ctx["body"]
    username = (body.get("username") or "").strip()
    if not username:
        raise ApiError("请输入账号")
    u = db.q1("SELECT * FROM users WHERE username=?", (username,))
    if not u:
        raise ApiError("账号不存在，请使用演示账号（教师 liyuejun / 学生 2023001—2023004）", 401)
    sid = secrets.token_urlsafe(16)
    SESSIONS[sid] = u["id"]
    db.log(u, "login")
    return {"user": user_public(u), "_cookie": sid}


@route("POST", r"/api/logout")
def api_logout(ctx):
    sid = ctx["sid"]
    if sid:
        SESSIONS.pop(sid, None)
    return {"ok": True}


@route("GET", r"/api/me")
def api_me(ctx):
    u = ctx["user"]
    if not u:
        raise ApiError("未登录", 401)
    return {"user": user_public(u), "llm": llm.status()}


@route("GET", r"/api/users")
def api_users(ctx):
    need(ctx["user"], "teacher")
    rows = db.q("SELECT id,name,role,class_name,username FROM users ORDER BY role DESC, id")
    return {"users": rows}


@route("GET", r"/api/codes")
def api_codes(ctx):
    u = need(ctx["user"])
    if u["role"] == "teacher":
        rows = db.q("""SELECT c.*, u.name AS student_name,
                              (SELECT COUNT(1) FROM assessments a WHERE a.code_id=c.id) AS assessment_count
                       FROM codes c JOIN users u ON u.id=c.student_id
                       ORDER BY c.id DESC""")
    else:
        rows = db.q("""SELECT c.*, u.name AS student_name,
                              (SELECT COUNT(1) FROM assessments a WHERE a.code_id=c.id) AS assessment_count
                       FROM codes c JOIN users u ON u.id=c.student_id
                       WHERE c.student_id=? ORDER BY c.id DESC""", (u["id"],))
    return {"codes": rows}


@route("POST", r"/api/codes")
def api_create_code(ctx):
    u = need(ctx["user"], "student")
    b = ctx["body"]
    title = (b.get("title") or "").strip()
    source = (b.get("source") or "").strip()
    if not title:
        raise ApiError("请填写代码题目")
    if len(source) < 20:
        raise ApiError("代码过短（至少 20 个字符），无法生成有针对性的测评题")
    if len(source) > 20000:
        raise ApiError("代码过长，请提交核心代码片段（不超过 20000 字符）")
    lang = (b.get("language") or "python").lower()
    if lang not in ("python", "java", "cpp", "c"):
        lang = "python"
    kp = (b.get("knowledge_points") or "").strip()
    cid = db.x("""INSERT INTO codes(student_id,course,title,language,source,knowledge_points,created_at)
                  VALUES(?,?,?,?,?,?,?)""",
               (u["id"], (b.get("course") or "程序设计基础").strip(), title, lang,
                source, kp, db.now()))
    db.log(u, "submit_code", "codes", cid, title)
    return {"code": db.q1("SELECT * FROM codes WHERE id=?", (cid,))}


@route("GET", r"/api/codes/(\d+)")
def api_code_detail(ctx, cid):
    u = need(ctx["user"])
    c = db.q1("""SELECT c.*, u.name AS student_name FROM codes c
                 JOIN users u ON u.id=c.student_id WHERE c.id=?""", (int(cid),))
    if not c:
        raise ApiError("代码不存在", 404)
    if u["role"] == "student" and c["student_id"] != u["id"]:
        raise ApiError("无权查看该代码", 403)
    idx = [{"id": a["id"], "title": a["title"], "status": a["status"]} for a in
           db.q("SELECT id,title,status FROM assessments WHERE code_id=? ORDER BY id DESC", (c["id"],))]
    return {"code": c, "assessments": idx}


@route("POST", r"/api/codes/(\d+)/assessments")
def api_create_assessment(ctx, cid):
    u = need(ctx["user"])
    code = db.q1("SELECT * FROM codes WHERE id=?", (int(cid),))
    if not code:
        raise ApiError("代码不存在", 404)
    if u["role"] == "student" and code["student_id"] != u["id"]:
        raise ApiError("只能为自己的代码发起测评", 403)
    b = ctx["body"]
    mode = b.get("mode") if b.get("mode") in ("class", "self") else "class"
    try:
        limit = int(b.get("time_limit") or 20)
    except Exception:
        limit = 20
    limit = max(5, min(180, limit))
    qs, gen, model = generator.generate(code["source"], code["language"],
                                        code["knowledge_points"])
    aid = db.x("""INSERT INTO assessments(code_id,title,mode,time_limit,status,generator,model,
                  created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
               (code["id"], "%s · 代码理解测评" % code["title"], mode, limit,
                "reviewing", gen, model, u["id"], db.now()))
    for i, q in enumerate(qs, start=1):
        db.x("""INSERT INTO questions(assessment_id,seq,type,difficulty,stem,code_ref,options,
                answer,rubric,points,status,source,model) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (aid, i, q["type"], q["difficulty"], q["stem"], q["code_ref"], q["options"],
              q["answer"], q["rubric"], q["points"], "pending", q["source"], q["model"]))
    db.log(u, "generate_questions", "assessments", aid,
           {"count": len(qs), "generator": gen})
    return {"assessment_id": aid, "question_count": len(qs), "generator": gen}


def _assessment_row(aid):
    return db.q1("""SELECT a.*, c.title AS code_title, c.language, c.source, c.knowledge_points,
                           c.student_id, u.name AS student_name, c.course
                    FROM assessments a JOIN codes c ON c.id=a.code_id
                    JOIN users u ON u.id=c.student_id WHERE a.id=?""", (aid,))


def _question_counts(aid):
    rows = db.q("SELECT status, COUNT(1) AS n FROM questions WHERE assessment_id=? GROUP BY status",
                (aid,))
    d = {"pending": 0, "approved": 0, "rejected": 0}
    for r in rows:
        d[r["status"]] = r["n"]
    return d


@route("GET", r"/api/assessments")
def api_assessments(ctx):
    u = need(ctx["user"])
    sql = """SELECT a.*, c.title AS code_title, c.language, u.name AS student_name
             FROM assessments a JOIN codes c ON c.id=a.code_id
             JOIN users u ON u.id=c.student_id"""
    params = ()
    if u["role"] == "student":
        sql += " WHERE c.student_id=?"
        params = (u["id"],)
    sql += " ORDER BY a.id DESC"
    rows = db.q(sql, params)
    for r in rows:
        r.update(_question_counts(r["id"]))
    return {"assessments": rows}


@route("GET", r"/api/assessments/(\d+)")
def api_assessment_detail(ctx, aid):
    u = need(ctx["user"])
    a = _assessment_row(int(aid))
    if not a:
        raise ApiError("测评不存在", 404)
    if u["role"] == "student" and a["student_id"] != u["id"] and a["status"] != "published":
        raise ApiError("无权查看", 403)
    qs = db.q("SELECT * FROM questions WHERE assessment_id=? ORDER BY seq", (a["id"],))
    a["counts"] = _question_counts(a["id"])
    return {"assessment": a, "questions": qs}


@route("PATCH", r"/api/questions/(\d+)")
def api_review_question(ctx, qid):
    u = need(ctx["user"], "teacher")
    q = db.q1("SELECT * FROM questions WHERE id=?", (int(qid),))
    if not q:
        raise ApiError("题目不存在", 404)
    b = ctx["body"]
    action = b.get("action")
    if action == "approve":
        db.x("UPDATE questions SET status='approved', review_note=?, reviewed_by=?, reviewed_at=?"
             " WHERE id=?", (b.get("note") or "", u["id"], db.now(), q["id"]))
    elif action == "reject":
        db.x("UPDATE questions SET status='rejected', review_note=?, reviewed_by=?, reviewed_at=?"
             " WHERE id=?", (b.get("note") or "教师删除", u["id"], db.now(), q["id"]))
    elif action == "edit":
        fields = ["stem", "difficulty", "points", "answer", "code_ref"]
        sets, vals = [], []
        for f in fields:
            if f in b and b[f] is not None:
                sets.append("%s=?" % f)
                vals.append(b[f])
        if "options" in b:
            sets.append("options=?")
            vals.append(json.dumps(b["options"], ensure_ascii=False))
        if "rubric" in b:
            sets.append("rubric=?")
            vals.append(json.dumps(b["rubric"], ensure_ascii=False))
        if not sets:
            raise ApiError("没有需要修改的内容")
        sets += ["status='approved'", "review_note=?", "reviewed_by=?", "reviewed_at=?"]
        vals += [b.get("note") or "教师修改后通过", u["id"], db.now(), q["id"]]
        db.x("UPDATE questions SET %s WHERE id=?" % ",".join(sets), tuple(vals))
    else:
        raise ApiError("未知操作")
    db.log(u, "review_question:%s" % action, "questions", q["id"], q["stem"][:40])
    return {"question": db.q1("SELECT * FROM questions WHERE id=?", (q["id"],))}


@route("POST", r"/api/assessments/(\d+)/publish")
def api_publish(ctx, aid):
    u = need(ctx["user"], "teacher")
    a = _assessment_row(int(aid))
    if not a:
        raise ApiError("测评不存在", 404)
    counts = _question_counts(a["id"])
    if counts["pending"]:
        raise ApiError("还有 %d 道候选题未审核，请先审核完再发布" % counts["pending"])
    if not counts["approved"]:
        raise ApiError("没有审核通过的题目，无法发布")
    db.x("UPDATE assessments SET status='published', published_at=? WHERE id=?",
         (db.now(), a["id"]))
    db.log(u, "publish_assessment", "assessments", a["id"], counts)
    return {"assessment": _assessment_row(a["id"])}


@route("POST", r"/api/assessments/(\d+)/close")
def api_close(ctx, aid):
    u = need(ctx["user"], "teacher")
    db.x("UPDATE assessments SET status='closed' WHERE id=?", (int(aid),))
    db.log(u, "close_assessment", "assessments", int(aid))
    return {"ok": True}


@route("GET", r"/api/student/assessments")
def api_student_assessments(ctx):
    u = need(ctx["user"], "student")
    rows = db.q("""SELECT a.*, c.title AS code_title, c.language, u.name AS student_name,
                          t.id AS attempt_id, t.status AS attempt_status, t.score,
                          t.max_score, t.submitted_at
                   FROM assessments a JOIN codes c ON c.id=a.code_id
                   JOIN users u ON u.id=c.student_id
                   LEFT JOIN attempts t ON t.assessment_id=a.id AND t.student_id=?
                   WHERE a.status IN ('published','closed') AND c.student_id=?
                   ORDER BY a.id DESC""", (u["id"], u["id"]))
    return {"assessments": rows}


@route("POST", r"/api/assessments/(\d+)/attempts")
def api_start_attempt(ctx, aid):
    u = need(ctx["user"], "student")
    a = _assessment_row(int(aid))
    if not a:
        raise ApiError("测评不存在", 404)
    if a["status"] != "published":
        raise ApiError("该测评尚未发布或已关闭")
    if a["student_id"] != u["id"]:
        raise ApiError("该测评针对其他同学提交的代码，不能作答", 403)
    exist = db.q1("SELECT * FROM attempts WHERE assessment_id=? AND student_id=?",
                  (a["id"], u["id"]))
    if exist:
        if exist["status"] == "in_progress":
            return {"attempt": exist}
        raise ApiError("你已经提交过该测评，不能重复作答")
    total = db.q1("SELECT COALESCE(SUM(points),0) AS s FROM questions"
                  " WHERE assessment_id=? AND status='approved'", (a["id"],))["s"]
    tid = db.x("INSERT INTO attempts(assessment_id,student_id,started_at,status,max_score)"
               " VALUES(?,?,?,?,?)", (a["id"], u["id"], db.now(), "in_progress", total))
    db.log(u, "start_attempt", "attempts", tid)
    return {"attempt": db.q1("SELECT * FROM attempts WHERE id=?", (tid,))}


@route("GET", r"/api/attempts/(\d+)")
def api_attempt(ctx, tid):
    u = need(ctx["user"])
    t = db.q1("""SELECT t.*, a.title, a.time_limit, a.code_id, a.status AS assessment_status,
                        c.source, c.language, c.title AS code_title, us.name AS student_name
                 FROM attempts t JOIN assessments a ON a.id=t.assessment_id
                 JOIN codes c ON c.id=a.code_id JOIN users us ON us.id=t.student_id
                 WHERE t.id=?""", (int(tid),))
    if not t:
        raise ApiError("作答记录不存在", 404)
    if u["role"] == "student" and t["student_id"] != u["id"]:
        raise ApiError("无权查看", 403)
    qs = db.q("SELECT * FROM questions WHERE assessment_id=? AND status='approved' ORDER BY seq",
              (t["assessment_id"],))
    answers = {a["question_id"]: a for a in
               db.q("SELECT * FROM answers WHERE attempt_id=?", (t["id"],))}
    show_answer = t["status"] in ("scored", "reviewed") or u["role"] == "teacher"
    out = []
    for q in qs:
        item = {
            "id": q["id"], "seq": q["seq"], "type": q["type"], "difficulty": q["difficulty"],
            "stem": q["stem"], "code_ref": q["code_ref"], "points": q["points"],
            "options": scoring.load_options(q["options"]),
        }
        if show_answer:
            item["answer"] = q["answer"]
            item["rubric"] = scoring.load_rubric(q["rubric"])
        if q["id"] in answers:
            a = answers[q["id"]]
            item["response"] = a["response"]
            item["auto_score"] = a["auto_score"]
            item["ai_score"] = a["ai_score"]
            item["final_score"] = a["final_score"]
            item["feedback"] = a["feedback"]
        out.append(item)
    t.pop("source", None)
    src = db.q1("SELECT source FROM codes WHERE id=?", (t["code_id"],))["source"]
    return {"attempt": t, "questions": out, "code": {"title": t.get("code_title"),
                                                     "language": t.get("language"),
                                                     "source": src}}


@route("POST", r"/api/attempts/(\d+)/submit")
def api_submit(ctx, tid):
    u = need(ctx["user"], "student")
    t = db.q1("SELECT * FROM attempts WHERE id=?", (int(tid),))
    if not t:
        raise ApiError("作答记录不存在", 404)
    if t["student_id"] != u["id"]:
        raise ApiError("无权提交", 403)
    if t["status"] != "in_progress":
        raise ApiError("该测评已提交")
    answers = ctx["body"].get("answers") or []
    qs = {q["id"]: q for q in db.q(
        "SELECT * FROM questions WHERE assessment_id=? AND status='approved'", (t["assessment_id"],))}
    by_q = {}
    for a in answers:
        try:
            by_q[int(a.get("question_id"))] = (a.get("response") or "").strip()
        except Exception:
            continue
    total, mx = 0.0, 0.0
    for qid, q in qs.items():
        resp = by_q.get(qid, "")
        ev = scoring.evaluate_answer(q, resp)
        db.x("""INSERT INTO answers(attempt_id,question_id,response,auto_score,ai_score,
                final_score,feedback,point_hits) VALUES(?,?,?,?,?,?,?,?)""",
             (t["id"], qid, resp, ev["score"], ev["score"], ev["score"],
              ev["feedback"], json.dumps(ev["hits"], ensure_ascii=False)))
        total += ev["score"]
        mx += float(q["points"])
    db.x("UPDATE attempts SET submitted_at=?,status='scored',score=?,max_score=? WHERE id=?",
         (db.now(), round(total, 2), round(mx, 2), t["id"]))
    db.log(u, "submit_attempt", "attempts", t["id"], {"score": round(total, 2)})
    return {"attempt": db.q1("SELECT * FROM attempts WHERE id=?", (t["id"],))}


@route("POST", r"/api/attempts/(\d+)/review")
def api_review_attempt(ctx, tid):
    u = need(ctx["user"], "teacher")
    t = db.q1("SELECT * FROM attempts WHERE id=?", (int(tid),))
    if not t:
        raise ApiError("作答记录不存在", 404)
    adjustments = ctx["body"].get("adjust") or []
    for adj in adjustments:
        try:
            qid = int(adj["question_id"])
            fs = float(adj.get("final_score"))
        except Exception:
            continue
        q = db.q1("SELECT points FROM questions WHERE id=?", (qid,))
        if not q:
            continue
        fs = max(0.0, min(float(q["points"]), fs))
        db.x("UPDATE answers SET final_score=?, feedback=? WHERE attempt_id=? AND question_id=?",
             (fs, adj.get("comment") or db.q1(
                 "SELECT feedback FROM answers WHERE attempt_id=? AND question_id=?",
                 (t["id"], qid))["feedback"], t["id"], qid))
    total = db.q1("SELECT COALESCE(SUM(final_score),0) AS s FROM answers WHERE attempt_id=?",
                  (t["id"],))["s"]
    db.x("UPDATE attempts SET status='reviewed', score=?, reviewed_by=?, reviewed_at=? WHERE id=?",
         (round(total, 2), u["id"], db.now(), t["id"]))
    db.log(u, "review_attempt", "attempts", t["id"], {"score": round(total, 2)})
    return {"attempt": db.q1("SELECT * FROM attempts WHERE id=?", (t["id"],))}


@route("GET", r"/api/attempts")
def api_attempts(ctx):
    u = need(ctx["user"], "teacher")
    rows = db.q("""SELECT t.*, a.title, u.name AS student_name, c.title AS code_title
                   FROM attempts t JOIN assessments a ON a.id=t.assessment_id
                   JOIN users u ON u.id=t.student_id JOIN codes c ON c.id=a.code_id
                   ORDER BY t.id DESC""")
    return {"attempts": rows}


@route("GET", r"/api/stats/overview")
def api_overview(ctx):
    u = need(ctx["user"])
    if u["role"] == "teacher":
        d = {
            "codes": db.q1("SELECT COUNT(1) AS n FROM codes")["n"],
            "students": db.q1("SELECT COUNT(1) AS n FROM users WHERE role='student'")["n"],
            "assessments": db.q1("SELECT COUNT(1) AS n FROM assessments")["n"],
            "pending": db.q1("SELECT COUNT(1) AS n FROM questions WHERE status='pending'")["n"],
            "attempts": db.q1("SELECT COUNT(1) AS n FROM attempts WHERE status<>'in_progress'")["n"],
            "avg": db.q1("SELECT COALESCE(AVG(score*100.0/NULLIF(max_score,0)),0) AS v"
                         " FROM attempts WHERE status IN ('scored','reviewed')")["v"],
        }
    else:
        d = {
            "codes": db.q1("SELECT COUNT(1) AS n FROM codes WHERE student_id=?", (u["id"],))["n"],
            "attempts": db.q1("SELECT COUNT(1) AS n FROM attempts WHERE student_id=? AND status<>'in_progress'",
                              (u["id"],))["n"],
            "avg": db.q1("SELECT COALESCE(AVG(score*100.0/NULLIF(max_score,0)),0) AS v FROM attempts"
                         " WHERE student_id=? AND status IN ('scored','reviewed')", (u["id"],))["v"],
        }
    return {"overview": d, "llm": llm.status()}


@route("GET", r"/api/stats/class")
def api_class_stats(ctx):
    u = need(ctx["user"])
    where, params = "", ()
    if u["role"] == "student":
        where, params = " AND t.student_id=?", (u["id"],)
    type_rows = db.q("""SELECT q.type, AVG(ans.final_score*1.0/NULLIF(q.points,0)) AS ratio,
                               COUNT(1) AS n
                        FROM answers ans JOIN questions q ON q.id=ans.question_id
                        JOIN attempts t ON t.id=ans.attempt_id
                        WHERE t.status IN ('scored','reviewed')""" + where + " GROUP BY q.type",
                     params)
    kp_rows = db.q("""SELECT c.knowledge_points AS kp, AVG(t.score*100.0/NULLIF(t.max_score,0)) AS score,
                             COUNT(1) AS n
                      FROM attempts t JOIN assessments a ON a.id=t.assessment_id
                      JOIN codes c ON c.id=a.code_id
                      WHERE t.status IN ('scored','reviewed') AND c.knowledge_points<>''
                      GROUP BY c.knowledge_points ORDER BY score DESC""")
    stu_rows = db.q("""SELECT u.name, u.class_name, AVG(t.score*100.0/NULLIF(t.max_score,0)) AS score,
                              COUNT(1) AS n
                       FROM attempts t JOIN users u ON u.id=t.student_id
                       WHERE t.status IN ('scored','reviewed')
                       GROUP BY u.id ORDER BY score DESC""")
    return {"by_type": type_rows, "by_kp": kp_rows, "by_student": stu_rows}


@route("GET", r"/api/report/(\d+)")
def api_report(ctx, tid):
    u = need(ctx["user"])
    t = db.q1("""SELECT t.*, u.name AS student_name, a.title FROM attempts t
                 JOIN users u ON u.id=t.student_id JOIN assessments a ON a.id=t.assessment_id
                 WHERE t.id=?""", (int(tid),))
    if not t:
        raise ApiError("记录不存在", 404)
    if u["role"] == "student" and t["student_id"] != u["id"]:
        raise ApiError("无权查看", 403)
    rows = db.q("""SELECT q.seq,q.type,q.stem,q.points,q.answer,q.options,ans.response,
                          ans.final_score,ans.feedback
                   FROM answers ans JOIN questions q ON q.id=ans.question_id
                   WHERE ans.attempt_id=? ORDER BY q.seq""", (t["id"],))
    by_type = {}
    for r in rows:
        d = by_type.setdefault(r["type"], {"got": 0.0, "max": 0.0, "n": 0})
        d["got"] += r["final_score"] or 0
        d["max"] += r["points"]
        d["n"] += 1
    for k, v in by_type.items():
        v["ratio"] = round(v["got"] / v["max"], 3) if v["max"] else 0
    return {"attempt": t, "questions": rows, "by_type": by_type}


@route("GET", r"/api/audit")
def api_audit(ctx):
    need(ctx["user"], "teacher")
    return {"audit": db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 50")}


@route("GET", r"/api/health")
def api_health(ctx):
    return {"app": APP_NAME, "ok": True}


class Handler(BaseHTTPRequestHandler):
    server_version = "CodeAssess/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", cookie=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _json(self, obj, code=200, cookie=None):
        self._send(code, json.dumps(obj, ensure_ascii=False), cookie=cookie)

    def _session_user(self):
        raw = self.headers.get("Cookie") or ""
        m = re.search(r"sid=([\w\-]+)", raw)
        if not m:
            return None, None
        uid = SESSIONS.get(m.group(1))
        if not uid:
            return None, m.group(1)
        return db.q1("SELECT * FROM users WHERE id=?", (uid,)), m.group(1)

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            return self._static(path)
        body = {}
        if method in ("POST", "PATCH", "PUT"):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b"{}"
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                body = {}
        user, sid = self._session_user()
        ctx = {"user": user, "sid": sid, "body": body,
               "query": parse_qs(parsed.query), "path": path}
        for m, pattern, fn in ROUTES:
            if m != method:
                continue
            match = pattern.match(path)
            if not match:
                continue
            try:
                data = fn(ctx, *match.groups())
                cookie = None
                if isinstance(data, dict) and "_cookie" in data:
                    cid = data.pop("_cookie")
                    cookie = "sid=%s; Path=/; HttpOnly; SameSite=Lax" % cid
                self._json({"ok": True, "data": data}, 200, cookie=cookie)
                return
            except ApiError as e:
                self._json({"ok": False, "error": e.msg}, e.code)
                return
            except Exception as e:
                traceback.print_exc()
                self._json({"ok": False, "error": "服务器内部错误：%s" % e}, 500)
                return
        self._json({"ok": False, "error": "接口不存在"}, 404)

    def _static(self, path):
        if path in ("/", "/index.html"):
            f = STATIC_DIR / "index.html"
        else:
            rel = path.lstrip("/")
            if rel.startswith("static/"):
                rel = rel[len("static/"):]
            f = (STATIC_DIR / rel).resolve()
            if not str(f).startswith(str(STATIC_DIR.resolve())):
                return self._send(403, b"forbidden", "text/plain; charset=utf-8")
        if not f.exists() or not f.is_file():
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if f.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif f.suffix in (".css",):
            ctype = "text/css; charset=utf-8"
        elif f.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def do_GET(self):
        try:
            self._dispatch("GET")
        except ApiError as e:
            self._json({"ok": False, "error": e.msg}, e.code)

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")


def create_server(host="127.0.0.1", port=8765):
    db.init_db()
    db.seed()
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd


def serve(host="127.0.0.1", port=8765):
    httpd = create_server(host, port)
    print("代码理解测评系统已启动： http://%s:%d" % (host, port))
    if not llm.available():
        print("提示：未配置大模型 API，当前使用本地规则引擎出题/评分（离线模式）。")
    else:
        print("大模型接口：%s (%s)" % (llm.status()["base_url"], llm.status()["model"]))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    port = 8765
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    serve(port=port)