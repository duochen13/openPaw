"""Tests for the PDF export (issue #115).

All question content is synthetic (``SYN-`` prefix) -- real teacher
materials are pending #108 field work.

Verification strategy (stdlib-only, no PDF parser available):

* :func:`review.export.verify_pdf_structure` parses the xref table for
  real: header, every live object offset, trailer ``/Root``, ``%%EOF``,
  and an exact page count.
* Where ``pdftotext``/``pdfinfo`` exist (CI here), tests additionally
  extract the rendered text and assert the expected strings survived
  typesetting -- this is the closest we get to "the PDF renders".
"""

import json
import shutil
import subprocess
from copy import deepcopy

import pytest

from ..export import (
    export_class,
    export_student_sheet,
    export_teacher_key,
    verify_pdf_structure,
)
from ..models import (
    Difficulty,
    FigureStatus,
    HomeworkPlan,
    PublishedPlan,
    Question,
)
from ..review import ReviewSession

ASSIGNMENT = "A-CH3-01"
HAS_PDFTOTEXT = shutil.which("pdftotext") is not None
HAS_PDFINFO = shutil.which("pdfinfo") is not None


def _q(qid: str, **kw) -> Question:
    base = dict(
        skill_ids=["ch3-gravitational-work"],
        stem=f"Synthetic stem of {qid}: a 2 kg object falls 5 m, find the "
             f"gravitational work (g = 10 N/kg).",
        answer="100 J",
        solution_steps=["G = m*g = 2 kg * 10 N/kg = 20 N",
                        "W = G*h = 20 N * 5 m = 100 J"],
        scoring_notes="Half credit for the correct formula; full credit "
                      "for value and unit (J).",
        difficulty=Difficulty.MEDIUM,
        recommendation_reason="basic gravitational-work computation",
        category="共同题",
    )
    base.update(kw)
    return Question(id=qid, **base)


def _published(student_id: str, questions: list[Question]) -> PublishedPlan:
    return PublishedPlan(
        student_id=student_id,
        assignment_number=ASSIGNMENT,
        questions=deepcopy(questions),
        published_at="2026-09-27T00:00:00+00:00",
    )


@pytest.fixture()
def three_students(tmp_path):
    """Three approved, published students incl. a figure-placeholder item."""
    q1 = _q("SYN-Q1")
    q2 = _q("SYN-Q2", figure=FigureStatus.PLACEHOLDER,
            figure_description="free-body diagram of the falling object")
    q3 = _q("SYN-Q3", difficulty=Difficulty.HARD,
            stem=("Synthetic hard stem: " + "a 2 kg object falls 5 m. ") * 12)
    session = ReviewSession([
        HomeworkPlan("S001", [deepcopy(q1), deepcopy(q2)], ASSIGNMENT),
        HomeworkPlan("S002", [deepcopy(q1), deepcopy(q2)], ASSIGNMENT),
        HomeworkPlan("S003", [deepcopy(q2), deepcopy(q3)], ASSIGNMENT),
    ], assignment_number=ASSIGNMENT)
    session.approve_all()
    plans = session.publish_class()
    out = export_class(plans, str(tmp_path))
    return out, plans


# -- sample student sheets ----------------------------------------------------

def test_student_pdfs_are_valid(three_students):
    out, _ = three_students
    assert len(out.student_files) == 3
    for student_id, path in out.student_files:
        with open(path, "rb") as f:
            data = f.read()
        assert len(data) > 2000, f"{student_id}: PDF suspiciously small"
        check = verify_pdf_structure(data)
        assert check["ok"], f"{student_id}: {check}"
        assert check["page_count"] >= 1
        # ID + assignment number are printed on the sheet
        assert student_id.encode("ascii") in data
        assert ASSIGNMENT.encode("ascii") in data
        # numbered question stems made it into the content stream
        assert b"Question 1" in data


def test_figure_placeholder_renders_labeled_box(three_students):
    out, _ = three_students
    by_id = dict(out.student_files)
    with open(by_id["S001"], "rb") as f:
        data = f.read()
    assert b"FIGURE NEEDED" in data
    assert b"tu dai bu chong" in data  # pinyin for 图待补充


def test_chinese_terms_embedded_in_metadata(three_students):
    out, _ = three_students
    _, path = out.student_files[0]
    with open(path, "rb") as f:
        data = f.read()
    # real Chinese terms (UTF-16BE in the Info dict) survive in the file
    for term in ("学生作业", "图待补充", "共同题"):
        hexed = term.encode("utf-16-be").hex().upper().encode()
        assert hexed in data, term


@pytest.mark.skipif(not HAS_PDFTOTEXT, reason="pdftotext not installed")
def test_student_pdf_text_extracts(three_students):
    """Closest to 'the PDF renders': real text extraction from the file."""
    out, _ = three_students
    by_id = dict(out.student_files)
    for student_id, path in (("S001", by_id["S001"]),
                             ("S003", by_id["S003"])):
        text = subprocess.run(
            ["pdftotext", path, "-"], capture_output=True, text=True,
            check=True).stdout
        assert student_id in text
        assert ASSIGNMENT in text
        assert "Question 1" in text
        assert "Your answer" in text
        assert "Page 1 of" in text
    assert "FIGURE NEEDED" in subprocess.run(
        ["pdftotext", by_id["S001"], "-"], capture_output=True, text=True,
        check=True).stdout


