"""Teacher console renderer (issue #167).

Renders :class:`~webui.models.ConsoleData` into ONE self-contained HTML
file -- no external stylesheets, scripts, fonts or images (the same
philosophy as the portfolio dashboard). View switching and the class
switcher are small vanilla-JS interactions inside the file; action
buttons are demo placeholders (a click stamps the card as handled,
client-side only) until the console is wired to the pipeline.

Design language: the Muse desktop app -- neutral grey paper, white
cards, one charcoal accent (#262626), serif display headings + clean
sans body, fixed left sidebar. Tokens are documented in
``webui/README.md``. (Palette revised 2026-10-21 per Daniel: grey +
white, superseding the original warm ivory / clay scheme.)

Data flows in through the view-model builders below
(``recognition_vm`` / ``hypothesis_vm`` / ``review_vm`` / ...), which
turn the model dataclasses into plain dicts the section templates
consume; the templates never touch the dataclasses directly.
"""

from __future__ import annotations

import html
import json
import sys

from .models import (
    GRADING_RESULTS,
    MASTERY_STATES,
    MIX_CATEGORIES,
    TIER_PRESENTATION,
    ClassData,
    ConsoleData,
    RecognitionItem,
    ReviewQuestionView,
    SkillHypothesisView,
)

__all__ = [
    "dashboard_vm",
    "recognition_vm",
    "hypothesis_vm",
    "review_vm",
    "export_vm",
    "render_console",
    "main",
]


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# Presentation maps (state -> pill class). Colors live in the CSS below.
# ---------------------------------------------------------------------------

_STATE_CLASSES = {
    "证据不足": "state-insufficient",
    "需要练习": "state-needs",
    "正在改善": "state-improving",
    "已有较充分掌握证据": "state-mastered",
    "待复习": "state-review",
}

_GRADING_CLASSES = {
    "正确": "grade-correct",
    "错误": "grade-wrong",
    "部分正确": "grade-partial",
    "无法辨认": "grade-unreadable",
}

_CATEGORY_CLASSES = {
    "共同题": "cat-common",
    "当前学习": "cat-current",
    "薄弱点练习": "cat-weak",
    "旧知识复习": "cat-review",
}

# ---------------------------------------------------------------------------
# Styles: Muse desktop design tokens (see webui/README.md).
# ---------------------------------------------------------------------------

