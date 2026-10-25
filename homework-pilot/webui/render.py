"""Student-side MVP renderer (issue #176; pivots the #167 console).

Renders :class:`~webui.models.StudentData` into ONE self-contained
HTML file -- no external stylesheets, scripts, fonts or images (the
same philosophy as the portfolio dashboard). View switching is a small
vanilla-JS interaction inside the file; the initial view can be set
with ``?view=papers|result|confirm`` (plus ``&paper=<id>``) for
deep-linking. Action buttons are inline-SVG icon buttons (the Chinese
action word lives in ``title`` / ``aria-label`` only) and demo
placeholders (a click stamps the card as handled, client-side only)
until the UI is wired to the pipeline.

The three views, per issue #176:

* ``papers`` -- upload card + the student's paper list with compact
  verdict counts.
* ``result`` -- one paper's per-question verdicts. The verdict chip and
  the recognition-reliability note are rendered as separate elements:
  reliability describes the *read*, never the verdict.
* ``confirm`` -- the 待确认 queue: proposed verdict + confirm /
  edit-transcription / flip actions. Confirmations become labeled
  training data (see the view's footnote).

Design language: the Muse desktop app -- neutral grey paper, white
cards, one charcoal accent (#262626), serif display headings + clean
sans body, fixed left sidebar. Tokens are documented in
``webui/README.md``.
"""

from __future__ import annotations

import html
import sys

from .models import (
    VERDICTS,
    PaperResult,
    QuestionResult,
    StudentData,
)

__all__ = [
    "question_vm",
    "paper_vm",
    "confirm_vm",
    "render_demo",
    "main",
]


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# Presentation maps (verdict -> pill class). Colors live in the CSS below.
# ---------------------------------------------------------------------------

_VERDICT_CLASSES = {
    "对": "verdict-correct",
    "错": "verdict-wrong",
    "待确认": "verdict-pending",
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
.user-row { display: flex; align-items: center; gap: 10px; padding: 0 6px; }
.avatar {
  width: 34px; height: 34px; border-radius: 50%; flex: none;
  background: var(--accent-soft); color: var(--accent-dark);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--serif); font-size: 15px;
}
.user-name { font-size: 14px; line-height: 1.3; }
.user-ctx { font-size: 12px; color: var(--ink-2); }
.privacy-note { font-size: 12px; color: var(--ink-3); padding: 10px 6px 0; }

/* ---- view scaffolding ---- */
.view-head { margin-bottom: 28px; }
.view-head h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: .01em; }
.view-sub { color: var(--ink-2); margin: 0; font-size: 14.5px; }
.head-flex { display: flex; align-items: flex-start; gap: 16px; }
.head-flex .spacer { flex: 1; }
.head-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-top: 10px; }
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
  padding: 24px 26px; margin-bottom: 22px;
}
.card.is-done { opacity: .72; }
.muted { color: var(--ink-2); }
.small { font-size: 13px; }
.demo-status { font-size: 13px; color: var(--sage); margin-left: 6px; }
.back-link {
  display: inline-flex; align-items: center; gap: 6px;
  border: none; background: transparent; padding: 4px 0;
  color: var(--ink-2); font-size: 13.5px; margin-bottom: 10px;
}
.back-link:hover { color: var(--ink); }
.footnote { color: var(--ink-2); font-size: 13px; margin: 4px 0 0; }

/* ---- pills & chips ---- */
.pill {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12.5px; line-height: 1; padding: 5px 10px;
  border-radius: 999px; white-space: nowrap;
}
.verdict-correct { background: var(--sage-soft); color: var(--sage); }
.verdict-wrong { background: var(--red-soft); color: var(--red); }
.verdict-pending { background: var(--amber-soft); color: var(--amber); }
.count-chip { background: var(--gray-soft); color: var(--ink-2); }
.count-chip.verdict-correct { background: var(--sage-soft); color: var(--sage); }
.count-chip.verdict-wrong { background: var(--red-soft); color: var(--red); }
.count-chip.verdict-pending { background: var(--amber-soft); color: var(--amber); }

/* ---- buttons ---- */
.actions { display: flex; align-items: center; gap: 6px; margin-top: 16px;
  flex-wrap: wrap; }
