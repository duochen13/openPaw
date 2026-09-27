"""Teacher review workflow with an approval gate (issue #115).

Review happens at the *shared-question* level (共同题 semantics): one
review decision covers every student assigned that question. Approving,
replacing, or adjusting a question propagates to all affected student
plans. Per-student overrides are also supported: a teacher can replace or
adjust a single student's instance without touching anyone else.

Approval gate: :meth:`ReviewSession.publish` raises
:class:`ApprovalError` unless *every* question in the student's plan has
cleared review. Nothing becomes official homework without the teacher's
approval.

Every teacher action is appended to a full audit trail
(:meth:`ReviewSession.audit_trail`), so the pilot can answer "who changed
what, when" for each homework round.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, timezone
from enum import Enum

from .models import HomeworkPlan, PublishedPlan, Question


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"    # 审核通过
    ADJUSTED = "adjusted"    # teacher edited the question, then approved
    REPLACED = "replaced"    # teacher swapped in a different question
    REJECTED = "rejected"    # rejected with a reason; must be replaced or
                             # adjusted before it can be published


#: Statuses that let a question through the approval gate.
CLEARED = frozenset(
    {ReviewStatus.APPROVED, ReviewStatus.ADJUSTED, ReviewStatus.REPLACED}
)


class ApprovalError(Exception):
    """Raised when publish is attempted on an unapproved plan."""


@dataclass
class ReviewAction:
    """One entry in the session's audit trail."""

    seq: int
    at: str                      # ISO-8601 UTC timestamp
    action: str                  # "approve" | "reject" | "replace" | "adjust"
    question_id: str
    student_id: str = ""         # "" = shared-level (all students)
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "at": self.at,
            "action": self.action,
            "question_id": self.question_id,
            "student_id": self.student_id,
            "detail": self.detail,
        }


@dataclass
class StudentOverride:
    """A per-student change that does not touch the shared question."""

    action: str                  # "replace" | "adjust"
    new_question: Question       # the student's own copy
    at: str
    note: str = ""


