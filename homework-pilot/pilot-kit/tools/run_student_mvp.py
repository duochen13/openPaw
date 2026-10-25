#!/usr/bin/env python3
"""Student MVP pipeline run on the synthetic kit (issue #176).

Grades all 5 synthetic papers with the grading pipeline and checks the
output against the kit's own TEST ground truth:

1. MODE A (red-pen marks present, the designed flow) -- every item's
   verdict must equal the truth derived from the kit's grading marks:
   decisive mark -> that verdict; partial score / comment-only / no
   mark -> 待确认. Nothing else is an acceptable answer.
2. MODE B (marks withheld) -- the answer key alone judges the items
   whose comparison is well-defined (multiple-choice letters,
   fill-blank values, single numeric final values); every item whose
   key is free text (worked solutions, estimations, explanations)
   must come out 待确认. A single decided verdict there is a guess
   and fails the run.
3. CONFIRM/EXPORT -- one pending item per paper is confirmed as a
   student would, and the labeled examples are exported to JSONL and
   checked ID-only (privacy.guard.assert_id_only).

Exit code 0 = all checks passed. Run from anywhere:
    python3 homework-pilot/pilot-kit/tools/run_student_mvp.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
HW = KIT.parent
sys.path.insert(0, str(HW))

from grading.backends import expected_verdicts, load_kit_records  # noqa: E402
from grading.confirm import (  # noqa: E402
    apply_confirmation,
    export_labeled_examples,
    write_jsonl,
)
from grading.judge import comparison_mode, resolve_key_answers  # noqa: E402
from grading.backends import load_kit_questions  # noqa: E402
from grading.pipeline import grade_kit_paper  # noqa: E402

STUDENTS = ["S-001", "S-002", "S-003", "S-004", "S-005"]
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


def main() -> int:
    modes: dict[str, str | None] = {}
    for question in load_kit_questions(KIT):
        for item_key, key in resolve_key_answers(question).items():
            modes[item_key] = comparison_mode(question, key)

    total_decided = total_pending = 0
    for sid in STUDENTS:
        paper = grade_kit_paper(KIT, sid)
        expected = expected_verdicts(load_kit_records(KIT, sid))
        mismatches = [
            f"{item.item_key}: got {item.verdict}, want {expected[item.item_key]}"
            for item in paper.items
            if item.verdict != expected[item.item_key]
        ]
        queued = len(paper.confirmation_queue())
        print(
            f"{sid}: 对 {sum(1 for i in paper.items if i.verdict == '对')}, "
            f"错 {sum(1 for i in paper.items if i.verdict == '错')}, "
            f"待确认 {len(paper.pending())} (confirmation queue incl. "
            f"low-reliability reads: {queued})"
        )
        check(not mismatches,
              f"{sid} mode A verdicts match kit ground truth"
              + ("" if not mismatches else ": " + "; ".join(mismatches)))
        total_decided += len(paper.decided())
        total_pending += len(paper.pending())

        paper_b = grade_kit_paper(KIT, sid, include_marks=False)
        guessed = [
            item.item_key for item in paper_b.items
            if modes[item.item_key] is None and item.verdict != "待确认"
        ]
        check(not guessed,
              f"{sid} mode B: no verdicts on non-comparable items"
              + ("" if not guessed else ": " + ", ".join(guessed)))

        # Confirm the first pending item that carries a proposal, the
        # way a student would, and export the labeled example.
        target = next(
            (i for i in paper.items if i.proposed_verdict), None)
        if target is not None:
            confirmed = apply_confirmation(
                paper, target.item_key, accept_proposal=True)
            examples = export_labeled_examples(confirmed)
            check(len(examples) == 1
                  and examples[0]["system_verdict"] == "待确认",
                  f"{sid} confirm+export keeps the system/student pair")

    check(total_decided == 67 and total_pending == 23,
          f"kit census: 67 decided / 23 pending across 5 papers "
          f"(got {total_decided}/{total_pending})")

    with tempfile.TemporaryDirectory() as tmp:
        # S-001's only pending item (Q10, score mark, free-text key)
        # carries no proposal: the student decides manually and the
        # reference answer is supplied, exercising the no-lean path.
        paper = grade_kit_paper(KIT, "S-001")
        pending = paper.pending()
        check(len(pending) == 1 and not pending[0].proposed_verdict,
              "S-001's pending item honestly has no proposal to confirm")
        confirmed = apply_confirmation(
            paper, pending[0].item_key, verdict="对",
            reference_answer="（1）1.2×10⁷ J；（2）4×10⁴ W")
        out = Path(tmp) / "labeled.jsonl"
        written = write_jsonl(export_labeled_examples(confirmed), out)
        check(written == 1 and out.read_text("utf-8").count("\n") == 1,
              "labeled examples write as JSONL")

    if failures:
        print(f"\n{len(failures)} CHECK(S) FAILED")
        return 1
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
