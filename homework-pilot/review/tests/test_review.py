"""Tests for the teacher review workflow (issue #115).

All question content is synthetic (``SYN-`` prefix) -- real teacher
materials are pending #108 field work.
"""

from copy import deepcopy

import pytest

from ..models import FigureStatus, HomeworkPlan, Question
from ..review import ApprovalError, ReviewSession, ReviewStatus


def _q(qid: str, stem: str | None = None, **kw) -> Question:
    return Question(
        id=qid,
        skill_ids=["ch3-gravitational-work"],
        stem=stem or f"Synthetic stem of {qid}.",
        answer="100 J",
        solution_steps=["G = m*g = 20 N", "W = G*h = 100 J"],
        scoring_notes="Half credit for the correct formula; full credit "
                      "for value and unit.",
        **kw,
    )


def _plans() -> list[HomeworkPlan]:
    q1 = _q("SYN-Q1", category="共同题")
    q2 = _q("SYN-Q2", figure=FigureStatus.PLACEHOLDER,
            figure_description="free-body diagram of the falling object")
    q3 = _q("SYN-Q3")
    return [
        HomeworkPlan(student_id="S001", assignment_number="A-CH3-01",
                     questions=[deepcopy(q1), deepcopy(q2)]),
        HomeworkPlan(student_id="S002", assignment_number="A-CH3-01",
                     questions=[deepcopy(q1), deepcopy(q2)]),
        HomeworkPlan(student_id="S003", assignment_number="A-CH3-01",
                     questions=[deepcopy(q2), deepcopy(q3)]),
    ]


def _session() -> ReviewSession:
    return ReviewSession(_plans(), assignment_number="A-CH3-01")


# -- approval gate ----------------------------------------------------------

def test_gate_blocks_unapproved_publish():
    s = _session()
    assert not s.is_approved("S001")
    with pytest.raises(ApprovalError) as exc:
        s.publish("S001")
    assert "SYN-Q1" in str(exc.value)  # names the blocking question


def test_approve_all_then_publish_class():
    s = _session()
    s.approve_all()
    assert s.pending_questions() == []
    plans = s.publish_class()
    assert {p.student_id for p in plans} == {"S001", "S002", "S003"}
    assert all(p.assignment_number == "A-CH3-01" for p in plans)


def test_reject_blocks_until_replaced_or_adjusted():
    s = _session()
    s.reject("SYN-Q1", "stem uses the wrong value of g")
    assert s.question_status("SYN-Q1") is ReviewStatus.REJECTED
    with pytest.raises(ApprovalError):
        s.publish("S001")
    # S003 was never assigned SYN-Q1: still blocked on its own questions
    s.approve("SYN-Q2")
    s.approve("SYN-Q3")
    assert s.is_approved("S003")
    assert not s.is_approved("S001")
    # adjusting clears the rejection and propagates the fix
    s.adjust("SYN-Q1", {"stem": "Fixed synthetic stem with g = 10 N/kg."})
    assert s.question_status("SYN-Q1") is ReviewStatus.ADJUSTED
    assert s.is_approved("S001")
    s.publish("S001")


def test_publish_class_reports_all_blocked_plans():
    s = _session()
    s.approve("SYN-Q2")
    with pytest.raises(ApprovalError) as exc:
        s.publish_class()
    msg = str(exc.value)
    assert "S001" in msg and "SYN-Q1" in msg


def test_pending_questions_lists_blockers():
    s = _session()
    s.approve("SYN-Q1")
    pending = s.pending_questions()
    assert "SYN-Q2" in pending and "SYN-Q3" in pending
    assert "SYN-Q1" not in pending


# -- shared-question propagation --------------------------------------------

def test_shared_replace_propagates_to_all_students():
    s = _session()
    new = _q("SYN-Q1B", "Teacher-written replacement stem.")
    s.replace("SYN-Q1", new, note="original stem ambiguous")
    for sid in ("S001", "S002"):
        plan = s.plan_for(sid)
        assert plan.question_ids() == ["SYN-Q1B", "SYN-Q2"]
    # S003 never had SYN-Q1: untouched
    assert s.plan_for("S003").question_ids() == ["SYN-Q2", "SYN-Q3"]
    assert s.question_status("SYN-Q1") is ReviewStatus.REPLACED
    assert s.question_status("SYN-Q1B") is ReviewStatus.APPROVED


