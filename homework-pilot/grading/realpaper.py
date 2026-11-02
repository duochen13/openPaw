"""Real-paper grading backend (issue #184, Phase 2).

The kit backends in :mod:`grading.backends` are test doubles: they
replay scripted recognition records for five synthetic students. This
module is the real backend behind the same interfaces, for a real
uploaded paper from *any* student:

    upload bytes -> pages -> template segmentation -> recognizer
    transcription -> the unchanged judge -> GradedPaper

* **Pages** come from the upload itself: :func:`pages_from_pdf` counts
  the pages of the uploaded PDF with a stdlib-only reader (no external
  tools, no third-party packages); photos are one page each
  (:func:`pages_from_photos`).
* **Segmentation** reuses :class:`grading.backends.TemplateSegmenter`
  over the *assignment's* layout template. Real assignments carry the
  same template shape as the kit's (Phase 2 swaps the file's contents,
  not its shape), so the segmenter is shared, not forked.
* **Transcription** is :class:`RecognizerTranscriber`, which bridges
  grading segments to the ingestion package's ``Recognizer`` interface
  (per-item handwriting + red-pen-mark recognition with reliability).
  A real OCR/VLM recognizer plugs in there; it is the one component
  this project does not ship. Until one is configured,
  :func:`grade_real_paper` defaults to :func:`unavailable_recognizer`,
  which reads nothing: every item is still segmented and recorded,
  and the judge pends every one of them 待确认 / unreadable rather
  than guessing -- the same honesty rule as ``UnavailableSelfSolver``.
* **Judging** is untouched: 红笔标记 > 答案 key > 模型自解， never
  blended, verdict vocabulary exactly 对 / 错 / 待确认. Reliability
  still routes only the *read* to the confirmation queue.
* **Privacy**: the graded paper's record dict passes
  ``privacy.guard.assert_id_only`` before the paper is returned --
  student IDs only, no names, same as every other storage boundary.

**Validation status (stated plainly):** the acceptance evaluation for
this backend -- decided-rate and verdict agreement against teacher
ground truth on the 5 real sample papers from issue #108 -- has NOT
run, because those papers have not been provided yet (human-blocked
on Daniel/teacher). :func:`evaluate_against_truth` and
:func:`summarize_evaluations` implement exactly that report; the
tests drive them over synthetic fixtures (kit records replayed
through the real backend's recognizer bridge) so the harness is
proven, but no real-paper accuracy number exists yet and none is
claimed anywhere.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

from .backends import (
    PageImage,
    Segment,
    SelfSolver,
    TemplateSegmenter,
    Transcriber,
    Transcription,
)
from .models import GradedPaper
from .pipeline import grade_paper

_HOMEWORK_PILOT = Path(__file__).resolve().parent.parent
_INGESTION_DIR = _HOMEWORK_PILOT / "ingestion"


# ---------------------------------------------------------------------------
# Ingestion bridge (flat-import package; see pilot-kit/tools/run_end_to_end.py)
# ---------------------------------------------------------------------------

_ingestion_cache: SimpleNamespace | None = None


def load_ingestion() -> SimpleNamespace:
    """Import the ingestion package's modules (cached).

    Ingestion is a flat-import package (its modules do
    ``from models import ...``), so its directory goes on ``sys.path``
    -- the same pattern ``pilot-kit/tools/run_end_to_end.py`` uses.
    Returns a namespace with ``.models`` and ``.recognizer``.
    """
    global _ingestion_cache
    if _ingestion_cache is not None:
        return _ingestion_cache
    if str(_INGESTION_DIR) not in sys.path:
        sys.path.insert(0, str(_INGESTION_DIR))
    import models as ing_models
    import recognizer as ing_recognizer

    _ingestion_cache = SimpleNamespace(models=ing_models, recognizer=ing_recognizer)
    return _ingestion_cache


def _assert_id_only(record: dict) -> None:
    """privacy.guard.assert_id_only, imported the grading.confirm way."""
    if str(_HOMEWORK_PILOT) not in sys.path:
        sys.path.insert(0, str(_HOMEWORK_PILOT))
    from privacy.guard import assert_id_only

    assert_id_only(record, where="real-paper grading output")


# ---------------------------------------------------------------------------
# Upload ingest: bytes -> pages (stdlib only)
# ---------------------------------------------------------------------------


class UnreadableUploadError(ValueError):
    """The upload cannot be paged at all (not a PDF, or its page count
    cannot be determined). Callers store the upload as 未识别 rather
    than inventing pages."""


_PAGES_MARKER = re.compile(rb"/Type\s*/Pages\b")
_COUNT_IN_DICT = re.compile(rb"/Count\s+(\d+)")
_PAGE_OBJECT = re.compile(rb"/Type\s*/Page(?![\w])")


def count_pdf_pages(content: bytes) -> int:
    """Count the pages of a PDF using only the standard library.

    Reads the page tree's ``/Count`` (taking the largest when several
    ``/Pages`` nodes exist); falls back to counting ``/Type /Page``
    objects. PDFs whose page tree lives in compressed object streams
    expose neither and raise :class:`UnreadableUploadError` -- a
    stated limitation, never a guessed count.
    """
    if not content.startswith(b"%PDF-"):
        raise UnreadableUploadError("not a PDF (missing %PDF- header)")
    counts: list[int] = []
    for marker in _PAGES_MARKER.finditer(content):
        found = _COUNT_IN_DICT.search(content[marker.end():marker.end() + 512])
        if found:
            counts.append(int(found.group(1)))
    if counts and max(counts) > 0:
        return max(counts)
    objects = len(_PAGE_OBJECT.findall(content))
    if objects > 0:
        return objects
    raise UnreadableUploadError(
        "could not determine the PDF page count "
        "(no readable /Pages /Count or /Type /Page objects)"
    )


def pages_from_pdf(content: bytes, location: str) -> list[PageImage]:
    """One :class:`PageImage` per page of an uploaded PDF.

    ``location`` is where the caller stores the uploaded file; each
    page's ``image_location`` is ``"<location>#page<i>"``, the same
    page-reference shape the kit manifest uses.
    """
    return [
        PageImage(
            page_index=i,
            image_location=f"{location}#page{i}",
            media_type="pdf_scan",
        )
        for i in range(count_pdf_pages(content))
    ]


def pages_from_photos(locations: list[str]) -> list[PageImage]:
    """One :class:`PageImage` per uploaded photo, in upload order."""
    return [
        PageImage(page_index=i, image_location=loc, media_type="photo")
        for i, loc in enumerate(locations)
    ]


# ---------------------------------------------------------------------------
# Transcriber: grading segments -> ingestion Recognizer -> Transcription
# ---------------------------------------------------------------------------


class RecognizerTranscriber(Transcriber):
    """Transcribe segments with an ingestion ``Recognizer``.

    Each segment becomes an ingestion ``SegmentedItem`` over the
    segment's page, and the recognizer reads it twice -- handwriting
    and grading mark -- exactly as the ingestion pipeline does. The
    merge follows ``ingestion.recognizer.recognitions_to_records``:

    * the transcription reliability is the *minimum* of the reads that
      contributed to the record (a mark that was read bounds the
      record's trust just as the handwriting read does);
    * a mark read as ``unknown`` contributed nothing, so it neither
      sets ``mark_kind`` nor drags the reliability down -- this is what
      makes key-only mode (no marks scripted/readable) behave like the
      kit's Mode B instead of flagging every read as shaky.

    ``kinds`` maps question_id -> ingestion question kind; recognizers
    receive it as metadata on the item ref and must not branch on it.
    """

    def __init__(
        self,
        recognizer,
        page_files: Mapping[int, str],
        *,
        kinds: Mapping[str, str] | None = None,
    ) -> None:
        self._recognizer = recognizer
        self._page_files = dict(page_files)
        self._kinds = dict(kinds or {})

    def transcribe(self, segments: list[Segment]) -> list[Transcription]:
        ing = load_ingestion()
        out: list[Transcription] = []
        for seg in segments:
            page = ing.models.Page(
                upload_id="grading",
                file_path=self._page_files.get(seg.page_index, ""),
                page_index=seg.page_index,
                page_no_in_file=seg.page_index,
            )
            try:
                kind = ing.models.QuestionKind(
                    self._kinds.get(seg.question_id, "")
                )
            except ValueError:
                kind = ing.models.QuestionKind.SUB_QUESTIONS
            item = ing.models.SegmentedItem(
                page=page,
                sub_question=ing.models.SubQuestionRef(
                    question_id=seg.question_id,
                    part_id=seg.part_id or None,
                    kind=kind,
                    region=ing.models.Region(**seg.region),
                ),
            )
            handwriting = self._recognizer.recognize(
                item, ing.recognizer.HANDWRITING
            )
            mark_rec = self._recognizer.recognize(
                item, ing.recognizer.GRADING_MARK
            )
            mark_kind, mark_text = "", ""
            reliability = handwriting.reliability
            if (
                mark_rec.mark is not None
                and mark_rec.mark is not ing.models.GradingMarkKind.UNKNOWN
            ):
                mark_kind = mark_rec.mark.value
                if mark_kind == "score":
                    mark_text = mark_rec.score or ""
                reliability = min(reliability, mark_rec.reliability)
            out.append(
                Transcription(
                    item_key=seg.item_key,
                    student_answer=handwriting.text,
                    reliability=reliability,
                    mark_kind=mark_kind,
                    mark_text=mark_text,
                )
            )
        return out


_unavailable_recognizer_singleton = None


def unavailable_recognizer():
    """A recognizer that reads nothing (the shipped default).

    Every recognition is ``unknown`` at reliability 0.0, so the real
    backend still segments and records every item of a real upload,
    and the judge pends each one 待确认 / unreadable. Wiring a real
    OCR/VLM recognizer is a configuration change, not a code change.
    """
    global _unavailable_recognizer_singleton
    if _unavailable_recognizer_singleton is not None:
        return _unavailable_recognizer_singleton
    ing = load_ingestion()

    class _UnavailableRecognizer(ing.recognizer.Recognizer):
        def recognize(self, item, item_type):
            return ing.models.Recognition(
                item_key=item.sub_question.item_key,
                item_type=item_type,
                text=None,
                mark=ing.models.GradingMarkKind.UNKNOWN,
                reliability=0.0,
            )

    _unavailable_recognizer_singleton = _UnavailableRecognizer()
    return _unavailable_recognizer_singleton


def recognizer_from_records(records: list[dict], *, include_marks: bool = True):
    """Build ingestion's ``TestDoubleRecognizer`` from answer records.

    ``records`` are AnswerRecord-shaped dicts (the kit's
    ``answer-records.json`` shape); the scripting mirrors
    ``pilot-kit/tools/run_end_to_end.py``. This exists so tests -- and,
    when the #108 samples land, the acceptance run -- can drive the
    real backend with known recognitions. ``include_marks=False``
    withholds the red-pen marks (key-only mode).
    """
    ing = load_ingestion()
    script: dict = {}
    for record in records:
        key = record["item_key"]
        reliability = float(record.get("reliability", 0.0))
        if record.get("student_answer") is not None:
            script[(key, ing.recognizer.HANDWRITING)] = {
                "text": record["student_answer"],
                "reliability": reliability,
            }
        mark = record.get("grading_mark")
        if include_marks and mark:
            entry = {"mark": mark["kind"], "reliability": reliability}
            if mark.get("score"):
                entry["score"] = mark["score"]
            if mark.get("comment"):
                entry["text"] = mark["comment"]
            script[(key, ing.recognizer.GRADING_MARK)] = entry
    return ing.recognizer.TestDoubleRecognizer(script)


# ---------------------------------------------------------------------------
# The backend entry point
# ---------------------------------------------------------------------------


def load_assignment(assignment_dir: Path) -> tuple[list[dict], dict, dict]:
    """Load an assignment definition: (questions, template, meta).

    Same files the kit loaders read (``questions.json`` +
    ``template.json``), from any assignment directory -- the teacher's
    real assignment directory in Phase 2, the kit's until then.
    """
    assignment_dir = Path(assignment_dir)
    data = json.loads((assignment_dir / "questions.json").read_text("utf-8"))
    template = json.loads((assignment_dir / "template.json").read_text("utf-8"))
    return data["questions"], template, data.get("meta", {})


def grade_real_paper(
    *,
    student_id: str,
    pages: list[PageImage],
    questions: list[dict],
    template: dict,
    recognizer=None,
    solver: SelfSolver | None = None,
    assignment_id: str = "",
    title: str = "",
    date_label: str = "",
) -> GradedPaper:
    """Grade one real paper end to end, for any student ID.

    ``pages`` come from the student's own upload (see
    :func:`pages_from_pdf` / :func:`pages_from_photos`); ``questions``
    and ``template`` are the assignment's definition (the source of the
    answer key and the layout). ``recognizer`` is an ingestion
    ``Recognizer``; the default reads nothing (see
    :func:`unavailable_recognizer`). The output is the same
    :class:`GradedPaper` shape the kit path produces, and it passes
    ``privacy.guard.assert_id_only`` before it is returned.
    """
    from dataclasses import asdict

    recognizer = recognizer if recognizer is not None else unavailable_recognizer()
    page_files = {
        p.page_index: p.image_location.split("#")[0] for p in pages
    }
    kinds = {q["id"]: q.get("kind", "") for q in questions}
    paper = grade_paper(
        student_id=student_id,
        assignment_id=assignment_id or template.get("assignment_number", ""),
        title=title or template.get("title", ""),
        pages=pages,
        questions=questions,
        segmenter=TemplateSegmenter(template, questions),
        transcriber=RecognizerTranscriber(recognizer, page_files, kinds=kinds),
        solver=solver,
        date_label=date_label,
    )
    _assert_id_only(asdict(paper))
    return paper


# ---------------------------------------------------------------------------
# Acceptance evaluation (issue #184 criteria; runs on #108 samples when
# they land -- see the module docstring's validation-status note)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperEvaluation:
    """Decided-rate + verdict agreement for one paper vs teacher truth."""

    student_id: str
    total: int          # items that carry a ground-truth label
    decided: int        # of those, items the pipeline decided （对/错）
    agreed: int         # decided items whose verdict matches the truth
    disagreed: int      # decided items whose verdict differs

    @property
    def decided_rate(self) -> float:
        return self.decided / self.total if self.total else 0.0

    @property
    def agreement(self) -> float | None:
        """Agreement over decided items; None when nothing was decided."""
        return self.agreed / self.decided if self.decided else None

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "total": self.total,
            "decided": self.decided,
            "agreed": self.agreed,
            "disagreed": self.disagreed,
            "decided_rate": round(self.decided_rate, 4),
            "agreement": (
                round(self.agreement, 4) if self.agreement is not None else None
            ),
        }


def evaluate_against_truth(
    paper: GradedPaper, truth: Mapping[str, str]
) -> PaperEvaluation:
    """Score one graded paper against teacher ground truth.

    ``truth`` maps item_key -> the teacher's verdict （对/错/待确认）.
    Only labeled items count toward ``total``; agreement is measured
    over decided items only -- a 待确认 is never scored as wrong, it
    is scored by the decided-rate instead.
    """
    decided = agreed = disagreed = 0
    total = 0
    for item in paper.items:
        if item.item_key not in truth:
            continue
        total += 1
        if item.verdict in ("对", "错"):
            decided += 1
            if item.verdict == truth[item.item_key]:
                agreed += 1
            else:
                disagreed += 1
    return PaperEvaluation(
        student_id=paper.student_id,
        total=total,
        decided=decided,
        agreed=agreed,
        disagreed=disagreed,
    )


def summarize_evaluations(evaluations: list[PaperEvaluation]) -> dict:
    """Aggregate per-paper evaluations into the acceptance report."""
    total = sum(e.total for e in evaluations)
    decided = sum(e.decided for e in evaluations)
    agreed = sum(e.agreed for e in evaluations)
    disagreed = sum(e.disagreed for e in evaluations)
    return {
        "papers": [e.to_dict() for e in evaluations],
        "total": total,
        "decided": decided,
        "agreed": agreed,
        "disagreed": disagreed,
        "decided_rate": round(decided / total, 4) if total else 0.0,
        "agreement": round(agreed / decided, 4) if decided else None,
    }
