"""Unit tests for the assembly engine (issue #113 acceptance criteria).

Run from ``homework-pilot/`` with ``python3 -m unittest discover -s
assembly/tests -t .`` or with pytest.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from assembly import (  # noqa: E402
    HomeworkPlan,
    HypothesisStrength,
    ItemCategory,
    MasteryState,
    SkillEvidence,
    StudentProfile,
    TeacherConfig,
    WeakPointHypothesis,
    assemble,
    bank_selector,
)

CURRENT_SCOPE = [
    "ch3-gravitational-work",
    "ch3-estimate-average-power",
    "ch3-work-vs-power",
]
REVIEW_SCOPE = ["ch3-judge-work"]


def make_config(**overrides) -> TeacherConfig:
    kwargs = dict(
        current_scope=list(CURRENT_SCOPE),
        review_scope=list(REVIEW_SCOPE),
        max_questions=12,
        max_minutes=60.0,
        common_question_ids=["SYN-COMMON-01", "SYN-COMMON-02"],
        weak_point_base_count=3,
        recurring_difficulty_rounds=3,
        default_minutes_per_question=5.0,
    )
    kwargs.update(overrides)
    return TeacherConfig(**kwargs)


def ev(student_id, skill_id, state, weak_point=None) -> SkillEvidence:
    return SkillEvidence(
        student_id=student_id, skill_id=skill_id, state=state, weak_point=weak_point
    )


class TestNewStudent(unittest.TestCase):
    """New student: insufficient evidence -> mostly current-scope questions."""

    def test_mostly_current_learning(self):
        profile = StudentProfile(
            student_id="S-NEW",
            evidence=[ev("S-NEW", s, MasteryState.INSUFFICIENT) for s in CURRENT_SCOPE],
        )
        plan = assemble(profile, make_config(), selector=bank_selector)
        self.assertIsInstance(plan, HomeworkPlan)
        counts = plan.count_by_category()
        current = counts.get(ItemCategory.CURRENT.value, 0)
        non_common = len(plan.items) - counts.get(ItemCategory.COMMON.value, 0)
        # everything non-common must be 当前学习 for a brand-new student
        self.assertEqual(current, non_common)
        self.assertGreater(current, 0)
        # 共同题 present per config
        self.assertEqual(counts.get(ItemCategory.COMMON.value, 0), 2)
        self.assertTrue(plan.within_budget)
        self.assertEqual(plan.teacher_prompts, [])


class TestImprovingStudent(unittest.TestCase):
    """Improving student: reduced weak-point repetition + verification."""

    def test_reduced_repetition_and_verification(self):
        profile = StudentProfile(
            student_id="S-IMP",
            evidence=[
                ev("S-IMP", "ch3-gravitational-work", MasteryState.INSUFFICIENT),
                ev(
                    "S-IMP",
                    "ch3-estimate-average-power",
                    MasteryState.IMPROVING,
                    WeakPointHypothesis(
                        skill_id="ch3-estimate-average-power",
                        strength=HypothesisStrength.REPEATED_ERRORS,
                        consecutive_rounds=2,
                        basis_note="两次估算题数量级错误",
                    ),
                ),
                ev("S-IMP", "ch3-work-vs-power", MasteryState.INSUFFICIENT),
            ],
        )
        plan = assemble(profile, make_config(), selector=bank_selector)
        weak_items = [
            i for i in plan.items
            if i.skill_id == "ch3-estimate-average-power"
            and i.category == ItemCategory.WEAK_POINT
        ]
        plain_weak = [i for i in weak_items if not i.verification_kind and not i.is_diagnostic]
        verification = [i for i in weak_items if i.verification_kind == "different_context"]
        # base is 3; improving shrinks to base - 1 = 2 plain repeats ...
        self.assertEqual(len(plain_weak), 2)
        # ... plus one different-context verification item, never a plain repeat
        self.assertEqual(len(verification), 1)
        # no escalation prompt: only 2 consecutive rounds (< 3 threshold)
        self.assertEqual(plan.teacher_prompts, [])
        self.assertTrue(plan.within_budget)


class TestRecurringDifficulty(unittest.TestCase):
    """Recurring difficulty: escalation prompt + ONE diagnostic, bounded count."""

    def test_escalation_prompt_and_bounded_count(self):
        weak = WeakPointHypothesis(
            skill_id="ch3-work-vs-power",
            strength=HypothesisStrength.REPEATED_ERRORS,
            consecutive_rounds=4,  # >= threshold of 3
            basis_note="连续 4 轮混淆功与功率",
        )
        profile = StudentProfile(
            student_id="S-REC",
            evidence=[
                ev("S-REC", "ch3-gravitational-work", MasteryState.INSUFFICIENT),
                ev("S-REC", "ch3-estimate-average-power", MasteryState.MASTERED),
                ev("S-REC", "ch3-work-vs-power", MasteryState.NEEDS_PRACTICE, weak),
            ],
        )
        config = make_config(max_questions=10)
        plan = assemble(profile, config, selector=bank_selector)

        # exactly one diagnostic/foundational item
        diagnostics = [i for i in plan.items if i.is_diagnostic]
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].skill_id, "ch3-work-vs-power")

        # teacher prompt: 可能需要讲解, never silently absorbed
        self.assertEqual(len(plan.teacher_prompts), 1)
        self.assertIn("可能需要讲解", plan.teacher_prompts[0])
        self.assertIn("ch3-work-vs-power", plan.teacher_prompts[0])

        # bounded: capped weak-point items, total within budget
        weak_items = [
            i for i in plan.items
            if i.skill_id == "ch3-work-vs-power" and not i.is_diagnostic
        ]
        self.assertLessEqual(len(weak_items), 2)
        self.assertLessEqual(len(plan.items), 10)
        self.assertTrue(plan.within_budget)


class TestBudgetEnforcement(unittest.TestCase):
    """Total question count / estimated time stays within the teacher's budget."""

    def _struggling_everywhere(self, student_id="S-BUD"):
        return StudentProfile(
            student_id=student_id,
            evidence=[
                ev(
                    student_id,
                    s,
                    MasteryState.NEEDS_PRACTICE,
                    WeakPointHypothesis(skill_id=s, consecutive_rounds=1),
                )
                for s in CURRENT_SCOPE
            ],
        )

    def test_question_count_cap(self):
        plan = assemble(
            self._struggling_everywhere(), make_config(max_questions=6), selector=bank_selector
        )
        self.assertLessEqual(len(plan.items), 6)
        self.assertTrue(plan.within_budget)
        # overflow is recorded, not silently dropped
        self.assertGreater(len(plan.dropped_items), 0)

    def test_time_budget_cap(self):
        plan = assemble(
            self._struggling_everywhere(),
            make_config(max_questions=20, max_minutes=15.0),
            selector=bank_selector,
        )
        self.assertLessEqual(plan.total_minutes, 15.0)
        self.assertTrue(plan.within_budget)

    def test_diagnostic_still_fits_tiny_budget(self):
        weak = WeakPointHypothesis(
            skill_id="ch3-work-vs-power", consecutive_rounds=5,
        )
        profile = StudentProfile(
            student_id="S-TINY",
            evidence=[
                ev("S-TINY", "ch3-gravitational-work", MasteryState.MASTERED),
                ev("S-TINY", "ch3-estimate-average-power", MasteryState.MASTERED),
                ev("S-TINY", "ch3-work-vs-power", MasteryState.NEEDS_PRACTICE, weak),
            ],
        )
        # budget of 2 (after 0 common): diagnostic + teacher prompt must survive
        plan = assemble(
            profile,
            make_config(max_questions=2, common_question_ids=[]),
            selector=bank_selector,
        )
        self.assertLessEqual(len(plan.items), 2)
        self.assertEqual(len([i for i in plan.items if i.is_diagnostic]), 1)
        self.assertTrue(any("可能需要讲解" in p for p in plan.teacher_prompts))


