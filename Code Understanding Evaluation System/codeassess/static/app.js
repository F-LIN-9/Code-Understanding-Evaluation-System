/* 代码理解测评系统 · 前端（原生 JS，无构建依赖） */
const TYPE_LABEL = { explain: "代码解释", trace: "执行过程", diagnose: "错误诊断", modify: "局部修改" };
const TYPE_COLOR = { explain: "blue", trace: "green", diagnose: "amber", modify: "red" };
const DIFF_COLOR = { "易": "green", "中": "amber", "难": "red" };
const STATUS_LABEL = { reviewing: "待审核", published: "已发布", closed: "已关闭" };
const STATUS_COLOR = { reviewing: "amber", published: "green", closed: "gray" };
const ATT_LABEL = { in_progress: "作答中", submitted: "已提交", scored: "已评分", reviewed: "已复核" };
const ATT_COLOR = { in_progress: "blue", submitted: "blue", scored: "amber", reviewed: "green" };

const state = { user: null, view: { name: "login" }, ov: null, cache: {} };
const $app = document.getElementById("app");

/* ---------------------------------------------------------------- 工具 */
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;");

function toast(msg, bad) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = "toast"; }, 2600);
}

async function api(path, method = "GET", body = null) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const res = await fetch(path, opt);
  let data = {};
  try { data = await res.json(); } catch (e) { data = { ok: false, error: "响应解析失败" }; }
  if (!res.ok || data.ok === false) throw new Error(data.error || ("请求失败 " + res.status));
  return data.data;
}

function go(name, params = {}) {
  state.view = Object.assign({ name }, params);
  render().then(() => window.scrollTo({ top: 0, behavior: "smooth" }));
}

function codeHTML(src) {
  const lines = String(src || "").replace(/\r\n/g, "\n").split("\n");
  return "<pre class='code'>" + lines.map((l, i) =>
    "<span class='ln'>" + String(i + 1).padStart(3, " ") + "</span>  " + esc(l)
  ).join("\n") + "</pre>";
}

function bar(ratio, cls) {
  const pct = Math.max(0, Math.min(100, (ratio || 0) * 100));
  return `<div class="bar ${cls || ""}"><i style="width:${pct.toFixed(1)}%"></i></div>`;
}

/* ---------------------------------------------------------------- 外壳 */
function tabsHTML(active) {
  const isT = state.user.role === "teacher";
  const items = isT
    ? [["t_overview", "总览", 0], ["t_review", "题目审核", (state.ov && state.ov.pending) || 0],
       ["t_assess", "测评管理", 0], ["t_attempts", "成绩复核", 0], ["t_stats", "统计", 0]]
    : [["s_codes", "我的代码", 0], ["s_tasks", "待测测评", 0], ["s_report_list", "我的成绩", 0]];
  return `<div class="tabs">` + items.map(([k, label, n]) =>
    `<div class="tab ${active === k ? "active" : ""}" data-act="go" data-view="${k}">${label}` +
    (n ? `<span class="n">${n}</span>` : "") + `</div>`
  ).join("") + `</div>`;
}

async function refreshOverview() {
  try { state.ov = (await api("/api/stats/overview")).overview; } catch (e) { state.ov = null; }
}

async function render() {
  const v = state.view;
  if (!state.user) {
    document.getElementById("who").innerHTML = "";
    document.getElementById("logout").style.display = "none";
    return renderLogin();
  }
  document.getElementById("who").innerHTML =
    `<b>${esc(state.user.name)}</b> · ${state.user.role === "teacher" ? "教师" : "学生"} · ${esc(state.user.class_name || "")}`;
  document.getElementById("logout").style.display = "inline-block";
  await refreshOverview();

  const map = {
    t_overview: viewOverview, t_review: viewReviewList, t_review_one: viewReviewOne,
    t_assess: viewAssessments, t_attempts: viewAttemptList, t_attempt: viewAttemptReview,
    t_stats: viewStats,
    s_codes: viewMyCodes, s_tasks: viewMyTasks, s_attempt: viewDoAttempt,
    s_report_list: viewMyReports, s_report: viewReport
  };
  const fn = map[v.name] || (state.user.role === "teacher" ? viewOverview : viewMyCodes);
  try {
    await fn(v);
  } catch (e) {
    $app.innerHTML = tabsHTML(v.name) + `<div class="card"><b>出错了：</b>${esc(e.message)}</div>`;
  }
}