CSS = """
:root {
  --paper: #F7F7F7;
  --paper-deep: #EFEFEF;
  --card: #FFFFFF;
  --border: #E5E5E5;
  --border-strong: #D4D4D4;
  --ink: #1A1A1A;
  --ink-2: #737373;
  --ink-3: #A3A3A3;
  --accent: #262626;
  --accent-dark: #000000;
  --accent-soft: #F0F0F0;
  --sage: #5C6B58;
  --sage-soft: #E9EDE7;
  --amber: #7D6A2F;
  --amber-soft: #F1EDDF;
  --red: #9E4A3C;
  --red-soft: #F5E7E2;
  --bluegray: #47617A;
  --bluegray-soft: #E3EAF0;
  --gray-soft: #EDEDED;
  --radius: 14px;
  --shadow: 0 1px 2px rgba(26, 26, 26, .04), 0 6px 20px rgba(26, 26, 26, .04);
  --serif: "Tiempos Text", "Source Serif 4", Georgia, "Songti SC",
           "Noto Serif SC", serif;
  --sans: "Söhne", -apple-system, BlinkMacSystemFont, "Segoe UI",
          "PingFang SC", "Microsoft YaHei", sans-serif;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body { margin: 0; padding: 0; }
body {
  font-family: var(--sans);
  background: var(--paper);
  color: var(--ink);
  font-size: 15px;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3, .serif { font-family: var(--serif); font-weight: 600; }
button { font-family: inherit; cursor: pointer; }

/* ---- layout ---- */
.sidebar {
  position: fixed; top: 0; left: 0; bottom: 0; width: 252px;
  background: var(--paper-deep);
  border-right: 1px solid var(--border);
  padding: 22px 16px 16px;
  display: flex; flex-direction: column; gap: 20px;
  overflow-y: auto;
}
.main { margin-left: 252px; }
.content { max-width: 1020px; margin: 0 auto; padding: 42px 48px 72px; }

/* ---- sidebar ---- */
.brand { display: flex; align-items: center; gap: 11px; padding: 2px 6px; }
.logo-mark {
  width: 34px; height: 34px; border-radius: 9px; background: var(--accent);
  display: flex; align-items: center; justify-content: center; flex: none;
}
.brand-name { font-family: var(--serif); font-size: 17.5px; line-height: 1.25; }
.brand-sub { font-size: 12px; color: var(--ink-2); }
.side-label {
  font-size: 11.5px; letter-spacing: .08em; color: var(--ink-3);
  padding: 0 8px; margin-bottom: 7px;
}
.class-switcher { display: flex; gap: 6px; padding: 0 2px; }
.class-btn {
  flex: 1; padding: 8px 4px; font-size: 13.5px; border-radius: 999px;
  border: 1px solid var(--border-strong); background: transparent;
  color: var(--ink-2);
}
.class-btn:hover { background: #fff; }
.class-btn.is-active {
  background: var(--ink); color: #fff; border-color: var(--ink);
}
.nav { display: flex; flex-direction: column; gap: 3px; }
.nav-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 9px 11px; border: none; background: transparent;
  border-radius: 10px; font-size: 14.5px; color: var(--ink);
  text-align: left;
}
.nav-item svg { flex: none; color: var(--ink-2); }
.nav-item:hover { background: rgba(255, 255, 255, .65); }
.nav-item.is-active { background: var(--accent-soft); color: var(--accent-dark); }
.nav-item.is-active svg { color: var(--accent); }
.nav-badge {
  margin-left: auto; min-width: 22px; text-align: center;
  background: var(--accent); color: #fff; font-size: 12px; line-height: 1;
  padding: 4px 6px; border-radius: 999px;
}
.sidebar-foot { margin-top: auto; border-top: 1px solid var(--border);
  padding-top: 14px; }
.teacher-row { display: flex; align-items: center; gap: 10px; padding: 0 6px; }
.avatar {
  width: 34px; height: 34px; border-radius: 50%; flex: none;
  background: var(--accent-soft); color: var(--accent-dark);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--serif); font-size: 15px;
}
.teacher-name { font-size: 14px; line-height: 1.3; }
.teacher-ctx { font-size: 12px; color: var(--ink-2); }
.privacy-note { font-size: 12px; color: var(--ink-3); padding: 10px 6px 0; }

/* ---- view scaffolding ---- */
.view-head { margin-bottom: 26px; }
.view-head h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: .01em; }
.view-sub { color: var(--ink-2); margin: 0; font-size: 14.5px; }
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
  padding: 22px 24px; margin-bottom: 18px;
  transition: transform .15s ease, box-shadow .15s ease;
}
.card:hover { transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(31,30,28,.05), 0 10px 26px rgba(31,30,28,.06); }
.card.is-done { opacity: .72; }
.card h3 { margin: 0 0 8px; font-size: 18px; }
.muted { color: var(--ink-2); }
.small { font-size: 13px; }
.note-card { background: #FBFAF6; }
.demo-status { font-size: 13px; color: var(--sage); margin-left: 6px; }

/* ---- dashboard ---- */
.stat-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 16px; margin-bottom: 18px;
}
.stat-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px 22px;
}
.stat-num { font-family: var(--serif); font-size: 34px; line-height: 1.15;
  color: var(--accent-dark); }
.stat-num.plain { color: var(--ink); font-size: 21px; padding-top: 8px; }
.stat-label { font-size: 14.5px; margin-top: 2px; }
.stat-hint { font-size: 12.5px; color: var(--ink-3); margin-top: 3px; }
.flow-list { list-style: none; margin: 6px 0 0; padding: 0; }
.flow-list li {
  display: flex; gap: 12px; align-items: baseline;
  padding: 8px 0; border-bottom: 1px solid var(--border);
}
.flow-list li:last-child { border-bottom: none; }
.flow-dot {
  width: 9px; height: 9px; border-radius: 50%; flex: none;
  background: var(--border-strong); position: relative; top: -1px;
}
.flow-done .flow-dot { background: var(--sage); }
.flow-active .flow-dot { background: var(--accent); }
.flow-name { min-width: 128px; }
.flow-desc { color: var(--ink-2); font-size: 13.5px; }
.flow-state { margin-left: auto; font-size: 12.5px; color: var(--ink-3); }
.flow-active .flow-state { color: var(--accent-dark); }

/* ---- pills & chips ---- */
.pill {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12.5px; line-height: 1; padding: 5px 10px;
  border-radius: 999px; white-space: nowrap;
}
.pill-neutral { background: var(--gray-soft); color: var(--ink-2); }
.tier-reliable { background: var(--sage-soft); color: var(--sage); }
.tier-doubtful { background: var(--amber-soft); color: var(--amber); }
.tier-manual { background: var(--accent); color: #fff; }
.grade-correct { background: var(--sage-soft); color: var(--sage); }
.grade-wrong { background: var(--red-soft); color: var(--red); }
.grade-partial { background: var(--amber-soft); color: var(--amber); }
.grade-unreadable { background: var(--gray-soft); color: var(--ink-2); }
.state-insufficient { background: var(--gray-soft); color: var(--ink-2); }
.state-needs { background: var(--amber-soft); color: var(--amber); }
.state-improving { background: var(--bluegray-soft); color: var(--bluegray); }
.state-mastered { background: var(--sage-soft); color: var(--sage); }
.state-review { background: #F3E6DE; color: #96604A; }
.cat-common { background: var(--accent-soft); color: var(--accent-dark); }
.cat-current { background: var(--bluegray-soft); color: var(--bluegray); }
.cat-weak { background: var(--amber-soft); color: var(--amber); }
.cat-review { background: var(--gray-soft); color: var(--ink-2); }
.hypo-badge { background: var(--ink); color: #fff; }
.id-chip {
  font-weight: 600; background: var(--paper-deep);
  border: 1px solid var(--border-strong); border-radius: 8px;
  padding: 3px 9px; font-size: 13.5px;
}
.skill-tag { color: var(--ink-2); font-size: 13px; }

/* ---- cards shared ---- */
.card-head { display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
  margin-bottom: 12px; }
.card-head .spacer { flex: 1; }
.assigned { color: var(--ink-3); font-size: 13px; }
.actions { display: flex; align-items: center; gap: 9px; margin-top: 16px;
  flex-wrap: wrap; }
.btn {
  border: 1px solid var(--border-strong); background: #fff; color: var(--ink);
  font-size: 14px; padding: 9px 18px; border-radius: 10px; min-height: 40px;
}
.btn:hover { background: var(--paper); }
.btn-primary { background: var(--accent); border-color: var(--accent);
  color: #fff; }
.btn-primary:hover { background: var(--accent-dark); }
.btn-small { padding: 5px 12px; min-height: 32px; font-size: 13px; }

/* ---- recognition view ---- */
.recog-grid { display: grid; grid-template-columns: 218px 1fr; gap: 22px; }
.img-ph {
  border: 1.5px dashed var(--border-strong); border-radius: 12px;
  background: #FBFAF6; min-height: 168px; padding: 16px;
  display: flex; flex-direction: column; gap: 5px;
  align-items: center; justify-content: center; text-align: center;
}
.img-ph-title { font-family: var(--serif); font-size: 15.5px; }
.img-ph-loc { font-size: 12px; color: var(--ink-2); word-break: break-all; }
.img-ph-note { font-size: 12px; color: var(--ink-3); }
.field-label { font-size: 12.5px; color: var(--ink-3);
  letter-spacing: .04em; display: block; margin-bottom: 4px; }
.answer-text {
  background: #FBFAF7; border: 1px solid var(--border); border-radius: 10px;
  padding: 11px 14px; margin: 0 0 12px; font-size: 15px;
}
.answer-empty { color: var(--ink-3); }
.field-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.field-row .field-label { margin: 0; }

/* ---- hypothesis view ---- */
.legend-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.evidence-list { list-style: none; margin: 8px 0 0; padding: 0; }
.evidence-list li {
  display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap;
  padding: 7px 0; border-bottom: 1px solid var(--border); font-size: 14px;
}
.evidence-list li:last-child { border-bottom: none; }
.ev-q { font-weight: 600; }
.ev-date { color: var(--ink-3); font-size: 13px; }
.ev-note { color: var(--ink-2); }

/* ---- review view ---- */
.mix-table, .export-table { width: 100%; border-collapse: collapse;
  font-size: 14px; }
.mix-table th, .mix-table td, .export-table th, .export-table td {
  padding: 8px 10px; border-bottom: 1px solid var(--border);
  text-align: left;
}
.mix-table th, .export-table th { color: var(--ink-2); font-weight: 500;
  font-size: 13px; }
.mix-table td.num, .mix-table th.num { text-align: center; }
.stem { font-size: 16.5px; line-height: 1.75; margin: 2px 0 14px; }
.q-fields { margin: 0; }
.q-fields > div { display: grid; grid-template-columns: 84px 1fr; gap: 12px;
  padding: 7px 0; border-bottom: 1px solid var(--border); }
.q-fields > div:last-child { border-bottom: none; }
.q-fields dt { color: var(--ink-3); font-size: 13px; padding-top: 2px; }
.q-fields dd { margin: 0; }
.q-fields ol { margin: 0; padding-left: 20px; }
.answer-box { background: var(--sage-soft); border-radius: 8px;
  padding: 6px 12px; display: inline-block; }
.figure-ph {
  border: 1.5px dashed var(--border-strong); border-radius: 10px;
  background: #FBFAF6; color: var(--ink-2); font-size: 13.5px;
  padding: 12px 16px; margin-bottom: 14px;
}

/* ---- export view ---- */
.export-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 18px;
  align-items: start; }
.export-grid .card { margin-bottom: 0; }
.teacher-key-card { background: #FBFAF6; }
@media (max-width: 900px) {
  .recog-grid, .export-grid { grid-template-columns: 1fr; }
  .content { padding: 28px 20px 56px; }
}
"""

