"""Webui adapter: pipeline output drops into the student UI model."""

import sys
import unittest
from pathlib import Path

from ..adapter import to_webui_paper, to_webui_question, unrenderable_items
from ..models import GradedPaper, ItemResult
from ..pipeline import grade_kit_paper

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from webui.models import QuestionResult, StudentData  # noqa: E402
from webui.render import render_demo  # noqa: E402

KIT = Path(__file__).resolve().parents[2] / "pilot-kit"


def item(**overrides):
    base = dict(item_key="Q1", question_id="Q1", number=1,
                question_text="题干", student_answer="C",
                ocr_reliability=0.95, page_label="第 1 页")
    base.update(overrides)
    return ItemResult(**base)


class TestAdapterUnits(unittest.TestCase):
    def test_decided_item_converts_field_for_field(self):
        source = item(verdict="错", source="答案比对", reference_answer="B")
        converted = to_webui_question(source)
        self.assertIsInstance(converted, QuestionResult)
        self.assertEqual(converted.verdict, "错")
        self.assertEqual(converted.source, "答案比对")
        self.assertEqual(converted.reference_answer, "B")
        self.assertEqual(converted.student_answer, "C")

    def test_pending_with_lean_converts(self):
        source = item(verdict="待确认", pending_reason="judgment_uncertain",
                      proposed_verdict="对", proposal_source="模型判定")
        self.assertEqual(to_webui_question(source).proposed_verdict, "对")

    def test_pending_without_lean_fails_loudly(self):
        source = item(verdict="待确认", pending_reason="unreadable",
                      student_answer="")
        with self.assertRaises(ValueError):
            to_webui_question(source)

    def test_confirmed_item_is_not_demo_state(self):
        source = item(verdict="对", source="学生确认", confirmed=True,
                      confirmed_verdict="对")
        with self.assertRaises(ValueError):
            to_webui_question(source)


class TestAdapterOnKitPaper(unittest.TestCase):
    def test_kit_paper_conversion_coverage_is_exact(self):
        paper = grade_kit_paper(KIT, "S-001")
        blocked = unrenderable_items(paper)
        with self.assertRaises(ValueError):
            to_webui_paper(paper)  # strict: names the unrenderable items
        converted = to_webui_paper(paper, skip_unrenderable=True)
        self.assertEqual(
            len(converted.questions) + len(blocked), len(paper.items))
        for question in converted.questions:
            self.assertIn(question.verdict, ("对", "错", "待确认"))

    def test_converted_paper_renders_in_the_student_ui(self):
        paper = grade_kit_paper(KIT, "S-001")
        converted = to_webui_paper(paper, skip_unrenderable=True)
        html = render_demo(StudentData(student_id="S-001", papers=[converted]))
        self.assertIn("S-001", html)
        self.assertIn("第1题", html)
        self.assertIn("来源：红笔标记", html)


if __name__ == "__main__":
    unittest.main()
