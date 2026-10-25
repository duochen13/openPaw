"""Local web server for the student-side MVP (issue #179).

The static demo (``python3 -m webui``) renders one self-contained HTML
file over invented fixtures. This module is the runtime the product
loop actually needs, connecting the pieces that already exist:

    webui views  <->  grading pipeline (#176)  <->  grading.confirm store

Run it from ``homework-pilot/``::

    python3 -m webui --serve [--port 8000]

It binds **127.0.0.1 only** by default: a single-student local tool,
no accounts, no auth, no deployment story. Everything is stdlib
(``http.server.ThreadingHTTPServer``); there is no build step and the
static render path is untouched.

Routes (deliberately small):

* ``GET /`` -- papers list （试卷） from the local store + upload form.
* ``POST /papers`` -- multipart PDF upload -> grade -> store -> 303 to
  the results page.
* ``GET /papers/<id>`` -- results （结果） for one stored paper.
* ``GET /confirm`` -- the confirmation queue （待确认） across papers,
  one POST form per item.
* ``POST /confirm`` -- confirm a proposal / override a verdict / fix a
  transcription, persisted via :func:`grading.confirm.apply_confirmation`.
* ``GET /export`` -- every confirmed item across papers as a JSONL
  download (the labeled examples of :mod:`grading.confirm`).

Data lives in ``homework-pilot/.local-data/`` (gitignored): one JSON
record per paper under ``papers/``, the uploaded file under
``uploads/``. Every record passes ``privacy.guard.assert_id_only``
before it is written: students are IDs only, and the client's original
filename is never stored (it could carry a name).

How v1 grades an upload -- stated plainly, because the backends are
test doubles: the v1 segmentation/transcription backends are the
synthetic kit's deterministic ones (see :mod:`grading.backends`), so
an upload is graded **by student ID through the kit path**
(:func:`grading.pipeline.grade_kit_paper`). For a kit student
(S-001..S-005) the verdicts are exactly the pipeline output for that
student's kit paper; the uploaded bytes are stored for provenance and
hash-compared against the kit's ``paper.pdf`` -- the results page says
whether they matched, and says the grading came from the kit records
when they did not. For any other student ID the upload is stored as
**未识别 (unrecognized)**: v1 cannot read an arbitrary scan, so nothing
is segmented and nothing is judged -- no verdicts are invented. Inside
a kit paper, the pipeline's own honesty rule applies unchanged:
anything unreadable or undecidable lands in 待确认 with a reason.

The results page renders stored ``ItemResult`` records directly
rather than through :mod:`grading.adapter`: the adapter intentionally
refuses no-proposal pending items and post-confirmation records (the
demo model cannot represent them), while the server must show every
stored item -- including the manual-verdict queue state for pending
items with no system lean, which the confirm form below provides.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .render import (
    CSS,
    _ACTION_ICONS,
    _VERDICT_CLASSES,
    _crop_strip,
    _esc,
    _rel_note,
    _svg,
)

HOMEWORK_PILOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = HOMEWORK_PILOT / ".local-data"
DEFAULT_KIT_DIR = HOMEWORK_PILOT / "pilot-kit"

#: Upload bodies are PDFs of a few pages; anything past this is refused.
MAX_BODY_BYTES = 32 * 1024 * 1024

#: Student IDs in this project look like ``S-001`` -- an ID, never a name.
STUDENT_ID_RE = re.compile(r"^S-\d{3}$")

#: Status for an upload the v1 backends cannot read (see module docs).
UNRECOGNIZED_STATUS = "未识别"

_PAGE_ID_RE = re.compile(r"^S-\d{3}-\d{2,}$")


def _deps():
    """Import the sibling packages lazily (the grading.confirm pattern).

    ``grading`` / ``privacy`` are sibling top-level packages run from
    ``homework-pilot/``; inserting that dir on ``sys.path`` here keeps
    this module importable from anywhere the webui package is.
    """
    if str(HOMEWORK_PILOT) not in sys.path:
        sys.path.insert(0, str(HOMEWORK_PILOT))
    from grading import confirm as grading_confirm
    from grading.backends import load_kit_manifest
    from grading.models import PENDING_REASONS, GradedPaper, ItemResult
    from grading.pipeline import grade_kit_paper
    from privacy.guard import NameFieldError, assert_id_only

    return {
        "apply_confirmation": grading_confirm.apply_confirmation,
        "export_labeled_examples": grading_confirm.export_labeled_examples,
        "load_kit_manifest": load_kit_manifest,
        "PENDING_REASONS": PENDING_REASONS,
        "GradedPaper": GradedPaper,
        "ItemResult": ItemResult,
        "grade_kit_paper": grade_kit_paper,
        "NameFieldError": NameFieldError,
        "assert_id_only": assert_id_only,
    }


# ---------------------------------------------------------------------------
# Serialization: GradedPaper <-> JSON record
# ---------------------------------------------------------------------------


def _paper_from_record(record: dict):
    deps = _deps()
    items = []
    for raw in record.get("items", []):
        raw = dict(raw)
        raw["skill_ids"] = tuple(raw.get("skill_ids") or ())
        items.append(deps["ItemResult"](**raw))
    return deps["GradedPaper"](
        student_id=record["student_id"],
        assignment_id=record.get("assignment_id", ""),
        title=record.get("title", ""),
        date_label=record.get("date_label", ""),
        status=record.get("status", "已出结果"),
        items=tuple(items),
    )


# ---------------------------------------------------------------------------
# Store: one JSON record per paper + the uploaded file, on disk
# ---------------------------------------------------------------------------


class PaperStore:
    """File-backed store for graded papers (the server's persistence).

    Records are re-read from disk on every access, so a confirmation
    written by one server process is visible to the next -- that is
    what "survives a restart" means here, and the tests exercise it by
    reloading through a fresh store (and a fresh server) on the same
    directory.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.papers_dir = self.root / "papers"
        self.uploads_dir = self.root / "uploads"
        self.papers_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _record_path(self, paper_id: str) -> Path:
        return self.papers_dir / f"{paper_id}.json"

    def add_paper(self, paper, upload_meta: dict, content: bytes) -> str:
        """Store a fresh upload end to end; returns its new paper ID."""
        with self._lock:
            n = 1
            while self._record_path(f"{paper.student_id}-{n:02d}").exists():
                n += 1
            paper_id = f"{paper.student_id}-{n:02d}"
            self.save_upload(paper_id, content)
            self.save(paper_id, paper, upload_meta)
            return paper_id

    def save(self, paper_id: str, paper, upload_meta: dict) -> None:
        """Persist a paper. The record must pass the ID-only guard."""
        record = {
            "paper_id": paper_id,
            "upload": dict(upload_meta),
            "paper": asdict(paper),
        }
        _deps()["assert_id_only"](record, where="stored paper")
        path = self._record_path(paper_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(record, ensure_ascii=False, indent=1), "utf-8"
        )
        os.replace(tmp, path)

    def save_upload(self, paper_id: str, content: bytes) -> None:
        (self.uploads_dir / f"{paper_id}.pdf").write_bytes(content)

    def load(self, paper_id: str):
        """Return ``(paper, upload_meta)`` or None for an unknown ID."""
        path = self._record_path(paper_id)
        if not path.exists():
            return None
        record = json.loads(path.read_text("utf-8"))
        return _paper_from_record(record["paper"]), record.get("upload", {})

    def list(self) -> list:
        """All stored papers as ``(paper_id, paper, upload_meta)``,
        oldest upload first."""
        out = []
        for path in sorted(self.papers_dir.glob("*.json")):
            loaded = self.load(path.stem)
            if loaded is not None:
                out.append((path.stem, loaded[0], loaded[1]))
        out.sort(key=lambda row: row[2].get("uploaded_at", ""))
        return out

    def confirm(self, paper_id: str, item_key: str, **kwargs):
        """Apply one student confirmation and persist the new paper."""
        with self._lock:
            loaded = self.load(paper_id)
            if loaded is None:
                raise KeyError(f"unknown paper {paper_id!r}")
            paper, meta = loaded
            updated = _deps()["apply_confirmation"](paper, item_key, **kwargs)
            self.save(paper_id, updated, meta)
            return updated

    def export_jsonl(self) -> str:
        """All confirmed items across papers, one JSON object per line."""
        examples = []
        for _paper_id, paper, _meta in self.list():
            examples.extend(_deps()["export_labeled_examples"](paper))
        lines = [json.dumps(e, ensure_ascii=False) for e in examples]
        return "\n".join(lines) + ("\n" if lines else "")


# ---------------------------------------------------------------------------
# App: grading uploads through the kit-backed test-double path
# ---------------------------------------------------------------------------


class StudentApp:
    """Holds the store + kit manifest; grades uploads (see module docs)."""

    def __init__(self, store: PaperStore, kit_dir: Path) -> None:
        self.store = store
        self.kit_dir = Path(kit_dir)
        self.kit_students: set[str] = set()
        manifest = self.kit_dir / "papers" / "manifest.json"
        if manifest.exists():
            entries = _deps()["load_kit_manifest"](self.kit_dir)
            self.kit_students = {p["student_id"] for p in entries}

    def grade_upload(self, student_id: str, content: bytes):
        """Grade one uploaded PDF; returns ``(paper, upload_meta)``."""
        deps = _deps()
        digest = hashlib.sha256(content).hexdigest()
        matches = False
        if student_id in self.kit_students:
            kit_pdf = self.kit_dir / "papers" / student_id / "paper.pdf"
            if kit_pdf.exists():
                matches = hashlib.sha256(kit_pdf.read_bytes()).hexdigest() == digest
            paper = deps["grade_kit_paper"](self.kit_dir, student_id)
        else:
            # v1 cannot read an arbitrary scan: store the upload, judge
            # nothing. An empty, explicitly-unrecognized paper -- never
            # a fabricated question list with guessed verdicts.
            paper = deps["GradedPaper"](
                student_id=student_id,
                title="上传的试卷",
                status=UNRECOGNIZED_STATUS,
                items=(),
            )
        meta = {
            "sha256": digest,
            "matches_kit_paper": matches,
            "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return paper, meta


# ---------------------------------------------------------------------------
# View helpers: ItemResult -> the same dict shape webui.render consumes
# ---------------------------------------------------------------------------


def _item_vm(item) -> dict:
    reasons = _deps()["PENDING_REASONS"]
    return {
        "item_key": item.item_key,
        "number": item.number,
        "label": f"第{item.number}题",
        "question_text": item.question_text,
        "student_answer": item.student_answer,
        "verdict": item.verdict,
        "verdict_class": _VERDICT_CLASSES[item.verdict],
        "source": item.source,
        "source_label": f"来源：{item.source}",
        "proposed_verdict": item.proposed_verdict,
        "proposed_class": _VERDICT_CLASSES.get(item.proposed_verdict, ""),
        "reference_answer": item.reference_answer,
        "show_reference": bool(item.reference_answer) and item.verdict == "错",
        "low_reliability": item.is_low_reliability,
        "image_location": item.image_location,
        "page_label": item.page_label,
        "pending_reason_label": reasons.get(item.pending_reason, ""),
        "confirmed": item.confirmed,
        "needs_transcription_confirmation": item.needs_transcription_confirmation,
        "in_queue": item.in_confirmation_queue,
    }


def _counts(paper) -> dict:
    counts = {"对": 0, "错": 0, "待确认": 0}
    for item in paper.items:
        counts[item.verdict] += 1
    return counts


def _chips(counts: dict) -> str:
    return "".join(
        f'<span class="pill count-chip {_VERDICT_CLASSES[v]}">{_esc(v)} {n}</span>'
        for v, n in counts.items()
        if n
    )


def _queue_total(app: StudentApp) -> int:
    return sum(
        len(paper.confirmation_queue()) for _id, paper, _m in app.store.list()
    )


# ---------------------------------------------------------------------------
# Pages (server-rendered; same design tokens as the static demo)
# ---------------------------------------------------------------------------

_SERVE_CSS = """
a.paper-row { text-decoration: none; }
.text-input {
  font: inherit; font-size: 14px; color: var(--ink);
  border: 1px solid var(--border-strong); border-radius: 10px;
  background: #fff; padding: 9px 12px; min-height: 40px;
}
.text-input:focus { outline: 2px solid var(--accent-soft); }
.upload-form-fields {
  display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;
  align-items: center; margin-top: 6px;
}
.field-label-inline { font-size: 13.5px; color: var(--ink-2); }
.btn.secondary { background: #fff; color: var(--ink); border-color: var(--border-strong); }
.btn.secondary:hover { background: var(--paper); }
.notice {
  border: 1px solid var(--border); border-left: 3px solid var(--amber);
  background: var(--amber-soft); border-radius: 10px;
  padding: 12px 16px; font-size: 13.5px; margin-bottom: 22px;
}
.confirm-form { margin-top: 14px; border-top: 1px solid var(--border); padding-top: 14px; }
.confirm-form .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 10px; }
.confirm-form .text-input { flex: 1; min-width: 220px; }
.form-note { font-size: 12.5px; color: var(--ink-3); margin: 6px 0 0; }
"""


def _shell(app: StudentApp, title: str, body: str) -> str:
    queue = _queue_total(app)
    badge = f'<span class="nav-badge">{queue}</span>' if queue else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} · 个性化作业</title>
<style>{CSS}{_SERVE_CSS}</style>
</head>
<body>
<aside class="sidebar">
  <div class="brand">
    <div class="logo-mark"><svg width="18" height="18" viewBox="0 0 24 24"
      fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round">
      <path d="M12 3.5v17M4.6 7.8l14.8 8.4M19.4 7.8L4.6 16.2"/></svg></div>
    <div>
      <div class="brand-name">个性化作业</div>
      <div class="brand-sub">学生端 · 试卷自查（本地服务）</div>
    </div>
  </div>
  <nav class="nav">
    <a class="nav-item" href="/">{_svg(_ACTION_ICONS["image"])}<span>试卷</span></a>
    <a class="nav-item" href="/confirm">{_svg(_ACTION_ICONS["check"])}<span>待确认</span>{badge}</a>
    <a class="nav-item" href="/export">{_svg(_ACTION_ICONS["download"])}<span>导出标注</span></a>
  </nav>
  <div class="sidebar-foot">
    <div class="privacy-note">本地服务 · 仅本机访问 · 学生仅以编号显示，系统不保存姓名</div>
  </div>
</aside>
<main class="main">
  <div class="content">
{body}
  </div>
</main>
</body>
</html>
"""


def _papers_page(app: StudentApp) -> str:
    rows = []
    for paper_id, paper, meta in app.store.list():
        counts = _counts(paper)
        date_label = (meta.get("uploaded_at") or "")[:10]
        if paper.status == UNRECOGNIZED_STATUS:
            meta_line = f"{paper.student_id} · {date_label} · 未识别（v1 无法读取这份扫描）"
            chips = ""
        else:
            meta_line = (
                f"{paper.student_id} · {date_label} · {paper.status}"
                f" · 共 {len(paper.items)} 题"
            )
            chips = _chips(counts)
        rows.append(f"""
    <a class="paper-row" href="/papers/{_esc(paper_id)}">
      <span class="paper-main">
        <span class="paper-title">{_esc(paper.title)}</span>
        <span class="paper-meta">{_esc(meta_line)}</span>
      </span>
      <span class="paper-counts">{chips}</span>
      <span class="paper-arrow">{_svg(_ACTION_ICONS["arrow-right"], 18)}</span>
    </a>""")
    listing = "".join(rows) if rows else (
        '<div class="card"><p class="muted">还没有上传的试卷。'
        "用上面的表单上传第一份吧。</p></div>"
    )
    body = f"""
<header class="view-head"><h1>试卷</h1>
  <p class="view-sub">上传做完的试卷（扫描 PDF），系统会逐题给出判定。</p></header>
<form class="upload-card" method="post" action="/papers" enctype="multipart/form-data">
  <span class="upload-icon">{_svg(_ACTION_ICONS["upload"], 30)}</span>
  <div class="upload-title">上传已完成试卷（扫描 PDF）</div>
  <p class="upload-sub">v1 的判定来自合成试卷包的测试替身后端：按学生编号匹配试卷包
  （S-001…S-005），其他编号的扫描会被存档并标记为未识别，不做判定。</p>
  <div class="upload-form-fields">
    <label class="field-label-inline" for="f-student">学生编号</label>
    <input class="text-input" id="f-student" type="text" name="student_id"
      placeholder="S-001" required pattern="S-[0-9]{{3}}">
    <input class="text-input" type="file" name="file" accept="application/pdf,.pdf" required>
    <button type="submit" class="btn">{_svg(_ACTION_ICONS["upload"])}上传并判定</button>
  </div>
</form>
{listing}"""
    return _shell(app, "试卷", body)


def _result_page(app: StudentApp, paper_id: str, paper, meta: dict) -> str:
    counts = _counts(paper)
    date_label = (meta.get("uploaded_at") or "")[:10]
    banners = []
    if paper.status == UNRECOGNIZED_STATUS:
        banners.append(
            '<div class="notice">这份上传已存档并标记为「未识别」：v1 的测试替身'
            "后端只认识合成试卷包（S-001…S-005）的试卷，无法读取这份扫描——"
            "没有做任何切分或判定，也没有猜测任何结果。"
            "真实的识别后端接入后，这里会给出逐题判定。</div>"
        )
    elif meta.get("matches_kit_paper"):
        banners.append(
            '<div class="notice">上传文件与试卷包原件一致，'
            "下面的判定是管线对这份试卷的输出。</div>"
        )
    else:
        banners.append(
            '<div class="notice">上传文件与试卷包原件不一致：v1 的判定来自'
            "试卷包的识别记录（测试替身后端），不是对这份文件的实时识别。</div>"
        )
    rows = []
    for item in paper.items:
        vm = _item_vm(item)
        reference = ""
        if vm["show_reference"]:
            reference = (
                f'<p class="answer-line"><span class="field-label">参考答案</span>'
                f'<span class="answer-box">{_esc(vm["reference_answer"])}</span></p>'
            )
        rel = _rel_note(vm)
        rel_line = f'<p class="answer-line">{rel}</p>' if rel else ""
        pending = ""
        if vm["verdict"] == "待确认":
            pending = (
                f'<p class="answer-line"><span class="field-label">待确认</span>'
                f'{_esc(vm["pending_reason_label"])}</p>'
            )
        rows.append(f"""
    <article class="card" style="padding:20px 24px" data-item-key="{_esc(vm['item_key'])}">
      <div class="q-grid">
        {_crop_strip(vm)}
        <div>
          <div class="q-head">
            <strong>{_esc(vm['label'])}</strong>
            <span class="pill {vm['verdict_class']}">{_esc(vm['verdict'])}</span>
            <span class="spacer"></span>
            <span class="source-label">{_esc(vm['source_label'])}</span>
          </div>
          <p class="q-text">{_esc(vm['question_text'])}</p>
          <p class="answer-line"><span class="field-label">学生答案</span>{_esc(vm['student_answer'])}</p>
          {reference}
          {pending}
          {rel_line}
        </div>
      </div>
    </article>""")
    body_rows = "\n".join(rows) if rows else (
        '<div class="card"><p class="muted">这份试卷还没有判定结果。</p></div>'
    )
    body = f"""
<a class="back-link" href="/">{_svg(_ACTION_ICONS["arrow-left"], 15)}全部试卷</a>
<header class="view-head">
  <div class="head-flex">
    <h1>{_esc(paper.title)}</h1>
    <span class="spacer"></span>
    <a class="icon-btn" href="/export" title="导出标注" aria-label="导出标注">{_svg(_ACTION_ICONS["download"])}</a>
  </div>
  <div class="head-meta">{_chips(counts)}<span class="muted small">{_esc(paper.student_id)} · {_esc(date_label)} · 共 {len(paper.items)} 题</span></div>
</header>
{''.join(banners)}
{body_rows}"""
    return _shell(app, paper.title, body)


def _confirm_page(app: StudentApp) -> str:
    groups = []
    total = 0
    for paper_id, paper, _meta in app.store.list():
        queue = paper.confirmation_queue()
        if not queue:
            continue
        total += len(queue)
        cards = []
        for item in queue:
            vm = _item_vm(item)
            reference = ""
            if vm["reference_answer"] and (
                vm["verdict"] == "错" or vm["proposed_verdict"] == "错"
            ):
                reference = (
                    f'<p class="answer-line"><span class="field-label">参考答案</span>'
                    f'<span class="answer-box">{_esc(vm["reference_answer"])}</span></p>'
                )
            rel = _rel_note(vm)
            rel_line = f" {rel}" if rel else ""
            if vm["verdict"] == "待确认":
                if vm["proposed_verdict"]:
                    proposal = (
                        f'<span class="pill {vm["proposed_class"]}">'
                        f'{_esc(vm["proposed_verdict"])}</span>'
                    )
                    accept_btn = (
                        f'<button type="submit" class="btn" name="action" '
                        f'value="accept">确认系统倾向（{_esc(vm["proposed_verdict"])}）</button>'
                    )
                else:
                    # No source could lean: the manual-verdict state --
                    # the student decides directly, no proposal exists
                    # to confirm (the PR #178 gap, in minimal form).
                    proposal = '<span class="muted">无（系统无法给出倾向，请直接判定）</span>'
                    accept_btn = ""
                proposed_row = f"""
          <div class="proposed-row">
            <span class="field-label">系统倾向</span>{proposal}{rel_line}
          </div>
          <p class="answer-line"><span class="field-label">待确认原因</span>{_esc(vm['pending_reason_label'])}</p>"""
                actions = f"""
            {accept_btn}
            <button type="submit" class="btn secondary" name="action" value="right">判为对</button>
            <button type="submit" class="btn secondary" name="action" value="wrong">判为错</button>"""
                ref_row = f"""
          <div class="row">
            <label class="field-label-inline" for="ref-{_esc(paper_id)}-{_esc(vm['item_key'])}">参考答案（判为错时必填）</label>
            <input class="text-input" id="ref-{_esc(paper_id)}-{_esc(vm['item_key'])}" type="text"
              name="reference_answer" value="{_esc(vm['reference_answer'])}">
          </div>"""
            else:
                proposed_row = ""
                actions = """
            <button type="submit" class="btn" name="action" value="fix">保存转写修正</button>"""
                ref_row = ""
            cards.append(f"""
    <article class="card" data-item-key="{_esc(vm['item_key'])}">
      <div class="q-grid">
        {_crop_strip(vm)}
        <div>
          <div class="q-head">
            <strong>{_esc(vm['label'])}</strong>
            <span class="muted small">{_esc(paper.title)} · {_esc(vm['item_key'])}</span>
            <span class="spacer"></span>
            <span class="source-label">{_esc(vm['source_label'])}</span>
          </div>
          <p class="q-text">{_esc(vm['question_text'])}</p>
          <p class="answer-line"><span class="field-label">学生答案</span>{_esc(vm['student_answer'])}</p>
          {reference}
          {proposed_row}
          <form class="confirm-form" method="post" action="/confirm">
            <input type="hidden" name="paper_id" value="{_esc(paper_id)}">
            <input type="hidden" name="item_key" value="{_esc(vm['item_key'])}">
            <div class="row">
              <label class="field-label-inline" for="corr-{_esc(paper_id)}-{_esc(vm['item_key'])}">转写（可修正）</label>
              <input class="text-input" id="corr-{_esc(paper_id)}-{_esc(vm['item_key'])}" type="text"
                name="corrected_answer" value="{_esc(vm['student_answer'])}">
            </div>
            {ref_row}
            <div class="row">{actions}</div>
          </form>
        </div>
      </div>
    </article>""")
        groups.append(
            f'<h2 class="serif">{_esc(paper.title)}'
            f' <span class="muted small">{_esc(paper.student_id)} · '
            f'<a href="/papers/{_esc(paper_id)}">查看结果</a></span></h2>'
            + "\n".join(cards)
        )
    body_content = "\n".join(groups) if groups else (
        '<div class="card"><p class="muted">没有待确认的题目。</p></div>'
    )
    body = f"""
<header class="view-head"><h1>待确认</h1>
  <p class="view-sub">共 {total} 道题需要你确认判定或转写。</p></header>
{body_content}
<p class="footnote">你确认过的判定与转写会保存为标注数据，用于改进之后的识别与判定（侧栏「导出标注」可下载 JSONL）。</p>"""
    return _shell(app, "待确认", body)


def _error_page(app: StudentApp, status: int, message: str) -> str:
    body = f"""
<header class="view-head"><h1>{status}</h1></header>
<div class="card"><p>{_esc(message)}</p>
<p><a href="/">回到试卷列表</a></p></div>"""
    return _shell(app, str(status), body)


# ---------------------------------------------------------------------------
# Multipart parsing (stdlib only; browsers + curl + http.client bodies)
# ---------------------------------------------------------------------------


def _parse_multipart(body: bytes, content_type: str):
    """Split a multipart/form-data body into (fields, files).

    ``files`` maps field name -> (filename, content bytes). Deliberately
    small: it trusts the boundary not to appear inside a part's content,
    which holds for browser/curl-generated PDF uploads.
    """
    match = re.search(r'boundary=(?:"([^"]+)"|([^;\s]+))', content_type or "")
    if not match:
        raise ValueError("multipart boundary missing")
    boundary = (match.group(1) or match.group(2)).encode()
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in body.split(b"--" + boundary)[1:]:
        if part.startswith(b"--"):
            break
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        header_blob, sep, content = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = {}
        for line in header_blob.split(b"\r\n"):
            key, _, value = line.partition(b":")
            headers[key.strip().lower().decode("latin-1")] = value.strip().decode(
                "latin-1"
            )
        disposition = headers.get("content-disposition", "")
        name_match = re.search(r'name="([^"]*)"', disposition)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', disposition)
        if filename_match is not None:
            files[name] = (filename_match.group(1), content)
        else:
            fields[name] = content.decode("utf-8", "replace")
    return fields, files


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


def make_server(
    host: str,
    port: int,
    *,
    data_dir: Path,
    kit_dir: Path,
) -> ThreadingHTTPServer:
    """Build (but do not start) the student MVP server."""
    app = StudentApp(PaperStore(Path(data_dir)), Path(kit_dir))

    class Handler(BaseHTTPRequestHandler):
        server_version = "HomeworkPilotStudentMVP/0.1"

        def log_message(self, format, *args):  # keep test output clean
            pass

        # -- plumbing -------------------------------------------------
        def _send(self, status: int, body: bytes, content_type: str, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: int, page: str):
            self._send(status, page.encode("utf-8"), "text/html; charset=utf-8")

        def _error(self, status: int, message: str):
            self._send_html(status, _error_page(app, status, message))

        def _redirect(self, location: str):
            self._send(303, b"", "text/plain; charset=utf-8", {"Location": location})

        def _read_body(self) -> bytes | None:
            raw = self.headers.get("Content-Length")
            if raw is None:
                self._error(411, "缺少 Content-Length。")
                return None
            length = int(raw)
            if length > MAX_BODY_BYTES:
                self._error(413, "上传文件过大。")
                return None
            return self.rfile.read(length)

        # -- routes ---------------------------------------------------
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                self._send_html(200, _papers_page(app))
            elif path == "/confirm":
                self._send_html(200, _confirm_page(app))
            elif path == "/export":
                self._send(
                    200,
                    app.store.export_jsonl().encode("utf-8"),
                    "application/x-ndjson; charset=utf-8",
                    {"Content-Disposition": 'attachment; filename="labeled-examples.jsonl"'},
                )
            elif path.startswith("/papers/"):
                paper_id = unquote(path[len("/papers/"):])
                loaded = (
                    app.store.load(paper_id) if _PAGE_ID_RE.match(paper_id) else None
                )
                if loaded is None:
                    self._error(404, "没有这份试卷。")
                else:
                    paper, meta = loaded
                    self._send_html(200, _result_page(app, paper_id, paper, meta))
            else:
                self._error(404, "没有这个页面。")

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/papers":
                self._post_paper()
            elif path == "/confirm":
                self._post_confirm()
            else:
                self._error(404, "没有这个页面。")

        def _post_paper(self):
            body = self._read_body()
            if body is None:
                return
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self._error(400, "上传需要 multipart/form-data 表单。")
                return
            try:
                fields, files = _parse_multipart(body, content_type)
            except ValueError as exc:
                self._error(400, f"表单解析失败：{exc}")
                return
            deps = _deps()
            try:
                # Every submitted field is storage-bound input: a
                # name-like field key anywhere in the form refuses the
                # upload outright (ID-only rule).
                deps["assert_id_only"](fields, where="upload form")
            except deps["NameFieldError"] as exc:
                self._error(400, str(exc))
                return
            student_id = (fields.get("student_id") or "").strip()
            if not STUDENT_ID_RE.match(student_id):
                self._error(
                    400,
                    "学生编号格式应为 S-001 这样的编号（仅编号，不含姓名）。",
                )
                return
            if "file" not in files:
                self._error(400, "没有收到 PDF 文件。")
                return
            _filename, content = files["file"]
            if not content.startswith(b"%PDF-"):
                self._error(400, "只接受 PDF 文件。")
                return
            paper, meta = app.grade_upload(student_id, content)
            paper_id = app.store.add_paper(paper, meta, content)
            self._redirect(f"/papers/{paper_id}")

        def _post_confirm(self):
            body = self._read_body()
            if body is None:
                return
            parsed = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            fields = {k: v[0] for k, v in parsed.items()}
            paper_id = fields.get("paper_id", "")
            item_key = fields.get("item_key", "")
            loaded = app.store.load(paper_id) if _PAGE_ID_RE.match(paper_id) else None
            if loaded is None:
                self._error(404, "没有这份试卷。")
                return
            paper, _meta = loaded
            item = next((i for i in paper.items if i.item_key == item_key), None)
            if item is None:
                self._error(400, f"这份试卷里没有题目 {item_key}。")
                return
            if not item.in_confirmation_queue:
                self._error(400, "这道题不在待确认队列中。")
                return
            action = fields.get("action", "")
            # Only a *changed* transcription counts as a correction;
            # the form pre-fills the current read, and submitting it
            # untouched must not clear the shaky-read flag by itself.
            corrected = fields.get("corrected_answer")
            if corrected is not None and corrected == item.student_answer:
                corrected = None
            reference = fields.get("reference_answer") or None
            try:
                if action == "accept":
                    if item.verdict != "待确认" or not item.proposed_verdict:
                        raise ValueError("这道题没有可确认的系统倾向。")
                    kwargs = {"accept_proposal": True, "corrected_answer": corrected}
                elif action == "right":
                    if item.verdict != "待确认":
                        raise ValueError("这道题的判定已经确定，只能修正转写。")
                    kwargs = {"verdict": "对", "corrected_answer": corrected}
                elif action == "wrong":
                    if item.verdict != "待确认":
                        raise ValueError("这道题的判定已经确定，只能修正转写。")
                    kwargs = {
                        "verdict": "错",
                        "corrected_answer": corrected,
                        "reference_answer": reference,
                    }
                elif action == "fix":
                    if not item.needs_transcription_confirmation:
                        raise ValueError("这道题的转写不需要确认。")
                    if "corrected_answer" not in fields:
                        raise ValueError("缺少转写内容。")
                    # The verdict stands; the student confirms (or
                    # edits) the read itself.
                    kwargs = {
                        "verdict": item.verdict,
                        "corrected_answer": fields["corrected_answer"],
                    }
                else:
                    raise ValueError(f"未知的确认动作：{action!r}")
                app.store.confirm(paper_id, item_key, **kwargs)
            except (ValueError, KeyError) as exc:
                self._error(400, str(exc))
                return
            self._redirect("/confirm")

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.app = app  # for tests / embedding
    return server


def serve_main(argv: list[str] | None = None) -> int:
    """``python3 -m webui --serve`` -- run the local student MVP server."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m webui --serve",
        description="Serve the student-side MVP locally (issue #179).",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1, local only)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR),
                        help="where uploads + records live (gitignored)")
    parser.add_argument("--kit-dir", default=str(DEFAULT_KIT_DIR),
                        help="synthetic pilot kit the v1 backends read")
    args = parser.parse_args(argv)
    server = make_server(
        args.host,
        args.port,
        data_dir=Path(args.data_dir),
        kit_dir=Path(args.kit_dir),
    )
    host, port = server.server_address[:2]
    print(
        f"homework-pilot student MVP: http://{host}:{port}/"
        f"  (data dir: {args.data_dir})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
