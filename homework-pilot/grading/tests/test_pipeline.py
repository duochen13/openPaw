"""End-to-end tests on the pilot kit's synthetic papers (issue #176).

Ground truth comes from the kit itself, through two independent
artifacts: the grading marks in each paper's answer-records.json
(decisive mark = teacher's verdict; partial/comment/no mark = never a
binary truth) and the per-item points in papers/manifest.json
(full points <=> 对, zero <=> 错 or unreadable, partial <=> 待确认).
The judge shares no code with either derivation.

Mode A runs the pipeline as designed (red-pen marks present).
Mode B withholds the marks and exercises the answer-key source alone.
"""

import unittest
from pathlib import Path

from ..backends import (
    expected_verdicts,
    load_kit_manifest,
    load_kit_questions,
    load_kit_records,
)
from ..judge import comparison_mode, resolve_key_answers
from ..pipeline import grade_kit_paper

KIT = Path(__file__).resolve().parents[2] / "pilot-kit"
STUDENTS = ["S-001", "S-002", "S-003", "S-004", "S-005"]


def full_points() -> dict[str, int]:
    full: dict[str, int] = {}
    for question in load_kit_questions(KIT):
        for part_id, points in (question.get("points") or {}).items():
            key = f"{question['id']}#{part_id}" if part_id else question["id"]
            full[key] = points
    return full


def earned_points() -> dict[str, dict[str, int]]:
    return {
        entry["student_id"]: entry["points_earned"]
        for entry in load_kit_manifest(KIT)
    }


class TestModeAWithMarks(unittest.TestCase):
    """Every kit paper, marks present: verdicts match the kit's truth."""

    @classmethod
    def setUpClass(cls):
        cls.papers = {sid: grade_kit_paper(KIT, sid) for sid in STUDENTS}
        cls.full = full_points()
        cls.earned = earned_points()

    def test_all_items_match_ground_truth(self):
        for sid, paper in self.papers.items():
            expected = expected_verdicts(load_kit_records(KIT, sid))
            self.assertEqual(len(paper.items), 18, sid)
            for item in paper.items:
                self.assertEqual(
                    item.verdict, expected[item.item_key],
                    f"{sid} {item.item_key}",
                )

    def test_ground_truth_cross_checked_against_manifest_points(self):
        # The marks-derived truth must agree with the manifest's
        # independent points accounting -- this validates the truth,
        # not the pipeline.
        for sid in STUDENTS:
            expected = expected_verdicts(load_kit_records(KIT, sid))
            for item_key, verdict in expected.items():
                earned = self.earned[sid][item_key]
                full = self.full[item_key]
                if verdict == "对":
                    self.assertEqual(earned, full, f"{sid} {item_key}")
                elif verdict == "错":
                    self.assertEqual(earned, 0, f"{sid} {item_key}")
                else:  # 待确认: partial credit, or unreadable (0)
                    self.assertTrue(
                        0 < earned < full or earned == 0,
                        f"{sid} {item_key}: earned {earned} of {full}",
                    )

    def test_totals_are_the_kit_census(self):
        decided = sum(len(p.decided()) for p in self.papers.values())
        pending = sum(len(p.pending()) for p in self.papers.values())
        self.assertEqual(decided, 67)   # 51 correct + 16 wrong marks
        self.assertEqual(pending, 23)   # 19 score + 2 comment + 2 unreadable

    def test_decisive_items_are_mark_sourced(self):
        for paper in self.papers.values():
            for item in paper.decided():
                self.assertEqual(item.source, "红笔标记")
                if item.verdict == "错":
                    self.assertTrue(item.reference_answer)

    def test_unreadable_items_pend_unreadable_with_no_lean(self):
        paper = self.papers["S-005"]
        for item_key in ("Q9", "Q12#blank3"):
            item = next(i for i in paper.items if i.item_key == item_key)
            self.assertEqual(item.verdict, "待确认")
            self.assertEqual(item.pending_reason, "unreadable")
            self.assertEqual(item.student_answer, "")
            self.assertEqual(item.proposed_verdict, "")

    def test_knowledge_point_tag_and_skills_present(self):
        for paper in self.papers.values():
            for item in paper.items:
                self.assertTrue(item.knowledge_point_tag, item.item_key)
        q11b = next(
            i for i in self.papers["S-001"].items if i.item_key == "Q11#b"
        )
        self.assertEqual(q11b.skill_ids, ("ch3-apex-kinetic-energy",))


