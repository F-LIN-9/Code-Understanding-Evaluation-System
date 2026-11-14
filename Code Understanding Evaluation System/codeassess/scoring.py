# -*- coding: utf-8 -*-
"""评分：客观题精确判分；开放题按评分要点关键词匹配或由大模型初评。

评分结果只是"建议分"，教师复核后才是最终成绩。
"""
import json
import re
import unicodedata

from . import llm

PUNCT = set(" \t\r\n，。；：、！？（）()[]【】""''《》,.;:!?<>+-_=/\\|`~@#$%^&*")


def norm(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    return "".join(ch for ch in text if ch not in PUNCT)


def load_options(raw):
    try:
        v = json.loads(raw) if raw else []
        return v if isinstance(v, list) else []
    except Exception:
        return []


def load_rubric(raw):
    try:
        v = json.loads(raw) if raw else []
        return v if isinstance(v, list) else []
    except Exception:
        return []


def score_choice(question, response):
    """选择题：返回 (ratio, feedback, hits)。"""
    options = load_options(question.get("options"))
    if not options:
        return 0.0, "无选项", []
    ans = (question.get("answer") or "").strip()
    resp = (response or "").strip()
    picked = ""
    if resp.upper() in [o["key"] for o in options]:
        picked = resp.upper()
    else:
        for o in options:
            if norm(o["text"]) == norm(resp):
                picked = o["key"]
                break
        if not picked and len(resp) == 1 and resp.isalpha():
            picked = resp.upper()
    if not picked:
        return 0.0, "未作答或答案无法识别", []
    if picked == ans:
        text = next((o["text"] for o in options if o["key"] == ans), ans)
        return 1.0, "正确，参考答案：%s" % text, [ans]
    correct_text = next((o["text"] for o in options if o["key"] == ans), ans)
    return 0.0, "错误，参考答案是 %s：%s" % (ans, correct_text), []


def score_rubric(question, response):
    """按评分要点做关键词覆盖，返回 (ratio, feedback, hits)。"""
    rubric = load_rubric(question.get("rubric"))
    text = norm(response)
    if len(text) < 6:
        return 0.0, "作答过短，未能覆盖评分要点。", []
    if not rubric:
        return min(1.0, len(text) / 120.0), "缺少评分要点，按作答完整度给分。", []
    total = sum(float(p.get("weight", 1)) or 1 for p in rubric) or 1
    got = 0.0
    hits, misses = [], []
    for p in rubric:
        kws = [norm(k) for k in (p.get("keywords") or []) if norm(k)]
        hit = any(k in text for k in kws)
        w = float(p.get("weight", 1)) or 1
        if hit:
            got += w
            hits.append(p.get("point", ""))
        else:
            misses.append(p.get("point", ""))
    ratio = got / total
    if len(text) < 20:
        ratio = min(ratio, 0.35)
    fb = []
    if hits:
        fb.append("已覆盖：" + "；".join(h for h in hits if h))
    if misses:
        fb.append("未涉及：" + "；".join(m for m in misses if m))
    return round(ratio, 3), "；".join(fb) or "未匹配到评分要点。", hits


PROMPT = """你是一名计算机课程助教，请依据评分要点给学生的作答打分。

题目：{stem}
代码位置：{ref}
评分要点（JSON）：{rubric}
参考答案：{answer}
学生作答：{response}

要求：只输出 JSON，格式为
{{"score_ratio": 0~1 的小数, "hits": ["命中的要点"], "feedback": "给学生的具体反馈（不超过80字）"}}
评分要客观，只按要点覆盖情况给分，不因文采加分。"""


def score_open(question, response, use_llm=True, points=None):
    """开放题：优先大模型，失败退回关键词规则。"""
    rule_ratio, rule_fb, rule_hits = score_rubric(question, response)
    if use_llm and llm.available() and (response or "").strip():
        data = llm.chat_json([
            {"role": "system", "content": "你只输出 JSON。"},
            {"role": "user", "content": PROMPT.format(
                stem=question.get("stem", ""),
                ref=question.get("code_ref", ""),
                rubric=question.get("rubric", "[]"),
                answer=(question.get("answer") or "")[:200],
                response=(response or "")[:1000])},
        ], temperature=0)
        if data and isinstance(data.get("score_ratio"), (int, float)):
            ratio = max(0.0, min(1.0, float(data["score_ratio"])))
            fb = str(data.get("feedback") or rule_fb)[:200]
            hits = data.get("hits") or rule_hits
            return round(ratio, 3), fb, hits
    return rule_ratio, rule_fb, rule_hits


def evaluate_answer(question, response, use_llm=True):
    """单题评分：返回 dict(auto_score=得分, ratio, feedback, hits)。"""
    points = float(question.get("points") or 0)
    if question.get("options"):
        ratio, fb, hits = score_choice(question, response)
    else:
        ratio, fb, hits = score_open(question, response, use_llm=use_llm)
    return {
        "ratio": ratio,
        "score": round(points * ratio, 2),
        "feedback": fb,
        "hits": hits,
    }