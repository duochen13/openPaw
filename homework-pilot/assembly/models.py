"""Shared data model for the homework-pilot assembly engine and question pipeline.

Self-contained on purpose: the shapes below mirror (but do not import) the
schemas from the sibling issues so this package's tests pass on its own
branch without #109 or #112 merged:

* :class:`MasteryState` mirrors the five teaching judgments from the
  evidence ledger (issue #109): 证据不足 / 需要练习 / 正在改善 /
  已有较充分掌握证据 / 待复习. They are revisable assessments of evidence,
  never fixed labels on the student.
* :class:`WeakPointHypothesis` mirrors ``WeakPointProposal`` (issue #112):
  a *hypothesis* (假设), never a verdict. The extra ``consecutive_rounds``
  counter is what lets the assembly engine detect *recurring* difficulty
  (the same hypothesis persisting across homework rounds without
  improvement) and escalate to the teacher instead of growing the homework
  without bound.
* Skill ids follow the chapter-3 taxonomy (issue #112),
  ``homework-pilot/taxonomy/skills_ch3_v1.json``, e.g.
  ``ch3-gravitational-work`` （重力做功）, ``ch3-estimate-average-power``
  （平均功率）, ``ch3-work-vs-power`` （比较功与功率）.

Intended wiring once #109 and #112 land on main (no behavior change, just
conversion at the boundary):

* ``evidence.SkillAssessment`` -> ``SkillEvidence``: map the ledger's
  ``MasteryState`` value onto :class:`MasteryState` and carry over the
  student/skill ids.
* ``taxonomy.WeakPointProposal`` -> ``WeakPointHypothesis``: map
  ``skill_id`` / ``hypothesis_strength`` and derive
  ``consecutive_rounds`` from the proposal's history/audit (rounds the
  hypothesis survived without the student's state improving).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MasteryState(str, Enum):
    """The five teaching judgments on one student x one skill.

    Mirrors the evidence-ledger states (issue #109). Revisable
    assessments, never student labels.
    """

    INSUFFICIENT = "证据不足"          # not enough evidence yet
    NEEDS_PRACTICE = "需要练习"        # provisional weak-point hypothesis
    IMPROVING = "正在改善"              # improving, not yet solid
    MASTERED = "已有较充分掌握证据"     # fairly well-mastered evidence
    DUE_REVIEW = "待复习"               # stale evidence -> schedule a review check


class HypothesisStrength(str, Enum):
    """How strongly the evidence supports a weak-point hypothesis."""

    SINGLE_ERROR = "single_error"        # one wrong answer: weakest support
    PARTIAL_CREDIT = "partial_credit"    # partial answers repeatedly
    REPEATED_ERRORS = "repeated_errors"  # repeated errors: strongest support


@dataclass
class WeakPointHypothesis:
    """A proposed weak point （薄弱点） for one student x one skill.

    A hypothesis (假设）, never a verdict. The teacher confirms, modifies
    or rejects it upstream (issue #112); by the time it reaches the
    assembly engine it is an input the engine must respect, not re-judge.
    """

    skill_id: str
    strength: HypothesisStrength = HypothesisStrength.SINGLE_ERROR
    consecutive_rounds: int = 1  # homework rounds this hypothesis has
                                 # survived without the student's state
                                 # improving. Drives escalation.
    basis_note: str = ""  # human-readable reason, shown to the teacher

    def __post_init__(self) -> None:
        if isinstance(self.strength, str):
            self.strength = HypothesisStrength(self.strength)
        if self.consecutive_rounds < 1:
            raise ValueError("consecutive_rounds must be >= 1")


@dataclass
class SkillEvidence:
    """One student x one skill: the assembly engine's view of the evidence.

    Mirrors the evidence ledger's per-skill assessment (#109) plus the
    confirmed/modified weak-point hypothesis (#112). The engine never reads
    raw answers or scans -- only these judgments.
    """

    student_id: str
    skill_id: str
    state: MasteryState
    weak_point: WeakPointHypothesis | None = None

    def __post_init__(self) -> None:
        if not self.student_id:
            raise ValueError("student_id is required (students are ID-only)")
        if isinstance(self.state, str):
            self.state = MasteryState(self.state)
        if self.weak_point is not None and self.weak_point.skill_id != self.skill_id:
            raise ValueError("weak_point.skill_id must match SkillEvidence.skill_id")


@dataclass
class StudentProfile:
    """Everything the engine needs to know about one student."""

    student_id: str
    evidence: list[SkillEvidence] = field(default_factory=list)

    def evidence_for(self, skill_id: str) -> SkillEvidence | None:
        for ev in self.evidence:
            if ev.skill_id == skill_id:
                return ev
        return None


class ItemCategory(str, Enum):
    """The three dynamic mix buckets plus the shared common questions."""

    CURRENT = "当前学习"      # current learning: the teacher's current scope
    WEAK_POINT = "薄弱点练习"  # weak-point practice
    REVIEW = "旧知识复习"     # review of older, stale knowledge
    COMMON = "共同题"          # common questions: unified class review


@dataclass
class PlannedItem:
    """One question slot in the assembled homework plan."""

    question_id: str
    skill_id: str
    category: ItemCategory
    reason: str  # why this item was chosen; shown to the teacher
    estimated_minutes: float = 5.0
    is_diagnostic: bool = False  # True for foundational/diagnostic items
                                 # added on recurring difficulty
    verification_kind: str = ""  # "" | "different_context" | "spaced":
                                 # retention checks via a different context
                                 # or after an interval, never plain repeats

    def __post_init__(self) -> None:
        if isinstance(self.category, str):
            self.category = ItemCategory(self.category)


@dataclass
class TeacherConfig:
    """The teacher's knobs for one homework round.

    Personalized homework IS the official assignment, not extra on top of
    uniform homework -- so ``max_questions`` / ``max_minutes`` is a hard
    workload budget the engine must never exceed.
    """

    current_scope: list[str] = field(default_factory=list)  # skill ids taught now
    review_scope: list[str] = field(default_factory=list)   # allowed review skills
    max_questions: int = 10
    max_minutes: float | None = None  # estimated-time budget; None = count only
    common_question_ids: list[str] = field(default_factory=list)  # 共同题 slots
    weak_point_base_count: int = 3   # weak-point items per struggling skill
    recurring_difficulty_rounds: int = 3  # consecutive weak rounds that
                                          # trigger the teacher prompt
    default_minutes_per_question: float = 5.0

    def __post_init__(self) -> None:
        if self.max_questions < 1:
            raise ValueError("max_questions must be >= 1")
        if self.max_minutes is not None and self.max_minutes <= 0:
            raise ValueError("max_minutes must be positive when set")
        if self.weak_point_base_count < 1:
            raise ValueError("weak_point_base_count must be >= 1")


@dataclass
class HomeworkPlan:
    """The assembled, budget-checked homework for one student."""

    student_id: str
    items: list[PlannedItem] = field(default_factory=list)
    teacher_prompts: list[str] = field(default_factory=list)  # e.g. 可能需要讲解
    dropped_items: list[str] = field(default_factory=list)  # cut for budget
    total_minutes: float = 0.0
    within_budget: bool = True

    def count_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.category.value] = counts.get(item.category.value, 0) + 1
        return counts
