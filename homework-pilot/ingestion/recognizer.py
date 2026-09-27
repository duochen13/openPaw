"""Answer/grading-mark recognition with per-item reliability and threshold routing.

Each sub-question region holds two things to read: the student's
handwriting answer and the teacher's grading marks （批改痕迹：
√/×/scores/comments). The recognizer is therefore called per
(item, item_type), returning one ``Recognition`` with a reliability
score in [0, 1].

- ``Recognizer`` is the pluggable interface: real OCR models implement it.
- ``TestDoubleRecognizer`` is the deterministic stand-in used for tests,
  eval harness development, and end-to-end pipeline validation without
  waiting on a trained OCR model.
- ``route_by_reliability`` splits recognitions into accepted items and
  teacher-review items (reliability < threshold -> review queue).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from models import GradingMarkKind, Recognition, SegmentedItem

HANDWRITING = "handwriting"
GRADING_MARK = "grading_mark"
ITEM_TYPES = (HANDWRITING, GRADING_MARK)


class Recognizer(ABC):
    """Returns one recognition per (item, item_type) with a reliability score."""

    @abstractmethod
    def recognize(self, item: SegmentedItem, item_type: str) -> Recognition:
        ...


class TestDoubleRecognizer(Recognizer):
    """Deterministic recognizer driven by a scripted lookup table.

    ``script`` maps (item_key, item_type) or item_key -> dict with keys:
    text, mark, score, reliability. Anything not in the script returns an
    'unknown' reading with reliability 0.0, which routes it to review.
    """

    def __init__(self, script: Optional[Dict] = None,
                 default_reliability: float = 0.0) -> None:
        self.script = script or {}
        self.default_reliability = default_reliability

    def _entry(self, key: str, item_type: str) -> Optional[Dict]:
        return self.script.get((key, item_type), self.script.get(key))

    def recognize(self, item: SegmentedItem, item_type: str) -> Recognition:
        key = item.sub_question.item_key
        entry = self._entry(key, item_type)
        if entry is None:
            return Recognition(item_key=key, item_type=item_type,
                               text=None, mark=GradingMarkKind.UNKNOWN,
                               reliability=self.default_reliability)
        mark = entry.get("mark")
        return Recognition(
            item_key=key,
            item_type=item_type,
            text=entry.get("text"),
            mark=GradingMarkKind(mark) if mark else None,
            score=entry.get("score"),
            reliability=float(entry.get("reliability", self.default_reliability)),
        )


@dataclass
class ReviewItem:
    item: SegmentedItem
    item_type: str
    recognition: Recognition
    reason: str


def recognize_all(items: List[SegmentedItem], recognizer: Recognizer,
                  threshold: float = 0.8) -> Tuple[List[Tuple[SegmentedItem, str, Recognition]],
                                                   List[ReviewItem]]:
    """Recognize both item types per sub-question and route by reliability.

    Items with reliability < threshold go to the review queue so the
    errors that matter get human eyes; nothing below threshold is
    silently accepted.
    """
    accepted: List[Tuple[SegmentedItem, str, Recognition]] = []
    review: List[ReviewItem] = []
    for item in items:
        for item_type in ITEM_TYPES:
            rec = recognizer.recognize(item, item_type)
            if rec.reliability >= threshold:
                accepted.append((item, item_type, rec))
            else:
                review.append(ReviewItem(
                    item=item, item_type=item_type, recognition=rec,
                    reason=(f"reliability {rec.reliability:.2f} below threshold "
                            f"{threshold:.2f}"),
                ))
    return accepted, review


def recognitions_to_records(triples: List[Tuple[SegmentedItem, str, Recognition]],
                            student_id: str, assignment_number: str):
    """Convert accepted recognitions into AnswerRecords (source='ocr').

    Handwriting and grading-mark recognitions for the same sub-question
    are merged into a single AnswerRecord per item_key.
    """
    from models import AnswerRecord, GradingMark
    merged: Dict[str, Dict] = {}
    for item, item_type, rec in triples:
        sq = item.sub_question
        m = merged.setdefault(rec.item_key, {
            "question_id": sq.question_id, "part_id": sq.part_id,
            "page": item.page, "reliability": 1.0,
            "answer": None, "mark": None,
        })
        m["reliability"] = min(m["reliability"], rec.reliability)
        if item_type == HANDWRITING:
            m["answer"] = rec.text
        else:
            m["mark"] = (GradingMark(kind=rec.mark, score=rec.score, comment=rec.text)
                         if rec.mark and rec.mark is not GradingMarkKind.UNKNOWN else None)
    records = []
    for item_key, m in merged.items():
        records.append(AnswerRecord(
            student_id=student_id,
            assignment_number=assignment_number,
            question_id=m["question_id"],
            part_id=m["part_id"],
            item_key=item_key,
            student_answer=m["answer"],
            grading_mark=m["mark"],
            source="ocr",
            reliability=m["reliability"],
            page_ref=f"{m['page'].file_path}#page{m['page'].page_no_in_file}",
        ))
    return records
