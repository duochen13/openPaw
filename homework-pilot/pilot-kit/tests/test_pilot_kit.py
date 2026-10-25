"""Tests for the Phase 1 pilot starter kit (issue #108).

Run from the pilot-kit directory:

    python3 -m unittest discover -s tests -v

What is covered here (the end-to-end *behavior* — pipeline round-trip,
OCR evaluation, taxonomy diagnosis — is covered by
``tools/run_end_to_end.py``, which one test below executes):

* assignment integrity: 12 questions, 100 points, every question has a
  reference answer + solution steps + 评分说明； skill ids exist in the
  Ch.3 taxonomy; the layout template covers exactly the same items.
* record validity: every answer record parses through
  ``ingestion.models.AnswerRecord.from_dict`` and every evidence record
  through ``evidence.models.EvidenceRecord.from_dict`` (each in a
  subprocess, following that package's own import convention).
* privacy: every kit JSON record passes the privacy package's
  ``assert_id_only``; student ids match ``S-\\d{3}``; nothing else
  identifies a student.
* papers: 5 papers, score spread high/mid/low, per-paper totals match
  the rubric math in ``tools/paper_data.py``; rendered pages exist,
  differ across students (handwriting variety), include cross-outs and
  exactly one flagged low-quality photo paper.
* judgments: exactly 2 TEST weakest-skill judgments, confirmed status,
  stated basis, basis ids resolving into the kit's evidence records.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
HW = KIT.parent
sys.path.insert(0, str(KIT / "tools"))

import paper_data  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_guard():
    spec = importlib.util.spec_from_file_location(
        "privacy_guard", HW / "privacy" / "guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestAssignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qdata = load_json(KIT / "assignment" / "questions.json")
        cls.template = load_json(KIT / "assignment" / "template.json")
        taxonomy = load_json(HW / "taxonomy" / "skills_ch3_v1.json")
        cls.skill_ids = {s["id"] for s in taxonomy["skills"]}

    def test_twelve_questions_hundred_points(self):
        questions = self.qdata["questions"]
        self.assertEqual(len(questions), 12)
        total = sum(sum(q["points"].values()) for q in questions)
        self.assertEqual(total, 100)
        self.assertEqual(self.qdata["meta"]["total_points"], 100)

    def test_every_question_complete(self):
        for q in self.qdata["questions"]:
            self.assertTrue(q["stem"], q["id"])
            self.assertTrue(q["answer"], q["id"])
            self.assertTrue(q["solution_steps"], q["id"])
            self.assertTrue(q["scoring_notes"], q["id"])
            for skill in q["skill_ids"]:
                self.assertIn(skill, self.skill_ids, q["id"])
            for skill in q.get("part_skill_ids", {}).values():
                self.assertIn(skill, self.skill_ids, q["id"])

    def test_template_covers_same_items(self):
        def items_of(parts_owner):
            out = set()
            for q in parts_owner:
                if q["parts"]:
                    out |= {f"{q['id']}#{p}" for p in q["parts"]}
                else:
                    out.add(q["id"])
            return out
        template_items = set()
        for page in self.template["pages"]:
            template_items |= items_of(page["questions"])
        question_items = items_of(self.qdata["questions"])
        self.assertEqual(template_items, question_items)
        self.assertEqual(template_items, set(paper_data.ITEM_POINTS))


class TestRecordsValidity(unittest.TestCase):
    def _run_validator(self, package_dir: str, snippet: str) -> None:
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            cwd=HW / package_dir, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0,
                         f"{package_dir} validation failed:\n{proc.stdout}\n{proc.stderr}")

    def test_answer_records_parse_via_ingestion_models(self):
        snippet = (
            "import json, glob\n"
            "from models import AnswerRecord\n"
            "n = 0\n"
            "for f in glob.glob('../pilot-kit/papers/S-*/answer-records.json'):\n"
            "    for r in json.load(open(f, encoding='utf-8')):\n"
            "        AnswerRecord.from_dict(r); n += 1\n"
            "assert n == 90, n\n"
            "print('answer records ok:', n)\n"
        )
        self._run_validator("ingestion", snippet)

    def test_evidence_records_parse_via_evidence_models(self):
        snippet = (
            "import json, glob\n"
            "from models import EvidenceRecord\n"
            "n = 0\n"
            "for f in glob.glob('../pilot-kit/papers/S-*/evidence-records.json'):\n"
            "    for r in json.load(open(f, encoding='utf-8')):\n"
            "        EvidenceRecord.from_dict(r); n += 1\n"
            "assert n == 71, n\n"
            "print('evidence records ok:', n)\n"
        )
        self._run_validator("evidence", snippet)

    def test_end_to_end_driver(self):
        proc = subprocess.run(
            [sys.executable, str(KIT / "tools" / "run_end_to_end.py")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0,
                         f"end-to-end failed:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("ALL CHECKS PASSED", proc.stdout)


class TestPrivacy(unittest.TestCase):
    def test_all_records_are_id_only(self):
        guard = load_guard()
        checked = 0
        for path in (KIT / "papers").rglob("*.json"):
            data = load_json(path)
            records = data["papers"] if isinstance(data, dict) and "papers" in data else data
            for record in records:
                guard.assert_id_only(record, where=str(path))
                checked += 1
        judgments = load_json(KIT / "judgments" / "weakest-skill-judgments.json")
        for record in judgments["judgments"]:
            guard.assert_id_only(record, where="judgments")
            checked += 1
        self.assertGreater(checked, 160)

    def test_student_id_format(self):
        manifest = load_json(KIT / "papers" / "manifest.json")
        for paper in manifest["papers"]:
            self.assertRegex(paper["student_id"], r"^S-\d{3}$")


class TestPapers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(KIT / "papers" / "manifest.json")

    def test_five_papers_with_score_spread(self):
        papers = self.manifest["papers"]
        self.assertEqual(len(papers), 5)
        totals = sorted(p["total_score"] for p in papers)
        self.assertGreaterEqual(totals[-1], 90)   # at least one high
        self.assertTrue(any(55 <= t <= 85 for t in totals))  # a middle
        self.assertLessEqual(totals[0], 45)       # at least one low
        for p in papers:
            self.assertEqual(p["total_points"], 100)
            self.assertEqual(sum(p["points_earned"].values()), p["total_score"])

    def test_totals_match_rubric_math(self):
        for p in self.manifest["papers"]:
            entries = paper_data.PAPERS[p["student_id"]]["items"]
            expect = {k: paper_data.earned_points(k, entries[k])
                      for k in paper_data.ITEM_POINTS}
            self.assertEqual(p["points_earned"], expect, p["student_id"])

    def test_rendered_files_exist_and_vary(self):
        digests = set()
        for p in self.manifest["papers"]:
            d = KIT / "papers" / p["student_id"]
            for name in ("page-1.png", "page-2.png", "paper.pdf",
                         "answer-records.json", "evidence-records.json"):
                f = d / name
                self.assertTrue(f.exists() and f.stat().st_size > 1000,
                                f"{p['student_id']}/{name}")
            import hashlib
            digests.add(hashlib.sha256((d / "page-1.png").read_bytes()).hexdigest())
        self.assertEqual(len(digests), 5, "each paper renders differently")

    def test_defect_coverage(self):
        defects = {p["student_id"]: " ".join(p["defects"])
                   for p in self.manifest["papers"]}
        low_quality = [s for s, d in defects.items() if "LOW-QUALITY" in d]
        self.assertEqual(len(low_quality), 1)
        crossed = [sid for sid, paper in paper_data.PAPERS.items()
                   if any(e.get("crossed_out") for e in paper["items"].values())]
        self.assertGreaterEqual(len(crossed), 2)
        unreadable = [r for r in load_json(KIT / "papers" / low_quality[0]
                                           / "answer-records.json")
                      if r["student_answer"] is None]
        self.assertGreaterEqual(len(unreadable), 1)


class TestJudgments(unittest.TestCase):
    def test_two_confirmed_judgments_with_basis(self):
        data = load_json(KIT / "judgments" / "weakest-skill-judgments.json")
        self.assertTrue(data["synthetic"])
        judgments = data["judgments"]
        self.assertEqual(len(judgments), 2)
        evidence_ids = set()
        for sid in paper_data.PAPERS:
            for r in load_json(KIT / "papers" / sid / "evidence-records.json"):
                evidence_ids.add(r["record_id"])
        for j in judgments:
            self.assertEqual(j["status"], "confirmed")
            self.assertTrue(j["basis_note"])
            self.assertTrue(j["basis_record_ids"])
            for rid in j["basis_record_ids"]:
                self.assertIn(rid, evidence_ids)
            self.assertTrue(any(a["kind"] == "teacher_confirm" for a in j["audit"]))


if __name__ == "__main__":
    unittest.main()
