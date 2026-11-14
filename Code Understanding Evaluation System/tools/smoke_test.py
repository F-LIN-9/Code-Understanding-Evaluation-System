# -*- coding: utf-8 -*-
"""端到端冒烟测试：模拟"提交代码 → 生成题目 → 教师审核 → 发布 → 学生作答
→ 评分 → 教师复核 → 统计"的完整流程，全部通过 HTTP 接口完成。

用法：先启动 run.py，再执行
    python tools/smoke_test.py [http://127.0.0.1:8765]
"""
import json
import sys
import urllib.error
import urllib.request
import http.cookiejar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"

CODE = '''def second_largest(nums):
    if len(nums) < 2:
        return None
    first = max(nums)
    result = None
    for x in nums:
        if x < first and (result is None or x > result):
            result = x
    return result


print(second_largest([5, 3, 9, 9, 2]))
'''


class Client:
    def __init__(self, name):
        self.name = name
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, path, method="GET", body=None):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=30) as r:
                payload = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            payload = json.loads(e.read().decode("utf-8"))
        if not payload.get("ok"):
            raise AssertionError("%s %s 失败: %s" % (method, path, payload.get("error")))
        return payload["data"]


def check(cond, msg):
    print(("  [OK] " if cond else "  [FAIL] ") + msg)
    if not cond:
        raise SystemExit(1)


def main():
    print("== 1. 健康检查与登录")
    health = Client("anon").call("/api/health")
    check(health["ok"] is True, "服务可用：%s" % health["app"])

    teacher = Client("teacher")
    tu = teacher.call("/api/login", "POST", {"username": "liyuejun"})["user"]
    check(tu["role"] == "teacher", "教师登录：%s" % tu["name"])

    student = Client("student")
    su = student.call("/api/login", "POST", {"username": "2023002"})["user"]
    check(su["role"] == "student", "学生登录：%s" % su["name"])

    print("== 2. 学生提交代码")
    code = student.call("/api/codes", "POST", {
        "title": "求列表中第二大的数",
        "course": "数据结构与算法",
        "language": "python",
        "knowledge_points": "循环, 边界条件, 列表操作",
        "source": CODE,
    })["code"]
    check(code["id"] > 0, "代码已入库 id=%d" % code["id"])

    print("== 3. 生成测评题（规则引擎/大模型）")
    gen = student.call("/api/codes/%d/assessments" % code["id"], "POST",
                       {"mode": "class", "time_limit": 15})
    check(gen["question_count"] >= 4, "生成 %d 道候选题（%s）"
          % (gen["question_count"], gen["generator"]))
    aid = gen["assessment_id"]

    print("== 4. 教师审核")
    detail = teacher.call("/api/assessments/%d" % aid)
    qs = detail["questions"]
    check(len(qs) == gen["question_count"], "候选题数量一致")
    check(all(q["status"] == "pending" for q in qs), "候选题初始为待审核")
    pending = [q for q in qs]
    # 第一题修改后通过，其余直接通过
    first = pending[0]
    teacher.call("/api/questions/%d" % first["id"], "PATCH", {
        "action": "edit", "stem": first["stem"], "points": first["points"],
        "difficulty": first["difficulty"], "note": "教师核对后微调",
        "options": json.loads(first["options"]) if first["options"] else None,
        "answer": first["answer"],
    } if first["options"] else {
        "action": "edit", "stem": first["stem"], "points": first["points"],
        "difficulty": first["difficulty"], "answer": first["answer"],
        "note": "教师核对后微调",
    })
    for q in pending[1:]:
        teacher.call("/api/questions/%d" % q["id"], "PATCH", {"action": "approve"})
    after = teacher.call("/api/assessments/%d" % aid)
    check(after["assessment"]["counts"]["pending"] == 0, "全部候选题已审核")

    print("== 5. 发布测评")
    pub = teacher.call("/api/assessments/%d/publish" % aid, "POST", {})
    check(pub["assessment"]["status"] == "published", "测评已发布")

    print("== 6. 学生作答")
    tasks = student.call("/api/student/assessments")["assessments"]
    check(any(t["id"] == aid for t in tasks), "学生可以看到已发布测评")
    attempt = student.call("/api/assessments/%d/attempts" % aid, "POST", {})["attempt"]
    view = student.call("/api/attempts/%d" % attempt["id"])
    check(len(view["questions"]) >= 4, "作答页返回 %d 道题" % len(view["questions"]))
    check("answer" not in view["questions"][0], "作答页不泄露参考答案")
    answers = []
    for q in view["questions"]:
        if q["options"]:
            answers.append({"question_id": q["id"], "response": q["options"][0]["key"]})
        else:
            answers.append({"question_id": q["id"],
                            "response": "先判断输入是否为空，长度小于 2 直接返回 None；"
                                        "再用循环遍历列表比较大小，最后返回结果。"})
    res = student.call("/api/attempts/%d/submit" % attempt["id"], "POST", {"answers": answers})
    check(res["attempt"]["status"] == "scored", "交卷后自动评分")
    check(res["attempt"]["max_score"] > 0, "满分 %.0f 分，得分 %.1f"
          % (res["attempt"]["max_score"], res["attempt"]["score"]))

    print("== 7. 分项报告与统计")
    rep = student.call("/api/report/%d" % attempt["id"])
    check(len(rep["questions"]) == len(view["questions"]), "报告包含全部题目")
    check(len(rep["by_type"]) >= 2, "按任务类型分项统计：%s" % list(rep["by_type"].keys()))
    cls = teacher.call("/api/stats/class")
    check(len(cls["by_type"]) >= 1, "班级统计可用")
    ov = teacher.call("/api/stats/overview")["overview"]
    check(ov["codes"] > 0 and ov["assessments"] > 0, "总览数据：代码 %d / 测评 %d"
          % (ov["codes"], ov["assessments"]))

    print("== 8. 教师复核")
    attempts = teacher.call("/api/attempts")["attempts"]
    target = [a for a in attempts if a["id"] == attempt["id"]][0]
    qlist = teacher.call("/api/attempts/%d" % attempt["id"])["questions"]
    adjust = [{"question_id": q["id"], "final_score": q["points"]} for q in qlist]
    rev = teacher.call("/api/attempts/%d/review" % attempt["id"], "POST", {"adjust": adjust})
    check(rev["attempt"]["status"] == "reviewed", "复核后状态为已复核")
    check(abs(rev["attempt"]["score"] - target["max_score"]) < 0.01, "复核总分已按满分重算")

    print("== 9. 权限校验")
    try:
        student.call("/api/questions/%d" % qs[0]["id"], "PATCH", {"action": "approve"})
        check(False, "学生不应能审核题目")
    except AssertionError as e:
        check("没有权限" in str(e), "学生审核被拒绝（%s）" % str(e)[-30:])

    print("\n全部通过：端到端流程正常。")


if __name__ == "__main__":
    main()
