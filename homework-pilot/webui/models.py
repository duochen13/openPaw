"""View models for the student-side MVP UI (issue #176).

The product pivoted: homework-pilot now starts from the *student* side.
A student uploads a scanned PDF of a paper they have already completed;
the system segments the paper into questions, transcribes the student's
handwritten answers, and returns one verdict per question. These
dataclasses are the *view* shapes for that flow, following the repo's
per-package pattern (mirror upstream shapes, never import them):

* :class:`QuestionResult` mirrors one row of the ingestion pipeline's
  output for one question: the question crop location, the transcribed
  student answer, the ingestion ``ocr_reliability`` for that read, and
  the correctness verdict with the source it came from.
* :class:`PaperResult` is one uploaded paper and its questions.
* :class:`StudentData` is the whole demo: one student, their papers.

Verdict sources, in the priority order fixed by issue #176 -- the
system tries them in this order and never blends them silently:

1. ``红笔标记`` -- the teacher's red-pen marks already on the paper.
2. ``答案比对`` -- comparison against an answer key, when one exists.
3. ``模型判定`` -- the model solves the question itself and compares
   (only meaningful for questions with a determinate answer).

Binding rules, enforced by the tests in ``webui/tests``:

* Students are identified by ID only (``S-023``). There is no name
  field anywhere in this module, and there must never be one.
* The verdict vocabulary is exactly :data:`VERDICTS`
  （对 / 错 / 待确认）. There is deliberately no skill-state or mastery
  field: the five teaching judgments belong to the teacher-side design
  and do not exist on the student surface.
* OCR reliability (how well the system *read* the handwriting) and the
  correctness verdict (whether the answer is *right*) are separate
  uncertainties and are modeled -- and rendered -- separately. A low
  reliability read never changes a verdict; it routes the question to
  the confirmation queue instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: The whole verdict vocabulary of the student MVP (issue #176).
VERDICTS = ("对", "错", "待确认")

#: Verdict sources, in priority order (issue #176).
VERDICT_SOURCES = ("红笔标记", "答案比对", "模型判定")

#: Paper processing states shown in the paper list.
PAPER_STATUSES = ("已出结果", "处理中")


class ReliabilityTier(str, Enum):
    """How much the student can trust one OCR read.

    Bands follow the ingestion pipeline's own numbers
    (``ingestion.pipeline`` routes reads below its 0.8 recognition
    threshold to review; ``ingestion.evaluate`` buckets reliability at
    0.5 / 0.8 / 0.95). This is a property of the *reading*, never of
    the answer's correctness.
    """

    RELIABLE = "reliable"    # 可靠： read at/above the pipeline threshold
    DOUBTFUL = "doubtful"    # 存疑： read, but below threshold -- eyeball it
    MANUAL = "manual"        # 需手录： effectively unread


def reliability_tier(ocr_reliability: float) -> ReliabilityTier:
    """Bucket a raw OCR reliability score into its display tier."""
    if not 0.0 <= ocr_reliability <= 1.0:
        raise ValueError("ocr_reliability must be between 0.0 and 1.0")
    if ocr_reliability >= 0.8:
        return ReliabilityTier.RELIABLE
    if ocr_reliability >= 0.5:
        return ReliabilityTier.DOUBTFUL
    return ReliabilityTier.MANUAL


def is_low_reliability(ocr_reliability: float) -> bool:
    """True when a read fell below the pipeline's 0.8 threshold."""
    return reliability_tier(ocr_reliability) is not ReliabilityTier.RELIABLE


@dataclass
class QuestionResult:
    """One question of an uploaded paper, with its verdict.

    ``verdict`` is the system's current answer to "did the student get
    this right". ``待确认`` questions carry a ``proposed_verdict``
    （对 / 错）: the judgment the student is being asked to confirm or
    flip in the confirmation queue. ``reference_answer`` （参考答案） is
    shown for questions judged 错， so the student can see what the
    right answer was.
    """

    number: int                            # 题号， 1-based
    question_text: str                     # transcribed printed question
    student_answer: str = ""               # transcribed handwritten answer
    verdict: str = "待确认"
    source: str = "模型判定"
    proposed_verdict: str = ""             # required when verdict == 待确认
    reference_answer: str = ""             # required when verdict == 错
    ocr_reliability: float = 0.0
    image_location: str = ""               # crop location, e.g. "scan/p01.png"
    page_label: str = ""                   # e.g. "第 1 页"

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("question number is 1-based")
        if self.verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}: {self.verdict!r}")
        if self.source not in VERDICT_SOURCES:
            raise ValueError(
                f"source must be one of {VERDICT_SOURCES}: {self.source!r}")
        if self.verdict == "待确认" and self.proposed_verdict not in ("对", "错"):
            raise ValueError("待确认 questions need a proposed verdict （对/错）")
        if self.verdict == "错" and not self.reference_answer:
            raise ValueError("错 questions need a 参考答案 to show the student")
        reliability_tier(self.ocr_reliability)  # validates the range

    @property
    def label(self) -> str:
        return f"第{self.number}题"

    @property
    def tier(self) -> ReliabilityTier:
        return reliability_tier(self.ocr_reliability)

    @property
    def low_reliability(self) -> bool:
        return is_low_reliability(self.ocr_reliability)


@dataclass
class PaperResult:
    """One uploaded paper and (once processed) its per-question results."""

    id: str                                # stable DOM key, e.g. "paper-ch3"
    title: str
    date_label: str = ""                   # e.g. "10月24日"
    status: str = "已出结果"
    questions: list[QuestionResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("paper id is required")
        if self.status not in PAPER_STATUSES:
            raise ValueError(f"status must be one of {PAPER_STATUSES}")
        if self.status == "处理中" and self.questions:
            raise ValueError("a 处理中 paper has no question results yet")

    def verdict_counts(self) -> dict[str, int]:
        counts = {v: 0 for v in VERDICTS}
        for q in self.questions:
            counts[q.verdict] += 1
        return counts

    def pending(self) -> list[QuestionResult]:
        """Questions awaiting the student's confirmation, in order."""
        return [q for q in self.questions if q.verdict == "待确认"]


@dataclass
class StudentData:
    """The whole student-side demo: one student and their papers."""

    student_id: str                        # ID only, e.g. "S-023"
    student_context: str = ""              # e.g. "科学 · 九年级上册"
    papers: list[PaperResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.student_id:
            raise ValueError("student_id is required (students are ID-only)")

    def pending_items(self) -> list[tuple[PaperResult, QuestionResult]]:
        """Every 待确认 question across papers, paper order preserved."""
        return [
            (paper, q)
            for paper in self.papers
            for q in paper.pending()
        ]
