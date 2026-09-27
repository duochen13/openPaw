"""Human-in-the-loop manual-entry fallback (issue #111's priority).

The pilot does NOT wait for full auto-OCR. A teacher/assistant types or
corrects per-sub-question student answers + grading marks （批改痕迹：
√/×/score/comment), and this module turns that input into ``AnswerRecord``
objects in the documented downstream format (source="manual",
reliability=1.0 — human-verified), so diagnosis -> assembly -> print can
be validated end-to-end while OCR accuracy is being measured.

Three ways to feed entries:
1. Programmatic API: ``ManualEntrySession`` (validate as you go).
2. Scripted rows: ``entries_from_rows(rows)`` for CSV/JSONL-style dicts.
3. Interactive CLI: ``run_interactive_cli(...)`` prompts per sub-question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from models import AnswerRecord, AssignmentTemplate, GradingMark, GradingMarkKind, QuestionKind


@dataclass
class ManualEntry:
    question_id: str
    part_id: Optional[str]
    student_answer: Optional[str] = None
    mark_kind: GradingMarkKind = GradingMarkKind.UNKNOWN
    mark_score: Optional[str] = None
    mark_comment: Optional[str] = None

    @property
    def item_key(self) -> str:
        return f"{self.question_id}#{self.part_id}" if self.part_id else self.question_id


class ManualEntrySession:
    """Collects entries for one (student, assignment) pair, then commits."""

    def __init__(self, student_id: str, assignment_number: str,
                 template: Optional[AssignmentTemplate] = None) -> None:
        self.student_id = student_id
        self.assignment_number = assignment_number
        self.template = template
        self.entries: List[ManualEntry] = []
        self._valid_keys = self._template_keys(template)

    @staticmethod
    def _template_keys(template: Optional[AssignmentTemplate]) -> Optional[set]:
        if template is None:
            return None
        keys = set()
        for q in template.questions:
            if q.kind in (QuestionKind.SUB_QUESTIONS, QuestionKind.FILL_BLANK) and q.parts:
                keys.update(f"{q.id}#{p}" for p in q.parts)
            else:
                keys.add(q.id)
        return keys

    def add(self, entry: ManualEntry) -> None:
        """Add one sub-question entry; validates against the template when given."""
        if self._valid_keys is not None and entry.item_key not in self._valid_keys:
            raise ValueError(
                f"item_key '{entry.item_key}' is not in assignment "
                f"'{self.assignment_number}' (expected one of {sorted(self._valid_keys)})")
        self.entries.append(entry)

    def commit(self, page_ref: Optional[str] = None) -> List[AnswerRecord]:
        """Produce the downstream record list (source='manual', reliability=1.0)."""
        records = []
        for e in self.entries:
            mark = None
            if e.mark_kind is not GradingMarkKind.UNKNOWN:
                mark = GradingMark(kind=e.mark_kind, score=e.mark_score,
                                   comment=e.mark_comment)
            records.append(AnswerRecord(
                student_id=self.student_id,
                assignment_number=self.assignment_number,
                question_id=e.question_id,
                part_id=e.part_id,
                item_key=e.item_key,
                student_answer=e.student_answer,
                grading_mark=mark,
                source="manual",
                reliability=1.0,
                page_ref=page_ref,
            ))
        return records


def entries_from_rows(rows: Iterable[Dict]) -> List[ManualEntry]:
    """Build entries from scripted dicts, e.g. loaded from CSV/JSONL.

    Row schema:
        {"question_id": "Q11", "part_id": "a", "student_answer": "B",
         "mark_kind": "correct" | "wrong" | "score" | "comment",
         "mark_score": "8/10", "mark_comment": "..."}
    ``part_id``, ``mark_score`` and ``mark_comment`` are optional.
    """
    entries = []
    for r in rows:
        kind = r.get("mark_kind")
        entries.append(ManualEntry(
            question_id=r["question_id"],
            part_id=r.get("part_id"),
            student_answer=r.get("student_answer"),
            mark_kind=GradingMarkKind(kind) if kind else GradingMarkKind.UNKNOWN,
            mark_score=r.get("mark_score"),
            mark_comment=r.get("mark_comment"),
        ))
    return entries


def commit_rows(rows: Iterable[Dict], student_id: str, assignment_number: str,
                template: Optional[AssignmentTemplate] = None,
                page_ref: Optional[str] = None) -> List[AnswerRecord]:
    """One-shot: rows -> validated entries -> downstream AnswerRecords."""
    session = ManualEntrySession(student_id, assignment_number, template)
    for entry in entries_from_rows(rows):
        session.add(entry)
    return session.commit(page_ref=page_ref)


def run_interactive_cli(student_id: str, assignment_number: str,
                        template: AssignmentTemplate) -> List[AnswerRecord]:
    """Prompt per sub-question; returns committed AnswerRecords.

    Run as:  python3 -m manual_entry  (from the ingestion directory)
    """
    session = ManualEntrySession(student_id, assignment_number, template)
    print(f"Manual entry — student {student_id}, assignment {assignment_number}")
    print("Leave the answer blank to skip a sub-question. "
          "Mark: c=√ correct, x=× wrong, s=score, m=comment, Enter=none.")
    for q in template.questions:
        parts: List[Optional[str]] = q.parts if q.kind is QuestionKind.SUB_QUESTIONS and q.parts else [None]
        for part in parts:
            key = f"{q.id}#{part}" if part else q.id
            answer = input(f"[{key}] student answer: ").strip() or None
            raw = input(f"[{key}] grading mark (c/x/s/m): ").strip().lower()
            kind = {"c": GradingMarkKind.CORRECT, "x": GradingMarkKind.WRONG,
                    "s": GradingMarkKind.SCORE, "m": GradingMarkKind.COMMENT}.get(raw,
                    GradingMarkKind.UNKNOWN)
            score = comment = None
            if kind is GradingMarkKind.SCORE:
                score = input(f"[{key}] score (e.g. 8/10): ").strip() or None
            if kind is GradingMarkKind.COMMENT:
                comment = input(f"[{key}] comment: ").strip() or None
            if answer is None and kind is GradingMarkKind.UNKNOWN:
                continue
            session.add(ManualEntry(question_id=q.id, part_id=part,
                                    student_answer=answer, mark_kind=kind,
                                    mark_score=score, mark_comment=comment))
    records = session.commit()
    print(f"Committed {len(records)} records (source=manual).")
    return records


if __name__ == "__main__":
    import sys
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from fixtures import make_sample_template  # type: ignore
    sid = input("student ID: ").strip()
    anum = input("assignment number: ").strip()
    run_interactive_cli(sid, anum, make_sample_template())
