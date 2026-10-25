"""Judge unit tests: strict source priority, no guessing (issue #176)."""

import inspect
import unittest

from ..backends import Transcription, UnavailableSelfSolver
from ..judge import (
    compare_with_key,
    comparison_mode,
    judge_item,
    resolve_key_answers,
)

MC = {"id": "Q1", "kind": "multiple_choice", "answer": "C",
      "answer_is_unique": True, "stem": "下列情境中，力对物体做功的是（ ）"}
CALC = {"id": "Q8", "kind": "sub_questions", "answer": "400 J",
        "answer_is_unique": True, "stem": "求重力做的功。"}
ESTIMATION = {"id": "Q4", "kind": "sub_questions",
              "answer": "约 200 W（用题中估算值计算）",
              "answer_is_unique": False, "stem": "估算平均功率。"}
OPEN = {"id": "Q9", "kind": "sub_questions",
        "answer": "重力势能转化为动能；机械能守恒，因为只有重力做功。",
        "answer_is_unique": False, "stem": "写出能量转化并说明理由。"}


def judge(question, key, answer, mark="", solver=None):
    return judge_item(
        question=question,
        key_answer=key,
        transcription=Transcription("X", answer, 0.95, mark_kind=mark),
        solver=solver or UnavailableSelfSolver(),
    )


class CapableSolver:
    """A self-solve backend that can judge (proves source-3 wiring)."""

    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def solve(self, question_text, student_answer):
        self.calls += 1
        return self.verdict


class TestMarkPriority(unittest.TestCase):
    def test_correct_mark_decides(self):
        out = judge(MC, "C", "A", mark="correct")
        self.assertEqual((out.verdict, out.source), ("对", "红笔标记"))

    def test_wrong_mark_decides_and_carries_reference(self):
        out = judge(MC, "C", "C", mark="wrong")
        self.assertEqual((out.verdict, out.source), ("错", "红笔标记"))
        self.assertEqual(out.reference_answer, "C")

    def test_marks_beat_key_comparison(self):
        # The student picked the key's letter, but the teacher's red
        # mark says wrong (e.g. the letter was corrected afterwards).
        # Source 1 wins; sources are never blended.
        out = judge(MC, "C", "C", mark="wrong")
        self.assertEqual(out.verdict, "错")
        self.assertEqual(out.source, "红笔标记")

    def test_score_mark_is_partial_credit_never_binary(self):
        out = judge(CALC, "400 J", "W = Gh = 50 × 8 = 400 J", mark="score")
        self.assertEqual(out.verdict, "待确认")
        self.assertEqual(out.pending_reason, "partial_credit")
        # The key comparison may lean as a labeled proposal only.
        self.assertEqual(out.proposed_verdict, "对")
        self.assertEqual(out.proposal_source, "答案比对")

    def test_score_mark_on_wrong_value_leans_wrong_with_reference(self):
        out = judge(CALC, "400 J", "W = 10 × 8 = 80 J", mark="score")
        self.assertEqual(out.verdict, "待确认")
        self.assertEqual(out.proposed_verdict, "错")
        self.assertEqual(out.reference_answer, "400 J")

    def test_comment_mark_falls_through_to_key(self):
        out = judge(MC, "C", "C", mark="comment")
        self.assertEqual((out.verdict, out.source), ("对", "答案比对"))

    def test_comment_mark_on_open_question_pends_as_open_type(self):
        out = judge(OPEN, OPEN["answer"], "重力势能转化为动能", mark="comment")
        self.assertEqual(out.verdict, "待确认")
        self.assertEqual(out.pending_reason, "open_type")