# ---------------------------------------------------------------------------
# View-model builders: models -> plain dicts for the templates.
# ---------------------------------------------------------------------------


def recognition_vm(item: RecognitionItem) -> dict:
    label, css = TIER_PRESENTATION[item.tier]
    return {
        "student_id": item.student_id,
        "question_label": item.question_label + item.sub_question,
        "skill_name": item.skill_name,
        "answer": item.recognized_answer,
        "grading_result": item.grading_result,
        "grading_class": _GRADING_CLASSES[item.grading_result],
        "tier_label": label,
        "tier_class": css,
        "image_location": item.image_location,
        "page_label": item.page_label,
        "observed_date": item.observed_date,
    }


def hypothesis_vm(h: SkillHypothesisView) -> dict:
    return {
        "student_id": h.student_id,
        "skill_id": h.skill_id,
        "skill_name": h.skill_name,
        "state": h.state,
        "state_class": _STATE_CLASSES[h.state],
        "provisional": h.provisional,
        "hypothesis_note": h.hypothesis_note,
        "confidence": h.confidence,
        "evidence": [
            {
                "question_label": e.question_label,
                "date": e.date,
                "grading_result": e.grading_result,
                "grading_class": _GRADING_CLASSES[e.grading_result],
                "note": e.note,
            }
            for e in h.evidence
        ],
    }


