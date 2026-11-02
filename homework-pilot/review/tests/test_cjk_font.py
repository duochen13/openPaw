"""Tests for the bundled CJK font (issue #185).

Acceptance criteria under test:

* PDFs generated from the Chapter 3 sample question set
  (``pilot-kit/assignment/questions.json`` -- 浙教版 Science Grade 9
  Vol. 1, Chapter 3 《能量的转化与守恒》) render all Chinese text
  correctly with no missing glyphs, in both the student sheet and the
  teacher key.
* Glyph coverage is asserted for the Chapter 3 vocabulary used in the
  sample set (plus the skill taxonomy's Chinese names).
* The font license is recorded and the bundled files are in the repo.

Like ``test_export.py``, rendering is verified structurally (the PDF
embeds the font + a ToUnicode map) and, where ``pdftotext`` exists, by
extracting the rendered text and comparing it with the source Chinese.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ..cjk_font import (
    FONT_FILES,
    FONT_LICENSE,
    FONT_NAME,
    FONT_VERSION,
    _ASSETS,
    load_font,
    missing_glyphs,
    render_text,
)
from ..export import (
    export_student_sheet,
    export_teacher_key,
    verify_pdf_structure,
)
from ..models import PublishedPlan, Question

HAS_PDFTOTEXT = shutil.which("pdftotext") is not None
_ROOT = Path(__file__).resolve().parents[2]          # homework-pilot/
SAMPLE_PATH = _ROOT / "pilot-kit" / "assignment" / "questions.json"
TAXONOMY_PATH = _ROOT / "taxonomy" / "skills_ch3_v1.json"


def _sample_questions() -> list[Question]:
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    return [
        Question(
            id=q["id"], skill_ids=q["skill_ids"], stem=q["stem"],
            question_type=q["question_type"], figure=q["figure"],
            figure_description=q["figure_description"],
            answer=q["answer"], solution_steps=q["solution_steps"],
            scoring_notes=q["scoring_notes"], difficulty=q["difficulty"],
            category="共同题",
        )
        for q in data["questions"]
    ]


def _sample_text() -> str:
    """Every character the Chapter 3 sample set + taxonomy can emit."""
    chunks = [SAMPLE_PATH.read_text(encoding="utf-8"),
              TAXONOMY_PATH.read_text(encoding="utf-8")]
    # the export module's own Chinese UI strings
    chunks += ["学号 作业编号 作业 教师版 评分说明 答题区 图待补充 共同题",
               "能量的转化与守恒 浙教版科学九年级上册"]
    return "".join(chunks)


def _extract(pdf_path: str) -> str:
    text = subprocess.run(["pdftotext", pdf_path, "-"],
                          capture_output=True, text=True,
                          check=True).stdout
    return "".join(text.split())          # wrap-insensitive comparison


# -- the bundled font itself -------------------------------------------------

def test_bundled_font_files_exist_with_license():
    for filename, _base in FONT_FILES.values():
        path = os.path.join(_ASSETS, filename)
        assert os.path.isfile(path), path
        size = os.path.getsize(path)
        # subset of the ~17 MB upstream variable font: sane, not empty
        assert 1_000_000 < size < 3_000_000, (filename, size)
    license_text = Path(_ASSETS, "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in license_text
    assert FONT_NAME == "Noto Sans SC"
    assert FONT_VERSION == "2.004-H2"
    assert "Open Font License" in FONT_LICENSE


def test_font_parses_and_covers_core_chapter3_terms():
    font = load_font("Regular")
    assert font.units_per_em == 1000
    for ch in "能量的转化与守恒浙教版科学九年级上册学生作业教师版评分说明":
        assert font.glyph_id(ch) != 0, ch          # not .notdef
        assert font.widths[font.glyph_id(ch)] == 1000   # full-width CJK
    bold = load_font("Bold")
    assert bold.glyph_id("能") == font.glyph_id("能")  # same cmap layout


# -- glyph coverage for the Chapter 3 vocabulary ------------------------------

def test_chapter3_sample_vocabulary_has_no_missing_glyphs():
    assert missing_glyphs(_sample_text()) == []


def test_chapter3_sample_cjk_characters_all_covered():
    text = _sample_text()
    cjk = sorted({c for c in text if "一" <= c <= "鿿"})
    assert len(cjk) > 200                       # the sample is really CJK
    font = load_font("Regular")
    assert [c for c in cjk if font.glyph_id(c) == 0] == []


def test_render_text_passes_chinese_through_verbatim():
    text = "质量为 5 kg 的物体从高处自由下落，求重力做功。"
    assert render_text(text) == text
    assert missing_glyphs(render_text(_sample_text())) == []


def test_render_text_normalizes_superscript_digits():
    # The upstream font itself lacks most superscript digits; the render
    # layer writes them as ^n instead of dropping a missing glyph.
    assert render_text("3×10⁵ J 与 1.2×10⁷ J") == "3×10^5 J 与 1.2×10^7 J"
    assert missing_glyphs("⁵⁷") == []


def test_render_text_maps_newlines_to_spaces_not_question_marks():
    assert render_text("第一行\n第二行") == "第一行 第二行"


# -- Chapter 3 sample PDFs ------------------------------------------------------

@pytest.fixture()
def sample_pdfs(tmp_path):
    questions = _sample_questions()
    plan = PublishedPlan(
        student_id="S001", assignment_number="A-CH3-01",
        questions=questions, published_at="2026-09-27T00:00:00+00:00")
    student = export_student_sheet(plan, str(tmp_path / "student.pdf"))
    key = export_teacher_key("A-CH3-01", questions,
                             str(tmp_path / "key.pdf"), class_size=80)
    return student, key


def test_sample_pdfs_embed_the_bundled_font(sample_pdfs):
    for path in sample_pdfs:
        data = Path(path).read_bytes()
        assert verify_pdf_structure(data)["ok"]
        assert b"/Subtype /Type0" in data
        assert b"/FontFile2" in data                 # the TTF is embedded
        assert b"/ToUnicode" in data
        assert b"NotoSansSC-Regular" in data
        assert b"NotoSansSC-Bold" in data


@pytest.mark.skipif(not HAS_PDFTOTEXT, reason="pdftotext not installed")
def test_student_sheet_renders_chapter3_chinese(sample_pdfs):
    student, _key = sample_pdfs
    text = _extract(student)
    # question stems render verbatim (whitespace-normalized)
    assert "质量为5kg的物体从离地8m高处自由下落" in text   # Q8 stem
    assert "下列情境中，力对物体做功的是" in text          # Q1 stem
    assert "图待补充" in text                            # figure box
    assert "学号" in text and "作业编号" in text          # sheet header
    assert "答题区" in text
    assert "?" not in text               # no missing-glyph fallbacks


@pytest.mark.skipif(not HAS_PDFTOTEXT, reason="pdftotext not installed")
def test_teacher_key_renders_chapter3_chinese(sample_pdfs):
    _student, key = sample_pdfs
    text = _extract(key)
    assert "教师版" in text
    assert "评分说明" in text                            # scoring notes
    assert "重力势能转化为动能" in text                  # Q9 answer
    assert "3×10^5" in text              # superscript normalized, not lost
    assert "1.2×10^7" in text
    assert "?" not in text