/* ---------------------------------------------------------------- 登录 */
function renderLogin() {
  $app.innerHTML = `
  <div class="login-wrap">
    <div class="card">
      <h1>代码理解测评系统</h1>
      <p class="muted small">以学生本人提交的代码为对象生成测评题——代码解释、执行过程、错误诊断、局部修改；
      经教师审核后组织作答，并按评分要点给出分项反馈。</p>
      <form id="login-form" class="mt">
        <label class="field"><span>账号</span>
          <input type="text" id="login-name" placeholder="请输入账号，如 2023001" autocomplete="off"></label>
        <button class="btn primary" type="submit" style="width:100%">登录</button>
      </form>
      <div class="demo">
        <button class="btn sm" data-act="quick-login" data-user="liyuejun">教师演示 · 李跃军</button>
        <button class="btn sm" data-act="quick-login" data-user="2023001">学生演示 · 张明</button>
        <button class="btn sm" data-act="quick-login" data-user="2023002">学生演示 · 李婷</button>
      </div>
      <p class="small muted mt">演示账号：教师 liyuejun；学生 2023001—2023004。系统为开放实验项目原型，账号无需密码。</p>
    </div>
  </div>`;
  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    await doLogin(document.getElementById("login-name").value.trim());
  });
}

async function doLogin(username) {
  try {
    const d = await api("/api/login", "POST", { username });
    state.user = d.user;
    toast("欢迎，" + d.user.name);
    go(d.user.role === "teacher" ? "t_overview" : "s_codes");
  } catch (e) { toast(e.message, true); }
}

/* ---------------------------------------------------------------- 教师：总览 */
async function viewOverview() {
  const [ov, list, audit] = await Promise.all([
    api("/api/stats/overview"), api("/api/assessments"), api("/api/audit").catch(() => ({ audit: [] })),
  ]);
  state.ov = ov.overview;
  const o = ov.overview;
  const reviewing = list.assessments.filter((a) => a.status === "reviewing");
  const llmTag = ov.llm.enabled
    ? `<span class="badge green">大模型已接入 · ${esc(ov.llm.model)}</span>`
    : `<span class="badge amber">离线规则模式（未配置 API，可在 data/config.json 配置）</span>`;
  $app.innerHTML = tabsHTML("t_overview") + `
    <div class="card"><h3>运行状态 ${llmTag}</h3>
      <div class="grid c4">
        <div class="stat"><div class="k">学生代码提交</div><div class="v">${o.codes}</div></div>
        <div class="stat"><div class="k">参与学生</div><div class="v">${o.students}</div></div>
        <div class="stat"><div class="k">测评任务</div><div class="v">${o.assessments}</div></div>
        <div class="stat"><div class="k">待审核题目</div><div class="v">${o.pending}<small> 道</small></div></div>
        <div class="stat"><div class="k">已提交作答</div><div class="v">${o.attempts}<small> 份</small></div></div>
        <div class="stat"><div class="k">平均得分率</div><div class="v">${(o.avg || 0).toFixed(1)}<small> %</small></div></div>
      </div>
    </div>
    <div class="card"><h3>待审核的测评 <span class="sub">大模型/规则引擎只产生候选题，教师审核通过后才能发布</span></h3>
      ${reviewing.length ? `<table><thead><tr><th>测评</th><th>学生</th><th>题目</th><th>状态</th><th></th></tr></thead><tbody>
        ${reviewing.map((a) => `<tr>
          <td>${esc(a.title)}</td><td>${esc(a.student_name)}</td>
          <td class="small">待审 ${a.pending} · 通过 ${a.approved} · 删除 ${a.rejected}</td>
          <td><span class="badge amber">待审核</span></td>
          <td><button class="btn primary sm" data-act="go" data-view="t_review_one" data-id="${a.id}">进入审核</button></td>
        </tr>`).join("")}</tbody></table>` : `<div class="empty">暂无待审核的测评</div>`}
    </div>
    <div class="card"><h3>最近操作</h3>
      ${(audit.audit || []).length ? `<table><thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th></tr></thead><tbody>
        ${audit.audit.slice(0, 8).map((r) => `<tr><td class="small muted">${esc(r.ts)}</td><td>${esc(r.actor_name)}</td>
          <td class="small">${esc(r.action)}</td><td class="small muted">${esc((r.detail || "").slice(0, 60))}</td></tr>`).join("")}
      </tbody></table>` : `<div class="empty">暂无记录</div>`}
    </div>`;
}

/* ---------------------------------------------------------------- 教师：审核列表 */
async function viewReviewList() {
  const d = await api("/api/assessments");
  const list = d.assessments;
  $app.innerHTML = tabsHTML("t_review") + `
    <div class="card"><h3>测评任务列表 <span class="sub">共 ${list.length} 个</span></h3>
      ${list.length ? `<table><thead><tr><th>测评</th><th>学生</th><th>题目状态</th><th>状态</th><th>生成方式</th><th></th></tr></thead><tbody>
      ${list.map((a) => `<tr>
        <td><b>${esc(a.title)}</b><div class="small muted">${esc(a.language)} · ${a.pending + a.approved + a.rejected} 题</div></td>
        <td>${esc(a.student_name)}</td>
        <td class="small">待审 ${a.pending} · 通过 ${a.approved} · 删除 ${a.rejected}</td>
        <td><span class="badge ${STATUS_COLOR[a.status]}">${STATUS_LABEL[a.status]}</span></td>
        <td class="small muted">${a.generator === "llm" ? "大模型" : "本地规则"}</td>
        <td><button class="btn sm primary" data-act="go" data-view="t_review_one" data-id="${a.id}">审核</button></td>
      </tr>`).join("")}</tbody></table>` : `<div class="empty">暂无测评任务</div>`}
    </div>`;
}