def review_vm(q: ReviewQuestionView) -> dict:
    return {
        "id": q.id,
        "stem": q.stem,
        "skill_names": list(q.skill_names),
        "category": q.category,
        "category_class": _CATEGORY_CLASSES[q.category],
        "difficulty_label": q.difficulty_label,
        "recommendation_reason": q.recommendation_reason,
        "answer": q.answer,
        "solution_steps": list(q.solution_steps),
        "scoring_notes": q.scoring_notes,
        "figure_note": q.figure_note,
        "assigned_count": q.assigned_count,
    }


def dashboard_vm(cls: ClassData) -> dict:
    return {
        "recognition_count": len(cls.recognition),
        "hypothesis_count": len(cls.hypotheses),
        "review_count": len(cls.review_questions),
        "last_export": cls.export.last_export if cls.export else "",
        "hypothesis_students": len({h.student_id for h in cls.hypotheses}),
    }


def export_vm(cls: ClassData) -> dict:
    exp = cls.export
    return {
        "assignment_number": exp.assignment_number if exp else "",
        "students": list(exp.students) if exp else [],
        "teacher_key_pages": exp.teacher_key_pages if exp else 0,
        "last_export": exp.last_export if exp else "",
    }


# ---------------------------------------------------------------------------
# Section templates (one <section> per class x view; JS shows one at a time).
# ---------------------------------------------------------------------------

_ICONS = {
    "dashboard": (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8"><rect x="3.5" y="3.5" '
        'width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" '
        'height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" '
        'rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/></svg>'
    ),
    "recognition": (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8"><path d="M4 8V5.5A1.5 1.5 '
        '0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 '
        '0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16M3.5 12h17"/></svg>'
    ),
    "hypotheses": (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" '
        'r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" '
        'r="1" fill="currentColor"/></svg>'
    ),
    "review": (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8"><rect x="5" y="4.5" '
        'width="14" height="17" rx="2"/><path d="M9 4.5V3h6v1.5M9.5 13.5l2 '
        '2 3.5-4"/></svg>'
    ),
    "export": (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8"><path d="M12 4v10.5M7.5 '
        '10.5L12 15l4.5-4.5M4.5 19.5h15"/></svg>'
    ),
}

_VIEWS = (
    ("dashboard", "工作台", None),
    ("recognition", "识别确认", "recognition"),
    ("hypotheses", "薄弱点确认", "hypotheses"),
    ("review", "作业审核", "review"),
    ("export", "导出", None),
)


def _head(title: str, sub: str) -> str:
    return (
        f'<header class="view-head"><h1>{_esc(title)}</h1>'
        f'<p class="view-sub">{_esc(sub)}</p></header>'
    )


