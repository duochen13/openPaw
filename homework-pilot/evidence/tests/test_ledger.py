"""Unit tests for the evidence ledger, on fully synthetic data.

Covers every acceptance criterion of issue #109:
  * wrong-once -> provisional weak-point hypothesis only
  * right-once != long-term mastery
  * same-question correction does not advance mastery
  * teacher correction overrides and is auditable
  * teacher can view the evidence behind any judgment

Run:  python3 -m unittest discover -s . -p "test_*.py"   (from homework-pilot/)
   or  python3 -m unittest evidence.tests.test_ledger     (from repo root)
"""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evidence import (  # noqa: E402
    AuditKind,
    Confidence,
    EvidenceLedger,
    EvidenceRecord,
    GradingResult,
    JsonFileBackend,
    MasteryState,
    SkillAssessment,
)

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
SKILL = "work-power-ch3"  # synthetic skill id (student IDs only, no names)


def rec(
    student="s-001",
    skill=SKILL,
    question="q-01",
    grading=GradingResult.INCORRECT,
    days_ago=0,
    context="ch3-hw-05",
    ocr=1.0,
    hint=False,
    independent=True,
    correction_of="",
    **kw,
):
    return EvidenceRecord(
        student_id=student,
        skill_id=skill,
        question_id=question,
        sub_question=kw.pop("sub_question", ""),
        knowledge_point="判断指定力是否做功",
        student_answer="sample answer",
        grading_result=grading,
        image_location=f"scan-2026-09-{27 - days_ago:02d}/p01.png",
        ocr_reliability=ocr,
        hint_used=hint,
        correction_of=correction_of,
        independently_completed=independent,
        context=context,
        observed_at=NOW - timedelta(days=days_ago),
        created_at=NOW - timedelta(days=days_ago),
        **kw,
    )


def fresh_ledger(**kw):
    tmp = tempfile.mkdtemp()
    return EvidenceLedger(JsonFileBackend(Path(tmp) / "ledger.json"), **kw)


class TestWrongOnceProvisionalHypothesis(unittest.TestCase):
    def test_wrong_once_gives_needs_practice_with_provisional_flag(self):
        ledger = fresh_ledger()
        a = ledger.record_evidence(rec(grading=GradingResult.INCORRECT), at=NOW)
        self.assertEqual(a.state, MasteryState.NEEDS_PRACTICE)
        # provisional weak-point hypothesis -- never a confirmed verdict
        self.assertTrue(a.provisional_hypothesis)
        self.assertNotEqual(a.state, MasteryState.FAIRLY_WELL_MASTERED)

    def test_wrong_once_not_confirmed_mastery_nor_failure(self):
        ledger = fresh_ledger()
        a = ledger.record_evidence(rec(grading=GradingResult.PARTIAL), at=NOW)
        self.assertEqual(a.state, MasteryState.NEEDS_PRACTICE)
        self.assertTrue(a.provisional_hypothesis)
        # confidence is qualitative, never a percentage
        self.assertIsInstance(a.confidence, Confidence)


class TestRightOnceNotMastery(unittest.TestCase):
    def test_single_right_answer_stays_insufficient_evidence(self):
        ledger = fresh_ledger()
        a = ledger.record_evidence(rec(grading=GradingResult.CORRECT), at=NOW)
        # one right answer != long-term mastery
        self.assertEqual(a.state, MasteryState.INSUFFICIENT_EVIDENCE)
        self.assertNotEqual(a.state, MasteryState.FAIRLY_WELL_MASTERED)

    def test_two_independent_corrects_still_not_mastered(self):
        ledger = fresh_ledger()
        ledger.record_evidence(
            rec(question="q-01", grading=GradingResult.CORRECT, days_ago=6,
                context="ch3-hw-05"), at=NOW,
        )
        a = ledger.record_evidence(
            rec(question="q-02", grading=GradingResult.CORRECT, days_ago=0,
                context="ch3-quiz-1"), at=NOW,
        )
        self.assertNotEqual(a.state, MasteryState.FAIRLY_WELL_MASTERED)


