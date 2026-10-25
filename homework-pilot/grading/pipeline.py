"""Pipeline composition: ingest -> segment -> transcribe -> judge -> paper.

:func:`grade_paper` is backend-agnostic: it takes any Segmenter /
Transcriber / SelfSolver triple. :func:`grade_kit_paper` wires the
pilot kit's deterministic backends for one synthetic student.

The reliability axis is applied here, after judging, and only here:
an item whose transcription reliability is below the threshold is
flagged ``needs_transcription_confirmation`` -- it joins the
confirmation queue for its *read*, with its verdict untouched.
"""

from __future__ import annotations

from pathlib import Path

from .backends import (
    KitTranscriber,
    PageImage,
    Segmenter,
    SelfSolver,
    TemplateSegmenter,
    Transcriber,
    UnavailableSelfSolver,
    load_kit_manifest,
    load_kit_meta,
    load_kit_questions,
    load_kit_records,
    load_kit_template,
)
from .judge import judge_item, resolve_key_answers
from .models import GradedPaper, ItemResult, reliability_tier


def _skill_ids_for(question: dict, part_id: str) -> tuple[str, ...]:
    part_skills = question.get("part_skill_ids") or {}
    if part_id and part_id in part_skills:
        value = part_skills[part_id]
        return (value,) if isinstance(value, str) else tuple(value)
    return tuple(question.get("skill_ids") or [])


def grade_paper(
    *,
    student_id: str,
    assignment_id: str,
    title: str,
    pages: list[PageImage],
    questions: list[dict],
    segmenter: Segmenter,
    transcriber: Transcriber,
    solver: SelfSolver | None = None,
    date_label: str = "",
) -> GradedPaper:
    """Run the five stages over one student's paper."""
    solver = solver or UnavailableSelfSolver()
    questions_by_id = {q["id"]: q for q in questions}
    key_answers: dict[str, str] = {}
    for question in questions:
        key_answers.update(resolve_key_answers(question))

    segments = segmenter.segment(pages)
    transcriptions = {t.item_key: t for t in transcriber.transcribe(segments)}
    page_files = {p.page_index: p.image_location for p in pages}

    items: list[ItemResult] = []
    for number, segment in enumerate(segments, start=1):
        question = questions_by_id[segment.question_id]
        transcription = transcriptions[segment.item_key]
        outcome = judge_item(
            question=question,
            key_answer=key_answers.get(segment.item_key, ""),
            transcription=transcription,
            solver=solver,
        )
        region = segment.region
        crop_ref = (
            f"{page_files.get(segment.page_index, '')}"
            f"#region={region.get('x', 0):.2f},{region.get('y', 0):.2f},"
            f"{region.get('w', 0):.2f},{region.get('h', 0):.2f}"
        )
        item = ItemResult(
            item_key=segment.item_key,
            question_id=segment.question_id,
            part_id=segment.part_id,
            number=number,
            question_text=segment.question_text,
            student_answer=transcription.student_answer or "",
            verdict=outcome.verdict,
            source=outcome.source,
            proposed_verdict=outcome.proposed_verdict,
            proposal_source=outcome.proposal_source,
            reference_answer=outcome.reference_answer,
            ocr_reliability=transcription.reliability,
            image_location=crop_ref,
            page_label=f"第 {segment.page_index + 1} 页",
            knowledge_point_tag=question.get("knowledge_point", ""),
            skill_ids=_skill_ids_for(question, segment.part_id),
            pending_reason=outcome.pending_reason,
            mark_kind=outcome.mark_kind,
            # Reliability routes the READ to the confirmation queue.
            # The verdict above was computed without it and stands.
            needs_transcription_confirmation=(
                reliability_tier(transcription.reliability) != "reliable"
            ),
        )
        items.append(item)

    return GradedPaper(
        student_id=student_id,
        assignment_id=assignment_id,
        title=title,
        date_label=date_label,
        items=tuple(items),
    )


def grade_kit_paper(
    kit_dir: Path,
    student_id: str,
    *,
    include_marks: bool = True,
    solver: SelfSolver | None = None,
) -> GradedPaper:
    """Grade one synthetic kit paper end to end.

    ``include_marks=False`` withholds the red-pen marks from the
    transcriber, exercising the answer-key source on its own.
    """
    kit_dir = Path(kit_dir)
    manifest = {p["student_id"]: p for p in load_kit_manifest(kit_dir)}
    entry = manifest[student_id]
    questions = load_kit_questions(kit_dir)
    template = load_kit_template(kit_dir)
    records = load_kit_records(kit_dir, student_id)

    pages: list[PageImage] = []
    for file_info in entry["files"]:
        if file_info["media_type"] == "photo":
            pages.append(
                PageImage(
                    page_index=len(pages),
                    image_location=file_info["path"],
                    media_type="photo",
                )
            )
    pages.sort(key=lambda p: p.page_index)

    meta = load_kit_meta(kit_dir)
    return grade_paper(
        student_id=student_id,
        assignment_id=meta.get("assignment_number", ""),
        title="第三章单元测验",
        pages=pages,
        questions=questions,
        segmenter=TemplateSegmenter(template, questions),
        transcriber=KitTranscriber(records, include_marks=include_marks),
        solver=solver,
        date_label="合成试卷（pilot-kit）",
    )