@pytest.mark.skipif(not HAS_PDFINFO, reason="pdfinfo not installed")
def test_pdfinfo_agrees_with_structural_check(three_students):
    out, _ = three_students
    _, path = out.student_files[0]
    info = subprocess.run(["pdfinfo", path], capture_output=True, text=True,
                          check=True).stdout
    assert "PDF version:" in info
    with open(path, "rb") as f:
        check = verify_pdf_structure(f.read())
    pages_line = next(l for l in info.splitlines()
                      if l.startswith("Pages:"))
    assert int(pages_line.split(":")[1]) == check["page_count"]


def test_render_is_deterministic(tmp_path):
    """Stable pagination: the same plan renders byte-identical twice."""
    q = _q("SYN-Q1")
    p1 = _published("S010", [q])
    a = export_student_sheet(p1, str(tmp_path / "a.pdf"))
    b = export_student_sheet(_published("S010", [q]), str(tmp_path / "b.pdf"))
    assert open(a, "rb").read() == open(b, "rb").read()


def test_long_homework_paginates(tmp_path):
    """12 hard questions -> multiple pages, every page numbered."""
    questions = [_q(f"SYN-L{i:02d}", difficulty=Difficulty.HARD)
                 for i in range(12)]
    path = export_student_sheet(_published("S020", questions),
                                str(tmp_path / "long.pdf"))
    with open(path, "rb") as f:
        check = verify_pdf_structure(f.read())
    assert check["ok"]
    assert check["page_count"] >= 2
    if HAS_PDFTOTEXT:
        text = subprocess.run(["pdftotext", path, "-"], capture_output=True,
                              text=True, check=True).stdout
        assert f"Page {check['page_count']} of {check['page_count']}" in text


# -- teacher key ---------------------------------------------------------------

def test_teacher_key_is_separate_and_has_answers(three_students, tmp_path):
    out, _ = three_students
    key_path = out.teacher_key_path
    student_paths = {p for _, p in out.student_files}
    assert key_path not in student_paths
    with open(key_path, "rb") as f:
        data = f.read()
    check = verify_pdf_structure(data)
    assert check["ok"] and check["page_count"] >= 1
    assert b"TEACHER KEY" in data
    assert b"100 J" in data                       # the answers
    assert b"Ping fen shuo ming" in data          # 评分说明 label
    assert b"Solution steps" in data


def test_teacher_key_has_no_answer_space(three_students):
    """Student-only affordances must not leak into the key."""
    out, _ = three_students
    with open(out.teacher_key_path, "rb") as f:
        data = f.read()
    assert b"Your answer" not in data
    assert b"xue hao" not in data  # no per-student ID block


@pytest.mark.skipif(not HAS_PDFTOTEXT, reason="pdftotext not installed")
def test_teacher_key_text_extracts(three_students):
    text = subprocess.run(
        ["pdftotext", three_students[0].teacher_key_path, "-"],
        capture_output=True, text=True, check=True).stdout
    assert "TEACHER KEY" in text
    assert "100 J" in text
    assert "Solution steps" in text
    assert "scoring notes" in text


def test_teacher_key_standalone(tmp_path):
    path = export_teacher_key(ASSIGNMENT, [_q("SYN-Q9")],
                              str(tmp_path / "key.pdf"), class_size=80)
    with open(path, "rb") as f:
        assert verify_pdf_structure(f.read())["ok"]


# -- batch export ------------------------------------------------------------------

def _synthetic_class(n: int) -> list[PublishedPlan]:
    bank = [_q(f"SYN-B{i:02d}",
               figure=FigureStatus.PLACEHOLDER if i % 3 == 0
               else FigureStatus.NONE,
               figure_description="diagram for the teacher to supply"
               if i % 3 == 0 else "")
            for i in range(6)]
    plans = []
    for s in range(n):
        qs = [deepcopy(bank[(s + k) % len(bank)]) for k in range(4)]
        session = ReviewSession(
            [HomeworkPlan(f"S{s:03d}", qs, ASSIGNMENT)],
            assignment_number=ASSIGNMENT)
        session.approve_all()
        plans.extend(session.publish_class())
    return plans


def test_batch_export_80_students(tmp_path):
    plans = _synthetic_class(80)
    out = export_class(plans, str(tmp_path / "class"))
    assert len(out.student_files) == 80
    assert len({p for _, p in out.student_files}) == 80  # unique files
    for student_id, path in out.student_files:
        with open(path, "rb") as f:
            check = verify_pdf_structure(f.read())
        assert check["ok"], f"{student_id}: {check}"
        assert student_id.encode("ascii") in open(path, "rb").read()
    assert verify_pdf_structure(
        open(out.teacher_key_path, "rb").read())["ok"]


def test_manifest_round_trip_shape(three_students):
    out, _ = three_students
    manifest = json.load(open(out.manifest_path, encoding="utf-8"))
    assert manifest["version"] == 1
    # 3 student sheets + 1 teacher key
    assert len(manifest["entries"]) == 4
    kinds = {e["kind"] for e in manifest["entries"]}
    assert kinds == {"student_sheet", "teacher_key"}
    for entry in manifest["entries"]:
        assert entry["assignment_number"] == ASSIGNMENT
        assert entry["pages"] >= 1
        if entry["kind"] == "student_sheet":
            assert entry["student_id"].startswith("S")
            assert entry["file"].endswith(".pdf")


def test_export_class_requires_plans(tmp_path):
    with pytest.raises(ValueError):
        export_class([], str(tmp_path))
