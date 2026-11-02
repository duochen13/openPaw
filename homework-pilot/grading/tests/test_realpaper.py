"""Tests for the real-paper grading backend (issue #184).

The backend is driven over synthetic fixtures, stated plainly: the
recognizer is scripted from the kit's own answer records (the same
scripting pilot-kit/tools/run_end_to_end.py uses), and the uploaded
bytes are the kit's generated PDFs. What this proves is the backend
itself -- paging a real upload, segmenting it, bridging the ingestion
recognizer into the judge, grading a student the kit does not know,
and scoring the result against ground truth. What it does NOT prove
is recognition accuracy on real handwriting: that evaluation needs
the 5 real sample papers from issue #108, which have not been
provided yet (human-blocked). No accuracy claim is made anywhere.
"""

import sys
import unittest
from dataclasses import asdict
from pathlib import Path

from ..backends import (
    expected_verdicts,
    load_kit_questions,
    load_kit_records,
    load_kit_template,
)
from ..judge import comparison_mode, resolve_key_answers
from ..realpaper import (
    UnreadableUploadError,
    count_pdf_pages,
    evaluate_against_truth,
    grade_real_paper,
    load_assignment,
    pages_from_pdf,
    pages_from_photos,
    recognizer_from_records,
    summarize_evaluations,
    unavailable_recognizer,
)

HW = Path(__file__).resolve().parents[2]
KIT = HW / "pilot-kit"
if str(HW) not in sys.path:
    sys.path.insert(0, str(HW))
from privacy.guard import assert_id_only  # noqa: E402


def _assignment():
    questions, template, _meta = load_assignment(KIT / "assignment")
    return questions, template


def _grade_scripted(student_id="S-006", source_student="S-001", **kwargs):
    """Grade a non-kit student through the real backend, with the
    recognizer scripted from a kit student's records and the pages
    taken from that student's actual uploaded PDF bytes."""
    questions, template = _assignment()
    records = load_kit_records(KIT, source_student)
    content = (KIT / "papers" / source_student / "paper.pdf").read_bytes()
    pages = pages_from_pdf(content, f"uploads/{student_id}.pdf")
    return grade_real_paper(
        student_id=student_id,
        pages=pages,
        questions=questions,
        template=template,
        recognizer=recognizer_from_records(records, **kwargs),
    )


def _minimal_pdf(page_count: int, *, with_count: bool = True) -> bytes:
    kids = b" ".join(b"%d 0 R" % (3 + i) for i in range(page_count))
    count = b" /Count %d" % page_count if with_count else b""
    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages%s /Kids [ %s ] >>endobj\n" % (count, kids),
    ]
    for i in range(page_count):
        parts.append(b"%d 0 obj<< /Type /Page /Parent 2 0 R >>endobj\n" % (3 + i))
    parts.append(b"trailer<< >>\n%%EOF\n")
    return b"".join(parts)


class TestPdfPaging(unittest.TestCase):
    def test_kit_pdf_has_two_pages(self):
        content = (KIT / "papers" / "S-001" / "paper.pdf").read_bytes()
        self.assertEqual(count_pdf_pages(content), 2)
        pages = pages_from_pdf(content, "uploads/S-006.pdf")
        self.assertEqual([p.page_index for p in pages], [0, 1])
        self.assertEqual(pages[0].image_location, "uploads/S-006.pdf#page0")
        self.assertTrue(all(p.media_type == "pdf_scan" for p in pages))

    def test_count_from_page_tree(self):
        self.assertEqual(count_pdf_pages(_minimal_pdf(3)), 3)
        self.assertEqual(count_pdf_pages(_minimal_pdf(1)), 1)

    def test_count_falls_back_to_page_objects(self):
        self.assertEqual(count_pdf_pages(_minimal_pdf(2, with_count=False)), 2)

    def test_unreadable_uploads_raise(self):
        with self.assertRaises(UnreadableUploadError):
            count_pdf_pages(b"this is not a pdf at all")
        with self.assertRaises(UnreadableUploadError):
            count_pdf_pages(b"%PDF-1.4\n%%EOF\n")  # no page tree at all

    def test_photos_are_one_page_each(self):
        pages = pages_from_photos(["a.jpg", "b.jpg"])
        self.assertEqual([p.page_index for p in pages], [0, 1])
        self.assertTrue(all(p.media_type == "photo" for p in pages))