.actions .sep { width: 10px; }
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
/* Labeled text buttons are kept only where an icon alone would be
   ambiguous: a view's single primary action (选择 PDF 文件). */
.btn {
  display: inline-flex; align-items: center; gap: 8px;
  border: 1px solid var(--accent); background: var(--accent); color: #fff;
  font-size: 14px; padding: 10px 18px; border-radius: 10px; min-height: 40px;
}
.btn:hover { background: var(--accent-dark); }

/* ---- papers view ---- */
.upload-card {
  border: 1.5px dashed var(--border-strong); border-radius: var(--radius);
  background: var(--card); padding: 40px 26px; margin-bottom: 30px;
  display: flex; flex-direction: column; align-items: center;
  text-align: center; gap: 6px;
}
.upload-icon { color: var(--ink-3); margin-bottom: 4px; }
.upload-title { font-size: 16.5px; font-weight: 600; }
.upload-sub { color: var(--ink-2); font-size: 13.5px; margin: 0 0 12px; }
.paper-row {
  display: flex; align-items: center; gap: 16px; width: 100%;
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow);
  padding: 20px 24px; margin-bottom: 14px; text-align: left;
  font-size: 15px; color: var(--ink);
}
button.paper-row:hover { border-color: var(--border-strong); }
.paper-row.is-static { box-shadow: none; }
.paper-main { flex: 1; min-width: 0; }
.paper-title { display: block; font-family: var(--serif); font-size: 17px; line-height: 1.4; }
.paper-meta { display: block; color: var(--ink-2); font-size: 13px; margin-top: 2px; }
.paper-counts { display: flex; gap: 6px; flex-wrap: wrap; flex: none; }
.paper-arrow { color: var(--ink-3); flex: none; display: inline-flex; }

/* ---- question rows (result & confirm) ---- */
.q-grid { display: grid; grid-template-columns: 92px 1fr; gap: 18px; }
.img-ph {
  border: 1.5px dashed var(--border-strong); border-radius: 10px;
  background: #FAFAFA; min-height: 72px; padding: 10px 6px;
  display: flex; flex-direction: column; gap: 3px; color: var(--ink-3);
  align-items: center; justify-content: center; text-align: center;
}
.img-ph-loc { font-size: 12px; color: var(--ink-2); }
.img-ph-note { font-size: 12px; color: var(--ink-3); }
.q-head { display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
  margin-bottom: 8px; }
.q-head .spacer { flex: 1; }
.source-label { color: var(--ink-3); font-size: 12.5px; white-space: nowrap; }
.q-text { margin: 0 0 10px; font-size: 15px; }
.answer-line { margin: 0 0 6px; }
.field-label { color: var(--ink-3); font-size: 13px; margin-right: 8px; }
.answer-box { background: var(--sage-soft); border-radius: 8px;
  padding: 4px 10px; display: inline-block; }
.rel-note { color: var(--amber); font-size: 12.5px; }
.proposed-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-top: 10px; }

