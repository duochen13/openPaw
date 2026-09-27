"""Lightweight data model for teacher review and PDF export (issue #115).

Self-contained on purpose: the shapes below *mirror* (but do not import)
the assembly models (``homework-pilot/assembly``) so this package's tests
pass on its own branch without sibling PRs merged.

Intended wiring once the assembly engine lands on main (no behavior change,
just conversion at the boundary):

* ``assembly.generate.Question`` -> :class:`Question`: copy ``id``,
  ``skill_ids``, ``stem``, ``question_type``, ``figure``,
  ``figure_description``, ``answer``, ``solution_steps``,
  ``scoring_notes``, ``difficulty``, ``recommendation_reason``. A
  ``FigureTask`` (figure == PLACEHOLDER) is summarized into
  ``figure_description``; the full task still lives in the assembly
  review queue.
* ``assembly.models.HomeworkPlan`` -> :class:`HomeworkPlan`: resolve each
  ``PlannedItem.question_id`` against the teacher-approved question bank
  to build the ordered :attr:`HomeworkPlan.questions` list, and set
  ``category`` on each question from the item's ``ItemCategory``.

Domain terms are kept in Chinese where they are teacher-facing concepts:
审核 (review), 共同题 (common question), 评分说明 (scoring notes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionType(str, Enum):
    CALCULATION = "calculation"
    JUDGMENT = "judgment"        # e.g. 判断做功阶段
    COMPARISON = "comparison"    # e.g. 比较功与功率
    ESTIMATION = "estimation"    # e.g. 估算平均功率
    MULTIPLE_CHOICE = "multiple_choice"


class FigureStatus(str, Enum):
    NONE = "none"                # text-only question; no figure needed
    PROVIDED = "provided"        # a reliable figure ships with the question
    PLACEHOLDER = "placeholder"  # FIGURE NEEDED (图待补充): the teacher must
                                 # supply or draw the figure


@dataclass
class Question:
    """One reviewable question.

    Mirrors ``assembly.generate.Question`` (minus the pre-release
    validation machinery, which lives upstream). ``category`` records the
    assembly bucket (共同题 / 当前学习 / 薄弱点练习 / 旧知识复习).
    """

    id: str
    skill_ids: list[str]
    stem: str
    question_type: QuestionType = QuestionType.CALCULATION
    figure: FigureStatus = FigureStatus.NONE
    figure_description: str = ""  # what the figure shows (PROVIDED), or what
                                  # the teacher should supply (PLACEHOLDER)
    answer: str = ""
    solution_steps: list[str] = field(default_factory=list)
    scoring_notes: str = ""       # 评分说明： how to award partial credit
    difficulty: Difficulty = Difficulty.MEDIUM
    recommendation_reason: str = ""
    category: str = ""            # e.g. "共同题"

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("question id is required")
        if isinstance(self.question_type, str):
            self.question_type = QuestionType(self.question_type)
        if isinstance(self.figure, str):
            self.figure = FigureStatus(self.figure)
        if isinstance(self.difficulty, str):
            self.difficulty = Difficulty(self.difficulty)


@dataclass
class HomeworkPlan:
    """The assembled question list for one student, ready for review.

    Mirrors ``assembly.models.HomeworkPlan`` with ``PlannedItem``
    resolved to full :class:`Question` objects in display order.
    """

    student_id: str
    questions: list[Question] = field(default_factory=list)
    assignment_number: str = ""  # 作业编号， printed on every student sheet

    def __post_init__(self) -> None:
        if not self.student_id:
            raise ValueError("student_id is required (students are ID-only)")

    def question_ids(self) -> list[str]:
        return [q.id for q in self.questions]


@dataclass
class PublishedPlan:
    """A teacher-approved homework plan, ready to export.

    Only :meth:`review.ReviewSession.publish` creates these; the export
    module refuses anything else, so unapproved work can never leak into
    a student PDF.
    """

    student_id: str
    assignment_number: str
    questions: list[Question]
    published_at: str  # ISO-8601 UTC
    audit_ref: str = ""  # pointer into the review session's audit trail
