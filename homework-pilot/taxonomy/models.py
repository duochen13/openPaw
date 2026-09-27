"""Input records and weak-point proposals for #112.

``EvidenceInput`` deliberately mirrors the shape of
``evidence.models.EvidenceRecord`` (issue #109) but does NOT import it, so
this package stays self-contained until #109 merges. The intended wiring is
``EvidenceInput.from_dict(record.to_dict())`` — field names match exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Grading outcomes, mirroring evidence.models.GradingResult values.
RESULT_CORRECT = "正确"
RESULT_INCORRECT = "错误"
RESULT_PARTIAL = "部分正确"
RESULT_UNREADABLE = "无法辨认"

#: Grading results that carry a mastery signal. UNREADABLE ("we could not read
#: the handwriting") is stored but never drives a weak-point hypothesis.
READABLE_RESULTS = frozenset({RESULT_CORRECT, RESULT_INCORRECT, RESULT_PARTIAL})


@dataclass
class EvidenceInput:
    """Lightweight mirror of evidence.EvidenceRecord (#109), used as input to
    ``propose_weak_points``. Students are identified by ID only."""

    student_id: str
    skill_id: str
    grading_result: str = RESULT_UNREADABLE  # 正确 / 错误 / 部分正确 / 无法辨认
    question_id: str = ""
    sub_question: str = ""
    ocr_reliability: float = 1.0  # how well the answer could be read, 0..1
    hint_used: bool = False
    independently_completed: bool = True
    correction_of: str = ""  # record_id this is a correction (订正） of, else ""
    context: str = ""  # e.g. "ch3-hw-05" vs "ch3-quiz-1"
    observed_at: datetime = field(default_factory=_utcnow)
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.student_id:
            raise ValueError("student_id is required (students are identified by ID only)")
        if not 0.0 <= self.ocr_reliability <= 1.0:
            raise ValueError("ocr_reliability must be between 0.0 and 1.0")

    def readable(self) -> bool:
        """Whether this record carries any mastery signal."""
        return self.grading_result in READABLE_RESULTS

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceInput":
        """Build from a mapping with the evidence.EvidenceRecord (#109) field
        names — the intended adapter for the #109 wiring. Extra keys are
        ignored; missing keys fall back to defaults."""
        d = dict(data)
        observed = d.get("observed_at")
        if isinstance(observed, str):
            d["observed_at"] = datetime.fromisoformat(observed)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


class ProposalStatus(str, Enum):
    """Lifecycle of a weak-point proposal (薄弱点）. Every proposal starts at
    PROPOSED and must be moved by the teacher — the system never promotes a
    proposal to a verdict by itself."""

    PROPOSED = "proposed"      # system hypothesis, awaiting teacher
    CONFIRMED = "confirmed"    # teacher confirmed the weak point
    MODIFIED = "modified"      # teacher changed it (e.g. redirected skill)
    REJECTED = "rejected"      # teacher rejected the hypothesis


@dataclass
class AuditEntry:
    """One auditable teacher action on a proposal: who did what, when, why."""

    kind: str  # "auto_proposed" | "teacher_confirm" | "teacher_modify" | "teacher_reject"
    from_status: ProposalStatus | None
    to_status: ProposalStatus | None
    note: str = ""
    at: datetime = field(default_factory=_utcnow)
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class WeakPointProposal:
    """A proposed weak point （薄弱点） for one student x one skill.

    A proposal is a *hypothesis* (假设）, never a verdict: ``is_provisional``
    stays True until the teacher confirms, modifies, or rejects it, and every
    teacher action is appended to ``audit``.
    """

    student_id: str
    skill_id: str
    status: ProposalStatus = ProposalStatus.PROPOSED
    is_provisional: bool = True
    hypothesis_strength: str = "single_error"  # single_error | repeated_errors | partial_credit
    basis_record_ids: list[str] = field(default_factory=list)
    basis_note: str = ""  # human-readable reason, shown to the teacher
    modified_skill_id: str = ""  # set by the teacher when redirecting the weak point
    audit: list[AuditEntry] = field(default_factory=list)
    proposal_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    # -- teacher workflow ---------------------------------------------------
    def confirm(self, note: str = "") -> None:
        """The teacher confirms the weak point. Recorded and auditable."""
        self._transition(ProposalStatus.CONFIRMED, "teacher_confirm", note)

    def modify(self, note: str = "", new_skill_id: str = "") -> None:
        """The teacher modifies the proposal (optionally redirecting the skill)."""
        if new_skill_id:
            self.modified_skill_id = new_skill_id
        self._transition(ProposalStatus.MODIFIED, "teacher_modify", note)

    def reject(self, note: str = "") -> None:
        """The teacher rejects the hypothesis. Recorded and auditable."""
        self._transition(ProposalStatus.REJECTED, "teacher_reject", note)

    def _transition(self, to: ProposalStatus, kind: str, note: str) -> None:
        # Judgments are revisable, never fixed labels: a teacher may change
        # their mind, and every move is appended to the audit trail.
        self.audit.append(
            AuditEntry(kind=kind, from_status=self.status, to_status=to, note=note)
        )
        self.status = to
        self.is_provisional = False