def test_shared_adjust_propagates_new_stem():
    s = _session()
    s.adjust("SYN-Q2", {"scoring_notes": "Updated scoring notes."})
    for sid in ("S001", "S002", "S003"):
        plan = s.plan_for(sid)
        q2 = next(q for q in plan.questions if q.id == "SYN-Q2")
        assert q2.scoring_notes == "Updated scoring notes."
    assert s.question_status("SYN-Q2") is ReviewStatus.ADJUSTED


def test_shared_replace_is_deep_copied_per_plan():
    s = _session()
    s.replace("SYN-Q1", _q("SYN-Q1B"))
    p1 = s.plan_for("S001")
    p1.questions[0].stem = "mutated"
    assert s.plan_for("S002").questions[0].stem != "mutated"


# -- per-student overrides ---------------------------------------------------

def test_per_student_replace_is_isolated():
    s = _session()
    s.approve("SYN-Q1")
    s.approve("SYN-Q2")
    s.approve("SYN-Q3")
    s.replace_for_student("S002", "SYN-Q1", _q("SYN-Q1-S2"),
                          note="easier variant for S002")
    assert s.plan_for("S002").question_ids() == ["SYN-Q1-S2", "SYN-Q2"]
    assert s.plan_for("S001").question_ids() == ["SYN-Q1", "SYN-Q2"]
    # shared review status untouched
    assert s.question_status("SYN-Q1") is ReviewStatus.APPROVED
    # the override counts as teacher-handled: S002's gate is still green
    assert s.is_approved("S002")
    assert s.is_approved("S001")


def test_per_student_adjust_is_isolated():
    s = _session()
    s.approve_all()
    s.adjust_for_student("S001", "SYN-Q2",
                         {"answer": "about 100 J (accepted range)"})
    q_s1 = next(q for q in s.plan_for("S001").questions if q.id == "SYN-Q2")
    q_s2 = next(q for q in s.plan_for("S002").questions if q.id == "SYN-Q2")
    assert q_s1.answer == "about 100 J (accepted range)"
    assert q_s2.answer == "100 J"


def test_per_student_override_on_missing_question_raises():
    s = _session()
    with pytest.raises(KeyError):
        s.replace_for_student("S003", "SYN-Q1", _q("SYN-Q1X"))
    with pytest.raises(KeyError):
        s.adjust_for_student("S999", "SYN-Q1", {"stem": "x"})


# -- validation ----------------------------------------------------------------

def test_unknown_question_raises():
    s = _session()
    with pytest.raises(KeyError):
        s.approve("SYN-NOPE")


def test_adjust_rejects_unknown_fields_and_id_change():
    s = _session()
    with pytest.raises(ValueError):
        s.adjust("SYN-Q1", {"not_a_field": "x"})
    with pytest.raises(ValueError):
        s.adjust("SYN-Q1", {"id": "SYN-OTHER"})


def test_replace_requires_different_id():
    s = _session()
    with pytest.raises(ValueError):
        s.replace("SYN-Q1", _q("SYN-Q1"))


def test_reject_requires_reason():
    s = _session()
    with pytest.raises(ValueError):
        s.reject("SYN-Q1", "")


# -- audit trail -----------------------------------------------------------------

def test_audit_trail_records_actions_in_order():
    s = _session()
    s.approve("SYN-Q1", note="looks good")
    s.reject("SYN-Q2", "figure missing")
    s.replace_for_student("S001", "SYN-Q1", _q("SYN-Q1-S1"))
    trail = s.audit_trail()
    assert [a["action"] for a in trail] == ["approve", "reject", "replace"]
    assert [a["seq"] for a in trail] == [1, 2, 3]
    assert trail[0]["question_id"] == "SYN-Q1"
    assert trail[1]["detail"] == "figure missing"
    assert trail[2]["student_id"] == "S001"  # per-student action is marked
    assert all(a["at"] for a in trail)


def test_summary_shows_status_and_affected_students():
    s = _session()
    s.approve("SYN-Q1")
    summary = s.summary()
    assert summary["students"] == 3
    assert summary["questions"]["SYN-Q1"]["status"] == "approved"
    assert summary["questions"]["SYN-Q1"]["students_affected"] == 2
    assert summary["questions"]["SYN-Q2"]["status"] == "pending"


def test_session_does_not_mutate_caller_plans():
    plans = _plans()
    before = [p.question_ids() for p in plans]
    s = _session_from(plans)
    s.replace("SYN-Q1", _q("SYN-Q1B"))
    assert [p.question_ids() for p in plans] == before


def _session_from(plans: list[HomeworkPlan]) -> ReviewSession:
    return ReviewSession(plans, assignment_number="A-CH3-01")
