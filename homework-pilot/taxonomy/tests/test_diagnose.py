"""Unit tests for the homework-pilot skill taxonomy and weak-point diagnosis.

All data is synthetic. Run from the homework-pilot directory::

    python3 -m unittest taxonomy.tests.test_diagnose
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from .. import diagnose as dx
from ..models import (
    RESULT_CORRECT,
    RESULT_INCORRECT,
    RESULT_PARTIAL,
    RESULT_UNREADABLE,
    EvidenceInput,
    ProposalStatus,
)
from ..tagging import (
    SAMPLE_ASSIGNMENT_TAGS,
    skill_ids_for,
    tags_for,
    validate_tags,
)
from ..taxonomy import (
    Taxonomy,
    TaxonomyValidationError,
    load_taxonomy,
)

TAUGHT = {
    "ch3-judge-work",
    "ch3-friction-work",
    "ch3-estimate-average-power",
    "ch3-work-vs-power",
    "ch3-gravitational-work",
    "ch3-work-phases",
    "ch3-apex-kinetic-energy",
    "ch3-repeated-jump-power",
    "ch3-elastic-potential-energy",
    "ch3-force-velocity-changes",
}


def rec(student="s-001", skill="ch3-judge-work", result=RESULT_INCORRECT,
        q="Q2", sub="", reliability=1.0, **kw):
    return EvidenceInput(
        student_id=student, skill_id=skill, grading_result=result,
        question_id=q, sub_question=sub, ocr_reliability=reliability,
        observed_at=datetime(2026, 9, 27, tzinfo=timezone.utc), **kw)


class TaxonomyLoadingTest(unittest.TestCase):
    def test_v1_loads_and_is_pending_teacher_confirmation(self):
        tax = load_taxonomy()
        self.assertEqual(tax.version, "v1")
        self.assertEqual(tax.status, "pending_teacher_confirmation")
        self.assertFalse(tax.teacher_confirmed())
        self.assertEqual(len(tax.skills), 10)

    def test_v1_covers_design_doc_table(self):
        tax = load_taxonomy()
        names = {s.name_zh for s in tax.skills}
        for expected in (
            "根据力与沿力方向的位移判断指定力做功",
            "判断推下木板所需的位移并结合摩擦力计算功",
            "估算物理量并计算平均功率",
            "比较功与功率，排除无关条件",
            "计算重力做功",
            "判断做功阶段",
            "最高点动能",
            "重复跳跃功率",
            "弹性势能",
            "受力与速度变化",
        ):
            self.assertIn(expected, names)

    def test_sample_fixture_tags_reference_known_skills(self):
        tax = load_taxonomy()
        problems = validate_tags(SAMPLE_ASSIGNMENT_TAGS, tax)
        self.assertEqual(problems, [])

    def test_validation_rejects_duplicate_ids(self):
        tax = load_taxonomy()
        data = {"version": "v1", "chapter": "c", "source": "s",
                "status": "pending_teacher_confirmation",
                "skills": [tax.skills[0].to_dict(), tax.skills[0].to_dict()]}
        with self.assertRaises(TaxonomyValidationError):
            from ..taxonomy import validate_taxonomy_dict
            problems = validate_taxonomy_dict(data)
            self.assertTrue(any("duplicate" in p for p in problems))
            raise TaxonomyValidationError(problems)

    def test_validation_rejects_missing_fields(self):
        from ..taxonomy import validate_taxonomy_dict
        problems = validate_taxonomy_dict(
            {"version": "v1", "skills": [{"id": "x"}]})
        self.assertTrue(any("name_zh" in p for p in problems))
        self.assertTrue(any("chapter" in p for p in problems))


class TaggingTest(unittest.TestCase):
    def test_q2_single_tag(self):
        self.assertEqual(skill_ids_for("Q2"), ("ch3-judge-work",))

    def test_q11_subparts_tagged_separately(self):
        self.assertEqual(skill_ids_for("Q11", "(1)"), ("ch3-work-phases",))
        self.assertEqual(skill_ids_for("Q11", "(2)"), ("ch3-apex-kinetic-energy",))
        self.assertEqual(skill_ids_for("Q11", "(3)"), ("ch3-repeated-jump-power",))

    def test_q12_blanks_tagged_separately(self):
        self.assertEqual(skill_ids_for("Q12", "(1)"), ("ch3-gravitational-work",))
        self.assertEqual(skill_ids_for("Q12", "(2)"), ("ch3-elastic-potential-energy",))
        self.assertEqual(skill_ids_for("Q12", "(3)"), ("ch3-force-velocity-changes",))

    def test_multi_skill_composite_tagging(self):
        # Q3 and whole-question Q11/Q12 span multiple skills.
        q3 = skill_ids_for("Q3")
        self.assertGreaterEqual(len(q3), 2)
        self.assertIn("ch3-friction-work", q3)

        q11 = skill_ids_for("Q11")
        self.assertEqual(set(q11), {"ch3-work-phases", "ch3-apex-kinetic-energy",
                                    "ch3-repeated-jump-power"})
        q11_tags = tags_for("Q11")
        self.assertTrue(any(t.composite for t in q11_tags))

        q12 = skill_ids_for("Q12")
        self.assertEqual(set(q12), {"ch3-gravitational-work",
                                    "ch3-elastic-potential-energy",
                                    "ch3-force-velocity-changes"})

    def test_unmapped_questions_stay_untagged(self):
        self.assertEqual(skill_ids_for("Q9"), ())
        self.assertEqual(skill_ids_for("Q10"), ())


class DiagnoseTest(unittest.TestCase):
    def test_single_error_is_hypothesis_not_verdict(self):
        result = dx.propose_weak_points(
            [rec(result=RESULT_INCORRECT)], TAUGHT)
        self.assertEqual(len(result.proposals), 1)
        p = result.proposals[0]
        self.assertEqual(p.status, ProposalStatus.PROPOSED)
        self.assertTrue(p.is_provisional)  # hypothesis, NOT a verdict
        self.assertEqual(p.hypothesis_strength, "single_error")

    def test_repeated_errors_still_provisional(self):
        result = dx.propose_weak_points(
            [rec(result=RESULT_INCORRECT, q="Q2"),
             rec(result=RESULT_INCORRECT, q="Q2", sub="(b)")], TAUGHT)
        p = result.proposals[0]
        self.assertEqual(p.status, ProposalStatus.PROPOSED)
        self.assertTrue(p.is_provisional)  # even repeated errors never auto-verdict
        self.assertEqual(p.hypothesis_strength, "repeated_errors")

    def test_all_correct_no_proposal(self):
        result = dx.propose_weak_points(
            [rec(result=RESULT_CORRECT), rec(result=RESULT_CORRECT, q="Q8")],
            TAUGHT)
        self.assertEqual(result.proposals, [])

    def test_no_evidence_never_labeled_weak(self):
        result = dx.propose_weak_points([], TAUGHT, student_ids=["s-001"])
        self.assertEqual(result.proposals, [])
        self.assertIn(("s-001", "ch3-judge-work"), result.no_evidence)
        # Every taught skill with no evidence is listed, none proposed.
        self.assertEqual(len(result.no_evidence), len(TAUGHT))

    def test_unreadable_only_is_no_evidence(self):
        result = dx.propose_weak_points(
            [rec(result=RESULT_UNREADABLE)], TAUGHT)
        self.assertEqual(result.proposals, [])
        self.assertEqual(result.no_evidence, [("s-001", "ch3-judge-work")])

    def test_low_ocr_reliability_carries_no_signal(self):
        result = dx.propose_weak_points(
            [rec(result=RESULT_INCORRECT, reliability=0.2)], TAUGHT)
        self.assertEqual(result.proposals, [])
        self.assertEqual(result.no_evidence, [("s-001", "ch3-judge-work")])

    def test_untaught_skill_never_proposed(self):
        taught = set(TAUGHT) - {"ch3-judge-work"}
        result = dx.propose_weak_points(
            [rec(result=RESULT_INCORRECT),
             rec(result=RESULT_INCORRECT, q="Q2")], taught)
        self.assertEqual(result.proposals, [])
        self.assertIn("ch3-judge-work", result.excluded_untaught)

    def test_partial_credit_is_weaker_hypothesis(self):
        result = dx.propose_weak_points(
            [rec(result=RESULT_PARTIAL)], TAUGHT)
        self.assertEqual(len(result.proposals), 1)
        p = result.proposals[0]
        self.assertEqual(p.hypothesis_strength, "partial_credit")
        self.assertTrue(p.is_provisional)

    def test_corrected_error_noted_but_stays_provisional(self):
        err = rec(result=RESULT_INCORRECT)
        fix = rec(result=RESULT_CORRECT, correction_of=err.record_id)
        result = dx.propose_weak_points([err, fix], TAUGHT)
        self.assertEqual(len(result.proposals), 1)
        p = result.proposals[0]
        self.assertTrue(p.is_provisional)  # still needs the teacher
        self.assertIn("订正", p.basis_note)

    def test_deterministic_order(self):
        result = dx.propose_weak_points(
            [rec(student="s-002", skill="ch3-work-vs-power", result=RESULT_INCORRECT, q="Q7"),
             rec(student="s-001", skill="ch3-judge-work", result=RESULT_INCORRECT)], TAUGHT)
        self.assertEqual(
            [(p.student_id, p.skill_id) for p in result.proposals],
            [("s-001", "ch3-judge-work"), ("s-002", "ch3-work-vs-power")])


class TeacherWorkflowTest(unittest.TestCase):
    def _proposal(self):
        result = dx.propose_weak_points([rec(result=RESULT_INCORRECT)], TAUGHT)
        return result.proposals[0]

    def test_teacher_confirm_recorded_and_auditable(self):
        p = self._proposal()
        p.confirm("课堂观察确认：该生确实分不清做功条件")
        self.assertEqual(p.status, ProposalStatus.CONFIRMED)
        self.assertFalse(p.is_provisional)
        self.assertEqual(len(p.audit), 2)  # auto_proposed + teacher_confirm
        last = p.audit[-1]
        self.assertEqual(last.kind, "teacher_confirm")
        self.assertEqual(last.from_status, ProposalStatus.PROPOSED)
        self.assertEqual(last.to_status, ProposalStatus.CONFIRMED)
        self.assertIn("课堂观察", last.note)

    def test_teacher_modify_with_skill_redirect(self):
        p = self._proposal()
        p.modify("实际是摩擦力计算的问题，不是做功判断",
                 new_skill_id="ch3-friction-work")
        self.assertEqual(p.status, ProposalStatus.MODIFIED)
        self.assertEqual(p.modified_skill_id, "ch3-friction-work")
        self.assertFalse(p.is_provisional)
        self.assertEqual(p.audit[-1].kind, "teacher_modify")

    def test_teacher_reject_recorded(self):
        p = self._proposal()
        p.reject("笔误，学生实际掌握")
        self.assertEqual(p.status, ProposalStatus.REJECTED)
        self.assertFalse(p.is_provisional)
        kinds = [a.kind for a in p.audit]
        self.assertEqual(kinds, ["auto_proposed", "teacher_reject"])

    def test_teacher_can_change_mind_and_stays_audited(self):
        p = self._proposal()
        p.confirm("先确认")
        p.reject("复查后推翻")
        self.assertEqual(p.status, ProposalStatus.REJECTED)
        self.assertEqual(len(p.audit), 3)


class EvidenceInputAdapterTest(unittest.TestCase):
    def test_from_dict_accepts_issue109_shape(self):
        # Mirrors the serialized evidence.EvidenceRecord (#109) fields.
        d = {
            "student_id": "s-007",
            "skill_id": "ch3-work-vs-power",
            "question_id": "Q7",
            "sub_question": "",
            "knowledge_point": "比较功与功率",
            "student_answer": "功率大所以做功多",
            "grading_result": "错误",
            "image_location": "scan-2026-09-27/p03.png",
            "ocr_reliability": 0.9,
            "hint_used": False,
            "correction_of": "",
            "teacher_note": "",
            "followup_verified": False,
            "independently_completed": True,
            "context": "ch3-hw-05",
            "observed_at": "2026-09-27T10:00:00+00:00",
            "created_at": "2026-09-27T10:05:00+00:00",
            "record_id": "abc123",
        }
        rec_in = EvidenceInput.from_dict(d)  # must not raise; extra keys ignored
        self.assertEqual(rec_in.student_id, "s-007")
        self.assertEqual(rec_in.grading_result, RESULT_INCORRECT)
        self.assertEqual(rec_in.record_id, "abc123")
        result = dx.propose_weak_points([rec_in], TAUGHT)
        self.assertEqual(len(result.proposals), 1)
        self.assertEqual(result.proposals[0].skill_id, "ch3-work-vs-power")

    def test_student_id_required(self):
        with self.assertRaises(ValueError):
            EvidenceInput(student_id="", skill_id="ch3-judge-work")


if __name__ == "__main__":
    unittest.main()
