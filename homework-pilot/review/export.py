"""Print-ready PDF export for students and teachers (issue #115).

Stdlib-only, hand-rolled PDF 1.4 writer. This module is pragmatic and
honest about what it does:

* Student sheet: title header with student ID (学号) + assignment number
  (作业编号), numbered question stems, figure placeholders rendered as
  labeled boxes ("FIGURE NEEDED", 图待补充）, ruled answer space, page
  numbers, and stable pagination via a keep-together rule (a question's
  stem block never splits awkwardly across pages).
* Teacher key (教师版）: a *separate* document with answers, solution
  steps, and scoring notes （评分说明） -- never bundled with student
  sheets.
* Batch: :func:`export_class` renders a whole class (~80 students) plus
  the teacher key plus a round-trip manifest in the same envelope shape
  as ``ingestion.id_manifest`` (``{"version": 1, "entries": [...]}``),
  so the #110/#111 upload-matching pipeline can consume it directly.

Known limits (stated here and in the README, not hidden):

* Typography uses a bundled, subset **Noto Sans SC** font (issue #185;
  see :mod:`review.cjk_font`), embedded in the PDF as a Type0 /
  CIDFontType2 font with a ToUnicode map. Chinese renders verbatim --
  no more pinyin transliteration -- for every character in the subset
  (printable ASCII + Latin-1, general/CJK punctuation, common math
  symbols, and the full GB2312-80 Han repertoire, which covers all
  Chapter 3 vocabulary). Characters outside the subset render as "?",
  and superscript digits render as ``^n`` (the upstream font itself
  lacks most of them). The real Chinese terms are also embedded
  verbatim in the PDF document metadata (UTF-16BE).
* Figures are labeled placeholder boxes with the teacher's description;
  no raster/vector figure rendering (that needs real artwork from the
  teacher, flagged upstream by the PLACEHOLDER figure status).
* There is no full typesetting engine: no hyphenation, no justification,
  no widow/orphan control beyond the keep-together rule.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .cjk_font import font_objects, load_font, render_text
from .models import FigureStatus, PublishedPlan, Question

# --------------------------------------------------------------------------
# Text handling: bundled CJK font (issue #185)
# --------------------------------------------------------------------------

def _hex_text(text: str, bold: bool = False) -> str:
    """Encode rendered text as a PDF hex string of 2-byte glyph IDs."""
    font = load_font("Bold" if bold else "Regular")
    return "".join(f"{font.glyph_id(ch):04X}" for ch in text)


def _runs(text: str) -> list[tuple[str, str]]:
    """Split text into (kind, chunk) runs for the content stream.

    ``cjk`` runs are drawn with the embedded Noto Sans SC font (any
    character with a glyph there -- all CJK, punctuation, and symbols);
    ``latin`` runs are drawn with Helvetica so body Latin keeps the
    original metrics. Both weights share classification by regular cmap.
    """
    runs: list[tuple[str, str]] = []
    for ch in text:
        # Latin-1 text (except the punctuation/symbols the bundled font
        # draws better) stays on Helvetica; everything else -- CJK,
        # fullwidth forms, Greek, math symbols -- uses the CJK font.
        kind = "latin" if (ord(ch) <= 0xFF and ch not in "‘’“”–—…·×÷") else "cjk"
        if runs and runs[-1][0] == kind:
            runs[-1] = (kind, runs[-1][1] + ch)
        else:
            runs.append((kind, ch))
    return runs


def _pdf_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    )


def _utf16_hex(text: str) -> str:
    """PDF hex string (with UTF-16BE BOM) for metadata, e.g. Chinese terms."""
    return "FEFF" + text.encode("utf-16-be").hex().upper()


# --------------------------------------------------------------------------
# Minimal PDF 1.4 writer
# --------------------------------------------------------------------------

PAGE_W, PAGE_H = 595.28, 841.89          # A4 in points
MARGIN_L = MARGIN_R = 54.0
MARGIN_TOP = 66.0                        # leaves room for the header band
MARGIN_BOTTOM = 52.0                     # leaves room for the footer

#: English display for the assembly category buckets (共同题 etc.).
CATEGORY_EN = {
    "共同题": "common question",
    "当前学习": "current learning",
    "薄弱点练习": "weak-point practice",
    "旧知识复习": "review",
}


class _PdfWriter:
    """Collects indirect objects and serializes a valid PDF 1.4 file."""

    def __init__(self) -> None:
        self._objects: list[bytes] = []

    def add(self, body: bytes) -> int:
        self._objects.append(body)
        return len(self._objects)  # 1-based object number

    def set(self, number: int, body: bytes) -> None:
        """Replace the body of an already-reserved object number."""
        self._objects[number - 1] = body

    def serialize(self, info: dict[str, str] | None = None) -> bytes:
        info_ref = 0
        if info:
            parts = " ".join(
                f"/{key} <{_utf16_hex(value)}>" for key, value in info.items()
            )
            info_ref = self.add(("<< " + parts + " >>").encode("ascii"))
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = []
        for i, body in enumerate(self._objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
        xref_pos = len(out)
        out += f"xref\n0 {len(self._objects) + 1}\n".encode("ascii")
        out += b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode("ascii")
        trailer = (
            f"trailer\n<< /Size {len(self._objects) + 1} /Root 1 0 R"
        ).encode("ascii")
        if info_ref:
            trailer += f" /Info {info_ref} 0 R".encode("ascii")
        trailer += b" >>\nstartxref\n" + str(xref_pos).encode("ascii") + b"\n%%EOF\n"
        out += trailer
        return bytes(out)


def _emit_text(buf: list[str], x: float, y: float, size: float,
               bold: bool, text: str) -> None:
    """Emit one positioned line, split into Latin / CJK font runs."""
    xx = x
    for kind, chunk in _runs(text):
        if kind == "latin":
            font = "/F2" if bold else "/F1"
            safe = _pdf_escape(chunk)
            buf.append(
                f"BT {font} {size:.1f} Tf 1 0 0 1 {xx:.2f} {y:.2f} Tm "
                f"({safe}) Tj ET"
            )
            xx += sum(0.30 * size if c == " " else 0.55 * size
                      for c in chunk)
        else:
            font = "/F4" if bold else "/F3"
            buf.append(
                f"BT {font} {size:.1f} Tf 1 0 0 1 {xx:.2f} {y:.2f} Tm "
                f"<{_hex_text(chunk, bold)}> Tj ET"
            )
            xx += load_font("Bold" if bold else "Regular").width(chunk, size)


def _content_stream(ops: list[tuple]) -> bytes:
    """Render layout ops to a PDF content stream."""
    buf: list[str] = []
    gray: float | None = None

    def set_gray(g: float) -> None:
        nonlocal gray
        if gray != g:
            buf.append(f"{g:.2f} g")
            gray = g

    for op in ops:
        kind = op[0]
        if kind == "txt":
            _, x, y, size, bold, text = op
            set_gray(0.0)
            _emit_text(buf, x, y, size, bold, render_text(text))
        elif kind == "gtext":
            _, x, y, size, text, g = op
            set_gray(g)
            _emit_text(buf, x, y, size, False, render_text(text))
        elif kind == "ln":
            _, x1, y1, x2, y2, w = op
            set_gray(0.0)
            buf.append(
                f"{w:.1f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
            )
        elif kind == "box":
            _, x, y, w, h, fill = op
            if fill is not None:
                set_gray(fill)
                buf.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
            set_gray(0.0)
            buf.append(f"0.6 w {x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")
    set_gray(0.0)
    return "\n".join(buf).encode("latin-1")


# --------------------------------------------------------------------------
# Layout: a tiny flow engine with a keep-together rule
# --------------------------------------------------------------------------

def _text_width(text: str, size: float) -> float:
    """Advance estimate matching the two render paths.

    Latin runs use the rough Helvetica estimate the layout has always
    used (0.55 em per glyph, 0.30 em per space); CJK runs use the real
    advances from the bundled font (CJK glyphs are exactly 1 em).
    """
    w = 0.0
    for kind, chunk in _runs(text):
        if kind == "latin":
            w += sum(0.30 * size if c == " " else 0.55 * size
                     for c in chunk)
        else:
            w += load_font("Regular").width(chunk, size)
    return w


def _hard_break(word: str, size: float, max_w: float) -> list[str]:
    """Split an over-wide word at the widest fitting character boundary."""
    pieces: list[str] = []
    cur = word
    while _text_width(cur, size) > max_w and len(cur) > 1:
        cut = len(cur) - 1
        while cut > 1 and _text_width(cur[:cut], size) > max_w:
            cut -= 1
        pieces.append(cur[:cut])
        cur = cur[cut:]
    if cur:
        pieces.append(cur)
    return pieces


def _wrap(text: str, size: float, max_w: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = (cur + " " + word).strip()
        if _text_width(trial, size) <= max_w:
            cur = trial
        elif _text_width(word, size) > max_w:
            # A single word wider than the line (long Chinese runs have
            # no spaces): flush, then hard-break it at char boundaries.
            if cur:
                lines.append(cur)
            pieces = _hard_break(word, size, max_w)
            lines.extend(pieces[:-1])
            cur = pieces[-1] if pieces else ""
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


class _Flow:
    """Top-down flow layout across pages; ops are added per page."""

    def __init__(self) -> None:
        self.pages: list[list[tuple]] = [[]]
        self.y = PAGE_H - MARGIN_TOP

    @property
    def text_w(self) -> float:
        return PAGE_W - MARGIN_L - MARGIN_R

    def space_left(self) -> float:
        return self.y - MARGIN_BOTTOM

    def full_page_space(self) -> float:
        return PAGE_H - MARGIN_TOP - MARGIN_BOTTOM

    def new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN_TOP

    def _ops(self) -> list[tuple]:
        return self.pages[-1]

    def ensure(self, height: float) -> None:
        """Keep-together: start a fresh page if the block won't fit."""
        if height > self.space_left() and self.pages[-1]:
            self.new_page()

    def gap(self, h: float) -> None:
        if h > self.space_left():
            self.new_page()
        self.y -= h

    def text_line(self, text: str, size: float, bold: bool = False,
                  x: float | None = None, gray: float = 0.0) -> None:
        """Emit one line; top of the line is at the current cursor."""
        leading = size * 1.32
        if leading > self.space_left():
            self.new_page()
        baseline = self.y - size * 0.92
        xx = MARGIN_L if x is None else x
        if gray == 0.0 and not bold:
            self._ops().append(("txt", xx, baseline, size, False, text))
        elif bold:
            self._ops().append(("txt", xx, baseline, size, True, text))
        else:
            self._ops().append(("gtext", xx, baseline, size, text, gray))
        self.y -= leading

    def wrapped(self, text: str, size: float, bold: bool = False,
                gray: float = 0.0) -> None:
        for line in _wrap(render_text(text), size, self.text_w):
            self.text_line(line, size, bold=bold, gray=gray)

    def hline(self, width: float = 0.8) -> None:
        if 4 > self.space_left():
            self.new_page()
        y = self.y - 2
        self._ops().append(
            ("ln", MARGIN_L, y, PAGE_W - MARGIN_R, y, width))
        self.y -= 8

    def figure_box(self, label: str, sublabel: str,
                   description: str = "") -> None:
        """Labeled placeholder box for a figure (图待补充 style)."""
        w, h = 250.0, 86.0
        if h + 6 > self.space_left():
            self.new_page()
        x = MARGIN_L
        y_top = self.y
        self._ops().append(("box", x, y_top - h, w, h, 0.94))
        cx = x + w / 2
        # centered labels: measure and offset
        lab = render_text(label)
        sub = render_text(sublabel)
        self._ops().append(
            ("txt", cx - _text_width(lab, 11) / 2, y_top - 34, 11, True, lab))
        self._ops().append(
            ("txt", cx - _text_width(sub, 9.5) / 2, y_top - 52, 9.5, False, sub))
        self.y = y_top - h - 6
        if description:
            self.wrapped("Figure: " + description, 9.5, gray=0.35)

    def answer_lines(self, n: int, spacing: float = 21.0) -> None:
        x1, x2 = MARGIN_L, PAGE_W - MARGIN_R
        for _ in range(n):
            if spacing > self.space_left():
                self.new_page()
            y = self.y - 4
            self._ops().append(("ln", x1, y, x2, y, 0.5))
            self.y -= spacing