def _dashboard_section(cls: ClassData) -> str:
    vm = dashboard_vm(cls)
    flow = [
        ("上传批改作业", "纸质作业照片 / 扫描件", "done", "已完成"),
        ("识别与匹配", "关联学生、页码与小题，识别作答与批改痕迹", "done", "已完成"),
        ("确认识别结果", f"还有 {vm['recognition_count']} 条识别结果待确认",
         "active" if vm["recognition_count"] else "done",
         "待处理" if vm["recognition_count"] else "已完成"),
        ("确认薄弱点", f"{vm['hypothesis_count']} 人次技能判断待确认",
         "active" if vm["hypothesis_count"] else "done",
         "待处理" if vm["hypothesis_count"] else "已完成"),
        ("按证据组卷", "当前学习 / 薄弱点练习 / 旧知识复习 动态混合", "done", "已完成"),
        ("审核题目", f"{vm['review_count']} 道共享题目待审核",
         "active" if vm["review_count"] else "done",
         "待处理" if vm["review_count"] else "已完成"),
        ("导出打印", "学生卷 PDF 与教师版分别导出", "todo", "未开始"),
    ]
    flow_html = "".join(
        f'<li class="flow-{status}"><span class="flow-dot"></span>'
        f'<span class="flow-name">{_esc(name)}</span>'
        f'<span class="flow-desc">{_esc(desc)}</span>'
        f'<span class="flow-state">{_esc(state)}</span></li>'
        for name, desc, status, state in flow
    )
    return f"""
<section class="view" data-cls="{_esc(cls.key)}" data-view="dashboard">
  {_head("工作台", f"{cls.label} · {cls.chapter_label} · 本次作业 {cls.assignment_number}")}
  <div class="stat-grid">
    <div class="stat-card"><div class="stat-num">{vm['recognition_count']}</div>
      <div class="stat-label">待确认识别（条）</div>
      <div class="stat-hint">含需手录与存疑条目</div></div>
    <div class="stat-card"><div class="stat-num">{vm['hypothesis_count']}</div>
      <div class="stat-label">待确认薄弱点（人次）</div>
      <div class="stat-hint">涉及 {vm['hypothesis_students']} 位学生</div></div>
    <div class="stat-card"><div class="stat-num">{vm['review_count']}</div>
      <div class="stat-label">待审核题目（道）</div>
      <div class="stat-hint">按共享题目审核，一次覆盖全班</div></div>
    <div class="stat-card"><div class="stat-num plain">{_esc(vm['last_export'])}</div>
      <div class="stat-label">最近一次导出</div>
      <div class="stat-hint">学生卷与教师版分开导出</div></div>
  </div>
  <div class="card">
    <h3>本次作业流程</h3>
    <ul class="flow-list">{flow_html}</ul>
  </div>
  <div class="card note-card">
    <h3>使用说明</h3>
    <p class="muted">学生仅以编号（如 S-023）显示，系统不保存姓名。技能状态是可修正的
    教学判断，不是学生的固定标签；识别可靠度只表示系统读得准不准，与学生是否掌握无关，
    两者分开呈现。</p>
  </div>
</section>"""


def _recognition_section(cls: ClassData) -> str:
    cards = []
    for item in cls.recognition:
        vm = recognition_vm(item)
        answer = (
            _esc(vm["answer"]) if vm["answer"]
            else '<span class="answer-empty">（未能读出内容，请对照原图手录）</span>'
        )
        cards.append(f"""
    <article class="card" data-card>
      <div class="recog-grid">
        <div class="img-ph">
          <div class="img-ph-title">原图区域</div>
          <div class="img-ph-loc">{_esc(vm['page_label'])} · {_esc(vm['image_location'])}</div>
          <div class="img-ph-note">接入扫描件后在此显示原图</div>
        </div>
        <div>
          <div class="card-head">
            <span class="id-chip">{_esc(vm['student_id'])}</span>
            <strong>{_esc(vm['question_label'])}</strong>
            <span class="skill-tag">{_esc(vm['skill_name'])}</span>
            <span class="spacer"></span>
            <span class="pill {vm['tier_class']}">识别{vm['tier_label']}</span>
          </div>
          <span class="field-label">识别到的作答</span>
          <p class="answer-text">{answer}</p>
          <div class="field-row">
            <span class="field-label">批改结果（识别）</span>
            <span class="pill {vm['grading_class']}">{_esc(vm['grading_result'])}</span>
            <span class="field-label">作答日期</span>
            <span>{_esc(vm['observed_date'])}</span>
          </div>
          <div class="actions">
            <button type="button" class="btn btn-primary" data-demo="已确认">确认</button>
            <button type="button" class="btn" data-demo="已打开修改">修改</button>
            <button type="button" class="btn" data-demo="已切换到手录">手录</button>
            <span class="demo-status"></span>
          </div>
        </div>
      </div>
    </article>""")
    intro = (
        '<div class="card note-card"><p class="muted" style="margin:0">'
        '这里确认的是<strong>系统读得对不对</strong>：可靠 = 识别把握较高；存疑 = 读出但'
        '把握不足，请对照原图核对；需手录 = 基本读不出，请照原图录入。识别可靠度与学生'
        '是否掌握是两件不同的事，不要混在一起判断。</p></div>'
    )
    body = "\n".join(cards) if cards else '<div class="card"><p class="muted">没有待确认的识别条目。</p></div>'
    return f"""
<section class="view" data-cls="{_esc(cls.key)}" data-view="recognition">
  {_head("识别确认", f"{cls.label} · 共 {len(cls.recognition)} 条待确认")}
  {intro}
  {body}
</section>"""


