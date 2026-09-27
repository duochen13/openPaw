"""Unit tests for question generation + pre-release validation (issue #114).

Covers: the sample generated set (>= 3 skills) passing the checklist,
the checklist catching insufficient conditions / non-unique answers /
missing units / figure inconsistencies, figure placeholder routing,
the internet-source rule, and per-skill figure-need stats.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from assembly import (  # noqa: E402
    SAMPLE_GENERATED_SET,
    Difficulty,
    FigureNeedStats,
    FigureStatus,
    FigureTask,
    Question,
    QuestionType,
    create_question,
    validate_question,
)


def base_question(**overrides):
    kwargs = dict(
        id="SYN-TEST-01",
        skill_ids=["ch3-gravitational-work"],
        stem="质量为 2 kg 的物体从 5 m 高处下落，求重力做功。",
        question_type=QuestionType.CALCULATION,
        figure=FigureStatus.NONE,
        given_quantities={"mass": "2 kg", "height": "5 m"},
        required_inputs=["mass", "height"],
        target="重力做功",
        answer="100 J（取 g = 10 N/kg）",
        answer_is_unique=True,
        solution_steps=["W = m·g·h"],
        scoring_notes="公式与单位正确即满分",
        difficulty=Difficulty.EASY,
        recommendation_reason="test fixture",
    )
    kwargs.update(overrides)
    return create_question(**kwargs)


class TestSampleGeneratedSet(unittest.TestCase):
    """Acceptance: sample generated set for >= 3 skills, all passing."""

    def test_at_least_three_skills_all_pass(self):
        skills = {s for q in SAMPLE_GENERATED_SET for s in q.skill_ids}
        self.assertGreaterEqual(len(skills), 3)
        failures = []
        for q in SAMPLE_GENERATED_SET:
            report = validate_question(q)
            if not report.passed:
                failures.append((q.id, report.failed_checks))
        self.assertEqual(failures, [], f"sample questions failed validation: {failures}")

    def test_full_metadata_present(self):
        for q in SAMPLE_GENERATED_SET:
            self.assertTrue(q.skill_ids)
            self.assertTrue(q.recommendation_reason)
            self.assertTrue(q.answer)
            self.assertTrue(q.solution_steps)
            self.assertTrue(q.scoring_notes)


class TestChecklistCatchesProblems(unittest.TestCase):
    def test_insufficient_conditions_caught(self):
        q = base_question(required_inputs=["mass", "height", "g"])  # g not given
        report = validate_question(q)
        self.assertFalse(report.passed)
        self.assertIn("sufficient_conditions", report.failed_checks)

    def test_missing_target_caught(self):
        q = base_question(target="")
        report = validate_question(q)
        self.assertIn("sufficient_conditions", report.failed_checks)

    def test_non_unique_answer_without_alternatives_caught(self):
        q = base_question(answer_is_unique=False, acceptable_alternatives=[])
        report = validate_question(q)
        self.assertIn("unique_answer", report.failed_checks)

    def test_non_unique_answer_with_alternatives_passes(self):
        q = base_question(
            answer_is_unique=False,
            acceptable_alternatives=["140–160 W（估算范围）"],
        )
        report = validate_question(q)
        self.assertNotIn("unique_answer", report.failed_checks)

    def test_missing_units_caught(self):
        q = base_question(given_quantities={"mass": "2", "height": "5 m"})
        report = validate_question(q)
        self.assertIn("si_units", report.failed_checks)

    def test_unrecognized_units_caught(self):
        q = base_question(given_quantities={"mass": "2 jin", "height": "5 m"})
        report = validate_question(q)
        self.assertIn("si_units", report.failed_checks)

    def test_figure_inconsistency_caught(self):
        q = base_question(
            stem="如图所示，物体从斜面滑下，求重力做功。",
            figure=FigureStatus.NONE,
        )
        report = validate_question(q)
        self.assertIn("figure_text_consistency", report.failed_checks)

    def test_provided_figure_without_description_caught(self):
        q = base_question(
            stem="如图所示，物体从斜面滑下，求重力做功。",
            figure=FigureStatus.PROVIDED,
            figure_description="",
        )
        report = validate_question(q)
        self.assertIn("figure_text_consistency", report.failed_checks)


class TestFigurePlaceholderRouting(unittest.TestCase):
    def test_placeholder_auto_flags_teacher_task(self):
        task = FigureTask(
            question_id="SYN-TEST-02",
            skill_id="ch3-work-phases",
            description="三阶段示意图",
            why_needed="纯文字易产生歧义",
        )
        q = base_question(
            id="SYN-TEST-02",
            stem="如图所示为跳远三阶段，判断做功阶段。",
            figure=FigureStatus.PLACEHOLDER,
            figure_task=task,
        )
        report = validate_question(q)
        # placeholder is NOT a validation failure ...
        self.assertNotIn("figure_text_consistency", report.failed_checks)
        # ... but it is flagged for the teacher, never silently dropped
        self.assertIsNotNone(report.teacher_figure_task)
        self.assertEqual(report.teacher_figure_task.description, "三阶段示意图")

    def test_placeholder_auto_creates_task_when_missing(self):
        q = create_question(
            id="SYN-TEST-03",
            skill_ids=["ch3-work-phases"],
            stem="如图所示，判断各阶段做功情况。",
            figure=FigureStatus.PLACEHOLDER,
            target="各阶段做功判断",
            answer="见解析",
        )
        self.assertIsNotNone(q.figure_task)
        self.assertEqual(q.figure_task.question_id, "SYN-TEST-03")


class TestInternetSourceRule(unittest.TestCase):
    def test_internet_rejected_without_explicit_flag(self):
        with self.assertRaises(ValueError):
            create_question(
                id="SYN-TEST-04",
                skill_ids=["ch3-gravitational-work"],
                stem="网络来源题目",
                source="internet",
                source_attribution="https://example.com/q/1",
            )

    def test_internet_rejected_without_attribution(self):
        with self.assertRaises(ValueError):
            create_question(
                id="SYN-TEST-05",
                skill_ids=["ch3-gravitational-work"],
                stem="网络来源题目",
                source="internet",
                allow_internet=True,
            )

    def test_internet_allowed_with_flag_and_attribution(self):
        q = create_question(
            id="SYN-TEST-06",
            skill_ids=["ch3-gravitational-work"],
            stem="网络来源题目（已获准作为补充材料）",
            source="internet",
            source_attribution="https://example.com/q/1（已获准引用）",
            allow_internet=True,
        )
        self.assertEqual(q.source, "internet")
        self.assertTrue(q.source_attribution)

    def test_generated_is_default(self):
        q = base_question()
        self.assertEqual(q.source, "generated")


class TestFigureNeedStats(unittest.TestCase):
    def test_tracks_figure_needs_per_skill(self):
        stats = FigureNeedStats()
        for q in SAMPLE_GENERATED_SET:
            stats.record(q)
        # ch3-work-phases genuinely needs a figure ...
        self.assertIn("ch3-work-phases", stats.skills_needing_figures())
        # ... while the calculation skills work fine text-only
        for skill in (
            "ch3-gravitational-work",
            "ch3-estimate-average-power",
            "ch3-work-vs-power",
            "ch3-judge-work",
        ):
            self.assertIn(skill, stats.text_only_skills())
        summary = stats.summary()
        self.assertEqual(summary["ch3-work-phases"]["needs_figure"], 1)


if __name__ == "__main__":
    unittest.main()
