# pilot-kit — Phase 1 pilot starter kit (issue #108)

A complete **synthetic** pilot kit for Chapter 3 《能量的转化与守恒》
（浙教版 Science, Grade 9 Vol. 1), built so every downstream consumer —
OCR evaluation (#111), skill-taxonomy confirmation (#112), the teacher
console (#167) — can run end-to-end **now**, before real field materials
exist. Real materials swap in during Phase 2 by replacing file
*contents*, never file *shapes*.

> **Everything in this folder is invented test data.** Students are IDs
> only (`S-001` … `S-005`); there are no names, no real handwriting, no
> real scores anywhere. The "teacher" marks and judgments are TEST
> placeholders written against the synthetic papers. Do not treat any
> of it as field data, and never paste real student material into these
> files without the anonymization steps in
> `../docs/field-materials-checklist.md`.

## What's inside

| Path | What it is |
|---|---|
| `assignment/questions.json` | The template assignment **A-CH3-01**: full 12-question set (100 points) with 参考答案， solution steps and 评分说明 per question/part. Shape mirrors `review.models.Question` plus ingestion layout fields. |
| `assignment/teacher-key.md` | Human-readable 教师版 (answers + 评分说明）, generated from `questions.json` — `questions.json` is the source of truth. |
| `assignment/template.json` | Page layout in the ingestion pipeline's exact shape (`AssignmentTemplate` / `QuestionSpec` / `Region`, one template per printed page — see the file's `_note` for why). |
| `papers/manifest.json` | The 5 uploads: files, media types, per-item points earned, totals (97 / 82 / 63 / 57 / 37), and each paper's planted defects. |
| `papers/S-00x/page-1.png`, `page-2.png`, `paper.pdf` | Rendered "photos" of the printed-and-marked sheets: printed questions, handwritten-style answers in 5 different styles, red-pen √ / × / scores / comments. Defects include cross-outs and rewrites (S-001 Q10, S-004 Q3/Q8) and one **low-quality photo** paper (S-005: rotated, blurred, darkened; Q9 and Q12-blank3 unreadable). |
| `papers/S-00x/answer-records.json` | Ingestion `AnswerRecord` dicts — the ground truth of what is on each paper, incl. grading marks and per-item OCR reliability. 18 items × 5 students. |
| `papers/S-00x/evidence-records.json` | Evidence-ledger `EvidenceRecord` dicts for the skill-mapped items (the taxonomy's input view). S-004's Q8 keeps its crossed-out first attempt as a separate record linked by `correction_of`. |
| `judgments/weakest-skill-judgments.json` | TEST weakest-skill （薄弱点） judgments for 2 students (S-003 × `ch3-estimate-average-power`, S-004 × `ch3-friction-work`), each with a stated basis, in the exact `taxonomy.WeakPointProposal` record shape the teacher will later produce. |
| `confirmation-checklist.md` | The template confirmation checklist: every open question the kit had to decide alone, its test-data answer marked **ASSUMED**, and what Phase 2 replaces it with. Success criteria and review-time budget are deliberately **not** assumed. |
| `tools/paper_data.py` | Single source of truth for the five papers (answers, marks, reliabilities, defects). |
| `tools/build_papers.py` | Regenerates all rendered pages + per-paper JSONs + the manifest from `questions.json` + `paper_data.py`. Deterministic. |
| `tools/run_end_to_end.py` | Smoke driver: runs the ingestion pipeline over all 5 papers against the kit template, exercises `ingestion.evaluate` (incl. catching a flipped high-reliability read), and runs `taxonomy.diagnose.propose_weak_points` over all kit evidence — the diagnosis independently proposes the same two (student, skill) pairs the TEST judgments name. |
| `tests/test_pilot_kit.py` | Structural tests: assignment integrity, record validity through the real `AnswerRecord.from_dict` / `EvidenceRecord.from_dict`, privacy-guard pass over every record, score/rubric consistency, defect coverage. |

## Run it

```bash
cd homework-pilot/pilot-kit
python3 tools/build_papers.py          # regenerate papers (needs Pillow + Noto CJK fonts)
python3 tools/run_end_to_end.py        # end-to-end smoke run (all checks)
python3 -m unittest discover -s tests -v
```

## How the consumers use it

- **OCR evaluation (#111):** script any recognizer against
  `papers/*/answer-records.json` as ground truth, or follow
  `run_end_to_end.py` §2 (labeled set + `evaluate()` + the review-queue
  split at the pipeline's 0.8 threshold — S-005 lands 8 of 18 items in
  the review list, by design).
- **Taxonomy confirmation (#112):** feed `evidence-records.json` via
  `EvidenceInput.from_dict` into `propose_weak_points` — see
  `run_end_to_end.py` §3. Skills with no v1-taxonomy sample (Q5, Q9,
  Q10) intentionally produce answer records but no evidence records.
- **Teacher console (#167):** the kit's evidence records are in the
  `EvidenceRecord` shape the console's `RecognitionItem` mirrors, and
  the judgments are `SkillAssessment`-shaped confirmed hypotheses, so
  the console's five views can be populated from the kit once the
  console's data loader replaces its demo fixtures (the console itself
  is PR #168; the kit was verified against its view models during
  development).

## Phase 2 swap-in rules

1. Replace contents, keep shapes: real assignment → `assignment/`,
   real anonymized papers → `papers/` (same per-student files), real
   teacher judgments → `judgments/`.
2. Every **ASSUMED** answer in `confirmation-checklist.md` gets replaced
   by the teacher's real answer and un-marked, one by one.
3. Nothing synthetic survives into the live pilot: if a file still says
   TEST/synthetic when real materials land, it has not been swapped yet.
