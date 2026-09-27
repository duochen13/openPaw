"""Student-ID matching with round-trip linking and a teacher confirmation queue.

Policy (non-negotiable):
- Exact ID + assignment-number match with sufficient confidence -> linked.
- Anything uncertain (missing ID, low confidence, unknown ID) -> the
  teacher confirmation queue. The system NEVER auto-guesses a student.

The ID-region reading itself is a pluggable interface (``IDReader``):
real OCR plugs in later; tests use deterministic doubles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models import MatchResult, Page


class IDReader(ABC):
    """Reads the printed student ID + assignment number from a page's ID region."""

    @abstractmethod
    def read_id(self, page: Page) -> Tuple[Optional[str], Optional[str], float]:
        """Return (student_id, assignment_number, confidence). None = not readable."""


def edit_distance(a: str, b: str) -> int:
    """Small Levenshtein for candidate suggestion (IDs are short)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[lb]


@dataclass
class ReviewCase:
    """One ambiguous match waiting for teacher confirmation."""
    case_id: str
    page: Page
    read_student_id: Optional[str]
    read_assignment_number: Optional[str]
    read_confidence: float
    candidates: List[Tuple[str, int]]  # (student_id, edit_distance) sorted, nearest first
    reason: str
    resolved: bool = False
    resolution: Optional[str] = None  # confirmed student_id, or "unmatched"/"duplicate"
    resolved_note: str = ""


class TeacherReviewQueue:
    """First-class confirmation queue: uncertain matches land here.

    The teacher sees the page reference, what was read, the confidence,
    WHY it was queued, and candidate student IDs to pick from.
    """

    def __init__(self) -> None:
        self._cases: Dict[str, ReviewCase] = {}
        self._seq = 0

    def add(self, page: Page, read_student_id: Optional[str],
            read_assignment_number: Optional[str], read_confidence: float,
            candidates: List[Tuple[str, int]], reason: str) -> ReviewCase:
        self._seq += 1
        case = ReviewCase(
            case_id=f"RC-{self._seq:04d}",
            page=page, read_student_id=read_student_id,
            read_assignment_number=read_assignment_number,
            read_confidence=read_confidence,
            candidates=sorted(candidates, key=lambda c: (c[1], c[0])),
            reason=reason,
        )
        self._cases[case.case_id] = case
        return case

    def resolve(self, case_id: str, student_id: str, note: str = "") -> ReviewCase:
        """Teacher confirms the student identity (may pick a candidate or type one)."""
        case = self._cases[case_id]
        case.resolved = True
        case.resolution = student_id
        case.resolved_note = note
        return case

    def mark_unmatched(self, case_id: str, note: str = "") -> ReviewCase:
        """Teacher declares the page cannot be attributed to any known student."""
        case = self._cases[case_id]
        case.resolved = True
        case.resolution = "unmatched"
        case.resolved_note = note
        return case

    def pending(self) -> List[ReviewCase]:
        return [c for c in self._cases.values() if not c.resolved]

    def all(self) -> List[ReviewCase]:
        return list(self._cases.values())


def suggest_candidates(read_id: Optional[str], known_students: List[str],
                       max_distance: int = 2, limit: int = 5) -> List[Tuple[str, int]]:
    """Nearest known student IDs by edit distance (empty read -> no candidates)."""
    if not read_id:
        return []
    scored = [(sid, edit_distance(read_id, sid)) for sid in known_students]
    near = [s for s in scored if s[1] <= max_distance]
    return sorted(near, key=lambda c: (c[1], c[0]))[:limit]


def match_pages(pages: List[Page], id_reader: IDReader,
                known_students: List[str],
                min_confidence: float = 0.9) -> Tuple[List[MatchResult], TeacherReviewQueue]:
    """Link each page to a student, or route it to the confirmation queue.

    Linking requires: readable ID, readable assignment number, ID known,
    confidence >= min_confidence. Everything else is queued.
    """
    linked: List[MatchResult] = []
    queue = TeacherReviewQueue()
    for page in pages:
        sid, anum, conf = id_reader.read_id(page)
        if sid and anum and sid in known_students and conf >= min_confidence:
            linked.append(MatchResult(page=page, student_id=sid,
                                     assignment_number=anum, confidence=conf,
                                     linked=True, note="exact ID + assignment match"))
            continue
        if not sid:
            reason = "student ID not readable on page"
        elif sid not in known_students:
            reason = f"read ID '{sid}' is not a known student"
        elif not anum:
            reason = "assignment number not readable on page"
        else:
            reason = f"read confidence {conf:.2f} below threshold {min_confidence:.2f}"
        candidates = suggest_candidates(sid, known_students)
        queue.add(page, sid, anum, conf, candidates, reason)
        linked.append(MatchResult(page=page, student_id=None,
                                  assignment_number=anum, confidence=conf,
                                  linked=False,
                                  note=f"queued for teacher confirmation: {reason}"))
    return linked, queue