class TestReliabilitySeparation(unittest.TestCase):
    """Reliability routes the read, never the verdict (pinned)."""

    @classmethod
    def setUpClass(cls):
        cls.papers = {sid: grade_kit_paper(KIT, sid) for sid in STUDENTS}

    def test_low_reliability_item_keeps_its_mark_verdict(self):
        item = next(
            i for i in self.papers["S-005"].items if i.item_key == "Q3#a"
        )
        self.assertEqual(item.ocr_reliability, 0.72)
        self.assertEqual(item.verdict, "对")            # from the red mark
        self.assertEqual(item.source, "红笔标记")
        self.assertTrue(item.needs_transcription_confirmation)
        self.assertTrue(item.in_confirmation_queue)     # queued for its READ

    def test_high_reliability_item_can_still_be_pending(self):
        found = [
            item
            for paper in self.papers.values()
            for item in paper.items
            if item.ocr_reliability >= 0.8 and item.verdict == "待确认"
        ]
        self.assertTrue(found, "expected high-reliability pending items")
        for item in found:
            self.assertFalse(item.needs_transcription_confirmation)

    def test_reliable_decided_items_are_not_queued(self):
        for paper in self.papers.values():
            for item in paper.items:
                if item.ocr_reliability >= 0.8 and item.verdict in ("对", "错"):
                    self.assertFalse(item.in_confirmation_queue)


class TestModeBKeyOnly(unittest.TestCase):
    """Marks withheld: the answer key alone must judge what it can
    and pend everything else -- zero guessed verdicts."""

    @classmethod
    def setUpClass(cls):
        cls.papers = {
            sid: grade_kit_paper(KIT, sid, include_marks=False)
            for sid in STUDENTS
        }
        cls.full = full_points()
        cls.earned = earned_points()
        cls.modes = {}
        for question in load_kit_questions(KIT):
            for item_key, key in resolve_key_answers(question).items():
                cls.modes[item_key] = comparison_mode(question, key)

    def test_comparable_items_match_manifest_points(self):
        asserted = 0
        records = {sid: {r["item_key"]: r for r in load_kit_records(KIT, sid)}
                   for sid in STUDENTS}
        for sid, paper in self.papers.items():
            for item in paper.items:
                mode = self.modes[item.item_key]
                if mode not in ("letter", "text", "numeric"):
                    continue
                if mode == "numeric" and not any(
                    ch.isdigit()
                    for ch in records[sid][item.item_key]["student_answer"] or ""
                ):
                    # A verbal answer with no numeric value at all
                    # (e.g. "动能最小，但不是零") gives the numeric
                    # comparator nothing to compare: it must pend,
                    # never guess 错 from the absence of a number.
                    self.assertEqual(
                        item.verdict, "待确认", f"{sid} {item.item_key}")
                    continue
                earned, full = self.earned[sid][item.item_key], self.full[item.item_key]
                if earned == full:
                    self.assertEqual(item.verdict, "对", f"{sid} {item.item_key}")
                    self.assertEqual(item.source, "答案比对")
                    asserted += 1
                elif earned == 0:
                    self.assertEqual(item.verdict, "错", f"{sid} {item.item_key}")
                    self.assertEqual(item.source, "答案比对")
                    self.assertTrue(item.reference_answer)
                    asserted += 1
                # partial points: the teacher's partial credit is not a
                # binary truth, so nothing is asserted for those items.
        self.assertGreaterEqual(asserted, 40)

    def test_incomparable_items_are_never_decided(self):
        for sid, paper in self.papers.items():
            for item in paper.items:
                if self.modes[item.item_key] is None:
                    self.assertEqual(
                        item.verdict, "待确认",
                        f"{sid} {item.item_key} must not be guessed",
                    )

    def test_phrase_items_decide_only_when_the_judgment_earned_credit(self):
        # Phrase containment verifies the core judgment word （不做功）,
        # not the explanation around it: the teacher may still award
        # partial points for an incomplete 理由. A phrase-based 对 must
        # therefore coincide with *some* earned credit, and a phrase
        # item can never come out 错 (the mode is one-directional).
        for sid, paper in self.papers.items():
            for item in paper.items:
                if self.modes[item.item_key] == "phrase":
                    self.assertNotEqual(item.verdict, "错")
                    if item.verdict == "对":
                        self.assertGreater(
                            self.earned[sid][item.item_key], 0,
                            f"{sid} {item.item_key}",
                        )


if __name__ == "__main__":
    unittest.main()