/* ---------------------------------------------------------------- 教师：审核单题 */
async function viewReviewOne(v) {
  const d = await api("/api/assessments/" + v.id);
  const a = d.assessment, qs = d.questions;
  const canPublish = a.counts.pending === 0 && a.counts.approved > 0;
  $app.innerHTML = tabsHTML("t_review") + `
    <div class="card">
      <div class="flex" style="flex-wrap:wrap">
        <div><h3 style="margin:0">${esc(a.title)}</h3>
          <div class="small muted">学生：${esc(a.student_name)} · 语言：${esc(a.language)} · 限时 ${a.time_limit} 分钟
          · 待审 ${a.counts.pending} / 通过 ${a.counts.approved} / 删除 ${a.counts.rejected}</div></div>
        <div class="right flex">
          <button class="btn sm" data-act="go" data-view="t_review">返回列表</button>
          <button class="btn primary sm" data-act="publish" data-id="${a.id}" ${canPublish ? "" : "disabled"}>发布测评</button>
        </div>
      </div>
      ${canPublish ? "" : `<p class="small" style="color:var(--amber);margin:10px 0 0">发布条件：所有候选题都完成审核，且至少有一道通过。</p>`}
    </div>
    <div class="grid c2" style="grid-template-columns: 1fr 1fr; align-items:start">
      <div class="card"><h3>学生提交的代码 <span class="sub">${esc(a.course)} · ${esc(a.knowledge_points || "未标注知识点")}</span></h3>
        ${codeHTML(a.source)}</div>
      <div>
        ${qs.map((q) => questionReviewCard(q)).join("")}
      </div>
    </div>`;
  state.cache.assessment = a;
  state.cache.questions = qs;
}

function optionListHTML(q, showAnswer) {
  let opts = [];
  try { opts = q.options ? JSON.parse(q.options) : []; } catch (e) { opts = []; }
  if (!opts.length) return "";
  return opts.map((o) => `<div class="opt ${showAnswer && q.answer === o.key ? "correct" : ""}">
      <b>${esc(o.key)}.</b><span>${esc(o.text)}</span>
      ${showAnswer && q.answer === o.key ? `<span class="right badge green">参考答案</span>` : ""}
    </div>`).join("");
}

function rubricHTML(q) {
  let rb = [];
  try { rb = q.rubric ? JSON.parse(q.rubric) : []; } catch (e) { rb = []; }
  if (!rb.length) return "";
  return `<div class="rubric">评分要点：` + rb.map((r) =>
    `<span class="badge gray" style="margin:2px 2px">${esc(r.point)} · 权重 ${r.weight}</span>`).join("") + `</div>`;
}

function questionReviewCard(q) {
  return `<div class="q" id="qc-${q.id}">
    <div class="qhead">
      <span class="badge ${TYPE_COLOR[q.type]}">${TYPE_LABEL[q.type]}</span>
      <span class="badge ${DIFF_COLOR[q.difficulty] || "gray"}">${esc(q.difficulty)}</span>
      <span class="badge gray">${q.points} 分</span>
      <span class="badge ${q.status === "approved" ? "green" : q.status === "rejected" ? "red" : "amber"}">
        ${q.status === "approved" ? "已通过" : q.status === "rejected" ? "已删除" : "待审核"}</span>
      <span class="right small muted">${esc(q.code_ref || "")}</span>
    </div>
    <div class="stem">${esc(q.stem)}</div>
    ${optionListHTML(q, true)}
    ${q.answer && !q.options ? `<div class="small muted">参考答案：${esc(q.answer)}</div>` : ""}
    ${rubricHTML(q)}
    <div class="flex mt">
      <button class="btn ok sm" data-act="q-approve" data-id="${q.id}">通过</button>
      <button class="btn sm" data-act="q-edit" data-id="${q.id}">修改</button>
      <button class="btn danger sm" data-act="q-reject" data-id="${q.id}">删除</button>
      ${q.review_note ? `<span class="small muted right">${esc(q.review_note)}</span>` : ""}
    </div>
    <div id="edit-${q.id}"></div>
  </div>`;
}