class TestRealBackendGradesAnyStudent(unittest.TestCase):
    """Mode A through the real backend: marks present, verdicts must
    equal the kit ground truth -- for a student ID the kit backend
    would have returned 未识别 for."""

    @classmethod
    def setUpClass(cls):
        cls.paper = _grade_scripted()  # S-006, scripted from S-001
        cls.expected = expected_verdicts(load_kit_records(KIT, "S-001"))

    def test_all_items_present_with_full_record_shape(self):
        self.assertEqual(len(self.paper.items), 18)
        for item in self.paper.items:
            self.assertTrue(item.image_location.startswith("uploads/S-006.pdf#page"))
            self.assertIn("#region=", item.image_location)
            self.assertTrue(item.page_label.startswith("第 "))
            self.assertTrue(item.knowledge_point_tag, item.item_key)

    def test_verdicts_match_ground_truth(self):
        for item in self.paper.items:
            self.assertEqual(
                item.verdict, self.expected[item.item_key],
                f"{item.item_key}",
            )

    def test_decided_items_are_mark_sourced(self):
        for item in self.paper.decided():
            self.assertEqual(item.source, "红笔标记")
            if item.verdict == "错":
                self.assertTrue(item.reference_answer)

    def test_output_passes_privacy_guard(self):
        assert_id_only(asdict(self.paper), where="test paper")

    def test_evaluation_reports_full_agreement(self):
        evaluation = evaluate_against_truth(self.paper, self.expected)
        decided_truth = sum(
            1 for v in self.expected.values() if v in ("对", "错")
        )
        self.assertEqual(evaluation.total, 18)
        self.assertEqual(evaluation.decided, decided_truth)
        self.assertEqual(evaluation.agreed, decided_truth)
        self.assertEqual(evaluation.disagreed, 0)
        self.assertEqual(evaluation.agreement, 1.0)
        summary = summarize_evaluations([evaluation])
        self.assertEqual(summary["decided"], decided_truth)
        self.assertEqual(summary["agreement"], 1.0)

    def test_evaluation_counts_a_flipped_truth_as_disagreement(self):
        truth = dict(self.expected)
        decided_key = next(k for k, v in truth.items() if v in ("对", "错"))
        truth[decided_key] = "错" if truth[decided_key] == "对" else "对"
        evaluation = evaluate_against_truth(self.paper, truth)
        self.assertEqual(evaluation.disagreed, 1)
        self.assertEqual(evaluation.agreed, evaluation.decided - 1)


class TestRealBackendKeyOnly(unittest.TestCase):
    """Mode B through the real backend: marks withheld, the answer key
    alone judges -- zero guessed verdicts (acceptance criterion)."""

    @classmethod
    def setUpClass(cls):
        cls.paper = _grade_scripted(include_marks=False)
        cls.modes = {}
        for question in load_kit_questions(KIT):
            for item_key, key in resolve_key_answers(question).items():
                cls.modes[item_key] = comparison_mode(question, key)

    def test_every_decided_item_is_key_sourced(self):
        self.assertTrue(self.paper.decided(), "key-only mode must decide some")
        for item in self.paper.decided():
            self.assertEqual(item.source, "答案比对", item.item_key)

    def test_incomparable_items_are_never_decided(self):
        for item in self.paper.items:
            if self.modes[item.item_key] is None:
                self.assertEqual(
                    item.verdict, "待确认",
                    f"{item.item_key} must not be guessed",
                )


class TestUnavailableRecognizer(unittest.TestCase):
    """No recognizer configured: the backend still segments and
    records every item, and decides nothing -- never a guess."""

    @classmethod
    def setUpClass(cls):
        questions, template = _assignment()
        content = (KIT / "papers" / "S-002" / "paper.pdf").read_bytes()
        cls.paper = grade_real_paper(
            student_id="S-007",
            pages=pages_from_pdf(content, "uploads/S-007.pdf"),
            questions=questions,
            template=template,
            recognizer=None,  # the shipped default
        )

    def test_every_item_recorded_and_pending_unreadable(self):
        self.assertEqual(len(self.paper.items), 18)
        self.assertEqual(self.paper.decided(), ())
        for item in self.paper.items:
            self.assertEqual(item.verdict, "待确认")
            self.assertEqual(item.pending_reason, "unreadable")
            self.assertEqual(item.student_answer, "")
            self.assertTrue(item.needs_transcription_confirmation)

    def test_unavailable_recognizer_reads_nothing(self):
        recognizer = unavailable_recognizer()
        self.assertIs(recognizer, unavailable_recognizer())


if __name__ == "__main__":
    unittest.main()