# --------------------------------------------------------------------------
# Document assembly
# --------------------------------------------------------------------------

def _answer_line_count(q: Question) -> int:
    base = 5
    if q.difficulty.value == "medium":
        base = 6
    elif q.difficulty.value == "hard":
        base = 8
    # long stems usually need more working room
    if len(q.stem) > 160:
        base += 2
    return base


def _question_block_height(flow: _Flow, q: Question) -> float:
    # Estimate on the transliterated text -- that is what actually renders.
    h = 0.0
    h += 13 * 1.32 + 4                       # "Question N" label
    h += 9.5 * 1.32 + 2                      # skill line
    h += len(_wrap(render_text(q.stem), 11.5, flow.text_w)) * 11.5 * 1.32 + 6
    fig_desc = render_text(q.figure_description)
    if q.figure.value in ("placeholder", "provided"):
        h += 86 + 6 + 4
        if fig_desc:
            h += len(_wrap("Figure: " + fig_desc, 9.5,
                           flow.text_w)) * 9.5 * 1.32
    h += 11 * 1.32 + 2                       # "Your answer" label
    h += _answer_line_count(q) * 21.0 + 14    # ruled lines + trailing gap
    return h


def _emit_student_question(flow: _Flow, q: Question, number: int) -> None:
    flow.ensure(
        min(_question_block_height(flow, q), flow.full_page_space()))
    cat = CATEGORY_EN.get(q.category, q.category)
    label = f"Question {number}"
    if cat:
        label += f"  [{cat}]"
    flow.text_line(label, 13, bold=True)
    flow.text_line("Skills: " + ", ".join(q.skill_ids), 9.5, gray=0.35)
    flow.gap(4)
    flow.wrapped(q.stem, 11.5)
    flow.gap(6)
    if q.figure.value == "placeholder":
        flow.figure_box("FIGURE NEEDED", "图待补充",
                        q.figure_description)
        flow.gap(4)
    elif q.figure.value == "provided":
        flow.figure_box("FIGURE", render_text(q.figure_description)[:40],
                        q.figure_description)
        flow.gap(4)
    flow.text_line("Your answer (答题区):", 11, bold=True)
    flow.answer_lines(_answer_line_count(q))
    flow.gap(14)


