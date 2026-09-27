# homework-pilot ingestion + OCR

Implements [issue #110](https://github.com/duochen13/openPaw/issues/110)
(homework ingestion) and
[issue #111](https://github.com/duochen13/openPaw/issues/111)
(OCR with reliability scores + manual-entry fallback).

Pilot context: teacher uploads photos / scanned PDFs of graded homework
(Chapter 3 《能量的转化与守恒》, 浙教版 Science Grade 9). Students have no
accounts — everything is paper-based, identified by student ID.

## Pipeline

```
upload (photos / scanned PDFs)
  -> pages                      (segmentation.expand_pages)
  -> sub-question items         (segmentation.segment_upload, driven by AssignmentTemplate)
  -> student matching           (matching.match_pages)
       exact ID + assignment match -> linked
       anything uncertain       -> TeacherReviewQueue (NEVER auto-guessed)
  -> recognition                (recognizer.recognize_all: handwriting + grading marks)
       reliability >= threshold -> accepted -> AnswerRecord (source="ocr")
       reliability < threshold  -> teacher review list
  -> AnswerRecord list per student -> downstream (diagnosis, assembly, print)
```

Or skip OCR entirely for the pilot:

```
teacher/assistant typed rows -> manual_entry.commit_rows -> AnswerRecord (source="manual", reliability=1.0)
```

## Modules

| Module | Purpose |
|---|---|
| `models.py` | Dataclasses: `Upload`, `Page`, `AssignmentTemplate`, `SubQuestionRef`, `MatchResult`, `Recognition`, `AnswerRecord` (+ documented dict contract for downstream) |
| `segmentation.py` | Upload → pages; pages → sub-question items via the declarative template (MC, multi-blank fill-in, Q11/Q12 sub-parts recorded separately) |
| `matching.py` | Pluggable `IDReader` interface; exact-match linking; `TeacherReviewQueue` with candidates, `resolve()` / `mark_unmatched()` |
| `recognizer.py` | Pluggable `Recognizer` interface returning `(text/mark, reliability)` per item; deterministic `TestDoubleRecognizer`; threshold routing; OCR records merged per sub-question |
| `evaluate.py` | `evaluate(recognizer, labeled_set)` → per-item-type accuracy + reliability calibration; `go_no_go_report()` → pilot-ready vs needs-work verdicts |
| `manual_entry.py` | Human-in-the-loop fallback: `ManualEntrySession` API, `entries_from_rows()` / `commit_rows()` for scripted rows, `run_interactive_cli()` for prompting |
| `id_label.py` | Round-trip ID support: JSON manifest + minimal valid PDF label rendering student ID + assignment number (see limitation below) |
| `pipeline.py` | `run_pipeline()` — the single end-to-end entry point |
| `fixtures.py` | Synthetic fixtures (students S001–S010, assignment A-CH3-01, scripted ID readers, labeled eval set) |

## ID labels — honest limitation

`id_label.write_id_label_pdf` writes a **minimal but valid** single-page PDF
(hand-written PDF 1.4, built-in Helvetica) with the ID block as printable
text, plus a JSON manifest for machine-readable round-trip matching. It is
**not** a full typeset assignment — full print layout comes with #115's
export work. Print the label as a cover sheet, or have #115 embed the ID
block into the generated assignment PDFs.

## Status: built but unevaluated on real papers

The 5 sample papers from the field-materials issue (#108) do not exist yet,
so paper-dependent acceptance criteria are **built but unevaluated**:

- #110: upload → page → sub-question pipeline runs on synthetic fixtures;
  matching accuracy is measured by `evaluate()`-style matching tests, not on
  real papers; the confirmation queue works end-to-end; generated PDFs carry
  ID + assignment number via `id_label`.
- #111: per-item reliability + threshold routing works on synthetic data;
  `evaluate()` reports per-item-type accuracy (handwriting vs 批改痕迹） and
  flags would-be silent errors; the manual-entry fallback works end-to-end
  **now** on synthetic data — this is the path the pilot should use while
  OCR accuracy is being measured.

Re-run `evaluate()` + `go_no_go_report()` on the real 5-paper set once #108
lands; treat no verdict as trustworthy before that.

## Tests

From this directory:

```
python3 -m unittest discover -s tests -v
```

14 tests, all synthetic: clean match links; ambiguous ID → queue with
candidates; below-threshold recognition → review; eval accuracy/calibration
with a deliberate high-reliability miss; manual entry round-trip through the
downstream dict format; valid label PDF; manifest round-trip; full pipeline
(clean upload links, ambiguous upload queues everything).
