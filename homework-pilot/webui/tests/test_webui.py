"""Tests for the student-side MVP UI (issue #176).

All fixture content is synthetic (one invented student, ``S-023``) --
real student materials must never be pasted into fixtures.

The privacy / honesty tests here are the point of the package: they
pin the rules the pivot kept -- ID-only students, the exact verdict
vocabulary （对 / 错 / 待确认）, no skill-state or mastery UI anywhere
on the student surface, and OCR reliability kept separate from the
correctness verdict -- so a future fixture or template edit cannot
quietly break them.
"""

import re
import unittest
from dataclasses import asdict
from html import escape as html_escape

from ..fixtures import build_demo_data
from ..models import (
    VERDICTS,
    VERDICT_SOURCES,
    PaperResult,
    QuestionResult,
    ReliabilityTier,
    StudentData,
    reliability_tier,
)
from ..render import confirm_vm, paper_vm, question_vm, render_demo

STUDENT_ID_RE = re.compile(r"^S-\d{3}$")

#: Keys that would mean a student's name entered the data (mirrors the
#: spirit of privacy.guard.NAME_FIELD_KEYS).
FORBIDDEN_KEYS = {
    "name", "names", "student_name", "studentname", "full_name",
    "fullname", "nickname", "姓名", "名字",
}

#: The five teacher-side teaching judgments. They belong to the old
#: teacher console (#167) and must never leak onto the student surface.
FIVE_STATES = (
    "证据不足", "需要练习", "正在改善", "已有较充分掌握证据", "待复习",
)

MAIN_PAPER_ID = "paper-ch3-test"


