#!/usr/bin/env python3
"""End-to-end smoke run of the Phase 1 pilot starter kit (issue #108).

Proves the kit is sufficient to run the existing pipeline stages
end-to-end, with no real student data anywhere:

1. INGESTION — per-page ``AssignmentTemplate`` objects are built from
   ``assignment/template.json``; each synthetic paper is pushed through
   ``ingestion.pipeline.run_pipeline`` with a scripted ID reader and a
   ``TestDoubleRecognizer`` scripted from the kit's own answer records.
   Accepted records must reproduce the kit's ground truth exactly;
   below-threshold reads (incl. S-005's low-quality items) must land in
   the review list instead.
2. OCR EVALUATION — ``ingestion.evaluate.evaluate`` runs on a labeled
   set built from S-001's records (accuracy 1.0 against the scripted
   recognizer), and a deliberately flipped grading-mark read must be
   caught as an error — the eval harness works on kit data.
3. TAXONOMY CONFIRMATION — every ``evidence-records.json`` is adapted
   via ``taxonomy.EvidenceInput.from_dict`` and fed to
   ``taxonomy.diagnose.propose_weak_points``. The two TEST weakest-skill
   judgments in ``judgments/weakest-skill-judgments.json`` (constructed
   as ``taxonomy.WeakPointProposal`` objects, i.e. the real record
   shape) must be independently proposed by the diagnosis from the
   kit's evidence, and every basis record id must resolve.

Exit code 0 = all checks passed. Run from anywhere:
    python3 homework-pilot/pilot-kit/tools/run_end_to_end.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
HW = KIT.parent

# ingestion is a flat-import package (its own tests insert its dir);
# taxonomy is a package imported from homework-pilot/.
sys.path.insert(0, str(HW / "ingestion"))
sys.path.insert(1, str(HW))

FAILURES: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok  " if cond else "FAIL  ") + label)
    if not cond:
        FAILURES.append(label)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    import models as ing  # ingestion.models (flat import, see above)
    from matching import IDReader
    from pipeline import run_pipeline
    from recognizer import GRADING_MARK, HANDWRITING, TestDoubleRecognizer
    from segmentation import segment_upload
    from evaluate import LabeledItem, evaluate
    from taxonomy.diagnose import propose_weak_points
    from taxonomy.models import (AuditEntry, EvidenceInput, ProposalStatus,
                                 WeakPointProposal)
    from taxonomy.taxonomy import load_taxonomy

    template_data = load_json(KIT / "assignment" / "template.json")
    manifest = load_json(KIT / "papers" / "manifest.json")
    taxonomy = load_taxonomy()
    taught = set(taxonomy.skill_ids())

    def page_template(page: dict) -> ing.AssignmentTemplate:
        questions = []
        for q in page["questions"]:
            questions.append(ing.QuestionSpec(
                id=q["id"], kind=ing.QuestionKind(q["kind"]),
                parts=q["parts"],
                regions={p: ing.Region(**r) for p, r in q["regions"].items()},
            ))
        return ing.AssignmentTemplate(
            assignment_number=template_data["assignment_number"],
            title=template_data["title"], questions=questions,
            id_region=ing.Region(**template_data["id_region"]),
            id_region_page=template_data["id_region_page"],
        )

    templates = {p["page_index"]: page_template(p) for p in template_data["pages"]}

    class KitIDReader(IDReader):
        """Reads the ID block the kit prints on every sheet."""

        def __init__(self, student_id: str) -> None:
            self.student_id = student_id

        def read_id(self, page):
            return (self.student_id, template_data["assignment_number"], 0.99)

    print("== 1. ingestion pipeline on the kit template + papers ==")
    for paper in manifest["papers"]:
        sid = paper["student_id"]
        truth = {r["item_key"]: r
                 for r in load_json(KIT / "papers" / sid / "answer-records.json")}
        script = {}
        for key, r in truth.items():
            if r["student_answer"] is not None:
                script[(key, HANDWRITING)] = {"text": r["student_answer"],
                                              "reliability": r["reliability"]}
            if r["grading_mark"] is not None:
                entry = {"mark": r["grading_mark"]["kind"],
                         "reliability": r["reliability"]}
                if r["grading_mark"]["score"]:
                    entry["score"] = r["grading_mark"]["score"]
                if r["grading_mark"]["kind"] == "comment":
                    entry["text"] = r["grading_mark"]["comment"]
                script[(key, GRADING_MARK)] = entry
        recognizer = TestDoubleRecognizer(script)
        got, reviewed = {}, set()
        for page_index, template in templates.items():
            f = paper["files"][page_index]
            upload = ing.Upload(
                upload_id=f"{paper['upload_id']}-P{page_index + 1}",
                files=[ing.UploadedFile(path=f["path"], media_type="photo",
                                        page_count=1)],
                uploaded_by="TEST (synthetic)",
                assignment_number=template_data["assignment_number"])
            result = run_pipeline(upload, template, KitIDReader(sid),
                                  recognizer, [p["student_id"] for p in manifest["papers"]])
            for rec in result.records:
                got[rec.item_key] = rec
            for item in result.recognition_review:
                reviewed.add(item.item.sub_question.item_key)
        expect_records = {k for k, r in truth.items() if r["reliability"] >= 0.8}
        check(set(got) == expect_records,
              f"{sid}: pipeline records == kit ground truth at/above threshold "
              f"({len(got)}/{len(truth)} items)")
        check(expect_records | reviewed == set(truth) and not (expect_records & reviewed),
              f"{sid}: every remaining item routed to the review list")
        mismatches = []
        for key in expect_records:
            rec, r = got[key], truth[key]
            mark = rec.grading_mark
            if (rec.student_answer != r["student_answer"]
                    or (mark.kind.value if mark else None) !=
                       (r["grading_mark"]["kind"] if r["grading_mark"] else None)
                    or (mark.score if mark else None) !=
                       (r["grading_mark"]["score"] if r["grading_mark"] else None)):
                mismatches.append(key)
        check(not mismatches, f"{sid}: record contents match ground truth {mismatches}")

    print("== 2. OCR evaluation harness on kit data ==")
    sid = "S-001"
    truth = load_json(KIT / "papers" / sid / "answer-records.json")
    upload = ing.Upload(upload_id="UP-EVAL", files=[ing.UploadedFile(
        path=f"papers/{sid}/page-1.png", media_type="photo", page_count=1)],
        uploaded_by="TEST (synthetic)",
        assignment_number=template_data["assignment_number"])
    items = {it.sub_question.item_key: it
             for it in segment_upload(upload, templates[0])}
    script, labeled = {}, []
    for r in truth:
        if items.get(r["item_key"]) is None:
            continue  # page-2 items are not in this page's segmentation
        if r["student_answer"] is not None:
            script[(r["item_key"], HANDWRITING)] = {
                "text": r["student_answer"], "reliability": r["reliability"]}
            labeled.append(LabeledItem(item=items[r["item_key"]],
                                       item_type=HANDWRITING,
                                       expected_text=r["student_answer"]))
        if r["grading_mark"] is not None:
            entry = {"mark": r["grading_mark"]["kind"],
                     "reliability": r["reliability"]}
            if r["grading_mark"]["score"]:
                entry["score"] = r["grading_mark"]["score"]
            script[(r["item_key"], GRADING_MARK)] = entry
            labeled.append(LabeledItem(
                item=items[r["item_key"]], item_type=GRADING_MARK,
                expected_mark=ing.GradingMarkKind(r["grading_mark"]["kind"]),
                expected_score=r["grading_mark"]["score"]))
    good = evaluate(TestDoubleRecognizer(script), labeled)
    check(good.accuracy == 1.0,
          f"eval on S-001 page 1: scripted recognizer scores {good.correct}/{good.total}")
    flipped = dict(script)
    flipped[("Q2", GRADING_MARK)] = {"mark": "wrong", "reliability": 0.93}
    bad = evaluate(TestDoubleRecognizer(flipped), labeled)
    silent = [e for e in bad.errors if e["reliability"] >= 0.8]
    check(bad.accuracy < 1.0 and len(silent) == 1
          and silent[0]["item_key"] == "Q2",
          "eval catches a flipped high-reliability grading-mark read "
          f"(errors={len(bad.errors)}, silent={len(silent)})")

    print("== 3. taxonomy diagnosis + TEST weakest-skill judgments ==")
    all_records, by_id = [], {}
    for paper in manifest["papers"]:
        for rec in load_json(KIT / "papers" / paper["student_id"] / "evidence-records.json"):
            by_id[rec["record_id"]] = rec
            all_records.append(EvidenceInput.from_dict(rec))
    result = propose_weak_points(all_records, taught,
                                 student_ids=[p["student_id"] for p in manifest["papers"]])
    proposed = {(p.student_id, p.skill_id) for p in result.proposals}
    judgments = load_json(KIT / "judgments" / "weakest-skill-judgments.json")["judgments"]
    for j in judgments:
        proposal = WeakPointProposal(
            student_id=j["student_id"], skill_id=j["skill_id"],
            status=ProposalStatus(j["status"]),
            is_provisional=j["is_provisional"],
            hypothesis_strength=j["hypothesis_strength"],
            basis_record_ids=j["basis_record_ids"], basis_note=j["basis_note"],
            modified_skill_id=j["modified_skill_id"],
            audit=[AuditEntry(kind=a["kind"],
                              from_status=ProposalStatus(a["from_status"]),
                              to_status=ProposalStatus(a["to_status"]),
                              note=a["note"]) for a in j["audit"]],
            proposal_id=j["proposal_id"])
        check(proposal.skill_id in taught,
              f"{proposal.proposal_id}: skill {proposal.skill_id} exists in taxonomy")
        check(all(rid in by_id for rid in proposal.basis_record_ids),
              f"{proposal.proposal_id}: basis records resolve to kit evidence")
        check((proposal.student_id, proposal.skill_id) in proposed,
              f"{proposal.proposal_id}: diagnosis independently proposes "
              f"{proposal.student_id} x {proposal.skill_id}")

    print(f"\n{'ALL CHECKS PASSED' if not FAILURES else 'FAILURES: ' + str(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
