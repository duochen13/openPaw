"""Data model for the homework-pilot evidence ledger.

The long-term learning record is the product's core: per-student, per-skill
current judgments plus dated evidence history (see ``homwork-pilot/design.md``,
section 学习记录).

Key design constraints, taken directly from the design doc:
  * Judgments are revisable teaching assessments, never fixed labels on students.
  * Five states only: 证据不足 / 需要练习 / 正在改善 / 已有较充分掌握证据 / 待复习.
  * ``ocr_reliability`` (how well we read the handwriting/scan) and the mastery
    judgment are TWO separate fields. "We couldn't read it" is never conflated
    with "the student doesn't know it".
  * No precise mastery percentages in v1 (no calibration basis). Mastery
    uncertainty is qualitative (``Confidence``: 高/中/低), never a number.
  * Students are identified by ID only. There is no name field anywhere, and
    :meth:`EvidenceRecord.from_dict` rejects name-like keys outright.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

#: Current on-disk schema version. Bump when the serialized layout changes and
#: register a migration in ``evidence.ledger.MIGRATIONS``.
SCHEMA_VERSION = 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MasteryState(str, Enum):
    """The five teaching judgments. Revisable assessments, not student labels."""

    INSUFFICIENT_EVIDENCE = "证据不足"          # not enough evidence yet
    NEEDS_PRACTICE = "需要练习"                 # provisional weak-point hypothesis
    IMPROVING = "正在改善"                       # improving, not yet solid
    FAIRLY_WELL_MASTERED = "已有较充分掌握证据"  # fairly well-mastered evidence
    DUE_FOR_REVIEW = "待复习"                    # stale evidence -> schedule a review check


class GradingResult(str, Enum):
    """批改结果： the teacher's/system's grading outcome for one answer."""

    CORRECT = "正确"
    INCORRECT = "错误"
    PARTIAL = "部分正确"
    UNREADABLE = "无法辨认"  # could not be read; carries NO mastery signal


class Confidence(str, Enum):
    """Qualitative mastery uncertainty. Deliberately NOT a percentage (v1 has
    no calibration basis). Separate from ``EvidenceRecord.ocr_reliability``."""

    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class AuditKind(str, Enum):
    TEACHER_OVERRIDE = "teacher_override"  # teacher manually set the state
    TEACHER_NOTE = "teacher_note"          # teacher annotated without changing state
    STALE_FLAG = "stale_flag"              # system scheduled a review check
    STATE_CHANGE = "state_change"          # automatic transition from new evidence


# Keys that must never appear on an evidence record: students are ID-only.
_FORBIDDEN_NAME_KEYS = {"name", "student_name", "studentName", "姓名", "名字"}


@dataclass
class EvidenceRecord:
    """One dated piece of evidence for one student × one skill.

    ``ocr_reliability`` answers "how well did we read it?" (0.0-1.0).
    The mastery judgment lives on :class:`SkillAssessment` and is derived from
    the history of these records -- the two are never the same field.
    """

    student_id: str
    skill_id: str
    question_id: str = ""          # 题目编号
    sub_question: str = ""         # 小题 (e.g. "11(2)")
    knowledge_point: str = ""      # 知识点
    student_answer: str = ""       # 学生作答
    grading_result: GradingResult = GradingResult.UNREADABLE  # 批改结果
    image_location: str = ""       # 原图位置, e.g. "scan-2026-09-27/p03.png"
    ocr_reliability: float = 1.0   # how well the answer could be read, 0..1
    hint_used: bool = False        # 是否使用了提示
    correction_of: str = ""        # record_id this is a correction of (订正), else ""
    teacher_note: str = ""         # 教师修正/批注
    followup_verified: bool = False  # 后续验证： has this been checked again later?
    followup_note: str = ""
    independently_completed: bool = True  # 学生是否独立完成
    context: str = ""              # where the evidence came from,
                                   # e.g. "ch3-hw-05" vs "ch3-quiz-1"
    observed_at: datetime = field(default_factory=_utcnow)
    created_at: datetime = field(default_factory=_utcnow)
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.student_id:
            raise ValueError("student_id is required (students are identified by ID only)")
        if not 0.0 <= self.ocr_reliability <= 1.0:
            raise ValueError("ocr_reliability must be between 0.0 and 1.0")
        if isinstance(self.grading_result, str):
            self.grading_result = GradingResult(self.grading_result)

    # -- JSON serialization -------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["grading_result"] = self.grading_result.value
        d["observed_at"] = self.observed_at.isoformat()
        d["created_at"] = self.created_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceRecord":
        forbidden = _FORBIDDEN_NAME_KEYS.intersection(data.keys())
        if forbidden:
            raise ValueError(
                f"students are identified by ID only; name-like keys are forbidden: "
                f"{sorted(forbidden)}"
            )
        d = dict(data)
        d["grading_result"] = GradingResult(d.get("grading_result", GradingResult.UNREADABLE.value))
        for key in ("observed_at", "created_at"):
            if isinstance(d.get(key), str):
                d[key] = datetime.fromisoformat(d[key])
        return cls(**d)


@dataclass
class SkillAssessment:
    """Current teaching judgment for one student × one skill.

    ``provisional_hypothesis`` marks a 薄弱点假设 (weak-point hypothesis) that is
    still 待验证 (pending verification) -- it is never a confirmed verdict.
    """

    student_id: str
    skill_id: str
    state: MasteryState = MasteryState.INSUFFICIENT_EVIDENCE
    provisional_hypothesis: bool = False
    hypothesis_note: str = ""
    confidence: Confidence = Confidence.LOW  # mastery uncertainty (not a %)
    last_evidence_at: datetime | None = None
    updated_at: datetime = field(default_factory=_utcnow)
    state_before_review: MasteryState | None = None  # set when flagged 待复习

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        d["confidence"] = self.confidence.value
        d["state_before_review"] = (
            self.state_before_review.value if self.state_before_review else None
        )
        d["last_evidence_at"] = (
            self.last_evidence_at.isoformat() if self.last_evidence_at else None
        )
        d["updated_at"] = self.updated_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SkillAssessment":
        d = dict(data)
        d["state"] = MasteryState(d["state"])
        d["confidence"] = Confidence(d.get("confidence", Confidence.LOW.value))
        sbr = d.get("state_before_review")
        d["state_before_review"] = MasteryState(sbr) if sbr else None
        lea = d.get("last_evidence_at")
        d["last_evidence_at"] = datetime.fromisoformat(lea) if lea else None
        d["updated_at"] = datetime.fromisoformat(d["updated_at"])
        return cls(**d)


@dataclass
class AuditEntry:
    """An auditable event behind a judgment: teacher overrides, teacher notes,
    automatic transitions, and stale-evidence review flags."""

    student_id: str
    skill_id: str
    kind: AuditKind
    from_state: MasteryState | None
    to_state: MasteryState | None
    note: str = ""
    at: datetime = field(default_factory=_utcnow)
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["from_state"] = self.from_state.value if self.from_state else None
        d["to_state"] = self.to_state.value if self.to_state else None
        d["at"] = self.at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        d = dict(data)
        d["kind"] = AuditKind(d["kind"])
        d["from_state"] = MasteryState(d["from_state"]) if d.get("from_state") else None
        d["to_state"] = MasteryState(d["to_state"]) if d.get("to_state") else None
        d["at"] = datetime.fromisoformat(d["at"])
        return cls(**d)