function questionEditForm(q) {
  let opts = [];
  try { opts = q.options ? JSON.parse(q.options) : []; } catch (e) { opts = []; }
  const isChoice = opts.length > 0;
  return `<div class="editing">
    <label class="field"><span>题干</span><textarea id="e-stem-${q.id}" style="min-height:70px">${esc(q.stem)}</textarea></label>
    <div class="row">
      <label class="field"><span>难度</span><select id="e-diff-${q.id}">
        ${["易", "中", "难"].map((x) => `<option ${q.difficulty === x ? "selected" : ""}>${x}</option>`).join("")}
      </select></label>
      <label class="field"><span>分值</span><input type="number" id="e-pts-${q.id}" value="${q.points}" min="1" max="30" step="1"></label>
    </div>
    ${isChoice ? opts.map((o) => `<label class="field"><span>选项 ${o.key}</span>
        <input type="text" id="e-opt-${q.id}-${o.key}" value="${esc(o.text)}"></label>`).join("") +
      `<label class="field"><span>正确答案</span><select id="e-ans-${q.id}">
        ${opts.map((o) => `<option ${q.answer === o.key ? "selected" : ""}>${o.key}</option>`).join("")}</select></label>`
      : `<label class="field"><span>参考答案</span><textarea id="e-answer-${q.id}">${esc(q.answer)}</textarea></label>`}
    <div class="flex">
      <button class="btn primary sm" data-act="q-save" data-id="${q.id}" data-choice="${isChoice ? 1 : 0}">保存并标为通过</button>
      <button class="btn sm" data-act="q-cancel" data-id="${q.id}">取消</button>
    </div>
  </div>`;
}

/* ---------------------------------------------------------------- 教师：测评管理 */
async function viewAssessments() {
  const d = await api("/api/assessments");
  $app.innerHTML = tabsHTML("t_assess") + `
    <div class="card"><h3>测评管理 <span class="sub">共 ${d.assessments.length} 个</span></h3>
      <table><thead><tr><th>测评</th><th>学生</th><th>题量</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody>
      ${d.assessments.map((a) => `<tr>
        <td><b>${esc(a.title)}</b><div class="small muted">${esc(a.mode === "class" ? "课堂限时" : "课后自主")} · ${a.time_limit} 分钟</div></td>
        <td>${esc(a.student_name)}</td>
        <td class="small">待审 ${a.pending} · 通过 ${a.approved} · 删除 ${a.rejected}</td>
        <td><span class="badge ${STATUS_COLOR[a.status]}">${STATUS_LABEL[a.status]}</span></td>
        <td class="small muted">${esc(a.created_at)}</td>
        <td>
          <button class="btn sm" data-act="go" data-view="t_review_one" data-id="${a.id}">查看题目</button>
          ${a.status === "reviewing" ? `<button class="btn primary sm" data-act="publish" data-id="${a.id}">发布</button>` : ""}
          ${a.status === "published" ? `<button class="btn sm" data-act="close" data-id="${a.id}">关闭</button>` : ""}
        </td>
      </tr>`).join("") || `<tr><td colspan="6" class="empty">暂无测评</td></tr>`}
      </tbody></table>
    </div>`;
}

/* ---------------------------------------------------------------- 教师：成绩复核 */
async function viewAttemptList() {
  const d = await api("/api/attempts");
  $app.innerHTML = tabsHTML("t_attempts") + `
    <div class="card"><h3>学生作答与复核 <span class="sub">共 ${d.attempts.length} 份</span></h3>
      ${d.attempts.length ? `<table><thead><tr><th>测评</th><th>学生</th><th>得分</th><th>状态</th><th>提交时间</th><th></th></tr></thead><tbody>
      ${d.attempts.map((t) => `<tr>
        <td>${esc(t.title)}<div class="small muted">${esc(t.code_title || "")}</div></td>
        <td>${esc(t.student_name)}</td>
        <td><b>${(t.score || 0).toFixed(1)}</b><span class="muted small"> / ${(t.max_score || 0).toFixed(0)}</span></td>
        <td><span class="badge ${ATT_COLOR[t.status]}">${ATT_LABEL[t.status]}</span></td>
        <td class="small muted">${esc(t.submitted_at || t.started_at)}</td>
        <td><button class="btn sm primary" data-act="go" data-view="t_attempt" data-id="${t.id}">复核</button></td>
      </tr>`).join("")}</tbody></table>` : `<div class="empty">暂无作答记录</div>`}
    </div>`;
}