@media (max-width: 900px) {
  .content { padding: 28px 20px 56px; }
  .q-grid { grid-template-columns: 1fr; }
}
"""

# ---------------------------------------------------------------------------
# View-model builders: models -> plain dicts for the templates.
# ---------------------------------------------------------------------------


def question_vm(q: QuestionResult) -> dict:
    return {
        "number": q.number,
        "label": q.label,
        "question_text": q.question_text,
        "student_answer": q.student_answer,
        "verdict": q.verdict,
        "verdict_class": _VERDICT_CLASSES[q.verdict],
        "source": q.source,
        "source_label": f"来源：{q.source}",
        "proposed_verdict": q.proposed_verdict,
        "proposed_class": _VERDICT_CLASSES.get(q.proposed_verdict, ""),
        "reference_answer": q.reference_answer,
        # In the result view, 参考答案 is shown once a question has
        # been judged 错. (confirm_vm widens this for the queue.)
        "show_reference": bool(q.reference_answer) and q.verdict == "错",
        # Reliability is exposed on its own, never folded into the
        # verdict fields above.
        "low_reliability": q.low_reliability,
        "image_location": q.image_location,
        "page_label": q.page_label,
    }


def paper_vm(paper: PaperResult) -> dict:
    counts = paper.verdict_counts()
    return {
        "id": paper.id,
        "title": paper.title,
        "date_label": paper.date_label,
        "status": paper.status,
        "counts": counts,
        "count_chips": [
            (verdict, counts[verdict], _VERDICT_CLASSES[verdict])
            for verdict in VERDICTS
            if counts[verdict]
        ],
        "total": len(paper.questions),
        "pending_count": counts["待确认"],
        "questions": [question_vm(q) for q in paper.questions],
    }


def confirm_vm(paper: PaperResult, q: QuestionResult) -> dict:
    vm = question_vm(q)
    # In the queue, a proposed 错 also shows its 参考答案 so the student
    # can judge the proposal before confirming or flipping it.
    vm["show_reference"] = bool(q.reference_answer) and (
        q.verdict == "错" or q.proposed_verdict == "错"
    )
    vm["paper_id"] = paper.id
    vm["paper_title"] = paper.title
    return vm


# ---------------------------------------------------------------------------
# Icons: inline SVG (24x24 viewBox, stroke style). Nav icons render at
# 18px; action icons at 18px inside 38px buttons.
# ---------------------------------------------------------------------------

_NAV_ICONS = {
    "papers": (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8"><rect x="5" y="4.5" '
        'width="14" height="17" rx="2"/><path d="M9 4.5V3h6v1.5M9.5 13.5l2 '
        '2 3.5-4"/></svg>'
    ),
    "confirm": (
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8"><path d="M4 8V5.5A1.5 1.5 '
        '0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 '
        '0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16M3.5 12h17"/></svg>'
    ),
}

_ACTION_ICONS = {
    "upload": (
        '<path d="M12 16V5"/><path d="M7 9l5-5 5 5"/>'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
    ),
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "x": '<path d="M18 6L6 18M6 6l12 12"/>',
    "pencil": (
        '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>'
    ),
    "download": (
        '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/>'
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
    ),
    "arrow-right": '<path d="M5 12h14"/><path d="M12 5l7 7-7 7"/>',
    "arrow-left": '<path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>',
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
    export_fn: str | None = None,
) -> str:
    """One icon-only action button.

    ``label`` is the Chinese action word; it appears only in ``title``
    (tooltip) and ``aria-label``. Demo buttons stamp their card via
    ``data-demo``; export buttons stay inert and name the future
    backend hand-off in the title.
    """
    cls = "icon-btn primary" if primary else "icon-btn"
    if export_fn:
        title = f"{label} · 将导出已确认的转写与判定标注（演示）"
        action = f'data-export-fn="{export_fn}"'
    else:
        title = label
        action = f'data-demo="{_esc(demo or "")}"'
    return (
        f'<button type="button" class="{cls}" {action} '
        f'title="{_esc(title)}" aria-label="{_esc(label)}">'
        f"{_svg(_ACTION_ICONS[icon])}</button>"
    )


# ---------------------------------------------------------------------------
# Section templates (one <section> per view; result is per paper).
# ---------------------------------------------------------------------------

_VIEWS = (
    ("papers", "试卷"),
    ("confirm", "待确认"),
)


def _chips(vm: dict) -> str:
    return "".join(
        f'<span class="pill count-chip {css}">{_esc(v)} {n}</span>'
        for v, n, css in vm["count_chips"]
    )


def _crop_strip(vm: dict) -> str:
    return f"""
        <div class="img-ph">
          {_svg(_ACTION_ICONS["image"], 22)}
          <div class="img-ph-loc">{_esc(vm['page_label'])}</div>
          <div class="img-ph-note">原图待接入</div>
        </div>"""


def _rel_note(vm: dict) -> str:
    if not vm["low_reliability"]:
        return ""
    return '<span class="rel-note">识别可靠性低</span>'


def _papers_section(data: StudentData) -> str:
    rows = []
    for paper in data.papers:
        vm = paper_vm(paper)
        meta = f"{vm['date_label']} · {vm['status']}"
        if vm["status"] == "处理中":
            rows.append(f"""
    <div class="paper-row is-static">
      <div class="paper-main">
        <div class="paper-title">{_esc(vm['title'])}</div>
        <div class="paper-meta">{_esc(meta)}</div>
      </div>
      <span class="muted small">处理中</span>
    </div>""")
        else:
            rows.append(f"""
    <button type="button" class="paper-row" data-open-paper="{_esc(vm['id'])}">
      <span class="paper-main">
        <span class="paper-title">{_esc(vm['title'])}</span>
        <span class="paper-meta">{_esc(meta)} · 共 {vm['total']} 题</span>
      </span>
      <span class="paper-counts">{_chips(vm)}</span>
      <span class="paper-arrow">{_svg(_ACTION_ICONS["arrow-right"], 18)}</span>
    </button>""")
    upload_btn = (
        '<button type="button" class="btn" data-demo="已选择文件">'
        f'{_svg(_ACTION_ICONS["upload"])}选择 PDF 文件</button>'
    )
    return f"""