def _emit_key_question(flow: _Flow, q: Question, number: int) -> None:
    flow.ensure(min(120.0, flow.full_page_space()))
    flow.text_line(f"Question {number} — answer key", 13, bold=True)
    flow.gap(2)
    flow.wrapped(q.stem, 10.5, gray=0.25)
    flow.gap(4)
    flow.text_line("Answer:", 11, bold=True)
    flow.wrapped(q.answer or "(no answer recorded)", 11.5)
    flow.gap(4)
    if q.solution_steps:
        flow.text_line("Solution steps:", 11, bold=True)
        for i, step in enumerate(q.solution_steps, start=1):
            flow.wrapped(f"{i}. {step}", 10.5)
        flow.gap(4)
    flow.text_line("评分说明 (scoring notes):", 11, bold=True)
    flow.wrapped(q.scoring_notes or "(no scoring notes recorded)", 10.5)
    flow.hline()
    flow.gap(10)


def _render_pages(flow: _Flow, header_left: str, header_right: str,
                  info: dict[str, str]) -> bytes:
    writer = _PdfWriter()
    catalog_slot = writer.add(b"")  # object 1: catalog, patched in below
    # fonts must exist before pages reference them: F1/F2 keep the
    # Latin Helvetica pair; F3/F4 are the bundled CJK font (issue #185)
    helv = writer.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    helv_b = writer.add(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    cjk = font_objects(writer.add, "Regular")
    cjk_b = font_objects(writer.add, "Bold")
    n_pages = len(flow.pages)
    kids: list[int] = []
    for i, ops in enumerate(flow.pages):
        page_ops = list(ops)
        # header band
        page_ops.insert(
            0,
            ("gtext", MARGIN_L, PAGE_H - 42, 9,
             f"{header_left}", 0.35),
        )
        page_ops.insert(
            1,
            ("txt", PAGE_W - MARGIN_R - _text_width(header_right, 9),
             PAGE_H - 42, 9, False, header_right),
        )
        page_ops.insert(2, ("ln", MARGIN_L, PAGE_H - 50,
                            PAGE_W - MARGIN_R, PAGE_H - 50, 0.6))
        # footer
        footer = f"Page {i + 1} of {n_pages}"
        page_ops.append(
            ("gtext", PAGE_W / 2 - _text_width(footer, 9) / 2,
             32, 9, footer, 0.35))
        content = _content_stream(page_ops)
        content_id = writer.add(
            f"<< /Length {len(content)} >>\nstream\n".encode("latin-1")
            + content + b"\nendstream"
        )
        page_id = writer.add(
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {helv} 0 R /F2 {helv_b} 0 R "
            f"/F3 {cjk} 0 R /F4 {cjk_b} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode("ascii")
        )
        kids.append(page_id)
    pages_id = writer.add(
        ("<< /Type /Pages /Kids [" + " ".join(f"{k} 0 R" for k in kids)
         + f"] /Count {n_pages} >>").encode("ascii")
    )
    writer.set(
        catalog_slot,
        f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"),
    )
    return writer.serialize(info)


def export_student_sheet(published: PublishedPlan, out_path: str) -> str:
    """Render one student's homework sheet. Returns the PDF path."""
    flow = _Flow()
    flow.text_line("Homework 作业", 18, bold=True)
    flow.text_line(
        f"学号 (student ID): {published.student_id}    "
        f"作业编号 (assignment): {published.assignment_number}",
        12,
    )
    flow.gap(6)
    flow.hline()
    flow.gap(8)
    for i, q in enumerate(published.questions, start=1):
        _emit_student_question(flow, q, i)
    info = {
        "Title": f"学生作业 {published.assignment_number} {published.student_id}",
        "Subject": "homework sheet (student)",
        "Keywords": "审核 共同题 图待补充",
    }
    data = _render_pages(
        flow,
        header_left=f"作业编号: {published.assignment_number}",
        header_right=f"学号: {published.student_id}",
        info=info,
    )
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def export_teacher_key(assignment_number: str, questions: list[Question],
                       out_path: str, class_size: int = 0) -> str:
    """Render the teacher's answer key (教师版） as a separate document."""
    flow = _Flow()
    flow.text_line("TEACHER KEY — 教师版 (do not distribute)", 16,
                   bold=True)
    flow.text_line(
        f"作业编号 (assignment): {assignment_number}"
        + (f"    Class size: {class_size}" if class_size else ""),
        11,
    )
    flow.gap(4)
    flow.hline()
    flow.gap(8)
    for i, q in enumerate(questions, start=1):
        _emit_key_question(flow, q, i)
    info = {
        "Title": f"教师版 {assignment_number} (answer key)",
        "Subject": "teacher answer key with scoring notes",
        "Keywords": "教师版 评分说明 审核",
    }
    data = _render_pages(
        flow,
        header_left=f"TEACHER KEY — {assignment_number}",
        header_right="教师版",
        info=info,
    )
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


# --------------------------------------------------------------------------
# Batch export + round-trip manifest
# --------------------------------------------------------------------------

@dataclass
class ClassExport:
    assignment_number: str
    student_files: list[tuple[str, str]] = field(default_factory=list)
    teacher_key_path: str = ""
    manifest_path: str = ""


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _union_questions(plans: list[PublishedPlan]) -> list[Question]:
    seen: dict[str, Question] = {}
    for plan in plans:
        for q in plan.questions:
            seen.setdefault(q.id, q)
    return list(seen.values())


def export_class(plans: list[PublishedPlan], out_dir: str) -> ClassExport:
    """Export a whole class: one sheet per student + teacher key + manifest.

    Returns :class:`ClassExport`. The manifest follows the same envelope
    shape as ``ingestion.id_manifest`` (``{"version": 1, "entries": [...]}``)
    so the upload-matching pipeline can map printed pages back to
    (student_id, assignment_number).
    """
    if not plans:
        raise ValueError("export_class needs at least one published plan")
    os.makedirs(out_dir, exist_ok=True)
    assignment = plans[0].assignment_number
    result = ClassExport(assignment_number=assignment)
    entries: list[dict] = []

    for plan in plans:
        fname = f"{assignment}_{plan.student_id}.pdf"
        path = os.path.join(out_dir, fname)
        export_student_sheet(plan, path)
        result.student_files.append((plan.student_id, path))
        entries.append({
            "file": fname,
            "student_id": plan.student_id,
            "assignment_number": assignment,
            "pages": verify_pdf_structure(_read_bytes(path))["page_count"],
            "kind": "student_sheet",
        })

    key_fname = f"{assignment}_TEACHER-KEY.pdf"
    key_path = os.path.join(out_dir, key_fname)
    export_teacher_key(assignment, _union_questions(plans), key_path,
                       class_size=len(plans))
    result.teacher_key_path = key_path
    entries.append({
        "file": key_fname,
        "student_id": "",
        "assignment_number": assignment,
        "pages": verify_pdf_structure(_read_bytes(key_path))["page_count"],
        "kind": "teacher_key",
    })

    manifest_path = os.path.join(out_dir, f"{assignment}_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "entries": entries}, f,
                  ensure_ascii=False, indent=2)
    result.manifest_path = manifest_path
    return result


# --------------------------------------------------------------------------
# Structural verification (no PDF parser needed)
# --------------------------------------------------------------------------

_XREF_ENTRY = re.compile(rb"(\d{10}) (\d{5}) ([fn]) \r?\n")


def verify_pdf_structure(data: bytes) -> dict:
    """Structural sanity check for a generated PDF.

    Validates the header, the xref table (each live entry points at a real
    ``N 0 obj``), the trailer (``/Root`` present), and ``%%EOF``. Returns a
    dict with ``ok`` plus details. This is *not* a render check -- it
    cannot prove a viewer draws the page correctly -- but it catches
    truncated or malformed output.
    """
    result: dict = {"ok": False}
    result["header_ok"] = data.startswith(b"%PDF-")
    result["eof_ok"] = data.rstrip().endswith(b"%%EOF")
    try:
        sx = data.rindex(b"startxref")
        xref_pos = int(data[sx + 9:].split()[0])
    except (ValueError, IndexError):
        xref_pos = -1
    result["xref_found"] = xref_pos >= 0 and data[xref_pos:xref_pos + 4] == b"xref"
    entries_ok = 0
    entries_total = 0
    if result["xref_found"]:
        trailer_pos = data.find(b"trailer", xref_pos)
        section = data[xref_pos:trailer_pos]
        for m in _XREF_ENTRY.finditer(section):
            if m.group(3) != b"n":
                continue  # free head entry (object 0); not a live object
            entries_total += 1
            off = int(m.group(1))
            head = data[off:off + 24]
            if re.match(rb"\d+ \d+ obj", head):
                entries_ok += 1
        trailer = data[trailer_pos:trailer_pos + 400]
        result["trailer_ok"] = b"/Root" in trailer
    else:
        result["trailer_ok"] = False
    result["xref_entries_total"] = entries_total
    result["xref_entries_ok"] = entries_ok
    result["xref_ok"] = (
        result["xref_found"] and result["trailer_ok"]
        and entries_total > 0 and entries_ok == entries_total
    )
    pages = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    result["page_count"] = pages
    result["ok"] = bool(
        result["header_ok"] and result["eof_ok"] and result["xref_ok"]
        and pages >= 1
    )
    return result