def _hypotheses_section(cls: ClassData) -> str:
    legend = "".join(
        f'<span class="pill {_STATE_CLASSES[s]}">{_esc(s)}</span>'
        for s in MASTERY_STATES
    )
    cards = []
    for h in cls.hypotheses:
        vm = hypothesis_vm(h)
        evidence = "".join(
            f'<li><span class="ev-q">{_esc(e["question_label"])}</span>'
            f'<span class="ev-date">{_esc(e["date"])}</span>'
            f'<span class="pill {e["grading_class"]}">{_esc(e["grading_result"])}</span>'
            f'<span class="ev-note">{_esc(e["note"])}</span></li>'
            for e in vm["evidence"]
        )
        provisional = (
            '<span class="pill hypo-badge">待验证假设</span>' if vm["provisional"] else ""
        )
        cards.append(f"""
    <article class="card" data-card>
      <div class="card-head">
        <span class="id-chip">{_esc(vm['student_id'])}</span>
        <strong>{_esc(vm['skill_name'])}</strong>
        <span class="skill-tag">{_esc(vm['skill_id'])}</span>
        <span class="spacer"></span>
        {provisional}
        <span class="pill {vm['state_class']}">{_esc(vm['state'])}</span>
      </div>
      <p style="margin:0">{_esc(vm['hypothesis_note'])}</p>
      <p class="muted small" style="margin:6px 0 0">判断把握：{_esc(vm['confidence'])}（定性判断，不是百分比）</p>
      <span class="field-label" style="margin-top:12px">判断依据</span>
      <ul class="evidence-list">{evidence}</ul>
      <div class="actions">
        <button type="button" class="btn btn-primary" data-demo="已确认">确认</button>
        <button type="button" class="btn" data-demo="已打开修改状态">修改状态</button>
        <button type="button" class="btn" data-demo="已驳回">驳回</button>
        <span class="demo-status"></span>
      </div>
    </article>""")
    intro = (
        '<div class="card note-card"><h3>技能状态（五种教学判断）</h3>'
        '<p class="muted" style="margin:0">一次答错只能支持一个待验证的薄弱点假设，'
        '一次答对也不能证明长期掌握。状态可以随时修正，系统不显示缺乏校准依据的'
        '精确掌握百分比。</p>'
        f'<div class="legend-row">{legend}</div></div>'
    )
    body = "\n".join(cards) if cards else '<div class="card"><p class="muted">没有待确认的薄弱点。</p></div>'
    return f"""
<section class="view" data-cls="{_esc(cls.key)}" data-view="hypotheses">
  {_head("薄弱点确认", f"{cls.label} · 共 {len(cls.hypotheses)} 人次待确认")}
  {intro}
  {body}
</section>"""


def _mix_summary_card(cls: ClassData) -> str:
    header = "".join(f'<th class="num">{_esc(c)}</th>' for c in MIX_CATEGORIES)
    rows = []
    for m in cls.mix:
        cells = "".join(
            f'<td class="num">{m.counts.get(c, 0)}</td>' for c in MIX_CATEGORIES
        )
        rows.append(
            f'<tr><td><span class="id-chip">{_esc(m.student_id)}</span></td>'
            f"{cells}<td class=\"num\"><strong>{m.total}</strong></td></tr>"
        )
    return f"""
  <div class="card">
    <h3>每位学生的题目构成</h3>
    <p class="muted small" style="margin-top:0">共同题便于统一讲评；其余按每位学生的
    证据动态混合，不预设全班固定比例。（演示夹具仅列出部分学生）</p>
    <table class="mix-table">
      <thead><tr><th>学生</th>{header}<th class="num">合计</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>"""