class ReviewSession:
    """One 审核 (review) round over a set of assembled student plans."""

    def __init__(
        self,
        plans: list[HomeworkPlan],
        assignment_number: str = "",
    ) -> None:
        if not plans:
            raise ValueError("a review session needs at least one plan")
        self.assignment_number = assignment_number
        # Deep copies: review never mutates the caller's plans in place.
        self._plans: dict[str, HomeworkPlan] = {
            p.student_id: deepcopy(p) for p in plans
        }
        # Shared canonical question per id (latest teacher-edited version).
        self._canonical: dict[str, Question] = {}
        for plan in self._plans.values():
            for q in plan.questions:
                self._canonical.setdefault(q.id, deepcopy(q))
        self._status: dict[str, ReviewStatus] = {
            qid: ReviewStatus.PENDING for qid in self._canonical
        }
        self._reasons: dict[str, str] = {}          # qid -> reject reason
        self._replace_map: dict[str, str] = {}      # old qid -> new qid
        self._overrides: dict[str, dict[str, StudentOverride]] = {}
        self._actions: list[ReviewAction] = []
        self._seq = 0

    # -- internal helpers -------------------------------------------------

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _log(self, action: str, question_id: str, student_id: str = "",
             detail: str = "") -> None:
        self._seq += 1
        self._actions.append(
            ReviewAction(
                seq=self._seq,
                at=self._now(),
                action=action,
                question_id=question_id,
                student_id=student_id,
                detail=detail,
            )
        )

    def _require_known(self, question_id: str) -> None:
        if question_id not in self._canonical:
            raise KeyError(f"unknown question {question_id!r} in this session")

    def _plans_with(self, question_id: str) -> list[HomeworkPlan]:
        return [
            plan for plan in self._plans.values()
            if any(q.id == question_id for q in plan.questions)
        ]

    def _swap_in_plans(self, old_id: str, new_question: Question,
                       plans: list[HomeworkPlan]) -> None:
        for plan in plans:
            plan.questions = [
                deepcopy(new_question) if q.id == old_id else q
                for q in plan.questions
            ]

    # -- shared-level operations ------------------------------------------

    def approve(self, question_id: str, note: str = "") -> None:
        """Approve a question for every student assigned it (审核通过)."""
        self._require_known(question_id)
        self._status[question_id] = ReviewStatus.APPROVED
        self._log("approve", question_id, detail=note)

    def reject(self, question_id: str, reason: str) -> None:
        """Reject a question; it must be replaced/adjusted before publish."""
        self._require_known(question_id)
        if not reason:
            raise ValueError("a reject reason is required")
        self._status[question_id] = ReviewStatus.REJECTED
        self._reasons[question_id] = reason
        self._log("reject", question_id, detail=reason)

    def adjust(self, question_id: str, patch: dict, note: str = "") -> None:
        """Edit a question's fields, then mark it approved (adjusted).

        ``patch`` maps :class:`Question` field names to new values; unknown
        fields raise :class:`ValueError`. The edit propagates to every
        student assigned the question.
        """
        self._require_known(question_id)
        valid = {f.name for f in fields(Question)}
        unknown = set(patch) - valid
        if unknown:
            raise ValueError(f"unknown Question field(s): {sorted(unknown)}")
        if "id" in patch and patch["id"] != question_id:
            raise ValueError("adjust cannot change a question's id; use replace()")
        canonical = replace(deepcopy(self._canonical[question_id]), **patch)
        self._canonical[question_id] = canonical
        self._swap_in_plans(question_id, canonical, self._plans_with(question_id))
        self._status[question_id] = ReviewStatus.ADJUSTED
        self._reasons.pop(question_id, None)
        self._log("adjust", question_id, detail=note or f"patch={sorted(patch)}")

    def replace(self, question_id: str, new_question: Question,
                note: str = "") -> None:
        """Swap a shared question for a different one, class-wide.

        Every student assigned ``question_id`` gets ``new_question``
        instead. The replacement is the teacher's own choice, so it enters
        already approved.
        """
        self._require_known(question_id)
        if new_question.id == question_id:
            raise ValueError("replace needs a *different* question id; use adjust()")
        if not new_question.stem:
            raise ValueError("replacement question needs a stem")
        self._canonical[new_question.id] = deepcopy(new_question)
        self._swap_in_plans(question_id, new_question,
                            self._plans_with(question_id))
        self._status[question_id] = ReviewStatus.REPLACED
        self._status[new_question.id] = ReviewStatus.APPROVED
        self._replace_map[question_id] = new_question.id
        self._reasons.pop(question_id, None)
        self._log("replace", question_id,
                  detail=note or f"replaced by {new_question.id}")

    def approve_all(self, note: str = "") -> None:
        """Approve every still-pending question in one go."""
        for qid, status in self._status.items():
            if status is ReviewStatus.PENDING:
                self._status[qid] = ReviewStatus.APPROVED
                self._log("approve", qid, detail=note or "approve_all")

    # -- per-student overrides --------------------------------------------

    def replace_for_student(self, student_id: str, question_id: str,
                            new_question: Question, note: str = "") -> None:
        """Replace one student's instance of a question only.

        Other students keep the shared version; the shared review status
        is untouched.
        """
        plan = self._plans.get(student_id)
        if plan is None:
            raise KeyError(f"unknown student {student_id!r}")
        if not any(q.id == question_id for q in plan.questions):
            raise KeyError(
                f"student {student_id!r} has no question {question_id!r}"
            )
        if new_question.id == question_id:
            raise ValueError("override replace needs a *different* question id")
        self._overrides.setdefault(student_id, {})[question_id] = StudentOverride(
            action="replace",
            new_question=deepcopy(new_question),
            at=self._now(),
            note=note,
        )
        # The teacher hand-picked this instance, so it is approved by
        # definition; without a status entry the gate would block it.
        self._canonical[new_question.id] = deepcopy(new_question)
        self._status[new_question.id] = ReviewStatus.APPROVED
        plan.questions = [
            deepcopy(new_question) if q.id == question_id else q
            for q in plan.questions
        ]
        self._log("replace", question_id, student_id=student_id,
                  detail=note or f"per-student replacement {new_question.id}")

    def adjust_for_student(self, student_id: str, question_id: str,
                           patch: dict, note: str = "") -> None:
        """Adjust one student's instance of a question only."""
        plan = self._plans.get(student_id)
        if plan is None:
            raise KeyError(f"unknown student {student_id!r}")
        valid = {f.name for f in fields(Question)}
        unknown = set(patch) - valid
        if unknown:
            raise ValueError(f"unknown Question field(s): {sorted(unknown)}")
        if "id" in patch and patch["id"] != question_id:
            raise ValueError("adjust cannot change a question's id")
        target = next((q for q in plan.questions if q.id == question_id), None)
        if target is None:
            raise KeyError(
                f"student {student_id!r} has no question {question_id!r}"
            )
        adjusted = replace(deepcopy(target), **patch)
        self._overrides.setdefault(student_id, {})[question_id] = StudentOverride(
            action="adjust", new_question=adjusted, at=self._now(), note=note
        )
        plan.questions = [adjusted if q.id == question_id else q
                          for q in plan.questions]
        self._log("adjust", question_id, student_id=student_id,
                  detail=note or f"per-student patch={sorted(patch)}")

    # -- status, gate, publish --------------------------------------------

    def question_status(self, question_id: str) -> ReviewStatus:
        self._require_known(question_id)
        return self._status[question_id]

    def pending_questions(self) -> list[str]:
        """Question ids still blocking the approval gate."""
        return [qid for qid, s in self._status.items()
                if s not in CLEARED]

    def plan_for(self, student_id: str) -> HomeworkPlan:
        """The student's plan with all shared changes and overrides applied."""
        plan = self._plans.get(student_id)
        if plan is None:
            raise KeyError(f"unknown student {student_id!r}")
        return deepcopy(plan)

    def student_ids(self) -> list[str]:
        return list(self._plans)

    def _blocking(self, student_id: str) -> list[str]:
        """Question ids in this student's plan that are not cleared."""
        overrides = self._overrides.get(student_id, {})
        blocking: list[str] = []
        for q in self._plans[student_id].questions:
            if q.id in overrides:
                continue  # the teacher personally handled this instance
            if self._status.get(q.id) not in CLEARED:
                blocking.append(q.id)
        return blocking

    def is_approved(self, student_id: str) -> bool:
        """Approval gate: True only if every question in the plan cleared."""
        if student_id not in self._plans:
            raise KeyError(f"unknown student {student_id!r}")
        return not self._blocking(student_id)

    def publish(self, student_id: str) -> PublishedPlan:
        """Publish one student's homework. Raises unless fully approved."""
        if student_id not in self._plans:
            raise KeyError(f"unknown student {student_id!r}")
        blocking = self._blocking(student_id)
        if blocking:
            raise ApprovalError(
                f"cannot publish {student_id}: unapproved question(s) "
                f"{blocking} — teacher review (审核) is required first"
            )
        plan = self._plans[student_id]
        return PublishedPlan(
            student_id=student_id,
            assignment_number=self.assignment_number or plan.assignment_number,
            questions=deepcopy(plan.questions),
            published_at=self._now(),
            audit_ref=f"session:{self.assignment_number}:{student_id}",
        )

    def publish_class(self) -> list[PublishedPlan]:
        """Publish every student's plan. Raises if any plan is blocked."""
        blocked = {sid: self._blocking(sid) for sid in self._plans
                   if self._blocking(sid)}
        if blocked:
            raise ApprovalError(
                "cannot publish class: unapproved questions remain: "
                + "; ".join(f"{sid}: {qids}" for sid, qids in blocked.items())
            )
        return [self.publish(sid) for sid in self._plans]

    def audit_trail(self) -> list[dict]:
        """Full chronological record of teacher actions in this session."""
        return [a.as_dict() for a in self._actions]

    def summary(self) -> dict:
        """Teacher-facing overview: per-question status and blockers."""
        return {
            "assignment_number": self.assignment_number,
            "students": len(self._plans),
            "questions": {
                qid: {
                    "status": self._status[qid].value,
                    "students_affected": len(self._plans_with(qid)),
                    "reject_reason": self._reasons.get(qid, ""),
                    "replaced_by": self._replace_map.get(qid, ""),
                }
                for qid in self._canonical
            },
            "actions": len(self._actions),
        }