class TestSameQuestionCorrectionDoesNotAdvance(unittest.TestCase):
    def test_correction_of_same_question_records_but_does_not_advance(self):
        ledger = fresh_ledger()
        wrong = rec(question="q-11", grading=GradingResult.INCORRECT, days_ago=5)
        ledger.record_evidence(wrong, at=NOW)
        # student corrects the SAME question (订正)
        fixed = rec(
            question="q-11",
            grading=GradingResult.CORRECT,
            days_ago=1,
            correction_of=wrong.record_id,
        )
        a = ledger.record_evidence(fixed, at=NOW)
        self.assertEqual(a.state, MasteryState.NEEDS_PRACTICE)
        # the correction IS in the history (recorded, not lost)
        self.assertEqual(len(ledger.records_for("s-001", SKILL)), 2)

    def test_repeat_correct_without_correction_flag_also_does_not_advance(self):
        ledger = fresh_ledger()
        ledger.record_evidence(
            rec(question="q-11", grading=GradingResult.INCORRECT, days_ago=5), at=NOW
        )
        # same question answered again correctly, even without an explicit
        # correction link, must not count as independent mastery evidence
        a = ledger.record_evidence(
            rec(question="q-11", grading=GradingResult.CORRECT, days_ago=1), at=NOW
        )
        self.assertEqual(a.state, MasteryState.NEEDS_PRACTICE)

    def test_different_question_in_different_context_does_advance(self):
        ledger = fresh_ledger()
        ledger.record_evidence(
            rec(question="q-11", grading=GradingResult.INCORRECT, days_ago=5), at=NOW
        )
        ledger.record_evidence(
            rec(question="q-11", grading=GradingResult.CORRECT, days_ago=3,
                correction_of="earlier"), at=NOW,
        )
        # a NEW question, recent, independently completed, different context
        a = ledger.record_evidence(
            rec(question="q-12", grading=GradingResult.CORRECT, days_ago=0,
                context="ch3-quiz-1"), at=NOW,
        )
        self.assertEqual(a.state, MasteryState.IMPROVING)

    def test_hint_assisted_correct_does_not_count_as_independent(self):
        ledger = fresh_ledger()
        ledger.record_evidence(
            rec(question="q-11", grading=GradingResult.INCORRECT, days_ago=5), at=NOW
        )
        a = ledger.record_evidence(
            rec(question="q-12", grading=GradingResult.CORRECT, days_ago=0,
                hint=True, context="ch3-quiz-1"), at=NOW,
        )
        self.assertEqual(a.state, MasteryState.NEEDS_PRACTICE)


class TestMasteryRequiresIndependentEvidence(unittest.TestCase):
    def test_mastered_needs_several_questions_and_contexts(self):
        ledger = fresh_ledger()
        for i, ctx in enumerate(["ch3-hw-05", "ch3-quiz-1", "ch3-hw-06"]):
            a = ledger.record_evidence(
                rec(question=f"q-2{i}", grading=GradingResult.CORRECT,
                    days_ago=6 - 2 * i, context=ctx),
                at=NOW,
            )
        self.assertEqual(a.state, MasteryState.FAIRLY_WELL_MASTERED)
        self.assertFalse(a.provisional_hypothesis)

    def test_recent_wrong_after_mastery_drops_state(self):
        ledger = fresh_ledger()
        for i, ctx in enumerate(["ch3-hw-05", "ch3-quiz-1", "ch3-hw-06"]):
            ledger.record_evidence(
                rec(question=f"q-2{i}", grading=GradingResult.CORRECT,
                    days_ago=6 - 2 * i, context=ctx),
                at=NOW,
            )
        a = ledger.record_evidence(
            rec(question="q-30", grading=GradingResult.INCORRECT, days_ago=0,
                context="ch3-quiz-2"),
            at=NOW,
        )
        self.assertNotEqual(a.state, MasteryState.FAIRLY_WELL_MASTERED)
        self.assertTrue(a.provisional_hypothesis)


class TestTeacherCorrection(unittest.TestCase):
    def test_teacher_override_sets_state_and_is_audited(self):
        ledger = fresh_ledger()
        ledger.record_evidence(rec(grading=GradingResult.INCORRECT), at=NOW)
        a = ledger.apply_teacher_correction(
            "s-001", SKILL, MasteryState.IMPROVING,
            note="课堂观察：学生已能口头解释做功条件", at=NOW,
        )
        self.assertEqual(a.state, MasteryState.IMPROVING)
        self.assertFalse(a.provisional_hypothesis)  # teacher cleared the hypothesis
        entries = [
            e for e in ledger._audit if e.kind is AuditKind.TEACHER_OVERRIDE
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].from_state, MasteryState.NEEDS_PRACTICE)
        self.assertEqual(entries[0].to_state, MasteryState.IMPROVING)
        self.assertIn("做功条件", entries[0].note)

    def test_teacher_note_without_state_change_is_audited(self):
        ledger = fresh_ledger()
        ledger.add_teacher_note("s-001", SKILL, "家长反馈学生在家练习较多", at=NOW)
        kinds = [e.kind for e in ledger._audit]
        self.assertIn(AuditKind.TEACHER_NOTE, kinds)


