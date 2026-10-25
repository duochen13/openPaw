"""Data model for the student-side grading pipeline (issue #176).

``ItemResult`` mirrors ``webui.models.QuestionResult`` field-for-field
(number, question_text, student_answer, verdict, source,
proposed_verdict, reference_answer, ocr_reliability, image_location,
page_label) so pipeline output can render in the student web UI via
:mod:`grading.adapter`. Pipeline-only fields are additive: the item key,
the model-proposed knowledge-point tag (unconfirmed by design), the
pending reason for 待确认 items, the red-pen mark kind observed on the
paper, and the student-confirmation state.

Deliberate deviations from the webui demo model, both in the direction
of honesty:

* ``proposed_verdict`` may be empty on a 待确认 item. The demo fixtures
  only contain pending items where a source produced a lean; a real
  pipeline also meets items where *no* source can lean (an unreadable
  answer, a partially-credited process question). Inventing a lean for
  those would be a soft guess, so the pipeline records the pending
  reason instead. :mod:`grading.adapter` fails loudly on such items
  rather than fabricating a proposal for the demo UI.
* ``VERDICT_SOURCES`` adds 学生确认: after a student confirms or
  corrects an item in the confirmation queue, the deciding source is
  the student. The webui demo renders the pre-confirmation state, whose
  three sources are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The verdict vocabulary -- exactly these three strings (mirrors webui).
VERDICTS = ("对", "错", "待确认")

#: Verdict sources in judge-priority order, plus the post-confirmation
#: source. The first three mirror ``webui.VERDICT_SOURCES``.
VERDICT_SOURCES = ("红笔标记", "答案比对", "模型判定", "学生确认")

#: Pending reasons for 待确认 items (code -> student-facing label).
#: A 待确认 verdict without one of these is a model error.
REASON_UNREADABLE = "unreadable"
REASON_PARTIAL_CREDIT = "partial_credit"
REASON_OPEN_TYPE = "open_type"
REASON_UNCERTAIN = "judgment_uncertain"
PENDING_REASONS = {
    REASON_UNREADABLE: "无法识别（字迹/扫描不可读）",
    REASON_PARTIAL_CREDIT: "部分分（步骤分），需确认",
    REASON_OPEN_TYPE: "开放题/过程题，v1 不自动判定",
    REASON_UNCERTAIN: "判定不确定，需确认",
}

#: Recognition-reliability threshold, mirroring webui/ingestion: at or
#: above it a transcription is "reliable"; below it the *transcription*
#: (never the verdict) is routed to the confirmation queue.
RELIABILITY_THRESHOLD = 0.8


def reliability_tier(value: float) -> str:
    """Legibility tier for a recognition reliability score (mirrors webui)."""
    if value >= RELIABILITY_THRESHOLD:
        return "reliable"
    if value >= 0.5:
        return "doubtful"
    return "manual"


@dataclass(frozen=True)
class ItemResult:
    """One recordable unit: a whole question or one part/blank of it.

    Mirrors ingestion's recordable unit (``item_key`` like ``Q3#b``):
    parts and blanks are judged and recorded separately.
    """

    item_key: str                          # e.g. "Q3#b"; "Q1" when whole
    question_id: str                       # e.g. "Q3"
    part_id: str = ""                      # e.g. "b"; "" for whole question
    number: int = 0                        # 1-based row number within the paper
    question_text: str = ""
    student_answer: str = ""               # transcription; "" when unreadable
    verdict: str = "待确认"
    source: str = "模型判定"
    proposed_verdict: str = ""             # lean for 待确认 items; "" = no lean
    proposal_source: str = ""              # which source produced the lean
    reference_answer: str = ""             # required when verdict == 错
    ocr_reliability: float = 0.0           # legibility only; never the verdict
    image_location: str = ""               # page image + crop region reference
    page_label: str = ""                   # e.g. "第 1 页"
    knowledge_point_tag: str = ""          # model-proposed, UNCONFIRMED
    skill_ids: tuple[str, ...] = ()
    pending_reason: str = ""               # key of PENDING_REASONS
    mark_kind: str = ""                    # red-pen mark seen: correct/wrong/score/comment
    needs_transcription_confirmation: bool = False
    confirmed: bool = False
    confirmed_verdict: str = ""
    # Pre-confirmation system output, captured at confirmation time so
    # the labeled export keeps the (system output, student label) pair.
    system_verdict: str = ""
    system_source: str = ""
    system_proposed_verdict: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}: {self.verdict!r}")
        if self.source not in VERDICT_SOURCES:
            raise ValueError(
                f"source must be one of {VERDICT_SOURCES}: {self.source!r}"
            )
        if not 0.0 <= self.ocr_reliability <= 1.0:
            raise ValueError(
                f"ocr_reliability out of range: {self.ocr_reliability}"
            )
        if self.verdict == "错" and not self.reference_answer:
            raise ValueError("verdict 错 requires reference_answer")
        if self.verdict == "待确认":
            if self.pending_reason not in PENDING_REASONS:
                raise ValueError(
                    "待确认 requires a pending_reason in "
                    f"{tuple(PENDING_REASONS)}: {self.pending_reason!r}"
                )
            if self.proposed_verdict not in ("", "对", "错"):
                raise ValueError(
                    f"proposed_verdict must be 对/错 or empty: {self.proposed_verdict!r}"
                )
            if self.proposed_verdict and self.proposal_source not in VERDICT_SOURCES[:3]:
                raise ValueError(
                    "a proposed verdict must name its source "
                    f"(one of {VERDICT_SOURCES[:3]}): {self.proposal_source!r}"
                )
        else:
            if self.pending_reason:
                raise ValueError("a decided verdict must not carry a pending_reason")
            if self.proposed_verdict:
                raise ValueError("a decided verdict must not carry a proposed_verdict")
        if self.confirmed and self.confirmed_verdict not in ("对", "错"):
            raise ValueError("a confirmed item must record its confirmed verdict")

    @property
    def is_low_reliability(self) -> bool:
        """True when the transcription itself needs a second look."""
        return reliability_tier(self.ocr_reliability) != "reliable"

    @property
    def in_confirmation_queue(self) -> bool:
        """Queued when the verdict is pending OR the read is unreliable."""
        return self.verdict == "待确认" or self.needs_transcription_confirmation


@dataclass(frozen=True)
class GradedPaper:
    """One student's graded paper: ID only, never a name (privacy rule)."""

    student_id: str                        # e.g. "S-001"; IDs only, no names
    assignment_id: str = ""
    title: str = ""
    date_label: str = ""
    status: str = "已出结果"
    items: tuple[ItemResult, ...] = field(default_factory=tuple)

    def pending(self) -> tuple[ItemResult, ...]:
        return tuple(i for i in self.items if i.verdict == "待确认")

    def confirmation_queue(self) -> tuple[ItemResult, ...]:
        return tuple(i for i in self.items if i.in_confirmation_queue)

    def decided(self) -> tuple[ItemResult, ...]:
        return tuple(i for i in self.items if i.verdict in ("对", "错"))