<section class="view" data-view="papers">
  <header class="view-head"><h1>试卷</h1>
    <p class="view-sub">{_esc(data.student_id)} · 上传做完的试卷，看每道题的判定。</p></header>
  <div class="upload-card" data-card>
    <span class="upload-icon">{_svg(_ACTION_ICONS["upload"], 30)}</span>
    <div class="upload-title">上传已完成试卷（扫描 PDF）</div>
    <p class="upload-sub">一页一页扫好的 PDF 即可，系统会逐题给出判定。</p>
    <div>{upload_btn}<span class="demo-status"></span></div>
  </div>
  {''.join(rows)}
</section>"""


def _result_section(paper: PaperResult) -> str:
    vm = paper_vm(paper)
    export_btn = _icon_btn("download", "导出标注", export_fn="export_labeled_data")
    rows = []
    for q in vm["questions"]:
        reference = ""
        if q["show_reference"]:
            reference = (
                f'<p class="answer-line"><span class="field-label">参考答案</span>'
                f'<span class="answer-box">{_esc(q["reference_answer"])}</span></p>'
            )
        rel = _rel_note(q)
        rel_line = f'<p class="answer-line">{rel}</p>' if rel else ""
        rows.append(f"""
    <article class="card" style="padding:20px 24px">
      <div class="q-grid">
        {_crop_strip(q)}
        <div>
          <div class="q-head">
            <strong>{_esc(q['label'])}</strong>
            <span class="pill {q['verdict_class']}">{_esc(q['verdict'])}</span>
            <span class="spacer"></span>
            <span class="source-label">{_esc(q['source_label'])}</span>
          </div>
          <p class="q-text">{_esc(q['question_text'])}</p>
          <p class="answer-line"><span class="field-label">学生答案</span>{_esc(q['student_answer'])}</p>
          {reference}
          {rel_line}
        </div>
      </div>
    </article>""")
    body = "\n".join(rows) if rows else '<div class="card"><p class="muted">这份试卷还没有判定结果。</p></div>'
    return f"""
<section class="view" data-view="result" data-paper="{_esc(vm['id'])}">
  <button type="button" class="back-link" data-nav-view="papers">{_svg(_ACTION_ICONS["arrow-left"], 15)}全部试卷</button>
  <header class="view-head">
    <div class="head-flex">
      <h1>{_esc(vm['title'])}</h1>
      <span class="spacer"></span>
      {export_btn}
    </div>
    <div class="head-meta">{_chips(vm)}<span class="muted small">{_esc(vm['date_label'])} · 共 {vm['total']} 题</span></div>
  </header>
  {body}
</section>"""


def _confirm_section(data: StudentData) -> str:
    items = data.pending_items()
    cards = []
    for paper, q in items:
        vm = confirm_vm(paper, q)
        reference = ""
        if vm["show_reference"]:
            reference = (
                f'<p class="answer-line"><span class="field-label">参考答案</span>'
                f'<span class="answer-box">{_esc(vm["reference_answer"])}</span></p>'
            )
        rel = _rel_note(vm)
        rel_line = f" {rel}" if rel else ""
        actions = "".join([
            _icon_btn("check", "确认", demo="已确认", primary=True),
            _icon_btn("pencil", "改转写", demo="已打开修改转写"),
            '<span class="sep"></span>',
            _icon_btn("check", "改为对", demo="已改为对"),
            _icon_btn("x", "改为错", demo="已改为错"),
            '<span class="demo-status"></span>',
        ])
        cards.append(f"""
    <article class="card" data-card>
      <div class="q-grid">
        {_crop_strip(vm)}
        <div>
          <div class="q-head">
            <strong>{_esc(vm['label'])}</strong>
            <span class="muted small">{_esc(vm['paper_title'])}</span>
            <span class="spacer"></span>
            <span class="source-label">{_esc(vm['source_label'])}</span>
          </div>
          <p class="q-text">{_esc(vm['question_text'])}</p>
          <p class="answer-line"><span class="field-label">学生答案</span>{_esc(vm['student_answer'])}</p>
          {reference}
          <div class="proposed-row">
            <span class="field-label">系统倾向</span>
            <span class="pill {vm['proposed_class']}">{_esc(vm['proposed_verdict'])}</span>{rel_line}
          </div>
          <div class="actions">{actions}</div>
        </div>
      </div>
    </article>""")
    body = "\n".join(cards) if cards else '<div class="card"><p class="muted">没有待确认的题目。</p></div>'
    return f"""
