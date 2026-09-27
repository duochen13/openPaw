"""Teacher-facing question review queue (issue #114).

The review queue is the gate between candidate generation and the
teacher-approved bank: every entry shows the recommendation reason,
expected difficulty, answer, solution process and scoring notes so the
teacher can approve / replace / adjust. Full UI is issue #115's job --
this module provides the data structures and operations.

Figure placeholder tasks (:class:`generate.FigureTask`) ride along on
their question's entry, so the teacher sees exactly which figures they
are being asked to provide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .generate import FigureTask, Question


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"  # enters the teacher-approved bank
    REPLACED = "replaced"  # teacher swapped in a different question
    ADJUSTED = "adjusted"  # teacher edited then approved
    REJECTED = "rejected"


@dataclass
class ReviewEntry:
    """One candidate question awaiting the teacher's decision."""

    question: Question
    decision: ReviewDecision = ReviewDecision.PENDING
    teacher_note: str = ""
    decided_at: str = ""
    replacement_question_id: str = ""  # set on REPLACED

    def __post_init__(self) -> None:
        if isinstance(self.decision, str):
            self.decision = ReviewDecision(self.decision)

    def summary(self) -> dict:
        """What the teacher sees for this entry: reason, difficulty,
        answer, solution and scoring -- plus any figure task."""
        q = self.question
        return {
            "question_id": q.id,
            "skill_ids": list(q.skill_ids),
            "stem": q.stem,
            "question_type": q.question_type.value,
            "difficulty": q.difficulty.value,
            "recommendation_reason": q.recommendation_reason,
            "answer": q.answer,
            "solution_steps": list(q.solution_steps),
            "scoring_notes": q.scoring_notes,
            "figure": q.figure.value,
            "figure_task": (
                {
                    "description": q.figure_task.description,
                    "why_needed": q.figure_task.why_needed,
                }
                if q.figure_task
                else None
            ),
            "source": q.source,
            "source_attribution": q.source_attribution,
            "decision": self.decision.value,
            "teacher_note": self.teacher_note,
        }


class ReviewQueue:
    """The teacher's pending-decision list of candidate questions."""

    def __init__(self) -> None:
        self._entries: dict[str, ReviewEntry] = {}

    def add(self, question: Question) -> ReviewEntry:
        """Enqueue a candidate question. Returns the entry.

        Raises if the question id is already queued -- duplicates would
        make the teacher review the same question twice.
        """
        if question.id in self._entries:
            raise ValueError(f"question {question.id!r} is already in the review queue")
        entry = ReviewEntry(question=question)
        self._entries[question.id] = entry
        return entry

    def get(self, question_id: str) -> ReviewEntry:
        return self._entries[question_id]

    def pending(self) -> list[ReviewEntry]:
        """Entries still awaiting a decision, in insertion order."""
        return [e for e in self._entries.values()
                if e.decision == ReviewDecision.PENDING]

    def pending_figure_tasks(self) -> list[FigureTask]:
        """Figure placeholder tasks among the pending entries -- the
        explicit teacher to-do list for figures the pipeline would not
        generate on its own."""
        return [
            e.question.figure_task
            for e in self.pending()
            if e.question.figure_task is not None
        ]

    def decide(
        self,
        question_id: str,
        decision: ReviewDecision | str,
        teacher_note: str = "",
        replacement_question_id: str = "",
    ) -> ReviewEntry:
        """Record the teacher's approve/replace/adjust/reject decision."""
        entry = self._entries[question_id]
        entry.decision = ReviewDecision(decision)
        entry.teacher_note = teacher_note
        entry.decided_at = datetime.now(timezone.utc).isoformat()
        if entry.decision == ReviewDecision.REPLACED and not replacement_question_id:
            raise ValueError("REPLACED requires replacement_question_id")
        entry.replacement_question_id = replacement_question_id
        return entry

    def approved(self) -> list[ReviewEntry]:
        """Entries the teacher approved (or adjusted-then-approved)."""
        return [e for e in self._entries.values()
                if e.decision in (ReviewDecision.APPROVED, ReviewDecision.ADJUSTED)]

    def __len__(self) -> int:
        return len(self._entries)
