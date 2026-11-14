# -*- coding: utf-8 -*-
"""SQLite 数据访问层：建表、查询助手、审计日志。"""
import json
import sqlite3
import threading
import time
from datetime import datetime

from .config import DB_PATH

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('student', 'teacher')),
    class_name  TEXT DEFAULT '',
    student_no  TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES users(id),
    course      TEXT NOT NULL,
    title       TEXT NOT NULL,
    language    TEXT NOT NULL DEFAULT 'python',
    source      TEXT NOT NULL,
    knowledge_points TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code_id     INTEGER NOT NULL REFERENCES codes(id),
    title       TEXT NOT NULL,
    mode        TEXT NOT NULL DEFAULT 'class'   CHECK (mode IN ('class', 'self')),
    time_limit  INTEGER NOT NULL DEFAULT 20,
    status      TEXT NOT NULL DEFAULT 'reviewing'
                CHECK (status IN ('reviewing', 'published', 'closed')),
    generator   TEXT DEFAULT 'rule',
    model       TEXT DEFAULT '',
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL,
    published_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('explain','trace','diagnose','modify')),
    difficulty  TEXT NOT NULL DEFAULT '中',
    stem        TEXT NOT NULL,
    code_ref    TEXT DEFAULT '',
    options     TEXT DEFAULT '',
    answer      TEXT DEFAULT '',
    rubric      TEXT DEFAULT '',
    points      REAL NOT NULL DEFAULT 10,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected')),
    review_note TEXT DEFAULT '',
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TEXT DEFAULT '',
    source      TEXT DEFAULT 'rule',
    model       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id),
    student_id  INTEGER NOT NULL REFERENCES users(id),
    started_at  TEXT NOT NULL,
    submitted_at TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'in_progress'
                CHECK (status IN ('in_progress','submitted','scored','reviewed')),
    score       REAL DEFAULT 0,
    max_score   REAL DEFAULT 0,
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS answers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    response    TEXT DEFAULT '',
    auto_score  REAL DEFAULT 0,
    ai_score    REAL DEFAULT 0,
    final_score REAL DEFAULT 0,
    feedback    TEXT DEFAULT '',
    point_hits  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    actor_id    INTEGER,
    actor_name  TEXT DEFAULT '',
    action      TEXT NOT NULL,
    entity      TEXT DEFAULT '',
    entity_id   INTEGER,
    detail      TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_q_assessment ON questions(assessment_id);
CREATE INDEX IF NOT EXISTS idx_a_assessment ON answers(attempt_id);
CREATE INDEX IF NOT EXISTS idx_att_assessment ON attempts(assessment_id);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conn():
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(str(DB_PATH), timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn = c
    return c


def init_db():
    c = sqlite3.connect(str(DB_PATH), timeout=15)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.commit()
    c.close()


def q(sql, params=()):
    rows = conn().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def q1(sql, params=()):
    r = conn().execute(sql, params).fetchone()
    return dict(r) if r else None


def x(sql, params=()):
    c = conn()
    cur = c.execute(sql, params)
    c.commit()
    return cur.lastrowid


def log(actor, action, entity="", entity_id=None, detail=""):
    actor_id = actor.get("id") if actor else None
    actor_name = actor.get("name") if actor else "system"
    x("INSERT INTO audit(ts, actor_id, actor_name, action, entity, entity_id, detail)"
      " VALUES(?,?,?,?,?,?,?)",
      (now(), actor_id, actor_name, action, entity, entity_id,
       detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)))


def seed():
    """初始化演示数据：教师、学生、示例代码。重复执行不会重复插入。"""
    if q1("SELECT id FROM users LIMIT 1"):
        return
    t = now()
    teacher_id = x(
        "INSERT INTO users(username,name,role,class_name,student_no,created_at)"
        " VALUES(?,?,?,?,?,?)",
        ("liyuejun", "李跃军", "teacher", "计算机与人工智能学院", "", t))
    students = [
        ("2023001", "张明", "软件工程2023级1班", "2023001"),
        ("2023002", "李婷", "软件工程2023级1班", "2023002"),
        ("2023003", "王浩", "软件工程2023级2班", "2023003"),
        ("2023004", "陈雨", "软件工程2023级2班", "2023004"),
    ]
    for u, n, cls, no in students:
        x("INSERT INTO users(username,name,role,class_name,student_no,created_at)"
          " VALUES(?,?,?,?,?,?)", (u, n, "student", cls, no, t))
    log(None, "seed", "db", None, "初始化演示用户")