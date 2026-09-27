"""Teacher review (审核) + print-ready PDF export (issue #115).

* :mod:`review.models` -- self-contained input dataclasses mirroring the
  assembly ``HomeworkPlan`` / ``Question`` shapes (see the module docstring
  for the intended wiring once sibling PRs land on main).
* :mod:`review.review` -- :class:`~review.review.ReviewSession`:
  shared-question-level approve / replace / adjust / reject, per-student
  overrides, the approval gate (``publish()`` raises unless every question
  cleared), and a full audit trail.
* :mod:`review.export` -- stdlib-only PDF writer: student sheets
  (student ID 学号 + assignment number 作业编号， numbered stems, labeled
  figure boxes, ruled answer space, page numbers, keep-together
  pagination), a separate teacher key (教师版： answers + solution steps +
  评分说明）, whole-class batch export, and a round-trip manifest for the
  #110/#111 upload-matching pipeline.
"""

from .export import (
    ClassExport,
    export_class,
    export_student_sheet,
    export_teacher_key,
    verify_pdf_structure,
)
from .models import (
    Difficulty,
    FigureStatus,
    HomeworkPlan,
    PublishedPlan,
    Question,
    QuestionType,
)
from .review import (
    CLEARED,
    ApprovalError,
    ReviewAction,
    ReviewSession,
    ReviewStatus,
    StudentOverride,
)

__all__ = [
    "CLEARED",
    "ApprovalError",
    "ClassExport",
    "Difficulty",
    "FigureStatus",
    "HomeworkPlan",
    "PublishedPlan",
    "Question",
    "QuestionType",
    "ReviewAction",
    "ReviewSession",
    "ReviewStatus",
    "StudentOverride",
    "export_class",
    "export_student_sheet",
    "export_teacher_key",
    "verify_pdf_structure",
]
