"""Core data structures for the homework ingestion + OCR pipeline.

These structures are the contract between pipeline stages:
segmentation -> matching -> recognition -> manual entry -> diagnosis.

Downstream stages (diagnosis, assembly) consume ``AnswerRecord`` via
``to_dict()`` / ``AnswerRecord.from_dict()``; the dict format is
documented in ``manual_entry.py`` and ``README.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class QuestionKind(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"
    SUB_QUESTIONS = "sub_questions"  # e.g. Q11/Q12 with separately recorded parts


class GradingMarkKind(str, Enum):
    """Teacher grading marks （批改痕迹）."""
    CORRECT = "correct"      # √
    WRONG = "wrong"          # ×
    SCORE = "score"          # numeric score, e.g. "8/10"
    COMMENT = "comment"      # free-text teacher comment
    UNKNOWN = "unknown"


@dataclass
class Region:
    """Normalized bounding region inside a page (0.0 - 1.0 coordinates)."""
    x: float
    y: float
    w: float
    h: float

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class SubQuestionRef:
    """Declarative reference to one recordable unit: question + optional part.

    Examples: Q1 (multiple-choice), Q5 blank 2, Q11 part 'a', Q12 blank 3.
    """
    question_id: str
    part_id: Optional[str]  # None for whole-question items
    kind: QuestionKind
    region: Region

    @property
    def item_key(self) -> str:
        return f"{self.question_id}#{self.part_id}" if self.part_id else self.question_id

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["item_key"] = self.item_key
        return d


@dataclass
class QuestionSpec:
    id: str
    kind: QuestionKind
    parts: List[str] = field(default_factory=list)  # e.g. ["a","b","c"] or ["blank1","blank2"]
    regions: Dict[str, Region] = field(default_factory=dict)  # part_id -> region; whole question under ""


@dataclass
class AssignmentTemplate:
    """Declarative layout of one generated assignment.

    Segmentation is driven by this template: no ML needed to find where
    each sub-question lives on the page.
    """
    assignment_number: str
    title: str
    questions: List[QuestionSpec] = field(default_factory=list)
    id_region: Optional[Region] = None  # where the printed student ID + assignment number sit
    id_region_page: int = 0


@dataclass
class UploadedFile:
    path: str
    media_type: str  # "photo" | "pdf_scan"
    page_count: int = 1


@dataclass
class Upload:
    upload_id: str
    files: List[UploadedFile]
    uploaded_by: str
    assignment_number: Optional[str] = None  # teacher-declared, may be absent


@dataclass
class Page:
    upload_id: str
    file_path: str
    page_index: int  # 0-based within the whole upload
    page_no_in_file: int = 0
    image_ref: Optional[str] = None  # path to the page image when extracted from PDF


@dataclass
class SegmentedItem:
    page: Page
    sub_question: SubQuestionRef


@dataclass
class MatchResult:
    """Outcome of student identification for one page."""
    page: Page
    student_id: Optional[str]
    assignment_number: Optional[str]
    confidence: float  # 0.0 - 1.0
    linked: bool  # False => routed to the teacher confirmation queue
    note: str = ""


@dataclass
class Recognition:
    """One recognized item: student handwriting or a teacher grading mark."""
    item_key: str
    item_type: str  # "handwriting" | "grading_mark"
    text: Optional[str] = None
    mark: Optional[GradingMarkKind] = None
    score: Optional[str] = None
    reliability: float = 0.0  # 0.0 - 1.0


@dataclass
class GradingMark:
    kind: GradingMarkKind
    score: Optional[str] = None
    comment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind.value, "score": self.score, "comment": self.comment}


@dataclass
class AnswerRecord:
    """The downstream record format consumed by diagnosis/assembly.

    Dict schema (stable contract):
        {
          "student_id": str, "assignment_number": str,
          "question_id": str, "part_id": str | None, "item_key": str,
          "student_answer": str | None,
          "grading_mark": {"kind": str, "score": str | None, "comment": str | None} | None,
          "source": "ocr" | "manual",
          "reliability": float,          # 1.0 for manual entry (human-verified)
          "page_ref": str | None,        # file_path + page index for traceability
        }
    """
    student_id: str
    assignment_number: str
    question_id: str
    part_id: Optional[str]
    item_key: str
    student_answer: Optional[str]
    grading_mark: Optional[GradingMark]
    source: str  # "ocr" | "manual"
    reliability: float
    page_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["grading_mark"] = self.grading_mark.to_dict() if self.grading_mark else None
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnswerRecord":
        gm = d.get("grading_mark")
        return cls(
            student_id=d["student_id"],
            assignment_number=d["assignment_number"],
            question_id=d["question_id"],
            part_id=d.get("part_id"),
            item_key=d["item_key"],
            student_answer=d.get("student_answer"),
            grading_mark=GradingMark(
                kind=GradingMarkKind(gm["kind"]), score=gm.get("score"), comment=gm.get("comment")
            ) if gm else None,
            source=d["source"],
            reliability=d["reliability"],
            page_ref=d.get("page_ref"),
        )