<section class="view" data-view="confirm">
  <header class="view-head"><h1>待确认</h1>
    <p class="view-sub">共 {len(items)} 道题需要你确认判定或转写。</p></header>
  {body}
  <p class="footnote">你确认过的判定与转写会保存为标注数据，用于改进之后的识别与判定。</p>
</section>"""


_JS_TEMPLATE = """
var params = new URLSearchParams(window.location.search);
var state = {
  view: params.get("view") || "papers",
  paper: params.get("paper") || "__DEFAULT_PAPER__"
};
var NAV_OF = { papers: "papers", result: "papers", confirm: "confirm" };
function show() {
  document.querySelectorAll("section.view").forEach(function (s) {
    var v = s.getAttribute("data-view");
    var ok = (v === state.view) &&
      (v !== "result" || s.getAttribute("data-paper") === state.paper);
    s.hidden = !ok;
  });
  document.querySelectorAll("[data-nav-view]").forEach(function (b) {
    b.classList.toggle("is-active",
      NAV_OF[state.view] === b.getAttribute("data-nav-view"));
  });
  window.scrollTo(0, 0);
}
document.querySelectorAll("[data-nav-view]").forEach(function (b) {
  b.addEventListener("click", function () {
    state.view = b.getAttribute("data-nav-view"); show();
  });
});
document.querySelectorAll("[data-open-paper]").forEach(function (b) {
  b.addEventListener("click", function () {
    state.paper = b.getAttribute("data-open-paper");
    state.view = "result"; show();
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


def render_demo(data: StudentData) -> str:
    """Render the student-side demo as one self-contained HTML document."""
    if not data.papers:
        raise ValueError("demo needs at least one paper")
    pending_count = len(data.pending_items())
    default_paper = next(
        (p.id for p in data.papers if p.questions), data.papers[0].id)

    nav_items = []
    for view, label in _VIEWS:
        badge_html = ""
        if view == "confirm" and pending_count:
            badge_html = f'<span class="nav-badge">{pending_count}</span>'
        active = " is-active" if view == "papers" else ""
        nav_items.append(
            f'<button type="button" class="nav-item{active}" '
            f'data-nav-view="{view}">{_NAV_ICONS[view]}<span>{label}</span>'
            f"{badge_html}</button>"
        )

    sections = [_papers_section(data)]
    sections.extend(
        _result_section(paper) for paper in data.papers if paper.questions
    )
    sections.append(_confirm_section(data))
    sections_html = "\n".join(sections)

    js = _JS_TEMPLATE.replace("__DEFAULT_PAPER__", default_paper)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>个性化作业 · 学生端</title>
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
      <div class="brand-sub">学生端 · 试卷自查</div>
    </div>
  </div>
  <nav class="nav">{''.join(nav_items)}</nav>
  <div class="sidebar-foot">
    <div class="user-row">
      <div class="avatar">S</div>
      <div>
        <div class="user-name">学生 {_esc(data.student_id)}</div>
        <div class="user-ctx">{_esc(data.student_context)}</div>
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
    """Render the student-side demo to an HTML file.

    Usage (from ``homework-pilot/``): ``python3 -m webui [output.html]``
    -- defaults to ``student-mvp.html`` in the current directory.
    """
    from .fixtures import build_demo_data

    args = sys.argv[1:] if argv is None else argv
    out = args[0] if args else "student-mvp.html"
    document = render_demo(build_demo_data())
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(document)
    print(f"wrote {out} ({len(document)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