class TestKeyComparison(unittest.TestCase):
    def test_letter_mode(self):
        self.assertEqual(comparison_mode(MC, "C"), "letter")
        self.assertEqual(compare_with_key("letter", "C", "C"), "对")
        self.assertEqual(compare_with_key("letter", "C", "选 A"), "错")
        self.assertIsNone(compare_with_key("letter", "C", "看不清"))

    def test_numeric_mode_final_value(self):
        self.assertEqual(comparison_mode(CALC, "400 J"), "numeric")
        self.assertEqual(
            compare_with_key("numeric", "400 J", "W = Gh = 50×8 = 400 J"), "对")
        self.assertEqual(
            compare_with_key("numeric", "400 J", "W = 200 J"), "错")
        # No value with the key's unit anywhere: inconclusive, not 错.
        self.assertIsNone(compare_with_key("numeric", "400 J", "算式列对了"))

    def test_numeric_mode_scientific_notation(self):
        self.assertEqual(compare_with_key("numeric", "1.2×10⁷ J",
                                          "W = 1.2×10⁷ J"), "对")
        self.assertEqual(compare_with_key("numeric", "4×10⁴ W",
                                          "P = 40000 W"), "对")

    def test_estimation_key_is_not_comparable(self):
        self.assertIsNone(comparison_mode(ESTIMATION, ESTIMATION["answer"]))

    def test_open_key_is_not_comparable(self):
        self.assertIsNone(comparison_mode(OPEN, OPEN["answer"]))

    def test_phrase_mode_is_one_directional(self):
        q11a = {"id": "Q11", "kind": "sub_questions", "answer_is_unique": True}
        self.assertEqual(comparison_mode(q11a, "不做功"), "phrase")
        self.assertEqual(
            compare_with_key("phrase", "不做功", "不做功，因为没有位移"), "对")
        self.assertIsNone(compare_with_key("phrase", "不做功", "做功"))


class TestNoGuessing(unittest.TestCase):
    def test_unreadable_pends_with_reason(self):
        out = judge_item(
            question=OPEN, key_answer=OPEN["answer"],
            transcription=Transcription("Q9", None, 0.31),
            solver=UnavailableSelfSolver(),
        )
        self.assertEqual(out.verdict, "待确认")
        self.assertEqual(out.pending_reason, "unreadable")
        self.assertEqual(out.proposed_verdict, "")

    def test_open_type_never_consults_solver(self):
        solver = CapableSolver("对")
        out = judge(OPEN, OPEN["answer"], "随便写点什么", solver=solver)
        self.assertEqual(out.verdict, "待确认")
        self.assertEqual(out.pending_reason, "open_type")
        self.assertEqual(solver.calls, 0)

    def test_solver_stub_declines_determinate_questions(self):
        out = judge(MC, "C", "看不清的字母")
        self.assertEqual(out.verdict, "待确认")
        self.assertEqual(out.pending_reason, "judgment_uncertain")

    def test_solver_verdict_is_used_when_it_can_judge(self):
        solver = CapableSolver("错")
        out = judge(MC, "C", "看不清的字母", solver=solver)
        self.assertEqual((out.verdict, out.source), ("错", "模型判定"))
        self.assertEqual(out.reference_answer, "C")
        self.assertEqual(solver.calls, 1)

    def test_judge_cannot_see_reliability(self):
        # The separation is architectural: judge_item has no
        # reliability parameter to leak into a verdict.
        params = inspect.signature(judge_item).parameters
        self.assertNotIn("reliability", params)
        self.assertNotIn("ocr_reliability", params)


class TestKeyResolution(unittest.TestCase):
    def test_blank_segments(self):
        q = {"id": "Q5", "parts": ["blank1", "blank2"],
             "answer": "blank1：重力势；blank2：动"}
        self.assertEqual(
            resolve_key_answers(q),
            {"Q5#blank1": "重力势", "Q5#blank2": "动"},
        )

    def test_numbered_segments(self):
        q = {"id": "Q3", "parts": ["a", "b"], "answer": "（1）0.8 m；（2）16 J"}
        self.assertEqual(
            resolve_key_answers(q), {"Q3#a": "0.8 m", "Q3#b": "16 J"})

    def test_whole_question(self):
        q = {"id": "Q8", "parts": [], "answer": "400 J"}
        self.assertEqual(resolve_key_answers(q), {"Q8": "400 J"})

    def test_unsplittable_key_falls_back_to_full_text(self):
        q = {"id": "QX", "parts": ["a", "b"], "answer": "见解析"}
        self.assertEqual(
            resolve_key_answers(q), {"QX#a": "见解析", "QX#b": "见解析"})


if __name__ == "__main__":
    unittest.main()
