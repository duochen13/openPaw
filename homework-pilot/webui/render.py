"""Teacher console renderer (issue #167).

Renders :class:`~webui.models.ConsoleData` into ONE self-contained HTML
file -- no external stylesheets, scripts, fonts or images (the same
philosophy as the portfolio dashboard). View switching and the class
switcher are small vanilla-JS interactions inside the file; action
buttons are inline-SVG icon buttons (the Chinese action word lives in
``title`` / ``aria-label`` only) and demo placeholders (a click stamps
the card as handled, client-side only) until the console is wired to
the pipeline. Views show only their key elements; secondary detail is
shortened or folded away (2026-10-24 simplification pass per Daniel:
key features first, icons over text, calmer like the Muse app).

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
.content { max-width: 1020px; margin: 0 auto; padding: 48px 48px 84px; }

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
.view-head { margin-bottom: 28px; }
.view-head h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: .01em; }
.view-sub { color: var(--ink-2); margin: 0; font-size: 14.5px; }
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
  padding: 24px 26px; margin-bottom: 22px;
}
.card.is-done { opacity: .72; }
.card h3 { margin: 0 0 10px; font-size: 18px; }
.muted { color: var(--ink-2); }
.small { font-size: 13px; }
.view-note { margin: 0 0 16px; }
.demo-status { font-size: 13px; color: var(--sage); margin-left: 6px; }

/* ---- collapsed secondary detail (<details>) ---- */
details.more { margin-top: 12px; }
details.more > summary {
  cursor: pointer; color: var(--ink-2); font-size: 13.5px;
  list-style: none; display: inline-flex; align-items: center; gap: 6px;
}
details.more > summary::-webkit-details-marker { display: none; }
details.more > summary::before { content: "+"; color: var(--ink-3);
  font-size: 15px; line-height: 1; }
details.more[open ] > summary::before { content: "−"; }
details.more > summary:hover { color: var(--ink); }
details.more.block { margin: 0 0 18px; }

/* ---- dashboard ---- */
.todo-line { font-size: 15px; color: var(--ink-2); margin: 0 0 16px; }
.todo-line strong { color: var(--ink); font-family: var(--serif);
  font-size: 17px; }
.stat-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 16px; margin-bottom: 22px;
}
.stat-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px 22px;
}
.stat-num { font-family: var(--serif); font-size: 34px; line-height: 1.15;
  color: var(--accent-dark); }
.stat-label { font-size: 14.5px; margin-top: 2px; }

/* ---- pills & chips ---- */
.pill {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12.5px; line-height: 1; padding: 5px 10px;
  border-radius: 999px; white-space: nowrap;
}
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
.actions { display: flex; align-items: center; gap: 6px; margin-top: 16px;
  flex-wrap: wrap; }
/* Icon buttons: the action word lives in title / aria-label only. */
.icon-btn {
  width: 38px; height: 38px; padding: 0; flex: none;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-strong); border-radius: 10px;
  background: #fff; color: var(--ink-2);
}
.icon-btn:hover { background: var(--paper); color: var(--ink); }
.icon-btn.primary { background: var(--accent); border-color: var(--accent);
  color: #fff; }
.icon-btn.primary:hover { background: var(--accent-dark); }
.icon-btn.danger:hover { color: var(--red); border-color: var(--red); }
/* The one text button left: the whole-class batch export, whose scope
   (everything, not this row) an icon alone cannot say. */
.btn {
  display: inline-flex; align-items: center; gap: 8px;
  border: 1px solid var(--accent); background: var(--accent); color: #fff;
  font-size: 14px; padding: 10px 18px; border-radius: 10px; min-height: 40px;
}
.btn:hover { background: var(--accent-dark); }

/* ---- recognition view ---- */
.recog-grid { display: grid; grid-template-columns: 132px 1fr; gap: 20px; }
.img-ph {
  border: 1.5px dashed var(--border-strong); border-radius: 12px;
  background: #FAFAFA; min-height: 108px; padding: 12px 8px;
  display: flex; flex-direction: column; gap: 4px; color: var(--ink-3);
  align-items: center; justify-content: center; text-align: center;
}
.img-ph-loc { font-size: 12px; color: var(--ink-2); }
.img-ph-note { font-size: 12px; color: var(--ink-3); }
.answer-text {
  background: #FAFAFA; border: 1px solid var(--border); border-radius: 10px;
  padding: 11px 14px; margin: 0 0 12px; font-size: 15px;
}
.answer-empty { color: var(--ink-3); }
.meta-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

/* ---- hypothesis view ---- */
.legend-row { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 20px; }
.evidence-list { list-style: none; margin: 10px 0 0; padding: 0; }
.evidence-list li {
  display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap;
  padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13.5px;
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
  background: #FAFAFA; color: var(--ink-2); font-size: 13.5px;
  padding: 12px 16px; margin-bottom: 14px;
}
.answer-row { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.q-more { margin-top: 14px; }
.q-more summary { cursor: pointer; color: var(--ink-2); font-size: 13.5px;
  list-style: none; }
.q-more summary::-webkit-details-marker { display: none; }
.q-more summary:hover { color: var(--ink); }
.q-more .q-fields { margin-top: 4px; }

/* ---- export view ---- */
.export-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 18px;
  align-items: start; }
.export-grid .card { margin-bottom: 0; }
.teacher-key-card { background: #FAFAFA; }
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

# ---------------------------------------------------------------------------
# Action icons: inline SVG paths (24x24, stroke style matching the nav
# icons). Per Daniel's direction the buttons show the icon only; the
# Chinese action word is carried by title / aria-label.
# ---------------------------------------------------------------------------

_ACTION_ICONS = {
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "pencil": (
        '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>'
    ),
    "keyboard": (
        '<rect x="3" y="6.5" width="18" height="11" rx="2"/>'
        '<path d="M7 10.3h.01M10.3 10.3h.01M13.6 10.3h.01M17 10.3h.01'
        'M7.5 14h9"/>'
    ),
    "x": '<path d="M18 6L6 18M6 6l12 12"/>',
    "swap": (
        '<path d="M4 7h13"/><path d="M13.5 3.5L17 7l-3.5 3.5"/>'
        '<path d="M20 17H7"/><path d="M10.5 13.5L7 17l3.5 3.5"/>'
    ),
    "trash": (
        '<path d="M5 7h14M10 7V5a1.5 1.5 0 0 1 1.5-1.5h1A1.5 1.5 0 0 1 '
        '14 5v2M8 7l.7 11.2a1.5 1.5 0 0 0 1.5 1.3h3.6a1.5 1.5 0 0 0 '
        '1.5-1.3L16 7M10.3 11v4.5M13.7 11v4.5"/>'
    ),
    "download": (
        '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/>'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
    ),
    "arrow": '<path d="M5 12h14"/><path d="M12 5l7 7-7 7"/>',
    "image": (
        '<rect x="3" y="3" width="18" height="18" rx="2"/>'
        '<circle cx="8.5" cy="8.5" r="1.5"/>'
        '<path d="M21 15l-5-5L5 21"/>'
    ),
}


def _svg(paths: str, size: int = 18) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{paths}</svg>'
    )


def _icon_btn(
    icon: str,
    label: str,
    *,
    demo: str | None = None,
    primary: bool = False,
    danger: bool = False,
    export_fn: str | None = None,
    export_note: str = "",
) -> str:
    """One icon-only action button.

    ``label`` is the Chinese action word; it appears only in ``title``
    (tooltip) and ``aria-label``. Demo buttons stamp their card via
    ``data-demo``; export buttons stay inert and name their backend
    function in the title, per the export placeholder convention.
    """
    cls = "icon-btn"
    if primary:
        cls += " primary"
    if danger:
        cls += " danger"
    if export_fn:
        title = f"{label} · 将调用 review.export.{export_fn}（{export_note}）"
        action = f'data-export-fn="{export_fn}"'
    else:
        title = label
        action = f'data-demo="{_esc(demo or "")}"'
    return (
        f'<button type="button" class="{cls}" {action} '
        f'title="{_esc(title)}" aria-label="{_esc(label)}">'
        f"{_svg(_ACTION_ICONS[icon])}</button>"
    )


def _head(title: str, sub: str) -> str:
    return (
        f'<header class="view-head"><h1>{_esc(title)}</h1>'
        f'<p class="view-sub">{_esc(sub)}</p></header>'
    )


def _dashboard_section(cls: ClassData) -> str:
    vm = dashboard_vm(cls)
    # The single next action: the earliest stage of the loop that still
    # has pending work; when everything is confirmed, exporting is next.
    if vm["recognition_count"]:
        next_label = "确认识别结果"
        next_detail = f"还有 {vm['recognition_count']} 条待确认"
        next_view = "recognition"
    elif vm["hypothesis_count"]:
        next_label = "确认薄弱点"
        next_detail = f"还有 {vm['hypothesis_count']} 人次待确认"
        next_view = "hypotheses"
    elif vm["review_count"]:
        next_label = "审核题目"
        next_detail = f"还有 {vm['review_count']} 道待审核"
        next_view = "review"
    else:
        next_label = "导出打印"
        next_detail = "待办已清零，可以导出本轮作业"
        next_view = "export"
    return f"""
