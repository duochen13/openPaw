"""Synthetic-fixture tests for the ingestion + OCR pipeline (#110, #111).

Run from the ingestion directory:
    python3 -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluate import evaluate, go_no_go_report  # noqa: E402
from fixtures import (  # noqa: E402
    ambiguous_id_reader,
    clean_id_reader,
    known_students,
    labeled_set,
    make_sample_template,
    make_upload,
    manual_entry_rows,
    recognizer_script,
)
from id_label import label_for_assignment, write_id_label_pdf, write_manifest  # noqa: E402
from manual_entry import ManualEntrySession, commit_rows  # noqa: E402
from matching import match_pages  # noqa: E402
from models import AnswerRecord, GradingMarkKind  # noqa: E402
from pipeline import run_pipeline  # noqa: E402
from recognizer import (  # noqa: E402
    GRADING_MARK,
    HANDWRITING,
    TestDoubleRecognizer,
    recognize_all,
    recognitions_to_records,
)
from segmentation import expand_pages, segment_upload  # noqa: E402


class SegmentationTest(unittest.TestCase):
    def test_upload_to_subquestion_items(self):
        template = make_sample_template()
        upload = make_upload(n_pages=2)
        items = segment_upload(upload, template)
        # per page: Q1, Q2, Q5(blank1,blank2), Q11(a,b,c), Q12(blank1..3) = 10
        self.assertEqual(len(items), 20)
        keys = {it.sub_question.item_key for it in items if it.page.page_index == 0}
        self.assertEqual(keys, {"Q1", "Q2", "Q5#blank1", "Q5#blank2",
                                "Q11#a", "Q11#b", "Q11#c",
                                "Q12#blank1", "Q12#blank2", "Q12#blank3"})

    def test_page_expansion(self):
        pages = expand_pages(make_upload(n_pages=2))
        self.assertEqual([p.page_index for p in pages], [0, 1])
        self.assertEqual(pages[0].page_no_in_file, 0)


class MatchingTest(unittest.TestCase):
    def test_clean_match_links(self):
        pages = expand_pages(make_upload(n_pages=2))
        linked, queue = match_pages(pages, clean_id_reader(), known_students())
        self.assertTrue(all(m.linked for m in linked))
        self.assertEqual([m.student_id for m in linked], ["S001", "S002"])
        self.assertEqual(queue.pending(), [])

    def test_ambiguous_goes_to_queue_with_candidates(self):
        pages = expand_pages(make_upload(n_pages=2))
        linked, queue = match_pages(pages, ambiguous_id_reader(), known_students())
        self.assertTrue(all(not m.linked for m in linked))
        pending = queue.pending()
        self.assertEqual(len(pending), 2)
        # typo'd ID shows nearest candidates: S010 (distance 1), S001 (distance 2)
        self.assertIn(("S010", 1), pending[0].candidates)
        self.assertIn(("S001", 2), pending[0].candidates)
        self.assertTrue(pending[0].reason)
        # blank ID: no candidates, still queued with a reason
        self.assertEqual(pending[1].candidates, [])
        self.assertIn("not readable", pending[1].reason)

    def test_queue_resolve_and_unmatched(self):
        pages = expand_pages(make_upload(n_pages=2))
        _, queue = match_pages(pages, ambiguous_id_reader(), known_students())
        case = queue.pending()[0]
        queue.resolve(case.case_id, "S001", note="teacher confirmed by handwriting")
        self.assertEqual(queue.pending(), [queue.pending()[0]] if len(queue.pending()) else [])
        self.assertEqual(len(queue.pending()), 1)
        other = queue.pending()[0]
        queue.mark_unmatched(other.case_id, note="not our class")
        self.assertEqual(queue.pending(), [])
        self.assertEqual(other.resolution, "unmatched")


class RecognizerTest(unittest.TestCase):
    def setUp(self):
        self.template = make_sample_template()
        self.items = segment_upload(make_upload(n_pages=1), self.template)

    def test_below_threshold_goes_to_review(self):
        rec = TestDoubleRecognizer(recognizer_script())
        accepted, review = recognize_all(self.items, rec, threshold=0.8)
        review_keys = {(r.item.sub_question.item_key, r.item_type) for r in review}
        # scripted low-reliability items
        self.assertIn(("Q11#a", HANDWRITING), review_keys)   # 0.72
        self.assertIn(("Q11#b", GRADING_MARK), review_keys)   # 0.55
        # high-reliability items accepted
        accepted_keys = {(i.sub_question.item_key, t) for i, t, _ in accepted}
        self.assertIn(("Q1", HANDWRITING), accepted_keys)
        self.assertIn(("Q1", GRADING_MARK), accepted_keys)

    def test_records_merge_handwriting_and_marks(self):
        rec = TestDoubleRecognizer(recognizer_script())
        accepted, _ = recognize_all(self.items, rec, threshold=0.0)
        records = recognitions_to_records(accepted, "S001", "A-CH3-01")
        by_key = {r.item_key: r for r in records}
        q1 = by_key["Q1"]
        self.assertEqual(q1.student_answer, "B")
        self.assertEqual(q1.grading_mark.kind, GradingMarkKind.CORRECT)
        self.assertEqual(q1.source, "ocr")
        # round-trip through the documented dict format
        d = q1.to_dict()
        back = AnswerRecord.from_dict(json.loads(json.dumps(d)))
        self.assertEqual(back.to_dict(), d)


class EvaluateTest(unittest.TestCase):
    def test_accuracy_and_calibration(self):
        template = make_sample_template()
        items = segment_upload(make_upload(n_pages=1), template)
        rec = TestDoubleRecognizer(recognizer_script())
        report = evaluate(rec, labeled_set(template, items))
        self.assertEqual(report.total, 8)
        self.assertEqual(report.correct, 7)  # the deliberate Q2 grading-mark miss
        self.assertAlmostEqual(report.accuracy_for(HANDWRITING), 1.0)
        self.assertLess(report.accuracy_for(GRADING_MARK), 1.0)
        # the miss had reliability 0.93 >= threshold: a would-be silent error
        missed = [e for e in report.errors if e["reliability"] >= 0.8]
        self.assertEqual(len(missed), 1)
        self.assertEqual(missed[0]["item_key"], "Q2")

    def test_go_no_go_marks_unevaluated_and_warns(self):
        template = make_sample_template()
        items = segment_upload(make_upload(n_pages=1), template)
        rec = TestDoubleRecognizer(recognizer_script())
        report = evaluate(rec, labeled_set(template, items))
        text = go_no_go_report(report, recognizer_name="TestDoubleRecognizer",
                               dataset="synthetic fixture (8 items)")
        self.assertIn("NEEDS MORE WORK", text)  # grading marks below target
        self.assertIn("slip past the review queue", text)  # silent-error warning
        # empty eval set -> explicitly UNEVALUATED, never pilot-ready by default
        empty_text = go_no_go_report(evaluate(rec, []),
                                     recognizer_name="TestDoubleRecognizer",
                                     dataset="none")
        self.assertIn("UNEVALUATED", empty_text)
        self.assertIn("NOT pilot-ready by default", empty_text)


class ManualEntryTest(unittest.TestCase):
    def test_end_to_end_round_trip(self):
        template = make_sample_template()
        records = commit_rows(manual_entry_rows(), "S003", "A-CH3-01",
                              template=template, page_ref="scan.jpg#page0")
        self.assertEqual(len(records), 10)
        self.assertTrue(all(r.source == "manual" and r.reliability == 1.0
                            for r in records))
        by_key = {r.item_key: r for r in records}
        self.assertEqual(by_key["Q11#b"].grading_mark.comment, "需说明原因")
        self.assertEqual(by_key["Q5#blank2"].grading_mark.score, "1/2")
        # dict round-trip: the downstream contract
        for r in records:
            d = r.to_dict()
            self.assertEqual(AnswerRecord.from_dict(
                json.loads(json.dumps(d, ensure_ascii=False))).to_dict(), d)

    def test_template_validation_rejects_unknown_key(self):
        template = make_sample_template()
        session = ManualEntrySession("S003", "A-CH3-01", template)
        with self.assertRaises(ValueError):
            from manual_entry import ManualEntry
            session.add(ManualEntry(question_id="Q99", part_id=None,
                                    student_answer="x"))


class IdLabelTest(unittest.TestCase):
    def test_label_pdf_is_valid_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "label.pdf")
            write_id_label_pdf(p, "S001", "A-CH3-01", title="Energy chapter")
            with open(p, "rb") as f:
                data = f.read()
            self.assertTrue(data.startswith(b"%PDF-1.4"))
            self.assertIn(b"Student ID: S001", data)
            self.assertIn(b"Assignment: A-CH3-01", data)
            self.assertTrue(data.rstrip().endswith(b"%%EOF"))

    def test_manifest_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            entry = label_for_assignment("S001", "A-CH3-01", "ch3", d)
            mp = os.path.join(d, "manifest.json")
            write_manifest(mp, [entry])
            with open(mp, encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["entries"][0]["student_id"], "S001")
            self.assertEqual(loaded["entries"][0]["assignment_number"], "A-CH3-01")


class PipelineTest(unittest.TestCase):
    def test_full_pipeline_clean_and_ambiguous(self):
        template = make_sample_template()
        rec = TestDoubleRecognizer(recognizer_script())
        # clean upload: both pages link, records produced per student
        result = run_pipeline(make_upload("UP-CLEAN", n_pages=2), template,
                              clean_id_reader(), rec, known_students())
        self.assertEqual(result.pages_linked, 2)
        self.assertEqual(result.pages_queued, 0)
        self.assertEqual(set(result.records_by_student), {"S001", "S002"})
        self.assertTrue(all(r.source == "ocr" for r in result.records))
        # ambiguous upload: nothing linked, everything queued, no records
        result2 = run_pipeline(make_upload("UP-AMB", n_pages=2), template,
                               ambiguous_id_reader(), rec, known_students())
        self.assertEqual(result2.pages_linked, 0)
        self.assertEqual(result2.pages_queued, 2)
        self.assertEqual(result2.records, [])
        self.assertEqual(len(result2.review_queue.pending()), 2)


if __name__ == "__main__":
    unittest.main()
