"""Unit tests for the teacher review queue (issue #114)."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from assembly import (  # noqa: E402
    FigureStatus,
    QuestionType,
    ReviewDecision,
    ReviewQueue,
    create_question,
)


def sample_question(qid="SYN-RQ-01", **overrides):
    kwargs = dict(
        id=qid,
        skill_ids=["ch3-gravitational-work"],
        stem="质量为 2 kg 的物体从 5 m 高处下落，求重力做功。",
        question_type=QuestionType.CALCULATION,
        given_quantities={"mass": "2 kg", "height": "5 m"},
        required_inputs=["mass", "height"],
        target="重力做功",
        answer="100 J（取 g = 10 N/kg）",
        solution_steps=["W = m·g·h = 100 J"],
        scoring_notes="公式与单位正确即满分",
        recommendation_reason="基础计算题",
    )
    kwargs.update(overrides)
    return create_question(**kwargs)


class TestReviewQueue(unittest.TestCase):
    def test_add_and_pending(self):
        queue = ReviewQueue()
        queue.add(sample_question())
        queue.add(sample_question("SYN-RQ-02"))
        self.assertEqual(len(queue.pending()), 2)

    def test_duplicate_add_rejected(self):
        queue = ReviewQueue()
        queue.add(sample_question())
        with self.assertRaises(ValueError):
            queue.add(sample_question())

    def test_summary_shows_what_teacher_needs(self):
        queue = ReviewQueue()
        entry = queue.add(sample_question())
        summary = entry.summary()
        for key in (
            "recommendation_reason", "difficulty", "answer",
            "solution_steps", "scoring_notes",
        ):
            self.assertTrue(summary[key], f"summary missing {key}")
        self.assertEqual(summary["difficulty"], "medium")

    def test_approve_flow(self):
        queue = ReviewQueue()
        queue.add(sample_question())
        queue.decide("SYN-RQ-01", ReviewDecision.APPROVED, teacher_note="可用")
        self.assertEqual(len(queue.pending()), 0)
        self.assertEqual(len(queue.approved()), 1)

    def test_replace_requires_replacement_id(self):
        queue = ReviewQueue()
        queue.add(sample_question())
        with self.assertRaises(ValueError):
            queue.decide("SYN-RQ-01", ReviewDecision.REPLACED)
        queue.decide(
            "SYN-RQ-01", ReviewDecision.REPLACED, replacement_question_id="T-REAL-001"
        )
        self.assertEqual(queue.get("SYN-RQ-01").replacement_question_id, "T-REAL-001")

    def test_adjust_and_reject(self):
        queue = ReviewQueue()
        queue.add(sample_question("SYN-RQ-01"))
        queue.add(sample_question("SYN-RQ-02"))
        queue.decide("SYN-RQ-01", ReviewDecision.ADJUSTED, teacher_note="改了数值")
        queue.decide("SYN-RQ-02", ReviewDecision.REJECTED, teacher_note="超纲")
        self.assertEqual(len(queue.approved()), 1)  # adjusted counts as approved
        self.assertEqual(len(queue.pending()), 0)

    def test_figure_tasks_surface_in_queue(self):
        queue = ReviewQueue()
        q = sample_question(
            "SYN-RQ-FIG",
            skill_ids=["ch3-work-phases"],
            stem="如图所示为跳远三阶段，判断做功阶段。",
            figure=FigureStatus.PLACEHOLDER,
        )
        queue.add(q)
        tasks = queue.pending_figure_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].question_id, "SYN-RQ-FIG")
        # once decided, the task leaves the pending teacher to-do list
        queue.decide("SYN-RQ-FIG", ReviewDecision.APPROVED)
        self.assertEqual(queue.pending_figure_tasks(), [])


if __name__ == "__main__":
    unittest.main()
