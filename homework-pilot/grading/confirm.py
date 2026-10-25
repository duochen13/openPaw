"""Student confirmation and the labeled-examples export.

The confirmation queue is the student's side of the pipeline: they
confirm a proposed verdict, override it, and/or correct a shaky
transcription. A confirmed item records the student's decision as its
verdict with source 学生确认 -- the pipeline never rewrites history:
the original verdict/source/proposal stay on the export record, so the
pair (system output, student-confirmed label) is exactly the labeled
example a future post-training run needs.

Exports are ID-only: every record passes
``privacy.guard.assert_id_only`` before it leaves.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from .models import GradedPaper, ItemResult

# privacy is a sibling package with absolute imports (run from
# homework-pilot/, like taxonomy); import lazily so grading's own unit
# tests of pure functions do not depend on sys.path setup.
def _assert_id_only(record: dict) -> None:
    homework_pilot = Path(__file__).resolve().parent.parent
    if str(homework_pilot) not in sys.path:
        sys.path.insert(0, str(homework_pilot))
    from privacy.guard import assert_id_only

    assert_id_only(record, where="labeled example")


def apply_confirmation(
    paper: GradedPaper,
    item_key: str,
    *,
    accept_proposal: bool = False,
    verdict: str | None = None,
    corrected_answer: str | None = None,
    reference_answer: str | None = None,
) -> GradedPaper:
    """Return a new paper with one item confirmed/corrected.

    ``accept_proposal`` adopts the item's proposed verdict;
    ``verdict`` overrides with the student's own 对/错;
    ``corrected_answer`` replaces a mis-read transcription (and clears
    the transcription-confirmation flag). Confirming an item as 错
    requires a reference answer -- the item's own if it has one, else
    the caller must supply it -- mirroring the webui model invariant.
    """
    items: list[ItemResult] = []
    found = False
    for item in paper.items:
        if item.item_key != item_key:
            items.append(item)
            continue
        found = True
        final = verdict or (item.proposed_verdict if accept_proposal else "")
        if final not in ("对", "错"):
            raise ValueError(
                f"{item_key}: confirmation needs a 对/错 decision "
                "(pass verdict= or accept_proposal=True on an item with a proposal)"
            )
        reference = item.reference_answer or reference_answer or ""
        if final == "错" and not reference:
            raise ValueError(
                f"{item_key}: confirming as 错 requires a reference answer"
            )
        items.append(
            replace(
                item,
                student_answer=(
                    corrected_answer
                    if corrected_answer is not None
                    else item.student_answer
                ),
                verdict=final,
                source="学生确认",
                proposed_verdict="",
                proposal_source="",
                reference_answer=reference,
                pending_reason="",
                needs_transcription_confirmation=(
                    False
                    if corrected_answer is not None
                    else item.needs_transcription_confirmation
                ),
                confirmed=True,
                confirmed_verdict=final,
                system_verdict=item.verdict,
                system_source=item.source,
                system_proposed_verdict=item.proposed_verdict,
            )
        )
    if not found:
        raise KeyError(f"no item {item_key!r} in paper for {paper.student_id}")
    return replace(paper, items=tuple(items))


def labeled_example(item: ItemResult, *, student_id: str) -> dict:
    """One exportable labeled example for a confirmed item."""
    record = {
        "student_id": student_id,
        "item_key": item.item_key,
        "question_id": item.question_id,
        "part_id": item.part_id,
        "question_text": item.question_text,
        "student_answer": item.student_answer,
        "ocr_reliability": item.ocr_reliability,
        "verdict": item.confirmed_verdict,
        "verdict_source": "学生确认",
        "system_verdict": item.system_verdict,
        "system_source": item.system_source,
        "system_proposed_verdict": item.system_proposed_verdict,
        "mark_kind": item.mark_kind,
        "knowledge_point_tag": item.knowledge_point_tag,
        "skill_ids": list(item.skill_ids),
        "image_location": item.image_location,
        "page_label": item.page_label,
    }
    _assert_id_only(record)
    return record


def export_labeled_examples(paper: GradedPaper) -> list[dict]:
    """All confirmed items of a paper, as labeled-example dicts."""
    return [
        labeled_example(item, student_id=paper.student_id)
        for item in paper.items
        if item.confirmed
    ]


def write_jsonl(examples: list[dict], path: Path) -> int:
    """Write labeled examples as JSONL; returns the count written."""
    lines = [json.dumps(e, ensure_ascii=False) for e in examples]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), "utf-8")
    return len(lines)
