"""End-to-end ingestion pipeline: upload -> pages -> sub-questions -> match -> recognize.

``run_pipeline`` is the single entry point the pilot uses:
1. expand the upload into pages (photos or scanned PDFs),
2. segment each page into sub-question items via the assignment template,
3. match each page to a student (exact ID+assignment match links;
   anything uncertain goes to the teacher confirmation queue —
   never auto-guessed),
4. recognize handwriting + grading marks per item, routing
   below-threshold items to the review list,
5. emit ``AnswerRecord`` lists per linked student.

``PipelineResult`` carries everything the teacher UI / downstream
stages need: records, the confirmation queue, and review items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from matching import IDReader, TeacherReviewQueue, match_pages
from models import AnswerRecord, AssignmentTemplate, Upload
from recognizer import Recognizer, recognize_all, recognitions_to_records
from segmentation import expand_pages, segment_upload


@dataclass
class PipelineResult:
    upload_id: str
    records: List[AnswerRecord] = field(default_factory=list)
    records_by_student: Dict[str, List[AnswerRecord]] = field(default_factory=dict)
    review_queue: TeacherReviewQueue = field(default_factory=TeacherReviewQueue)
    recognition_review: list = field(default_factory=list)  # ReviewItem list
    pages_linked: int = 0
    pages_queued: int = 0


def run_pipeline(upload: Upload, template: AssignmentTemplate,
                 id_reader: IDReader, recognizer: Recognizer,
                 known_students: List[str],
                 match_confidence: float = 0.9,
                 recognition_threshold: float = 0.8) -> PipelineResult:
    pages = expand_pages(upload)
    items = segment_upload(upload, template)
    match_results, queue = match_pages(pages, id_reader, known_students,
                                       min_confidence=match_confidence)

    result = PipelineResult(upload_id=upload.upload_id, review_queue=queue)
    items_by_page = {}
    for it in items:
        items_by_page.setdefault(it.page.page_index, []).append(it)

    for mr in match_results:
        if not mr.linked:
            result.pages_queued += 1
            continue
        result.pages_linked += 1
        page_items = items_by_page.get(mr.page.page_index, [])
        accepted, review = recognize_all(page_items, recognizer,
                                         threshold=recognition_threshold)
        result.recognition_review.extend(review)
        recs = recognitions_to_records(accepted, mr.student_id,
                                       mr.assignment_number or "")
        result.records.extend(recs)
        result.records_by_student.setdefault(mr.student_id, []).extend(recs)
    return result