def _review_section(cls: ClassData) -> str:
    cards = []
    for q in cls.review_questions:
        vm = review_vm(q)
        steps = "".join(f"<li>{_esc(s)}</li>" for s in vm["solution_steps"])
        skills = "、".join(_esc(s) for s in vm["skill_names"])
        figure = (
            f'<div class="figure-ph">图待补充：{_esc(vm["figure_note"])}</div>'
            if vm["figure_note"] else ""
        )
        cards.append(f"""
    <article class="card" data-card>
      <div class="card-head">
        <strong class="serif">{_esc(vm['id'])}</strong>
        <span class="pill {vm['category_class']}">{_esc(vm['category'])}</span>
        <span class="pill pill-neutral">预期难度：{_esc(vm['difficulty_label'])}</span>
        <span class="spacer"></span>
        <span class="assigned">布置给 {vm['assigned_count']} 位学生</span>
      </div>
      <p class="stem">{_esc(vm['stem'])}</p>
      {figure}
      <dl class="q-fields">
        <div><dt>目标技能</dt><dd>{skills}</dd></div>
        <div><dt>推荐原因</dt><dd>{_esc(vm['recommendation_reason'])}</dd></div>
        <div><dt>参考答案</dt><dd><span class="answer-box">{_esc(vm['answer'])}</span></dd></div>
        <div><dt>解题过程</dt><dd><ol>{steps}</ol></dd></div>
        <div><dt>评分说明</dt><dd>{_esc(vm['scoring_notes'])}</dd></div>
      </dl>
      <div class="actions">
        <button type="button" class="btn btn-primary" data-demo="已通过">通过</button>
        <button type="button" class="btn" data-demo="已打开替换">替换</button>
        <button type="button" class="btn" data-demo="已移除">移除</button>
        <span class="demo-status"></span>
      </div>
    </article>""")
    body = "\n".join(cards) if cards else '<div class="card"><p class="muted">没有待审核的题目。</p></div>'
    return f"""
<section class="view" data-cls="{_esc(cls.key)}" data-view="review">
  {_head("作业审核", f"{cls.label} · 作业 {cls.assignment_number} · 按共享题目审核，一次决定覆盖所有被布置到的学生")}
  {_mix_summary_card(cls)}
  {body}
</section>"""


def _export_section(cls: ClassData) -> str:
    vm = export_vm(cls)
    rows = "".join(
        f'<tr><td><span class="id-chip">{_esc(sid)}</span></td>'
        f"<td>{pages} 页</td><td>已生成</td>"
        f'<td><button type="button" class="btn btn-small" '
        f'data-export-fn="export_student_sheet" '
        f'title="将调用 review.export.export_student_sheet（单个学生）">下载</button></td></tr>'
        for sid, pages in vm["students"]
    )
    # Export buttons are inert placeholders in this static demo; each one
    # names the review.export function it will call once wired up:
    #   export_class        -> whole-class batch + teacher key + manifest
    #   export_student_sheet-> one student's sheet
    #   export_teacher_key  -> the separate teacher key (answers + 评分说明)
    return f"""
<section class="view" data-cls="{_esc(cls.key)}" data-view="export">
  {_head("导出", f"{cls.label} · 作业 {vm['assignment_number']} · 学生卷与教师版分开导出")}
  <div class="export-grid">
    <article class="card">
      <h3>学生作业 PDF</h3>
      <p class="muted">每位学生一份，只含题目与答题区，不含答案。
      （演示夹具仅列出部分学生）</p>
      <table class="export-table">
        <thead><tr><th>学生</th><th>页数</th><th>状态</th><th></th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <div class="actions">
        <button type="button" class="btn btn-primary" data-export-fn="export_class"
          title="将调用 review.export.export_class（全班批量导出）">全班批量导出</button>
      </div>
    </article>
    <article class="card teacher-key-card">
      <h3>教师版（答案与评分说明）</h3>
      <p class="muted">独立文件，含全部题目的参考答案、解题过程与评分说明，
      与学生卷分开发放，请勿发给学生。</p>
      <p class="muted">共 {vm['teacher_key_pages']} 页 · 作业 {vm['assignment_number']}</p>
      <div class="actions">
        <button type="button" class="btn" data-export-fn="export_teacher_key"
          title="将调用 review.export.export_teacher_key（教师版）">下载教师版</button>
      </div>
    </article>
  </div>
  <p class="muted" style="margin-top:18px">最近一次导出：{_esc(vm['last_export'])}</p>
</section>"""


_SECTION_BUILDERS = {
    "dashboard": _dashboard_section,
    "recognition": _recognition_section,
    "hypotheses": _hypotheses_section,
    "review": _review_section,
    "export": _export_section,
}