async function viewAttemptReview(v) {
  const d = await api("/api/attempts/" + v.id);
  const t = d.attempt;
  $app.innerHTML = tabsHTML("t_attempts") + `
    <div class="card">
      <div class="flex"><div>
        <h3 style="margin:0">${esc(t.title)}</h3>
        <div class="small muted">学生：${esc(t.student_name)} · 状态：${ATT_LABEL[t.status]} ·
          得分 ${(t.score || 0).toFixed(1)} / ${(t.max_score || 0).toFixed(0)}</div>
      </div><div class="right"><button class="btn sm" data-act="go" data-view="t_attempts">返回</button></div></div>
    </div>
    <div class="grid" style="grid-template-columns: 1fr 1fr; align-items:start">
      <div class="card"><h3>学生提交的代码</h3>${codeHTML(d.code.source)}</div>
      <div class="card"><h3>复核说明</h3>
        <p class="small muted">系统按评分要点给出建议分，教师可逐题调整。开放题以关键词覆盖为初评依据，
        确认后点击“保存复核结果”，记录会标记为“已复核”。</p>
        <div class="small">总分：<b>${(t.score || 0).toFixed(1)}</b> / ${(t.max_score || 0).toFixed(0)}</div>
      </div>
    </div>
    ${d.questions.map((q) => `
      <div class="q">
        <div class="qhead">
          <span class="badge ${TYPE_COLOR[q.type]}">${TYPE_LABEL[q.type]}</span>
          <span class="badge gray">${q.points} 分</span>
          <span class="right small muted">${esc(q.code_ref || "")}</span>
        </div>
        <div class="stem">${esc(q.stem)}</div>
        ${optionListHTML(q, true)}
        <div class="small"><b>学生作答：</b>${esc(q.response || "（未作答）")}</div>
        <div class="small muted">系统建议 ${(q.auto_score || 0).toFixed(1)} 分 · 反馈：${esc(q.feedback || "")}</div>
        <label class="field mt"><span>复核分数（0—${q.points}）</span>
          <input type="number" data-final="${q.id}" value="${(q.final_score || 0).toFixed(1)}" min="0" max="${q.points}" step="0.5"></label>
      </div>`).join("")}
    <div class="card"><div class="flex"><span class="small muted">可直接修改每题得分后保存，系统会重新计算总分。</span>
      <button class="btn primary right" data-act="save-review" data-id="${t.id}">保存复核结果</button></div></div>`;
  state.cache.attemptQuestions = d.questions;
}

