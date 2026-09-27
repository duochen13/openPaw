"""Shared synthetic fixtures: assignment template, uploads, ID readers, labels.

Everything here is synthetic (students S001-S010, assignment A-CH3-01)
and exists so the pipeline can be built, tested, and validated
end-to-end before the 5 real sample papers from #108 land.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from matching import IDReader
from models import (AssignmentTemplate, GradingMarkKind, Page, QuestionKind,
                    QuestionSpec, Region, Upload, UploadedFile)


def make_sample_template() -> AssignmentTemplate:
    """Chapter 3 《能量的转化与守恒》 sample: MC, multi-blank fill-in,
    Q11 sub-questions and Q12 separately-recorded blanks."""
    R = Region
    return AssignmentTemplate(
        assignment_number="A-CH3-01",
        title="浙教版科学九年级上册 第三章 能量的转化与守恒",
        id_region=R(x=0.02, y=0.02, w=0.35, h=0.08),
        questions=[
            QuestionSpec(id="Q1", kind=QuestionKind.MULTIPLE_CHOICE,
                         regions={"": R(0.05, 0.12, 0.9, 0.10)}),
            QuestionSpec(id="Q2", kind=QuestionKind.MULTIPLE_CHOICE,
                         regions={"": R(0.05, 0.24, 0.9, 0.10)}),
            QuestionSpec(id="Q5", kind=QuestionKind.FILL_BLANK,
                         parts=["blank1", "blank2"],
                         regions={"blank1": R(0.05, 0.40, 0.42, 0.06),
                                  "blank2": R(0.52, 0.40, 0.42, 0.06)}),
            QuestionSpec(id="Q11", kind=QuestionKind.SUB_QUESTIONS,
                         parts=["a", "b", "c"],
                         regions={"a": R(0.05, 0.52, 0.9, 0.08),
                                  "b": R(0.05, 0.62, 0.9, 0.08),
                                  "c": R(0.05, 0.72, 0.9, 0.08)}),
            QuestionSpec(id="Q12", kind=QuestionKind.SUB_QUESTIONS,
                         parts=["blank1", "blank2", "blank3"],
                         regions={"blank1": R(0.05, 0.84, 0.28, 0.06),
                                  "blank2": R(0.37, 0.84, 0.28, 0.06),
                                  "blank3": R(0.69, 0.84, 0.28, 0.06)}),
        ],
    )


def known_students() -> List[str]:
    return [f"S{i:03d}" for i in range(1, 11)]  # S001..S010


def make_upload(upload_id: str = "UP-001", n_pages: int = 2,
                media: str = "photo") -> Upload:
    return Upload(
        upload_id=upload_id,
        files=[UploadedFile(path=f"/tmp/{upload_id}/scan.jpg",
                            media_type=media, page_count=n_pages)],
        uploaded_by="teacher",
        assignment_number="A-CH3-01",
    )


class ScriptedIDReader(IDReader):
    """Deterministic ID reader: page_index -> (student_id, assignment_no, confidence)."""

    def __init__(self, script: Dict[int, Tuple[Optional[str], Optional[str], float]]) -> None:
        self.script = script

    def read_id(self, page: Page) -> Tuple[Optional[str], Optional[str], float]:
        return self.script.get(page.page_index, (None, None, 0.0))


def clean_id_reader() -> ScriptedIDReader:
    return ScriptedIDReader({
        0: ("S001", "A-CH3-01", 0.99),
        1: ("S002", "A-CH3-01", 0.97),
    })


def ambiguous_id_reader() -> ScriptedIDReader:
    """Page 0: one-char typo in the ID ('S01X' ~ S010/S001) -> queue with candidates.
    Page 1: blank/unreadable ID -> queue without candidates."""
    return ScriptedIDReader({
        0: ("S01X", "A-CH3-01", 0.62),
        1: (None, "A-CH3-01", 0.0),
    })


def recognizer_script() -> Dict:
    """Scripted (item_key, item_type) -> recognition for the eval fixture."""
    from recognizer import GRADING_MARK, HANDWRITING
    return {
        ("Q1", HANDWRITING): {"text": "B", "reliability": 0.99},
        ("Q1", GRADING_MARK): {"mark": "correct", "reliability": 0.98},
        ("Q2", HANDWRITING): {"text": "C", "reliability": 0.96},
        # deliberate miss: reads √ as "correct" with HIGH reliability (0.93)
        # while the truth is × "wrong" — a silent error the eval must catch
        ("Q2", GRADING_MARK): {"mark": "correct", "reliability": 0.93},
        ("Q11#a", HANDWRITING): {"text": "做功", "reliability": 0.72},   # below threshold
        ("Q11#a", GRADING_MARK): {"mark": "score", "score": "3/5", "reliability": 0.88},
        ("Q11#b", HANDWRITING): {"text": "动能最大", "reliability": 0.91},
        ("Q11#b", GRADING_MARK): {"mark": "comment", "text": "思路对，单位错",
                                  "reliability": 0.55},                 # below threshold
    }


def labeled_set(template: AssignmentTemplate, items) -> List:
    """Ground truth matching recognizer_script(): 8 items, one deliberate miss."""
    from evaluate import LabeledItem
    from recognizer import GRADING_MARK, HANDWRITING
    by_key = {it.sub_question.item_key: it for it in items}
    # One deliberate miss: Q2's grading mark is scripted as "correct" @0.93
    # reliability but the ground truth is "wrong" — it must show up as an
    # error with reliability >= threshold (a would-be silent slip-through).
    expect = {
        ("Q1", HANDWRITING): dict(expected_text="B"),
        ("Q1", GRADING_MARK): dict(expected_mark=GradingMarkKind.CORRECT),
        ("Q2", HANDWRITING): dict(expected_text="C"),
        ("Q2", GRADING_MARK): dict(expected_mark=GradingMarkKind.WRONG),
        ("Q11#a", HANDWRITING): dict(expected_text="做功"),
        ("Q11#a", GRADING_MARK): dict(expected_mark=GradingMarkKind.SCORE,
                                      expected_score="3/5"),
        ("Q11#b", HANDWRITING): dict(expected_text="动能最大"),
        ("Q11#b", GRADING_MARK): dict(expected_mark=GradingMarkKind.COMMENT),
    }
    labels = []
    for (key, itype), kw in expect.items():
        labels.append(LabeledItem(item=by_key[key], item_type=itype, **kw))
    return labels


def manual_entry_rows() -> List[Dict]:
    """Scripted teacher entry rows for one student (Q1..Q12 sample)."""
    return [
        {"question_id": "Q1", "student_answer": "B", "mark_kind": "correct"},
        {"question_id": "Q2", "student_answer": "D", "mark_kind": "wrong"},
        {"question_id": "Q5", "part_id": "blank1", "student_answer": "W=Fs",
         "mark_kind": "correct"},
        {"question_id": "Q5", "part_id": "blank2", "student_answer": "50J",
         "mark_kind": "score", "mark_score": "1/2"},
        {"question_id": "Q11", "part_id": "a", "student_answer": "重力做功",
         "mark_kind": "correct"},
        {"question_id": "Q11", "part_id": "b", "student_answer": "最高点动能为零",
         "mark_kind": "comment", "mark_comment": "需说明原因"},
        {"question_id": "Q11", "part_id": "c", "student_answer": "功率增大",
         "mark_kind": "wrong"},
        {"question_id": "Q12", "part_id": "blank1", "student_answer": "弹性势能"},
        {"question_id": "Q12", "part_id": "blank2", "student_answer": "减小"},
        {"question_id": "Q12", "part_id": "blank3", "student_answer": "增大",
         "mark_kind": "correct"},
    ]
