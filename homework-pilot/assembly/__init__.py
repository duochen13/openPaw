"""Personalized homework assembly + question generation (issues #113, #114).

* :mod:`assembly.engine` -- assembles each student's homework from their
  evidence record (``assemble``).
* :mod:`assembly.generate` -- candidate question model, pre-release
  validation, figure placeholder tasks, per-skill figure-need stats.
* :mod:`assembly.review_queue` -- teacher-facing review queue
  (approve / replace / adjust / reject).
* :mod:`assembly.question_bank` -- synthetic sample questions and a
  test-only bank selector (fixtures, NOT teacher-approved content).
* :mod:`assembly.models` -- self-contained input dataclasses mirroring
  the evidence-ledger (#109) and taxonomy (#112) schemas.

Self-contained: tests pass on this branch alone, without #109 or #112
merged. See ``README.md`` for the intended wiring once they land.
"""

from .engine import QuestionSelector, assemble, default_selector
from .generate import (
    SYNTHETIC_PREFIX,
    CheckResult,
    Difficulty,
    FigureNeedStats,
    FigureStatus,
    FigureTask,
    Question,
    QuestionType,
    ValidationReport,
    create_question,
    validate_question,
)
from .models import (
    HomeworkPlan,
    HypothesisStrength,
    ItemCategory,
    MasteryState,
    PlannedItem,
    SkillEvidence,
    StudentProfile,
    TeacherConfig,
    WeakPointHypothesis,
)
from .question_bank import QUESTION_BANK, SAMPLE_GENERATED_SET, bank_selector
from .review_queue import ReviewDecision, ReviewEntry, ReviewQueue

__all__ = [
    # engine (#113)
    "assemble",
    "QuestionSelector",
    "default_selector",
    # models
    "MasteryState",
    "HypothesisStrength",
    "WeakPointHypothesis",
    "SkillEvidence",
    "StudentProfile",
    "ItemCategory",
    "PlannedItem",
    "TeacherConfig",
    "HomeworkPlan",
    # generate (#114)
    "SYNTHETIC_PREFIX",
    "Question",
    "QuestionType",
    "Difficulty",
    "FigureStatus",
    "FigureTask",
    "CheckResult",
    "ValidationReport",
    "create_question",
    "validate_question",
    "FigureNeedStats",
    # review queue (#114)
    "ReviewQueue",
    "ReviewEntry",
    "ReviewDecision",
    # bank
    "QUESTION_BANK",
    "SAMPLE_GENERATED_SET",
    "bank_selector",
]
