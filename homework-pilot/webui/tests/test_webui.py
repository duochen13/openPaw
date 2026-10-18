"""Tests for the teacher console UI (issue #167).

All fixture content is synthetic (``S-0xx`` student IDs, ``SYN-``
questions) -- real teacher materials are pending #108 field work.

The privacy tests here are the point of the package: they pin the
design doc's hard rules so a future fixture or template edit cannot
quietly break them -- ID-only students, the five teaching-judgment
states, no precise mastery percentages, and OCR reliability kept
separate from mastery judgment.
"""

import json
import re
import unittest
from dataclasses import asdict, fields

from ..fixtures import build_demo_data
from ..models import (
    MASTERY_STATES,
    MIX_CATEGORIES,
    ReliabilityTier,
    reliability_tier,
)
from ..render import (
    dashboard_vm,
    export_vm,
    hypothesis_vm,
    recognition_vm,
    render_console,
    review_vm,
)

STUDENT_ID_RE = re.compile(r"^S-\d{3}$")

#: Keys that would mean a student's name entered the data (mirrors the
#: spirit of privacy.guard.NAME_FIELD_KEYS; "skill_name" is a *skill's*
#: name and is legitimate, a bare "name" is not).
FORBIDDEN_KEYS = {
    "name", "names", "student_name", "studentname", "full_name",
    "fullname", "nickname", "姓名", "名字",
}

VIEWS = ("dashboard", "recognition", "hypotheses", "review", "export")


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


def _all_student_ids(data):
    ids = set()
    for cls in data.classes:
        ids.update(i.student_id for i in cls.recognition)
        ids.update(h.student_id for h in cls.hypotheses)
        ids.update(m.student_id for m in cls.mix)
        ids.update(sid for sid, _pages in cls.export.students)
    return ids


class TestRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo_data()
        cls.html = render_console(cls.data)

    def test_all_five_views_render_for_each_class(self):
        for cls in self.data.classes:
            for view in VIEWS:
                marker = f'data-cls="{cls.key}" data-view="{view}"'
                self.assertIn(marker, self.html, marker)
        for label in ("工作台", "识别确认", "薄弱点确认", "作业审核", "导出"):
            self.assertIn(label, self.html)

    def test_class_switcher_and_counts(self):
        for cls in self.data.classes:
            self.assertIn(f'data-cls-btn="{cls.key}"', self.html)
            self.assertIn(cls.label, self.html)
        match = re.search(r"var CLASS_COUNTS = (\{.*?\});", self.html, re.S)
        self.assertIsNotNone(match)
        counts = json.loads(match.group(1))
        for cls in self.data.classes:
            self.assertEqual(
                counts[cls.key]["recognition"], len(cls.recognition))
            self.assertEqual(
                counts[cls.key]["hypotheses"], len(cls.hypotheses))
            self.assertEqual(
                counts[cls.key]["review"], len(cls.review_questions))

    def test_dashboard_counts_match_fixtures(self):
        for cls in self.data.classes:
            vm = dashboard_vm(cls)
            self.assertEqual(vm["recognition_count"], len(cls.recognition))
            self.assertEqual(vm["hypothesis_count"], len(cls.hypotheses))
            self.assertEqual(vm["review_count"], len(cls.review_questions))
            self.assertIn(cls.export.last_export, self.html)

    def test_self_contained_no_external_resources(self):
        self.assertNotIn("<script src", self.html)
        self.assertNotIn("<link", self.html)
        self.assertNotIn("<img", self.html)
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
        self.assertNotIn("url(", self.html)

    def test_user_text_is_escaped(self):
        from ..models import ClassData, ConsoleData, ReviewQuestionView

        evil = ReviewQuestionView(
            id="SYN-X", category="共同题",
            stem="<script>alert(1)</script>",
            skill_names=["计算重力做功"], answer="a", scoring_notes="b",
        )
        data = ConsoleData(classes=[ClassData(
            key="g9-9", label="九年级9班", chapter_label="演示",
            assignment_number="A-X", review_questions=[evil],
        )])
        html = render_console(data)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class TestPrivacyRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo_data()
        cls.html = render_console(cls.data)

    def test_no_name_like_fields_anywhere_in_fixtures(self):
        for _path, key, _value in _walk(asdict(self.data)):
            if key is not None:
                self.assertNotIn(
                    str(key).lower(), FORBIDDEN_KEYS,
                    f"name-like key leaked into fixtures: {key}")

    def test_every_student_reference_is_an_id(self):
        ids = _all_student_ids(self.data)
        self.assertTrue(ids, "fixtures should reference students")
        for sid in ids:
            self.assertRegex(sid, STUDENT_ID_RE)
        # No other S-### shaped tokens hide in fixture text.
        for _path, _key, value in _walk(asdict(self.data)):
            if isinstance(value, str):
                for token in re.findall(r"S-\d{3}", value):
                    self.assertIn(token, ids)

    def test_no_mastery_percentages(self):
        # Fixture and view-model text must never carry a percentage.
        for _path, _key, value in _walk(asdict(self.data)):
            if isinstance(value, str):
                self.assertNotIn("%", value)
                self.assertNotIn("％", value)
        # Visible page text (style/script stripped) shows no "NN %" either.
        text = re.sub(r"<(style|script)>.*?</\1>", "", self.html, flags=re.S)
        self.assertIsNone(re.search(r"\d\s*(%|％)", text))

    def test_skill_states_are_only_the_five_judgments(self):
        used = {h.state for cls in self.data.classes for h in cls.hypotheses}
        self.assertTrue(used)
        self.assertLessEqual(used, set(MASTERY_STATES))
        # The legend in the UI lists all five states.
        for state in MASTERY_STATES:
            self.assertIn(state, self.html)

    def test_reliability_and_mastery_are_separate(self):
        # Recognition items carry OCR reliability and no mastery state.
        item_fields = {f.name for f in fields(
            type(self.data.classes[0].recognition[0]))}
        self.assertIn("ocr_reliability", item_fields)
        self.assertNotIn("state", item_fields)
        # The recognition view shows all three reliability tiers...
        for label in ("识别可靠", "识别存疑", "识别需手录"):
            self.assertIn(label, self.html)
        # ...and hypothesis VMs expose a state but no OCR number.
        for cls in self.data.classes:
            for h in cls.hypotheses:
                vm = hypothesis_vm(h)
                self.assertIn(vm["state"], MASTERY_STATES)
                self.assertNotIn("ocr_reliability", vm)


class TestReliabilityTiers(unittest.TestCase):
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


class TestFixtureIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_demo_data()

    def test_every_question_is_reviewable(self):
        for cls in self.data.classes:
            self.assertTrue(cls.review_questions)
            for q in cls.review_questions:
                self.assertTrue(q.stem.strip(), q.id)
                self.assertTrue(q.skill_names, q.id)       # 目标技能
                self.assertTrue(q.answer.strip(), q.id)    # 参考答案
                self.assertTrue(q.scoring_notes.strip(), q.id)  # 评分说明
                self.assertTrue(q.solution_steps, q.id)
                self.assertIn(q.category, MIX_CATEGORIES)
                review_vm(q)  # builder must not choke

    def test_recognition_items_are_complete(self):
        for cls in self.data.classes:
            self.assertTrue(cls.recognition)
            for item in cls.recognition:
                vm = recognition_vm(item)
                self.assertTrue(vm["question_label"])
                self.assertTrue(vm["skill_name"])
                if item.tier is not ReliabilityTier.MANUAL:
                    self.assertTrue(vm["answer"])

    def test_export_view_model(self):
        for cls in self.data.classes:
            vm = export_vm(cls)
            self.assertTrue(vm["assignment_number"])
            self.assertTrue(vm["students"])
            for sid, pages in vm["students"]:
                self.assertRegex(sid, STUDENT_ID_RE)
                self.assertGreater(pages, 0)
            self.assertGreater(vm["teacher_key_pages"], 0)

    def test_export_placeholders_name_backend_functions(self):
        html = render_console(self.data)
        for fn in ("export_class", "export_teacher_key",
                   "export_student_sheet"):
            self.assertIn(f'data-export-fn="{fn}"', html)


if __name__ == "__main__":
    unittest.main()
