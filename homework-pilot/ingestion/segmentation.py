"""Page -> sub-question segmentation, driven by an assignment template.

Since the generated PDFs are produced by this project, each assignment
has a known layout (the ``AssignmentTemplate``). Segmentation is therefore
declarative: for every page we emit one ``SegmentedItem`` per recordable
sub-question unit, with its bounding region. No ML is required to find
where questions are; the recognizer only has to read what is inside
each region.
"""

from __future__ import annotations

from typing import List

from models import AssignmentTemplate, Page, QuestionKind, SegmentedItem, SubQuestionRef, Upload


def segment_upload(upload: Upload, template: AssignmentTemplate) -> List[SegmentedItem]:
    """Segment every page of an upload into sub-question items.

    Page index is aligned to template pages 1:1 (page 0 of the upload is
    page 0 of the template). The ID region is intentionally NOT emitted
    as a sub-question item — matching reads it separately (see
    ``matching.py``).
    """
    pages = expand_pages(upload)
    items: List[SegmentedItem] = []
    for page in pages:
        for question in template.questions:
            # Sub-questions (Q11) and multi-blank fill-ins (Q5, Q12) are
            # recorded per part; plain multiple-choice per question.
            if question.kind in (QuestionKind.SUB_QUESTIONS, QuestionKind.FILL_BLANK) \
                    and question.parts:
                parts = question.parts or [""]
                for part in parts:
                    region = question.regions.get(part)
                    if region is None:
                        continue
                    items.append(SegmentedItem(
                        page=page,
                        sub_question=SubQuestionRef(
                            question_id=question.id, part_id=part or None,
                            kind=question.kind, region=region),
                    ))
            else:
                region = question.regions.get("")
                if region is None:
                    continue
                items.append(SegmentedItem(
                    page=page,
                    sub_question=SubQuestionRef(
                        question_id=question.id, part_id=None,
                        kind=question.kind, region=region),
                ))
    return items


def expand_pages(upload: Upload) -> List[Page]:
    """Flatten an upload's files into a 0-based page list."""
    pages: List[Page] = []
    index = 0
    for f in upload.files:
        for n in range(f.page_count):
            pages.append(Page(
                upload_id=upload.upload_id,
                file_path=f.path,
                page_index=index,
                page_no_in_file=n,
                image_ref=f"{f.path}#page{n}" if f.media_type == "pdf_scan" else f.path,
            ))
            index += 1
    return pages