class TestTeacherCanViewEvidence(unittest.TestCase):
    def test_evidence_for_returns_dated_history_and_audit(self):
        ledger = fresh_ledger()
        ledger.record_evidence(
            rec(question="q-11", grading=GradingResult.INCORRECT, days_ago=5), at=NOW
        )
        ledger.record_evidence(
            rec(question="q-12", grading=GradingResult.CORRECT, days_ago=0,
                context="ch3-quiz-1"), at=NOW,
        )
        ledger.apply_teacher_correction(
            "s-001", SKILL, MasteryState.IMPROVING, note="已确认", at=NOW
        )
        view = ledger.evidence_for("s-001", SKILL)
        self.assertEqual(view["assessment"]["state"], MasteryState.IMPROVING.value)
        # dated history, chronological
        dates = [r["observed_at"] for r in view["records"]]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(view["records"]), 2)
        # audit trail includes the teacher correction
        kinds = [e["kind"] for e in view["audit"]]
        self.assertIn(AuditKind.TEACHER_OVERRIDE.value, kinds)
        self.assertIn("当前判断", view["summary"])


class TestOcrReliabilitySeparateFromMastery(unittest.TestCase):
    def test_unreadable_record_does_not_change_state(self):
        ledger = fresh_ledger()
        a = ledger.record_evidence(
            rec(grading=GradingResult.UNREADABLE, ocr=0.2), at=NOW
        )
        self.assertEqual(a.state, MasteryState.INSUFFICIENT_EVIDENCE)
        # both uncertainties live on the record, as separate fields
        stored = ledger.records_for("s-001", SKILL)[0]
        self.assertEqual(stored.ocr_reliability, 0.2)
        self.assertEqual(stored.grading_result, GradingResult.UNREADABLE)

    def test_ocr_reliability_validated(self):
        with self.assertRaises(ValueError):
            rec(ocr=1.5)


class TestStaleEvidenceSchedulesReview(unittest.TestCase):
    def test_long_gap_flags_due_for_review_not_forgetting(self):
        ledger = fresh_ledger(stale_days=45)
        for i, ctx in enumerate(["ch3-hw-05", "ch3-quiz-1", "ch3-hw-06"]):
            ledger.record_evidence(
                rec(question=f"q-4{i}", grading=GradingResult.CORRECT,
                    days_ago=60 - 2 * i, context=ctx),
                at=NOW - timedelta(days=55),
            )
        flagged = ledger.flag_stale_assessments(as_of=NOW)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0].state, MasteryState.DUE_FOR_REVIEW)
        # pre-flag state remembered; audit says "review check", not "forgot"
        self.assertEqual(
            flagged[0].state_before_review, MasteryState.FAIRLY_WELL_MASTERED
        )
        stale_entries = [
            e for e in ledger._audit if e.kind is AuditKind.STALE_FLAG
        ]
        self.assertTrue(any("不代表已遗忘" in e.note for e in stale_entries))

    def test_insufficient_evidence_is_never_flagged_stale(self):
        ledger = fresh_ledger(stale_days=45)
        ledger.record_evidence(rec(grading=GradingResult.CORRECT, days_ago=60), at=NOW)
        flagged = ledger.flag_stale_assessments(as_of=NOW)
        self.assertEqual(flagged, [])


class TestNoNamesEnforced(unittest.TestCase):
    def test_name_keys_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceRecord.from_dict(
                {"student_id": "s-001", "skill_id": SKILL, "student_name": "张三"}
            )
        with self.assertRaises(ValueError):
            EvidenceRecord.from_dict(
                {"student_id": "s-001", "skill_id": SKILL, "姓名": "张三"}
            )

    def test_model_has_no_name_field(self):
        r = rec()
        self.assertFalse(hasattr(r, "student_name"))
        self.assertFalse("name" in r.to_dict())


class TestPersistence(unittest.TestCase):
    def test_round_trip_preserves_everything(self):
        tmp = tempfile.mkdtemp()
        path = Path(tmp) / "ledger.json"
        ledger = EvidenceLedger(JsonFileBackend(path))
        ledger.record_evidence(
            rec(question="q-11", grading=GradingResult.INCORRECT, days_ago=5), at=NOW
        )
        ledger.apply_teacher_correction(
            "s-001", SKILL, MasteryState.NEEDS_PRACTICE,
            note="hypothesis stands", clear_hypothesis=False, at=NOW,
        )
        reloaded = EvidenceLedger(JsonFileBackend(path))
        a = reloaded.assessment_for("s-001", SKILL)
        self.assertEqual(a.state, MasteryState.NEEDS_PRACTICE)
        self.assertTrue(a.provisional_hypothesis)
        self.assertEqual(len(reloaded.records_for("s-001", SKILL)), 1)
        self.assertEqual(len(reloaded._audit), 2)  # state change + override

    def test_schema_version_written(self):
        import json

        tmp = tempfile.mkdtemp()
        path = Path(tmp) / "ledger.json"
        EvidenceLedger(JsonFileBackend(path)).save()
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["schema_version"], 1)

    def test_future_schema_version_rejected(self):
        import json

        tmp = tempfile.mkdtemp()
        path = Path(tmp) / "ledger.json"
        path.write_text(
            json.dumps({"schema_version": 999, "records": [],
                        "assessments": {}, "audit": []}),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            EvidenceLedger(JsonFileBackend(path))


if __name__ == "__main__":
    unittest.main()