class TestCommonQuestionSlots(unittest.TestCase):
    """Common-question slots are configurable by the teacher."""

    def test_common_slots_configurable(self):
        profile = StudentProfile(
            student_id="S-COM",
            evidence=[ev("S-COM", s, MasteryState.INSUFFICIENT) for s in CURRENT_SCOPE],
        )
        plan = assemble(
            profile, make_config(common_question_ids=["Q-A", "Q-B", "Q-C"]),
            selector=bank_selector,
        )
        commons = [i for i in plan.items if i.category == ItemCategory.COMMON]
        self.assertEqual([i.question_id for i in commons], ["Q-A", "Q-B", "Q-C"])

    def test_zero_common_slots(self):
        profile = StudentProfile(
            student_id="S-COM0",
            evidence=[ev("S-COM0", s, MasteryState.INSUFFICIENT) for s in CURRENT_SCOPE],
        )
        plan = assemble(
            profile, make_config(common_question_ids=[]), selector=bank_selector
        )
        self.assertEqual(
            plan.count_by_category().get(ItemCategory.COMMON.value, 0), 0
        )


class TestReviewMix(unittest.TestCase):
    """待复习 skills inside the review scope get review items."""

    def test_review_items_scheduled(self):
        profile = StudentProfile(
            student_id="S-REV",
            evidence=[
                ev("S-REV", "ch3-gravitational-work", MasteryState.INSUFFICIENT),
                ev("S-REV", "ch3-judge-work", MasteryState.DUE_REVIEW),
            ],
        )
        plan = assemble(profile, make_config(), selector=bank_selector)
        reviews = [i for i in plan.items if i.category == ItemCategory.REVIEW]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].skill_id, "ch3-judge-work")
        self.assertTrue(plan.within_budget)


if __name__ == "__main__":
    unittest.main()
