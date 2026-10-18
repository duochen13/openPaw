"""View models for the teacher console (issue #167).

These dataclasses are *view* shapes. Following the repo's per-package
pattern they mirror (but do not import) the upstream shapes, so the
console renders standalone and each package keeps passing its own tests:

* :class:`RecognitionItem` mirrors ``evidence.EvidenceRecord`` (one
  student x one sub-question: recognized answer, grading mark, image
  location) plus the ingestion pipeline's ``ocr_reliability``.
* :class:`SkillHypothesisView` mirrors ``evidence.SkillAssessment`` (the
  five teaching-judgment states, provisional 薄弱点假设 flag, qualitative
  confidence) with its supporting evidence snippets.
* :class:`ReviewQuestionView` mirrors ``review.models.Question`` as
  surfaced by ``assembly.review_queue.ReviewEntry.summary()``: stem,
  target skills, recommendation reason, expected difficulty, answer,
  solution steps, scoring notes （评分说明）, figure status.
* :class:`StudentMix` mirrors the per-student category counts of an
  ``assembly`` homework plan （共同题 / 当前学习 / 薄弱点练习 / 旧知识复习）.

Binding rules from design.md and the privacy package, enforced by the
tests in ``webui/tests``:

* Students are identified by ID only (``S-023``). There is no name field
  anywhere in this module, and there must never be one.
* Skill state is one of the five teaching judgments in
  :data:`MASTERY_STATES`. There is deliberately no numeric mastery field:
  v1 has no calibration basis for precise percentages.
* OCR reliability (how well the system *read* the page) and the mastery
  judgment (what the teacher concludes about the student) are separate
  uncertainties and are modeled -- and rendered -- separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: The five teaching judgments (design.md 学习记录； mirrors
#: ``evidence.MasteryState``). Revisable assessments, never student labels.
MASTERY_STATES = (
    "证据不足",
    "需要练习",
    "正在改善",
    "已有较充分掌握证据",
    "待复习",
)

#: Grading outcomes, mirroring ``evidence.GradingResult`` values.
GRADING_RESULTS = ("正确", "错误", "部分正确", "无法辨认")

#: Assembly mix categories, in display order （共同题 first).
MIX_CATEGORIES = ("共同题", "当前学习", "薄弱点练习", "旧知识复习")

#: Difficulty values mirror ``review.models.Difficulty``; labels are the
#: teacher-facing wording （预期难度）.
DIFFICULTY_LABELS = {"easy": "基础", "medium": "中等", "hard": "较难"}


class ReliabilityTier(str, Enum):
    """How much the teacher can trust one OCR read.

    Bands follow the ingestion pipeline's own numbers
    (``ingestion.pipeline`` routes reads below its 0.8 recognition
    threshold to review; ``ingestion.evaluate`` buckets reliability at
    0.5 / 0.8 / 0.95). This is a property of the *reading*, never of the
    student -- it says nothing about mastery.
    """

    RELIABLE = "reliable"    # 可靠： read at/above the pipeline threshold
    DOUBTFUL = "doubtful"    # 存疑： read, but below threshold -- eyeball it
    MANUAL = "manual"        # 需手录： effectively unread -- type it in


#: Tier -> (teacher-facing label, CSS class).
TIER_PRESENTATION = {
    ReliabilityTier.RELIABLE: ("可靠", "tier-reliable"),
    ReliabilityTier.DOUBTFUL: ("存疑", "tier-doubtful"),
    ReliabilityTier.MANUAL: ("需手录", "tier-manual"),
}


def reliability_tier(ocr_reliability: float) -> ReliabilityTier:
    """Bucket a raw OCR reliability score into its display tier."""
    if not 0.0 <= ocr_reliability <= 1.0:
        raise ValueError("ocr_reliability must be between 0.0 and 1.0")
    if ocr_reliability >= 0.8:
        return ReliabilityTier.RELIABLE
    if ocr_reliability >= 0.5:
        return ReliabilityTier.DOUBTFUL
    return ReliabilityTier.MANUAL


@dataclass
class RecognitionItem:
    """One recognized answer awaiting the teacher's confirmation.

    Mirrors ``evidence.EvidenceRecord`` fields the confirmation queue
    needs. ``grading_result`` is the read of the teacher's own grading
    mark -- confirming it confirms *what was read*, which is a different
    question from whether the student has mastered the skill.
    """

    student_id: str
    question_label: str            # e.g. "第3题"
    sub_question: str = ""         # e.g. "（2）"
    skill_name: str = ""           # 目标技能 (teacher-facing name)
    recognized_answer: str = ""    # what OCR read; "" when unreadable
    grading_result: str = "无法辨认"
    ocr_reliability: float = 0.0
    image_location: str = ""       # 原图位置, e.g. "scan-2026-10-12/p03.png"
    page_label: str = ""           # e.g. "第 3 页"
    observed_date: str = ""        # e.g. "10月12日"

    def __post_init__(self) -> None:
        if not self.student_id:
            raise ValueError("student_id is required (students are ID-only)")
        if self.grading_result not in GRADING_RESULTS:
            raise ValueError(f"unknown grading_result: {self.grading_result!r}")
        reliability_tier(self.ocr_reliability)  # validates the range

    @property
    def tier(self) -> ReliabilityTier:
        return reliability_tier(self.ocr_reliability)


@dataclass
class EvidenceSnippet:
    """One dated piece of evidence behind a skill judgment."""

    question_label: str            # e.g. "第3题（2）"
    date: str                      # e.g. "10月12日"
    grading_result: str = "错误"
    note: str = ""


@dataclass
class SkillHypothesisView:
    """A weak-point hypothesis / skill state for teacher confirmation.

    Mirrors ``evidence.SkillAssessment``: ``state`` is one of
    :data:`MASTERY_STATES`; ``provisional`` marks a 待验证 hypothesis
    (one wrong answer supports a hypothesis, never a verdict);
    ``confidence`` （高/中/低） is the qualitative mastery uncertainty --
    deliberately not a number, and unrelated to OCR reliability.
    """

    student_id: str
    skill_id: str                  # e.g. "ch3-friction-work"
    skill_name: str                # e.g. "摩擦力做功"
    state: str = "证据不足"
    provisional: bool = False
    hypothesis_note: str = ""
    confidence: str = "低"
    evidence: list[EvidenceSnippet] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.student_id:
            raise ValueError("student_id is required (students are ID-only)")
        if self.state not in MASTERY_STATES:
            raise ValueError(f"state must be one of {MASTERY_STATES}: {self.state!r}")
        if self.confidence not in ("高", "中", "低"):
            raise ValueError("confidence is qualitative: 高 / 中 / 低")


@dataclass
class ReviewQuestionView:
    """One shared question awaiting review at the shared-question level.

    Mirrors ``review.models.Question`` + ``assembly`` review-queue
    summary fields. One teacher decision covers every student assigned
    the question (``assigned_count``), which is what keeps review of
    ~80 personalized plans tractable.
    """

    id: str                        # e.g. "SYN-Q1"
    stem: str
    skill_names: list[str]         # 目标技能 (teacher-facing names)
    category: str                  # one of MIX_CATEGORIES
    difficulty: str = "medium"     # mirrors review.Difficulty value
    recommendation_reason: str = ""
    answer: str = ""               # 参考答案
    solution_steps: list[str] = field(default_factory=list)
    scoring_notes: str = ""        # 评分说明
    figure_note: str = ""          # "" = no figure; else 图待补充 description
    assigned_count: int = 0        # students this decision covers

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("question id is required")
        if self.category not in MIX_CATEGORIES:
            raise ValueError(f"category must be one of {MIX_CATEGORIES}")
        if self.difficulty not in DIFFICULTY_LABELS:
            raise ValueError(f"unknown difficulty: {self.difficulty!r}")

    @property
    def difficulty_label(self) -> str:
        return DIFFICULTY_LABELS[self.difficulty]


@dataclass
class StudentMix:
    """Per-student homework mix summary （共同题 / 当前学习 / 薄弱点 / 复习）."""

    student_id: str
    counts: dict[str, int] = field(default_factory=dict)  # category -> n

    @property
    def total(self) -> int:
        return sum(self.counts.get(c, 0) for c in MIX_CATEGORIES)


@dataclass
class ExportInfo:
    """What the export view shows for one class (mirrors the manifest
    entries of ``review.export.export_class``)."""

    assignment_number: str                       # 作业编号
    students: list[tuple[str, int]] = field(default_factory=list)  # (id, pages)
    teacher_key_pages: int = 0
    last_export: str = ""                        # human-readable summary


@dataclass
class ClassData:
    """Everything the console shows for one class."""

    key: str                       # stable DOM key, e.g. "g9-1"
    label: str                     # e.g. "九年级1班"
    chapter_label: str             # e.g. "第三章《能量的转化与守恒》"
    assignment_number: str
    recognition: list[RecognitionItem] = field(default_factory=list)
    hypotheses: list[SkillHypothesisView] = field(default_factory=list)
    review_questions: list[ReviewQuestionView] = field(default_factory=list)
    mix: list[StudentMix] = field(default_factory=list)
    export: ExportInfo | None = None


@dataclass
class ConsoleData:
    """The whole console: teacher identity + per-class data."""

    teacher_label: str = "试点教师"
    teacher_context: str = "科学 · 九年级"
    classes: list[ClassData] = field(default_factory=list)