/* ---------------------------------------------------------------- 教师：统计 */
async function viewStats() {
  const [cls, ov] = await Promise.all([api("/api/stats/class"), api("/api/stats/overview")]);
  state.ov = ov.overview;
  const types = ["explain", "trace", "diagnose", "modify"];
  const typeMap = {};
  (cls.by_type || []).forEach((r) => { typeMap[r.type] = r; });
  $app.innerHTML = tabsHTML("t_stats") + `
    <div class="card"><h3>班级整体情况</h3>
      <div class="grid c4">
        <div class="stat"><div class="k">代码提交</div><div class="v">${ov.overview.codes}</div></div>
        <div class="stat"><div class="k">已提交作答</div><div class="v">${ov.overview.attempts}</div></div>
        <div class="stat"><div class="k">平均得分率</div><div class="v">${(ov.overview.avg || 0).toFixed(1)}<small> %</small></div></div>
        <div class="stat"><div class="k">待审核题目</div><div class="v">${ov.overview.pending}<small> 道</small></div></div>
      </div>
    </div>
    <div class="card"><h3>四类测评任务得分率 <span class="sub">得分率 = 实得 / 满分</span></h3>
      <div class="grid c2">
      ${types.map((tp) => {
        const r = typeMap[tp] || { ratio: 0, n: 0 };
        return `<div><div class="flex small"><b>${TYPE_LABEL[tp]}</b>
          <span class="right muted">${(r.ratio * 100 || 0).toFixed(0)}% · ${r.n || 0} 题</span></div>
          ${bar(r.ratio, r.ratio >= 0.75 ? "green" : r.ratio >= 0.5 ? "" : "amber")}</div>`;
      }).join("")}
      </div>
    </div>
    <div class="card"><h3>知识点掌握情况 <span class="sub">按代码标注的知识点汇总</span></h3>
      ${(cls.by_kp || []).length ? `<table><thead><tr><th>知识点</th><th>得分率</th><th>次数</th></tr></thead><tbody>
        ${cls.by_kp.map((r) => `<tr><td>${esc(r.kp)}</td>
          <td style="width:220px"><div class="flex small">${(r.score || 0).toFixed(0)}%</div>${bar((r.score || 0) / 100, (r.score || 0) >= 75 ? "green" : (r.score || 0) >= 50 ? "" : "amber")}</td>
          <td>${r.n}</td></tr>`).join("")}</tbody></table>` : `<div class="empty">暂无数据</div>`}
    </div>
    <div class="card"><h3>学生得分情况</h3>
      ${(cls.by_student || []).length ? `<table><thead><tr><th>学生</th><th>班级</th><th>平均得分率</th><th>作答次数</th></tr></thead><tbody>
        ${cls.by_student.map((r) => `<tr><td>${esc(r.name)}</td><td class="small muted">${esc(r.class_name)}</td>
          <td>${(r.score || 0).toFixed(1)}%</td><td>${r.n}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">暂无数据</div>`}
    </div>`;
}

/* ---------------------------------------------------------------- 学生：我的代码 */
async function viewMyCodes() {
  const d = await api("/api/codes");
  $app.innerHTML = tabsHTML("s_codes") + `
    <div class="card"><h3>提交代码 <span class="sub">系统将以这段代码为对象出题</span></h3>
      <form id="code-form">
        <div class="row">
          <label class="field"><span>题目/作业名称</span><input type="text" id="c-title" placeholder="如：统计列表中的最大值"></label>
          <label class="field"><span>课程</span>
            <select id="c-course">
              <option>程序设计基础</option><option>面向对象程序设计</option>
              <option>数据结构与算法</option><option>数据库原理</option>
            </select></label>
          <label class="field"><span>语言</span>
            <select id="c-lang"><option value="python">Python</option><option value="java">Java</option>
              <option value="cpp">C++</option><option value="c">C</option></select></label>
        </div>
        <label class="field"><span>知识点（逗号分隔，用于统计掌握情况）</span>
          <input type="text" id="c-kp" placeholder="如：循环, 边界条件, 列表操作"></label>
        <label class="field"><span>代码</span>
          <textarea id="c-source" style="min-height:220px;font-family:Consolas,monospace"
            placeholder="粘贴你的代码（Python/Java/C++均可）"></textarea></label>
        <button class="btn primary" type="submit">提交代码</button>
      </form>
    </div>
    <div class="card"><h3>我的提交 <span class="sub">共 ${d.codes.length} 份</span></h3>
      ${d.codes.length ? `<table><thead><tr><th>题目</th><th>课程 / 语言</th><th>知识点</th><th>提交时间</th><th></th></tr></thead><tbody>
        ${d.codes.map((c) => `<tr>
          <td><b>${esc(c.title)}</b><div class="small muted">${esc((c.source || "").slice(0, 60))}…</div></td>
          <td class="small">${esc(c.course)} · ${esc(c.language)}</td>
          <td class="small muted">${esc(c.knowledge_points || "—")}</td>
          <td class="small muted">${esc(c.created_at)}</td>
          <td><button class="btn sm primary" data-act="gen" data-id="${c.id}">生成测评题</button></td>
        </tr>`).join("")}</tbody></table>` : `<div class="empty">还没有提交代码</div>`}
    </div>`;
  document.getElementById("code-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/codes", "POST", {
        title: document.getElementById("c-title").value,
        course: document.getElementById("c-course").value,
        language: document.getElementById("c-lang").value,
        knowledge_points: document.getElementById("c-kp").value,
        source: document.getElementById("c-source").value,
      });
      toast("代码已提交");
      render();
    } catch (err) { toast(err.message, true); }
  });
}

/* ---------------------------------------------------------------- 学生：待测测评 */
async function viewMyTasks() {
  const d = await api("/api/student/assessments");
  const list = d.assessments;
  $app.innerHTML = tabsHTML("s_tasks") + `
    <div class="card"><h3>可参与的测评 <span class="sub">共 ${list.length} 个</span></h3>
      ${list.length ? list.map((a) => `
        <div class="q">
          <div class="qhead">
            <b>${esc(a.title)}</b>
            <span class="badge gray">${a.time_limit} 分钟</span>
            <span class="badge ${a.mode === "class" ? "blue" : "gray"}">${a.mode === "class" ? "课堂限时" : "课后自主"}</span>
            <span class="right small muted">${esc(a.code_title)} · ${esc(a.language)}</span>
          </div>
          <div class="small muted">针对 ${esc(a.student_name)} 提交的代码 · ${esc(a.published_at || "")}</div>
          <div class="mt">
            ${!a.attempt_id ? `<button class="btn primary sm" data-act="start" data-id="${a.id}">开始作答</button>` : ""}
            ${a.attempt_id && a.attempt_status === "in_progress" ? `<button class="btn primary sm" data-act="resume" data-id="${a.attempt_id}">继续作答</button>` : ""}
            ${a.attempt_id && a.attempt_status !== "in_progress" ? `<button class="btn sm" data-act="go" data-view="s_report" data-tid="${a.attempt_id}">
              查看报告（${(a.score || 0).toFixed(1)} / ${(a.max_score || 0).toFixed(0)}）</button>` : ""}
          </div>
        </div>`).join("") : `<div class="empty">暂时没有可参与的测评，等待教师发布</div>`}
    </div>`;
}

/* ---------------------------------------------------------------- 学生：作答 */
async function viewDoAttempt(v) {
  let d;
  if (v.tid) {
    d = await api("/api/attempts/" + v.tid);
  } else {
    const r = await api(`/api/assessments/${v.id}/attempts`, "POST", {});
    d = await api("/api/attempts/" + r.attempt.id);
  }
  const t = d.attempt;
  if (t.status !== "in_progress") { return go("s_report", { tid: t.id }); }
  state.cache.attempt = d;
  const remain = Math.max(1, (t.time_limit || 20) * 60);
  $app.innerHTML = tabsHTML("s_tasks") + `
    <div class="card">
      <div class="flex"><div>
        <h3 style="margin:0">${esc(t.title)}</h3>
        <div class="small muted">共 ${d.questions.length} 题 · 满分 ${(t.max_score || 0).toFixed(0)} 分 ·
          老师审核通过的题目才会出现在这里</div>
      </div>
      <div class="right small">剩余时间 <span class="timer" id="timer">--:--</span></div></div>
    </div>
    <div class="card"><h3>题目所针对的代码</h3>${codeHTML(d.code.source)}</div>
    <form id="answer-form">
      ${d.questions.map((q, i) => `
        <div class="q">
          <div class="qhead">
            <span class="badge blue">第 ${i + 1} 题</span>
            <span class="badge ${TYPE_COLOR[q.type]}">${TYPE_LABEL[q.type]}</span>
            <span class="badge ${DIFF_COLOR[q.difficulty] || "gray"}">${esc(q.difficulty)}</span>
            <span class="badge gray">${q.points} 分</span>
            <span class="right small muted">${esc(q.code_ref || "")}</span>
          </div>
          <div class="stem">${esc(q.stem)}</div>
          ${q.options && q.options.length
            ? q.options.map((o) => `<label class="opt"><input type="radio" name="q${q.id}" value="${o.key}">
                <b>${o.key}.</b><span>${esc(o.text)}</span></label>`).join("")
            : `<textarea data-qid="${q.id}" placeholder="请写出你的分析过程与结论"></textarea>`}
        </div>`).join("")}
      <div class="card"><div class="flex"><span class="small muted">提交后系统会先自动判分并给出反馈建议，教师复核后为最终成绩。</span>
        <button class="btn primary right" type="submit">交卷</button></div></div>
    </form>`;
  startTimer(remain);
  document.getElementById("answer-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!confirm("确认交卷？交卷后不能修改。")) return;
    const answers = [];
    d.questions.forEach((q) => {
      if (q.options && q.options.length) {
        const el = document.querySelector(`input[name="q${q.id}"]:checked`);
        answers.push({ question_id: q.id, response: el ? el.value : "" });
      } else {
        const el = document.querySelector(`textarea[data-qid="${q.id}"]`);
        answers.push({ question_id: q.id, response: el ? el.value : "" });
      }
    });
    try {
      const r = await api(`/api/attempts/${t.id}/submit`, "POST", { answers });
      stopTimer();
      toast("已提交，系统完成初步评分");
      go("s_report", { tid: r.attempt.id });
    } catch (err) { toast(err.message, true); }
  });
}

let timerId = null;
function startTimer(sec) {
  stopTimer();
  let left = sec;
  const el = () => document.getElementById("timer");
  const tick = () => {
    const m = String(Math.floor(left / 60)).padStart(2, "0");
    const s = String(left % 60).padStart(2, "0");
    if (el()) {
      el().textContent = m + ":" + s;
      el().className = "timer" + (left < 120 ? " warn" : "");
    }
    left -= 1;
    if (left < 0) {
      stopTimer();
      const f = document.getElementById("answer-form");
      if (f) { toast("作答时间到，已自动交卷", true); f.requestSubmit(); }
    }
  };
  tick();
  timerId = setInterval(tick, 1000);
}
function stopTimer() { if (timerId) { clearInterval(timerId); timerId = null; } }

/* ---------------------------------------------------------------- 学生：成绩列表 */
async function viewMyReports() {
  const mine = await (async () => {
    const r = await api("/api/student/assessments");
    return r.assessments.filter((a) => a.attempt_id);
  })();
  $app.innerHTML = tabsHTML("s_report_list") + `
    <div class="card"><h3>我的测评记录 <span class="sub">共 ${mine.length} 份</span></h3>
      ${mine.length ? `<table><thead><tr><th>测评</th><th>得分</th><th>状态</th><th>时间</th><th></th></tr></thead><tbody>
        ${mine.map((a) => `<tr>
          <td><b>${esc(a.title)}</b><div class="small muted">${esc(a.code_title)}</div></td>
          <td><b>${(a.score || 0).toFixed(1)}</b><span class="muted small"> / ${(a.max_score || 0).toFixed(0)}</span></td>
          <td><span class="badge ${ATT_COLOR[a.attempt_status]}">${ATT_LABEL[a.attempt_status]}</span></td>
          <td class="small muted">${esc(a.submitted_at || "")}</td>
          <td><button class="btn sm" data-act="go" data-view="s_report" data-tid="${a.attempt_id}">查看分项报告</button></td>
        </tr>`).join("")}</tbody></table>` : `<div class="empty">还没有测评记录</div>`}
    </div>`;
}

/* ---------------------------------------------------------------- 学生：分项报告 */
async function viewReport(v) {
  const d = await api("/api/report/" + v.tid);
  const t = d.attempt;
  const pct = t.max_score ? (t.score / t.max_score * 100) : 0;
  const types = ["explain", "trace", "diagnose", "modify"].filter((k) => d.by_type[k]);
  $app.innerHTML = tabsHTML("s_report_list") + `
    <div class="card">
      <div class="flex" style="align-items:flex-start">
        <div>
          <h3 style="margin:0">${esc(t.title)}</h3>
          <div class="small muted">${esc(t.student_name)} · ${t.status === "reviewed" ? "教师已复核" : "系统初评（待教师复核）"}</div>
        </div>
        <div class="right center"><div class="score-big">${(t.score || 0).toFixed(1)}<small> / ${(t.max_score || 0).toFixed(0)}</small></div>
          <div class="small muted">得分率 ${pct.toFixed(0)}%</div></div>
      </div>
    </div>
    <div class="card"><h3>四类任务分项</h3>
      <div class="grid c2">
      ${types.map((k) => `<div><div class="flex small"><b>${TYPE_LABEL[k]}</b>
        <span class="right muted">${(d.by_type[k].ratio * 100).toFixed(0)}%</span></div>
        ${bar(d.by_type[k].ratio, d.by_type[k].ratio >= 0.75 ? "green" : d.by_type[k].ratio >= 0.5 ? "" : "amber")}</div>`).join("")}
      </div>
    </div>
    <div class="card"><h3>逐题反馈</h3>
      ${d.questions.map((q) => `<div class="q">
        <div class="qhead">
          <span class="badge ${TYPE_COLOR[q.type]}">${TYPE_LABEL[q.type]}</span>
          <span class="badge gray">${(q.final_score || 0).toFixed(1)} / ${q.points} 分</span>
          <span class="right small muted">${esc(q.stem).slice(0, 40)}…</span>
        </div>
        <div class="stem">${esc(q.stem)}</div>
        <div class="small muted">你的作答：${esc(q.response || "（未作答）")}</div>
        ${q.options ? "" : `<div class="small muted">参考答案：${esc((q.answer || "").slice(0, 160))}</div>`}
        <div class="small" style="margin-top:6px"><b>反馈：</b>${esc(q.feedback || "—")}</div>
      </div>`).join("")}
    </div>`;
}

/* ---------------------------------------------------------------- 事件委托 */
document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  const act = el.dataset.act;
  const id = el.dataset.id;
  try {
    if (act === "go") {
      const params = {};
      if (id) params.id = id;
      if (el.dataset.tid) params.tid = el.dataset.tid;
      return go(el.dataset.view, params);
    }
    if (act === "quick-login") return doLogin(el.dataset.user);
    if (act === "gen") {
      const r = await api(`/api/codes/${id}/assessments`, "POST", { mode: "class", time_limit: 20 });
      toast(`已生成 ${r.question_count} 道候选题，等待教师审核`);
      return render();
    }
    if (act === "start") return go("s_attempt", { id });
    if (act === "resume") return go("s_attempt", { tid: id });
    if (act === "publish") {
      await api(`/api/assessments/${id}/publish`, "POST", {});
      toast("测评已发布，学生可以作答");
      return render();
    }
    if (act === "close") {
      await api(`/api/assessments/${id}/close`, "POST", {});
      toast("测评已关闭");
      return render();
    }
    if (act === "q-approve") {
      await api(`/api/questions/${id}`, "PATCH", { action: "approve" });
      toast("已通过");
      return render();
    }
    if (act === "q-reject") {
      await api(`/api/questions/${id}`, "PATCH", { action: "reject", note: "教师审核删除" });
      toast("已删除该题");
      return render();
    }
    if (act === "q-edit") {
      const q = (state.cache.questions || []).find((x) => String(x.id) === String(id));
      const box = document.getElementById("edit-" + id);
      if (q && box) box.innerHTML = questionEditForm(q);
      return;
    }
    if (act === "q-cancel") {
      document.getElementById("edit-" + id).innerHTML = "";
      return;
    }
    if (act === "q-save") {
      const isChoice = el.dataset.choice === "1";
      const body = { action: "edit",
        stem: document.getElementById("e-stem-" + id).value,
        difficulty: document.getElementById("e-diff-" + id).value,
        points: parseFloat(document.getElementById("e-pts-" + id).value) };
      if (isChoice) {
        const keys = ["A", "B", "C", "D"];
        body.options = keys.map((k) => ({
          key: k, text: document.getElementById("e-opt-" + id + "-" + k).value }));
        body.answer = document.getElementById("e-ans-" + id).value;
      } else {
        body.answer = document.getElementById("e-answer-" + id).value;
      }
      await api(`/api/questions/${id}`, "PATCH", body);
      toast("已保存并标记为通过");
      return render();
    }
    if (act === "save-review") {
      const adjust = (state.cache.attemptQuestions || []).map((q) => {
        const inp = document.querySelector(`[data-final="${q.id}"]`);
        return { question_id: q.id, final_score: inp ? parseFloat(inp.value) : q.final_score };
      });
      await api(`/api/attempts/${id}/review`, "POST", { adjust });
      toast("复核结果已保存");
      return render();
    }
  } catch (err) {
    toast(err.message, true);
  }
});

document.getElementById("logout").addEventListener("click", async () => {
  try { await api("/api/logout", "POST", {}); } catch (e) { /* ignore */ }
  state.user = null;
  go("login");
});

/* 启动 */
(async function boot() {
  try {
    const d = await api("/api/me");
    state.user = d.user;
    go(d.user.role === "teacher" ? "t_overview" : "s_codes");
  } catch (e) {
    render();
  }
})();
