"""Pluggable stage backends for the grading pipeline.

Each pipeline stage is an interface so a real backend can replace the
synthetic-kit one without touching the judge:

* :class:`Segmenter` -- page images -> per-question regions. A vision
  model backend will implement this later; v1 ships
  :class:`TemplateSegmenter`, deterministic over the pilot kit's layout
  template (the kit papers are rendered from that template, so the
  regions are exact by construction).
* :class:`Transcriber` -- regions -> transcription + recognition
  reliability + any red-pen mark read from the same crop. v1 ships
  :class:`KitTranscriber`, which replays the kit's scripted recognition
  records (the same AnswerRecord-shaped data ingestion's test-double
  recognizer produces). A VLM/OCR backend implements the same shape.
* :class:`SelfSolver` -- the third verdict source (model self-solve).
  v1 ships only :class:`UnavailableSelfSolver`, which always declines:
  no real model calls in this PR, and declining is the honest default.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PageImage:
    """Ingest output: one scanned page of one student's paper."""

    page_index: int
    image_location: str          # where the page image lives (path/URI)
    media_type: str = "pdf_scan"


@dataclass(frozen=True)
class Segment:
    """Segment output: one recordable item's region on one page."""

    item_key: str                # "Q3#b" / "Q1"
    question_id: str
    part_id: str                 # "" for whole-question items
    page_index: int
    region: dict                 # normalized {"x","y","w","h"} crop box
    question_text: str = ""


@dataclass(frozen=True)
class Transcription:
    """Transcribe output for one item.

    ``student_answer`` is None when nothing could be read at all.
    ``mark_kind`` is the red-pen mark read from the same crop, in
    ingestion's GradingMarkKind vocabulary ("" when no mark was read).
    """

    item_key: str
    student_answer: str | None
    reliability: float           # legibility of the read, 0..1
    mark_kind: str = ""          # correct / wrong / score / comment
    mark_text: str = ""          # e.g. the score text "9/12"


class Segmenter(ABC):
    @abstractmethod
    def segment(self, pages: list[PageImage]) -> list[Segment]:
        """Return per-item regions for the given pages, in paper order."""


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, segments: list[Segment]) -> list[Transcription]:
        """Return one transcription per segment."""


class SelfSolver(ABC):
    """Verdict source 3: solve the question, compare with the student's
    answer. Implementations must return None when they cannot judge --
    returning a guess violates the pipeline's honesty rule."""

    @abstractmethod
    def solve(self, question_text: str, student_answer: str) -> str | None:
        """Return "对"/"错" for a determinate-answer question, else None."""


class UnavailableSelfSolver(SelfSolver):
    """v1 stub: no model is wired up, so self-solve always declines."""

    def solve(self, question_text: str, student_answer: str) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Pilot-kit backends (synthetic, deterministic)
# ---------------------------------------------------------------------------

def load_kit_questions(kit_dir: Path) -> list[dict]:
    data = json.loads((kit_dir / "assignment" / "questions.json").read_text("utf-8"))
    return data["questions"]


def load_kit_meta(kit_dir: Path) -> dict:
    data = json.loads((kit_dir / "assignment" / "questions.json").read_text("utf-8"))
    return data.get("meta", {})


def load_kit_template(kit_dir: Path) -> dict:
    return json.loads((kit_dir / "assignment" / "template.json").read_text("utf-8"))


def load_kit_manifest(kit_dir: Path) -> list[dict]:
    data = json.loads((kit_dir / "papers" / "manifest.json").read_text("utf-8"))
    return data["papers"]


def load_kit_records(kit_dir: Path, student_id: str) -> list[dict]:
    path = kit_dir / "papers" / student_id / "answer-records.json"
    data = json.loads(path.read_text("utf-8"))
    return data["records"] if isinstance(data, dict) else data


def item_key_of(question_id: str, part_id: str) -> str:
    return f"{question_id}#{part_id}" if part_id else question_id


class TemplateSegmenter(Segmenter):
    """Deterministic segmenter over the kit's per-page layout template.

    The template lists, per page, each question's normalized region per
    part -- exactly what a vision segmenter would have to find. Failure
    modes a VLM would have (cross-page questions, figures, two-column
    layouts) do not occur in the kit; the interface is where they will
    surface later, as low-reliability segments.
    """

    def __init__(self, template: dict, questions: list[dict]) -> None:
        self._template = template
        self._stems = {q["id"]: q.get("stem", "") for q in questions}

    def segment(self, pages: list[PageImage]) -> list[Segment]:
        wanted = {p.page_index for p in pages}
        segments: list[Segment] = []
        for page in self._template["pages"]:
            page_index = page["page_index"]
            if page_index not in wanted:
                continue
            for question in page["questions"]:
                qid = question["id"]
                parts = question["parts"] or [""]
                for part_id in parts:
                    region = question["regions"][part_id]
                    segments.append(
                        Segment(
                            item_key=item_key_of(qid, part_id),
                            question_id=qid,
                            part_id=part_id,
                            page_index=page_index,
                            region=dict(region),
                            question_text=self._stems.get(qid, ""),
                        )
                    )
        return segments


class KitTranscriber(Transcriber):
    """Replays the kit's scripted recognition records.

    With ``include_marks=False`` the red-pen marks are withheld (the
    no-marks exercise: only the answer key remains as a verdict source).
    Reliability values are the kit's own, including its deliberately
    low-reliability cases.
    """

    def __init__(self, records: list[dict], *, include_marks: bool = True) -> None:
        self._by_key = {r["item_key"]: r for r in records}
        self._include_marks = include_marks

    def transcribe(self, segments: list[Segment]) -> list[Transcription]:
        out: list[Transcription] = []
        for seg in segments:
            record = self._by_key.get(seg.item_key)
            if record is None:
                out.append(
                    Transcription(seg.item_key, None, 0.0)
                )
                continue
            mark_kind, mark_text = "", ""
            mark = record.get("grading_mark")
            if self._include_marks and mark:
                mark_kind = mark.get("kind", "")
                if mark_kind == "score":
                    mark_text = mark.get("score") or ""
            out.append(
                Transcription(
                    item_key=seg.item_key,
                    student_answer=record.get("student_answer"),
                    reliability=float(record.get("reliability", 0.0)),
                    mark_kind=mark_kind,
                    mark_text=mark_text,
                )
            )
        return out


def expected_verdicts(records: list[dict]) -> dict[str, str]:
    """TEST ground truth derived from the kit's own grading marks.

    A decisive red mark (correct/wrong) is the teacher's verdict; a
    partial score, a comment-only mark, or no mark at all can never be
    a binary ground truth -- the pipeline must answer 待确认 there.
    This derivation reads only the kit records; it shares no code with
    the judge.
    """
    expected: dict[str, str] = {}
    for record in records:
        mark = record.get("grading_mark") or {}
        kind = mark.get("kind", "")
        if kind == "correct":
            expected[record["item_key"]] = "对"
        elif kind == "wrong":
            expected[record["item_key"]] = "错"
        else:
            expected[record["item_key"]] = "待确认"
    return expected