_JS_TEMPLATE = """
var state = { cls: "__DEFAULT_CLS__", view: "dashboard" };
var CLASS_COUNTS = __COUNTS_JSON__;
function show() {
  document.querySelectorAll("section.view").forEach(function (s) {
    s.hidden = !(s.getAttribute("data-cls") === state.cls &&
                 s.getAttribute("data-view") === state.view);
  });
  document.querySelectorAll("[data-nav-view]").forEach(function (b) {
    b.classList.toggle("is-active",
      b.getAttribute("data-nav-view") === state.view);
  });
  document.querySelectorAll("[data-cls-btn]").forEach(function (b) {
    b.classList.toggle("is-active",
      b.getAttribute("data-cls-btn") === state.cls);
  });
  var counts = CLASS_COUNTS[state.cls] || {};
  document.querySelectorAll("[data-badge]").forEach(function (b) {
    var v = counts[b.getAttribute("data-badge")];
    b.textContent = (v == null ? "" : v);
    b.style.display = (v == null || v === 0) ? "none" : "";
  });
  window.scrollTo(0, 0);
}
document.querySelectorAll("[data-nav-view]").forEach(function (b) {
  b.addEventListener("click", function () {
    state.view = b.getAttribute("data-nav-view"); show();
  });
});
document.querySelectorAll("[data-cls-btn]").forEach(function (b) {
  b.addEventListener("click", function () {
    state.cls = b.getAttribute("data-cls-btn"); show();
  });
});
document.querySelectorAll("[data-demo]").forEach(function (btn) {
  btn.addEventListener("click", function () {
    var card = btn.closest("[data-card]");
    if (!card) return;
    card.classList.add("is-done");
    var st = card.querySelector(".demo-status");
    if (st) st.textContent = btn.getAttribute("data-demo") + "（演示，未保存）";
  });
});
show();
"""


def render_console(data: ConsoleData) -> str:
    """Render the whole console as one self-contained HTML document."""
    if not data.classes:
        raise ValueError("console needs at least one class")
    counts = {
        cls.key: {
            "recognition": len(cls.recognition),
            "hypotheses": len(cls.hypotheses),
            "review": len(cls.review_questions),
        }
        for cls in data.classes
    }
    default_cls = data.classes[0].key

    class_btns = "".join(
        f'<button type="button" class="class-btn{" is-active" if i == 0 else ""}" '
        f'data-cls-btn="{_esc(cls.key)}">{_esc(cls.label)}</button>'
        for i, cls in enumerate(data.classes)
    )
    nav_items = []
    for view, label, badge in _VIEWS:
        badge_html = (
            f'<span class="nav-badge" data-badge="{badge}"></span>' if badge else ""
        )
        active = " is-active" if view == "dashboard" else ""
        nav_items.append(
            f'<button type="button" class="nav-item{active}" '
            f'data-nav-view="{view}">{_ICONS[view]}<span>{label}</span>'
            f"{badge_html}</button>"
        )

    sections = []
    for cls in data.classes:
        for view, _label, _badge in _VIEWS:
            sections.append(_SECTION_BUILDERS[view](cls))
    sections_html = "\n".join(sections)

    js = _JS_TEMPLATE.replace("__DEFAULT_CLS__", default_cls).replace(
        "__COUNTS_JSON__", json.dumps(counts, ensure_ascii=False)
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>个性化作业 · 教师控制台</title>
<style>{CSS}</style>
</head>
<body>
<aside class="sidebar">
  <div class="brand">
    <div class="logo-mark"><svg width="18" height="18" viewBox="0 0 24 24"
      fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round">
      <path d="M12 3.5v17M4.6 7.8l14.8 8.4M19.4 7.8L4.6 16.2"/></svg></div>
    <div>
      <div class="brand-name">个性化作业</div>
      <div class="brand-sub">教师控制台 · 试点</div>
    </div>
  </div>
  <div>
    <div class="side-label">班级</div>
    <div class="class-switcher">{class_btns}</div>
  </div>
  <nav class="nav">{''.join(nav_items)}</nav>
  <div class="sidebar-foot">
    <div class="teacher-row">
      <div class="avatar">师</div>
      <div>
        <div class="teacher-name">{_esc(data.teacher_label)}</div>
        <div class="teacher-ctx">{_esc(data.teacher_context)}</div>
      </div>
    </div>
    <div class="privacy-note">学生仅以编号显示 · 系统不保存姓名</div>
  </div>
</aside>
<main class="main">
  <div class="content">
{sections_html}
  </div>
</main>
<script>{js}</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    """Render the demo console to an HTML file.

    Usage (from ``homework-pilot/``): ``python3 -m webui [output.html]``
    -- defaults to ``teacher-console.html`` in the current directory.
    """
    from .fixtures import build_demo_data

    args = sys.argv[1:] if argv is None else argv
    out = args[0] if args else "teacher-console.html"
    document = render_console(build_demo_data())
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(document)
    print(f"wrote {out} ({len(document)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
