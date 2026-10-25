"""Confirmation queue behavior + labeled-examples export (issue #176)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from ..confirm import apply_confirmation, export_labeled_examples, write_jsonl
from ..models import GradedPaper, ItemResult

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from privacy.guard import assert_id_only  # noqa: E402


def pending_item(**overrides):
    base = dict(
        item_key="Q10", question_id="Q10", number=7,
        question_text="牵引力做功与功率", student_answer="W = 40000 J",
        verdict="待确认", source="红笔标记",
        pending_reason="partial_credit", mark_kind="score",
        ocr_reliability=0.93, image_location="p2.png#region=0.05,0.30,0.90,0.10",
        page_label="第 2 页", knowledge_point_tag="功率的计算",
    )
    base.update(overrides)
    return ItemResult(**base)


def paper_with(item):
    return GradedPaper(student_id="S-001", items=(item,))


class TestApplyConfirmation(unittest.TestCase):
    def test_accept_proposal_records_student_as_source(self):
        paper = paper_with(pending_item(
            proposed_verdict="对", proposal_source="答案比对"))
        confirmed = apply_confirmation(paper, "Q10", accept_proposal=True)
        item = confirmed.items[0]
        self.assertEqual(item.verdict, "对")
        self.assertEqual(item.source, "学生确认")
        self.assertTrue(item.confirmed)
        self.assertEqual(item.confirmed_verdict, "对")
        # The system output is preserved for the labeled pair.
        self.assertEqual(item.system_verdict, "待确认")
        self.assertEqual(item.system_source, "红笔标记")
        self.assertEqual(item.system_proposed_verdict, "对")
        # The original paper is untouched (frozen pipeline output).
        self.assertEqual(paper.items[0].verdict, "待确认")

    def test_student_override_and_transcription_correction(self):
        paper = paper_with(pending_item(needs_transcription_confirmation=True))
        confirmed = apply_confirmation(
            paper, "Q10", verdict="错",
            corrected_answer="W = 2000 × 300 = 600000 J",
            reference_answer="（1）1.2×10⁷ J；（2）4×10⁴ W",
        )
        item = confirmed.items[0]
        self.assertEqual(item.verdict, "错")
        self.assertEqual(item.student_answer, "W = 2000 × 300 = 600000 J")
        self.assertFalse(item.needs_transcription_confirmation)
        self.assertFalse(item.in_confirmation_queue)

    def test_confirmation_as_wrong_needs_a_reference(self):
        paper = paper_with(pending_item())
        with self.assertRaises(ValueError):
            apply_confirmation(paper, "Q10", verdict="错")

    def test_confirmation_without_decision_is_rejected(self):
        paper = paper_with(pending_item())
        with self.assertRaises(ValueError):
            apply_confirmation(paper, "Q10")
        with self.assertRaises(ValueError):
            apply_confirmation(paper, "Q10", accept_proposal=True)

    def test_unknown_item_raises(self):
        with self.assertRaises(KeyError):
            apply_confirmation(paper_with(pending_item()), "Q99",
                               verdict="对")


class TestExport(unittest.TestCase):
    def test_only_confirmed_items_export(self):
        paper = GradedPaper(
            student_id="S-001",
            items=(
                pending_item(),
                pending_item(item_key="Q4", question_id="Q4"),
            ),
        )
        paper = apply_confirmation(paper, "Q10", verdict="对")
        examples = export_labeled_examples(paper)
        self.assertEqual(len(examples), 1)
        example = examples[0]
        self.assertEqual(example["student_id"], "S-001")
        self.assertEqual(example["verdict"], "对")
        self.assertEqual(example["verdict_source"], "学生确认")
        self.assertEqual(example["system_verdict"], "待确认")
        assert_id_only(example)  # ID-only: no name-like keys anywhere

    def test_jsonl_round_trip(self):
        paper = apply_confirmation(
            paper_with(pending_item()), "Q10", verdict="对")
        examples = export_labeled_examples(paper)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labeled.jsonl"
            self.assertEqual(write_jsonl(examples, path), 1)
            rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
        self.assertEqual(rows[0]["item_key"], "Q10")
        self.assertEqual(rows[0]["knowledge_point_tag"], "功率的计算")


if __name__ == "__main__":
    unittest.main()