def _walk(node, path=""):
    """Yield (path, key, value) for every leaf of a nested structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
            yield path, key, value
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}[{i}]")
    else:
        yield path, None, node


def _main_paper(data):
    return next(p for p in data.papers if p.id == MAIN_PAPER_ID)


class TestRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo_data()
        cls.html = render_demo(cls.data)

    def test_three_views_render(self):
        self.assertIn('data-view="papers"', self.html)
        self.assertIn('data-view="confirm"', self.html)
        # One result section per processed paper, none for 处理中.
        for paper in self.data.papers:
            marker = f'data-view="result" data-paper="{paper.id}"'
            if paper.questions:
                self.assertIn(marker, self.html)
            else:
                self.assertNotIn(marker, self.html)
        for label in ("试卷", "待确认"):
            self.assertIn(label, self.html)

    def test_teacher_console_is_gone(self):
        for gone in ("工作台", "薄弱点确认", "作业审核", "识别确认",
                     "班级", "教师版"):
            self.assertNotIn(gone, self.html)
        for state in FIVE_STATES:
            self.assertNotIn(state, self.html)

    def test_upload_card_and_paper_list(self):
        self.assertIn("上传已完成试卷（扫描 PDF）", self.html)
        for paper in self.data.papers:
            self.assertIn(paper.title, self.html)
            self.assertIn(paper.date_label, self.html)
        # Processed papers open their result; the processing one cannot.
        self.assertIn(f'data-open-paper="{MAIN_PAPER_ID}"', self.html)

    def test_pending_badge_matches_queue(self):
        pending = len(self.data.pending_items())
        self.assertIn(f'<span class="nav-badge">{pending}</span>', self.html)

    def test_result_view_shows_verdict_source_and_reference(self):
        for source in VERDICT_SOURCES:
            self.assertIn(f"来源：{source}", self.html)
        for paper in self.data.papers:
            for q in paper.questions:
                if q.verdict == "错":
                    self.assertIn(html_escape(q.reference_answer), self.html)
                    self.assertIn("学生答案", self.html)

    def test_confirm_queue_actions(self):
        for label in ("确认", "改转写", "改为对", "改为错"):
            self.assertIn(f'aria-label="{label}"', self.html)
        self.assertIn("标注数据", self.html)  # the training-data footnote

    def test_export_placeholder_names_backend_handoff(self):
        self.assertIn('data-export-fn="export_labeled_data"', self.html)

    def test_self_contained_no_external_resources(self):
        self.assertNotIn("<script src", self.html)
        self.assertNotIn("<link", self.html)
        self.assertNotIn("<img", self.html)
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
        self.assertNotIn("url(", self.html)

    def test_user_text_is_escaped(self):
        evil = PaperResult(
            id="paper-x", title="<script>alert(1)</script>",
            questions=[QuestionResult(
                number=1, question_text="题干", student_answer="答案",
                verdict="对", source="模型判定", ocr_reliability=0.9,
            )],
        )
        html = render_demo(StudentData(student_id="S-023", papers=[evil]))
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class TestPrivacyRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo_data()
        cls.html = render_demo(cls.data)

    def test_no_name_like_fields_anywhere_in_fixtures(self):
        for _path, key, _value in _walk(asdict(self.data)):
            if key is not None:
                self.assertNotIn(
                    str(key).lower(), FORBIDDEN_KEYS,
                    f"name-like key leaked into fixtures: {key}")

    def test_the_only_student_reference_is_the_demo_id(self):
        self.assertRegex(self.data.student_id, STUDENT_ID_RE)
        self.assertEqual(self.data.student_id, "S-023")
        for _path, _key, value in _walk(asdict(self.data)):
            if isinstance(value, str):
                for token in re.findall(r"S-\d{3}", value):
                    self.assertEqual(token, "S-023")

    def test_no_percentages_anywhere(self):
        for _path, _key, value in _walk(asdict(self.data)):
            if isinstance(value, str):
                self.assertNotIn("%", value)
                self.assertNotIn("％", value)
        text = re.sub(r"<(style|script)>.*?</\1>", "", self.html, flags=re.S)
        self.assertIsNone(re.search(r"\d\s*(%|％)", text))


class TestVerdictRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo_data()

    def test_vocabulary_is_exactly_three_states(self):
        used = {
            q.verdict
            for paper in self.data.papers for q in paper.questions
        }
        self.assertLessEqual(used, set(VERDICTS))
        # The main paper exercises all three.
        self.assertEqual(
            {q.verdict for q in _main_paper(self.data).questions},
            set(VERDICTS),
        )

    def test_main_paper_mix_is_4_2_2(self):
        counts = _main_paper(self.data).verdict_counts()
        self.assertEqual(counts, {"对": 4, "错": 2, "待确认": 2})

    def test_all_three_sources_appear(self):
        used = {
            q.source
            for q in _main_paper(self.data).questions
        }
        self.assertEqual(used, set(VERDICT_SOURCES))

    def test_wrong_questions_carry_a_reference_answer(self):
        for paper in self.data.papers:
            for q in paper.questions:
                if q.verdict == "错":
                    self.assertTrue(q.reference_answer, q.label)
                    self.assertTrue(question_vm(q)["show_reference"])

    def test_pending_questions_carry_a_proposal(self):
        pending = self.data.pending_items()
        self.assertEqual([q.label for _p, q in pending], ["第7题", "第8题"])
        for _paper, q in pending:
            self.assertIn(q.proposed_verdict, ("对", "错"))
            vm = confirm_vm(_paper, q)
            self.assertEqual(vm["paper_title"], _paper.title)


class TestReliabilitySeparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo_data()
        cls.html = render_demo(cls.data)

    def test_thresholds(self):
        self.assertEqual(reliability_tier(0.95), ReliabilityTier.RELIABLE)
        self.assertEqual(reliability_tier(0.8), ReliabilityTier.RELIABLE)
        self.assertEqual(reliability_tier(0.71), ReliabilityTier.DOUBTFUL)
        self.assertEqual(reliability_tier(0.5), ReliabilityTier.DOUBTFUL)
        self.assertEqual(reliability_tier(0.32), ReliabilityTier.MANUAL)
        self.assertEqual(reliability_tier(0.0), ReliabilityTier.MANUAL)

    def test_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            reliability_tier(1.5)

    def test_exactly_one_low_reliability_question(self):
        low = [
            q for q in _main_paper(self.data).questions if q.low_reliability
        ]
        self.assertEqual([q.label for q in low], ["第7题"])
        self.assertIn("识别可靠性低", self.html)

    def test_low_reliability_does_not_decide_the_verdict(self):
        # 第7题 was read shakily but the proposal stays 对： reliability
        # routes to the queue; it never flips a verdict by itself.
        q7 = next(
            q for q in _main_paper(self.data).questions if q.number == 7)
        self.assertTrue(q7.low_reliability)
        self.assertEqual(q7.verdict, "待确认")
        self.assertEqual(q7.proposed_verdict, "对")
        vm = question_vm(q7)
        self.assertTrue(vm["low_reliability"])
        self.assertEqual(vm["verdict"], "待确认")
        # 第8题 is the mirror image: read reliably, judgment uncertain.
        q8 = next(
            q for q in _main_paper(self.data).questions if q.number == 8)
        self.assertFalse(q8.low_reliability)
        self.assertEqual(q8.verdict, "待确认")

    def test_model_validation(self):
        base = dict(number=1, question_text="题", ocr_reliability=0.9)
        with self.assertRaises(ValueError):
            QuestionResult(verdict="错", **base)  # no 参考答案
        with self.assertRaises(ValueError):
            QuestionResult(verdict="待确认", **base)  # no proposal
        with self.assertRaises(ValueError):
            QuestionResult(verdict="大概对了", **base)
        with self.assertRaises(ValueError):
            QuestionResult(verdict="对", source="同学说的", **base)
        with self.assertRaises(ValueError):
            QuestionResult(
                number=1, question_text="题", verdict="对",
                ocr_reliability=1.2)


class TestFixtureIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo_data()

    def test_three_papers_one_processing(self):
        self.assertEqual(len(self.data.papers), 3)
        processing = [p for p in self.data.papers if p.status == "处理中"]
        self.assertEqual(len(processing), 1)
        self.assertEqual(processing[0].questions, [])

    def test_paper_vm_counts_match_model(self):
        for paper in self.data.papers:
            vm = paper_vm(paper)
            self.assertEqual(vm["counts"], paper.verdict_counts())
            self.assertEqual(vm["total"], len(paper.questions))
            self.assertEqual(
                sum(n for _v, n, _c in vm["count_chips"]),
                sum(c for c in vm["counts"].values() if c),
            )


if __name__ == "__main__":
    unittest.main()