<section class="view" data-cls="{_esc(cls.key)}" data-view="dashboard">
  {_head("工作台", f"{cls.label} · {cls.chapter_label} · 本次作业 {cls.assignment_number}")}
  <button type="button" class="next-card" data-nav-view="{next_view}">
    <span class="next-text">
      <span class="next-kicker">下一步</span>
      <span class="next-label">{_esc(next_label)}</span>
      <span class="next-detail">{_esc(next_detail)}</span>
    </span>
    <span class="next-arrow">{_svg(_ACTION_ICONS["arrow"], 20)}</span>
  </button>
  <div class="stat-grid">
    <div class="stat-card"><div class="stat-num">{vm['recognition_count']}</div>
      <div class="stat-label">待确认识别（条）</div></div>
    <div class="stat-card"><div class="stat-num">{vm['hypothesis_count']}</div>
      <div class="stat-label">待确认薄弱点（人次）</div>
      <div class="stat-hint">涉及 {vm['hypothesis_students']} 位学生</div></div>
    <div class="stat-card"><div class="stat-num">{vm['review_count']}</div>
      <div class="stat-label">待审核题目（道）</div></div>
  </div>
  <p class="muted small">学生仅以编号显示，系统不保存姓名；识别可靠度与掌握判断分开呈现。</p>
