"""Model invariants for the grading pipeline (issue #176).

Run from homework-pilot/:

    python3 -m unittest discover -s grading/tests -t . -v
"""

import unittest

from ..models import (
    PENDING_REASONS,
    ItemResult,
    GradedPaper,
    reliability_tier,
)


def item(**overrides):
    base = dict(item_key="Q1", question_id="Q1", number=1)
    base.update(overrides)
    return ItemResult(**base)


class TestItemResultInvariants(unittest.TestCase):
    def test_decided_correct_is_valid(self):
        result = item(verdict="对", source="红笔标记", ocr_reliability=0.9)
        self.assertEqual(result.verdict, "对")

    def test_wrong_requires_reference_answer(self):
        with self.assertRaises(ValueError):
            item(verdict="错", source="红笔标记")
        ok = item(verdict="错", source="红笔标记", reference_answer="C")
        self.assertEqual(ok.reference_answer, "C")

    def test_pending_requires_a_known_reason(self):
        with self.assertRaises(ValueError):
            item(verdict="待确认")
        with self.assertRaises(ValueError):
            item(verdict="待确认", pending_reason="made_up_reason")
        for reason in PENDING_REASONS:
            self.assertEqual(
                item(verdict="待确认", pending_reason=reason).pending_reason,
                reason,
            )

    def test_pending_proposal_must_name_its_source(self):
        with self.assertRaises(ValueError):
            item(verdict="待确认", pending_reason="judgment_uncertain",
                 proposed_verdict="对")
        ok = item(verdict="待确认", pending_reason="judgment_uncertain",
                  proposed_verdict="对", proposal_source="答案比对")
        self.assertEqual(ok.proposal_source, "答案比对")

    def test_decided_verdict_carries_no_pending_state(self):
        with self.assertRaises(ValueError):
            item(verdict="对", pending_reason="unreadable")
        with self.assertRaises(ValueError):
            item(verdict="对", proposed_verdict="对",
                 proposal_source="答案比对")

    def test_vocabulary_is_exact(self):
        with self.assertRaises(ValueError):
            item(verdict="正确")
        with self.assertRaises(ValueError):
            item(verdict="对", source="老师批改")

    def test_reliability_range(self):
        with self.assertRaises(ValueError):
            item(ocr_reliability=1.5)
        with self.assertRaises(ValueError):
            item(ocr_reliability=-0.1)

    def test_no_lean_pending_is_representable(self):
        # The honest state the webui demo cannot model: nothing read,
        # nothing leaned. The pipeline must be able to say so.
        result = item(verdict="待确认", pending_reason="unreadable",
                      student_answer="", ocr_reliability=0.31)
        self.assertEqual(result.proposed_verdict, "")


class TestReliabilityAxis(unittest.TestCase):
    def test_tiers_match_webui_cutoffs(self):
        self.assertEqual(reliability_tier(0.8), "reliable")
        self.assertEqual(reliability_tier(0.79), "doubtful")
        self.assertEqual(reliability_tier(0.5), "doubtful")
        self.assertEqual(reliability_tier(0.49), "manual")

    def test_queue_membership_is_verdict_or_transcription(self):
        decided_shaky = item(verdict="对", source="红笔标记",
                             ocr_reliability=0.72,
                             needs_transcription_confirmation=True)
        self.assertTrue(decided_shaky.in_confirmation_queue)
        self.assertEqual(decided_shaky.verdict, "对")  # verdict untouched
        decided_clean = item(verdict="对", source="红笔标记",
                             ocr_reliability=0.95)
        self.assertFalse(decided_clean.in_confirmation_queue)
        pending_clean_read = item(verdict="待确认",
                                  pending_reason="partial_credit",
                                  ocr_reliability=0.95)
        self.assertTrue(pending_clean_read.in_confirmation_queue)


class TestGradedPaper(unittest.TestCase):
    def test_pending_and_decided_partition(self):
        paper = GradedPaper(
            student_id="S-001",
            items=(
                item(item_key="Q1", verdict="对", source="红笔标记"),
                item(item_key="Q2", verdict="待确认",
                     pending_reason="open_type"),
            ),
        )
        self.assertEqual([i.item_key for i in paper.pending()], ["Q2"])
        self.assertEqual([i.item_key for i in paper.decided()], ["Q1"])


if __name__ == "__main__":
    unittest.main()
