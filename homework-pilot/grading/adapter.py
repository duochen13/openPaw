"""Adapter: graded papers -> the student web UI's data model.

``webui.models.QuestionResult`` requires every 待确认 item to carry a
proposed verdict -- the demo only models pending items where a source
produced a lean. Real pipeline output also contains pending items with
no lean (unreadable answers, partially-credited process questions).
This adapter converts everything it can and *fails loudly*, naming the
unrenderable items, rather than inventing proposals for them. Those
items are precisely the ones whose confirmation UI needs a manual
verdict entry instead of a confirm-the-proposal button (follow-up on
the webui side, out of scope for #176).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .models import GradedPaper, ItemResult


def _webui_models():
    homework_pilot = Path(__file__).resolve().parent.parent
    if str(homework_pilot) not in sys.path:
        sys.path.insert(0, str(homework_pilot))
    from webui import models

    return models


def unrenderable_items(paper: GradedPaper) -> tuple[ItemResult, ...]:
    """Pending items with no proposal -- the demo UI cannot show them."""
    return tuple(
        item
        for item in paper.items
        if item.verdict == "待确认" and not item.proposed_verdict
    )


def to_webui_question(item: ItemResult):
    """Convert one item. Raises ValueError for no-lean pending items."""
    models = _webui_models()
    if item.verdict == "待确认" and not item.proposed_verdict:
        raise ValueError(
            f"{item.item_key}: 待确认 without a proposed verdict cannot "
            "be represented in the webui demo model"
        )
    if item.source not in models.VERDICT_SOURCES:
        # Post-confirmation records （学生确认） belong to the export
        # world, not the demo's pre-confirmation rendering. Refuse
        # rather than relabel the source.
        raise ValueError(
            f"{item.item_key}: source {item.source!r} is not part of the "
            "webui demo model (it renders pre-confirmation state)"
        )
    source = item.source
    return models.QuestionResult(
        number=item.number,
        question_text=item.question_text,
        student_answer=item.student_answer,
        verdict=item.verdict,
        source=source,
        proposed_verdict=item.proposed_verdict,
        reference_answer=item.reference_answer,
        ocr_reliability=item.ocr_reliability,
        image_location=item.image_location,
        page_label=item.page_label,
    )


def to_webui_paper(paper: GradedPaper, *, skip_unrenderable: bool = False):
    """Convert a whole paper. Strict by default (see module docstring)."""
    models = _webui_models()
    blocked = unrenderable_items(paper)
    if blocked and not skip_unrenderable:
        keys = ", ".join(item.item_key for item in blocked)
        raise ValueError(
            f"{len(blocked)} item(s) cannot render in the webui demo "
            f"model (待确认 with no proposal): {keys}"
        )
    blocked_keys = {item.item_key for item in blocked}
    questions = tuple(
        to_webui_question(item)
        for item in paper.items
        if item.item_key not in blocked_keys
    )
    return models.PaperResult(
        id=f"paper-{paper.student_id}",
        title=paper.title,
        date_label=paper.date_label,
        status=paper.status,
        questions=questions,
    )