</section>"""


def _recognition_section(cls: ClassData) -> str:
    cards = []
    for item in cls.recognition:
        vm = recognition_vm(item)
        answer = (
            _esc(vm["answer"]) if vm["answer"]
            else '<span class="answer-empty">（未能读出内容，请对照原图手录）</span>'
        )
        actions = "".join([
            _icon_btn("check", "确认", demo="已确认", primary=True),
            _icon_btn("pencil", "修改", demo="已打开修改"),
            _icon_btn("keyboard", "手录", demo="已切换到手录"),
            '<span class="demo-status"></span>',
        ])
        cards.append(f"""
    <article class="card" data-card>
      <div class="recog-grid">
        <div class="img-ph">
          {_svg(_ACTION_ICONS["image"], 22)}
          <div class="img-ph-loc">{_esc(vm['page_label'])}</div>
          <div class="img-ph-note">原图待接入</div>
        </div>
        <div>
          <div class="card-head">
            <span class="id-chip">{_esc(vm['student_id'])}</span>
            <strong>{_esc(vm['question_label'])}</strong>
            <span class="spacer"></span>
            <span class="pill {vm['tier_class']}">识别{vm['tier_label']}</span>
          </div>
          <p class="answer-text">{answer}</p>
          <div class="meta-row">
            <span class="skill-tag">{_esc(vm['skill_name'])}</span>
            <span class="pill {vm['grading_class']}">{_esc(vm['grading_result'])}</span>
            <span class="muted small">{_esc(vm['observed_date'])}</span>
          </div>
          <div class="actions">{actions}</div>
        </div>
      </div>
    </article>""")
    intro = (
        '<p class="muted small view-note">'
        '确认的是系统读得对不对；识别可靠度与学生是否掌握无关。</p>'
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
        actions = "".join([
            _icon_btn("check", "确认", demo="已确认", primary=True),
            _icon_btn("pencil", "修改状态", demo="已打开修改状态"),
            _icon_btn("x", "驳回", demo="已驳回", danger=True),
            '<span class="demo-status"></span>',
        ])
        cards.append(f"""
    <article class="card" data-card>
      <div class="card-head">
        <span class="id-chip">{_esc(vm['student_id'])}</span>
        <strong>{_esc(vm['skill_name'])}</strong>
        <span class="spacer"></span>
        {provisional}
        <span class="pill {vm['state_class']}">{_esc(vm['state'])}</span>
      </div>
      <p style="margin:0">{_esc(vm['hypothesis_note'])}</p>
      <p class="muted small" style="margin:4px 0 0">判断把握：{_esc(vm['confidence'])}</p>
      <ul class="evidence-list">{evidence}</ul>
      <div class="actions">{actions}</div>
    </article>""")
    intro = (
        '<p class="muted small view-note">'
        '一次对错只支持待验证假设，状态可随时修正；这里判断的是掌握，'
        '与识别可靠度无关。</p>'
        f'<div class="legend-row">{legend}</div>'
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
    <p class="muted small" style="margin-top:0">共同题统一讲评，其余按各自证据混合。（演示夹具仅列出部分学生）</p>
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
        actions = "".join([
            _icon_btn("check", "通过", demo="已通过", primary=True),
            _icon_btn("swap", "替换", demo="已打开替换"),
            _icon_btn("trash", "移除", demo="已移除", danger=True),
            '<span class="demo-status"></span>',
        ])
        cards.append(f"""
    <article class="card" data-card>
      <div class="card-head">
        <strong class="serif">{_esc(vm['id'])}</strong>
        <span class="pill {vm['category_class']}">{_esc(vm['category'])}</span>
        <span class="spacer"></span>
        <span class="assigned">布置给 {vm['assigned_count']} 位学生</span>
      </div>
      <p class="stem">{_esc(vm['stem'])}</p>
      {figure}
      <div class="answer-row">
        <span class="muted small">参考答案</span>
        <span class="answer-box">{_esc(vm['answer'])}</span>
      </div>
      <details class="q-more">
        <summary>详情 · 目标技能 / 推荐原因 / 解题过程 / 评分说明</summary>
        <dl class="q-fields">
          <div><dt>目标技能</dt><dd>{skills}</dd></div>
          <div><dt>推荐原因</dt><dd>{_esc(vm['recommendation_reason'])}</dd></div>
          <div><dt>预期难度</dt><dd>{_esc(vm['difficulty_label'])}</dd></div>
          <div><dt>解题过程</dt><dd><ol>{steps}</ol></dd></div>
          <div><dt>评分说明</dt><dd>{_esc(vm['scoring_notes'])}</dd></div>
        </dl>
      </details>
      <div class="actions">{actions}</div>
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
        f"<td>{pages} 页</td>"
        f'<td style="text-align:right">'
        f'{_icon_btn("download", "下载", export_fn="export_student_sheet", export_note="单个学生")}'
        f"</td></tr>"
        for sid, pages in vm["students"]
    )
    # Export buttons are inert placeholders in this static demo; each one
    # names the review.export function it will call once wired up:
    #   export_class        -> whole-class batch + teacher key + manifest
    #   export_student_sheet-> one student's sheet
    #   export_teacher_key  -> the separate teacher key (answers + 评分说明)
    # The batch export keeps a visible text label next to its icon: it is
    # the one action whose scope (the whole class, not a row) an icon
    # alone cannot express.
    batch_btn = (
        '<button type="button" class="btn" data-export-fn="export_class" '
        'title="将调用 review.export.export_class（全班批量导出）">'
        f'{_svg(_ACTION_ICONS["download"])}全班批量导出</button>'
    )
    key_btn = _icon_btn(
        "download", "下载教师版",
        export_fn="export_teacher_key", export_note="教师版",
    )
    return f"""
<section class="view" data-cls="{_esc(cls.key)}" data-view="export">
  {_head("导出", f"{cls.label} · 作业 {vm['assignment_number']} · 学生卷与教师版分开导出")}
  <div class="export-grid">
    <article class="card">
      <h3>学生作业 PDF</h3>
      <p class="muted small" style="margin-top:0">每位学生一份，只含题目与答题区。（演示夹具仅列出部分学生）</p>
      <table class="export-table">
        <thead><tr><th>学生</th><th>页数</th><th></th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <div class="actions">{batch_btn}</div>
    </article>
    <article class="card teacher-key-card">
      <h3>教师版（答案与评分说明）</h3>
      <p class="muted">共 {vm['teacher_key_pages']} 页 · 与学生卷分开导出，请勿发给学生。</p>
      <div class="actions">{key_btn}</div>
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
