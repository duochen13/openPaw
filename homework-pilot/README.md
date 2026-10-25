# homework-pilot — personalized science homework pilot （个性化科学作业试点）

A pilot for generating **personalized science homework** driven by a long-term per-student learning record （学习记录）.
The pilot teacher is Daniel's mother: she teaches **2 classes, ~80 students**, and the initial content scope is
**Chapter 3 《能量的转化与守恒》 (Energy Conversion and Conservation)** of **浙教版 Science, Grade 9 Vol. 1**
(浙教版科学九年级上册） — bound to the teacher's actual textbook and teaching pace.

**Direction update (2026-10-25, [#176](https://github.com/duochen13/openPaw/issues/176)):** the product now starts
from the **student side**. The MVP is a student uploading a scanned PDF of a paper they have already completed and
getting a per-question verdict （对 / 错 / 待确认； sources in priority order: teacher's red-pen marks > answer key >
model self-solve), with a confirmation queue whose confirmations become labeled training data. The `webui/` frontend
was pivoted to this MVP on PR #168; the teacher-loop packages below (evidence / ingestion / taxonomy / assembly /
review) are unchanged and remain the longer-term backend direction.

## Flow

1. Teacher uploads graded paper homework (photos or scanned PDFs: 原题， 参考答案， graded student work).
2. System matches student / homework / page / sub-question (小题） and recognizes student answers and grading marks (批改结果）.
3. Teacher confirms anything the system couldn't read reliably, and confirms or edits the weak-point hypotheses （薄弱点）.
4. Confirmed evidence updates each student's long-term evidence ledger.
5. System assembles each student's official homework: a dynamic mix of 当前学习 (current learning), 薄弱点练习 (weak-point practice), and 旧知识复习 (review).
6. Teacher reviews, replaces, or adjusts at the shared-question level, then downloads student PDFs plus a separate teacher key （教师版） with answers and scoring notes （评分说明）.
7. Students complete the homework **on paper**; the next upload cycle feeds new evidence back in.

Students never answer online and need no product account.

## Design doc

The product design lives in `homwork-pilot/design.md` on `main` (note the folder-name typo — "homwork-pilot").
[PR #118](https://github.com/duochen13/openPaw/pull/118) proposing the rename to `homework-pilot/` is **open, not merged**,
so the design doc still lives under the misspelled folder.

## Module map

| Directory | Issue(s) | PR | What it does | Tests |
|---|---|---|---|---|
| `homework-pilot/evidence/` | [#109](https://github.com/duochen13/openPaw/issues/109) | [#122](https://github.com/duochen13/openPaw/pull/122) | Student × skill evidence ledger: `EvidenceRecord` (per-question evidence, incl. 批改结果， 订正 linkage, OCR reliability), `SkillAssessment` (5-state teaching judgment + provisional 薄弱点 flag, never a %), `AuditEntry` | `tests/test_ledger.py` in PR |
| `homework-pilot/ingestion/` | [#110](https://github.com/duochen13/openPaw/issues/110) [#111](https://github.com/duochen13/openPaw/issues/111) | [#123](https://github.com/duochen13/openPaw/pull/123) | Homework upload: student/page/question matching + OCR of answers and grading marks with reliability scores and manual-entry fallback | `tests/test_pipeline.py` in PR |
| `homework-pilot/taxonomy/` | [#112](https://github.com/duochen13/openPaw/issues/112) | [#124](https://github.com/duochen13/openPaw/pull/124) | Skill taxonomy for Chapter 3 and weak-point diagnosis from ledger evidence | `tests/test_diagnose.py` in PR |
| `homework-pilot/assembly/` | [#113](https://github.com/duochen13/openPaw/issues/113) [#114](https://github.com/duochen13/openPaw/issues/114) | [#125](https://github.com/duochen13/openPaw/pull/125) | Personalized assembly rules engine (per-student 当前/薄弱点/复习 mix, teacher budget cap, 共同题） + AI question generation with pre-release validation | `tests/test_engine.py`, `test_generate.py`, `test_review_queue.py` in PR |
| `homework-pilot/review/` | [#115](https://github.com/duochen13/openPaw/issues/115) | [#127](https://github.com/duochen13/openPaw/pull/127) | Teacher review workflow （审核： approve/reject/replace/adjust at shared-question level) + print-ready PDF export (student sheets + teacher key) | `tests/test_export.py`, `tests/test_review.py` in PR |
| `homework-pilot/privacy/` | [#117](https://github.com/duochen13/openPaw/issues/117) | [#121](https://github.com/duochen13/openPaw/pull/121) | Privacy guard: student-ID-only enforcement, no names anywhere | `tests/test_guard.py` in PR |
| `homework-pilot/webui/` | [#176](https://github.com/duochen13/openPaw/issues/176) (opened as [#167](https://github.com/duochen13/openPaw/issues/167)) | this PR | Student-side MVP UI (Muse desktop design language): one self-contained HTML with 试卷 / 结果 / 待确认， bound to synthetic demo fixtures. Originally a teacher console (#167); pivoted to the student MVP per #176 — the old console design is preserved in this branch's git history | `tests/test_webui.py` in PR |
| `homework-pilot/docs/` | [#108](https://github.com/duochen13/openPaw/issues/108) [#116](https://github.com/duochen13/openPaw/issues/116) [#117](https://github.com/duochen13/openPaw/issues/117) | [#120](https://github.com/duochen13/openPaw/pull/120) (checklist), [#119](https://github.com/duochen13/openPaw/pull/119) (protocol + tracking sheet), [#121](https://github.com/duochen13/openPaw/pull/121) (governance doc) | Field-materials checklist, validation protocol + pilot tracking sheet, privacy-governance doc | n/a (docs) |
| `homework-pilot/pilot-kit/` | [#108](https://github.com/duochen13/openPaw/issues/108) | this PR (Phase 1 kit) | Pilot starter kit (all **synthetic**): template assignment A-CH3-01 (questions + 参考答案 + 评分说明 + ingestion layout template), 5 rendered graded test papers with `AnswerRecord`/`EvidenceRecord` JSON, TEST weakest-skill judgments, template confirmation checklist (assumed answers marked) | `tests/test_pilot_kit.py` + `tools/run_end_to_end.py` (run from `pilot-kit/`) |

## Issue status

| Issue | Status |
|---|---|
| [#108](https://github.com/duochen13/openPaw/issues/108) pilot starter kit + field work | **Phase 1 DONE (this PR)** — synthetic test kit in `pilot-kit/` (template assignment, 5 test papers, TEST judgments, ASSUMED confirmation checklist); OCR evaluation + taxonomy confirmation run end-to-end on it. **Phase 2 still HUMAN** — real materials + teacher sign-off via `docs/field-materials-checklist.md` ([#120](https://github.com/duochen13/openPaw/pull/120)); the issue stays open until Phase 2 lands. |
| [#109](https://github.com/duochen13/openPaw/issues/109) evidence ledger | [#122](https://github.com/duochen13/openPaw/pull/122) open — data model implemented. |
| [#110](https://github.com/duochen13/openPaw/issues/110) + [#111](https://github.com/duochen13/openPaw/issues/111) ingestion/OCR | [#123](https://github.com/duochen13/openPaw/pull/123) open — ingestion + OCR with manual fallback. |
| [#112](https://github.com/duochen13/openPaw/issues/112) taxonomy | [#124](https://github.com/duochen13/openPaw/pull/124) open — taxonomy + diagnosis; still needs teacher sign-off on the skill list. |
| [#113](https://github.com/duochen13/openPaw/issues/113) + [#114](https://github.com/duochen13/openPaw/issues/114) assembly/generation | [#125](https://github.com/duochen13/openPaw/pull/125) open — assembly engine + question generation. |
| [#115](https://github.com/duochen13/openPaw/issues/115) review/export | [#127](https://github.com/duochen13/openPaw/pull/127) open — review workflow + PDF export. |
| [#116](https://github.com/duochen13/openPaw/issues/116) validation protocol | [#119](https://github.com/duochen13/openPaw/pull/119) open — pre-registered protocol + tracking sheet. |
| [#117](https://github.com/duochen13/openPaw/issues/117) privacy/governance | [#121](https://github.com/duochen13/openPaw/pull/121) open — governance doc + privacy guard. |
| [#167](https://github.com/duochen13/openPaw/issues/167) teacher console UI | this PR — built as a teacher console, then **pivoted to the student-side MVP (#176)** on the same branch; see the #176 row. |
| [#176](https://github.com/duochen13/openPaw/issues/176) student-side MVP | this PR — student uploads a completed paper scan (PDF) and gets per-question 对 / 错 / 待确认 verdicts with a confirmation queue. Demo fixtures only; live pipeline wiring and any real student data still gated on #108 Phase 2 (school stance / privacy). |

## How to run

Everything below works from a fresh clone with no build step. All commands were verified on the current `main` (2026-10-25).

### Prerequisites

- **Python 3.10+** (verified on 3.12). The packages, the demo, and the end-to-end run are **Python standard library only** — there is no `requirements.txt` and nothing to pip-install for them.
- Two corners need extras:
  - `review/` tests are pytest-style: `pip install pytest`. (stdlib `unittest` discovery finds 0 tests there — that is expected, not a failure.) A few export tests also call poppler's `pdftotext` / `pdfinfo` when available and skip otherwise.
  - Regenerating the synthetic pilot papers (`pilot-kit/tools/build_papers.py`) needs Pillow (`pip install pillow`) and Noto CJK fonts.

### Student web UI demo (`webui/`)

Run from `homework-pilot/`:

```bash
python3 -m webui                 # writes ./student-mvp.html
python3 -m webui /path/out.html  # or choose the output path
```

Expected output: `wrote student-mvp.html (34084 chars)`. Open the file in any browser — it is one self-contained HTML file (no server, no external assets) showing the 试卷 / 结果 / 待确认 views over synthetic demo fixtures (student ID S-023). Deep links: `?view=papers|result|confirm`, plus `&paper=<id>`.

### Tests

Per package, from `homework-pilot/`:

```bash
python3 -m unittest discover -s evidence/tests -t .    # 22 tests
python3 -m unittest discover -s ingestion/tests -t .   # 14 tests
python3 -m unittest discover -s taxonomy/tests -t .    # 26 tests
python3 -m unittest discover -s assembly/tests -t .    # 33 tests
python3 -m unittest discover -s privacy/tests -t .     # 25 tests
python3 -m unittest discover -s webui/tests -t .       # 24 tests
python3 -m pytest review/tests                         # 32 tests (pytest required, see above)
```

The `pilot-kit/` tests run from inside `pilot-kit/`:

```bash
cd pilot-kit
python3 -m unittest discover -s tests                  # 13 tests
```

Or the whole suite at once, from `homework-pilot/` (needs pytest):

```bash
python3 -m pytest                                      # 189 passed
```

### End-to-end smoke run (pilot-kit)

Proves the starter kit drives the real pipeline stages (ingestion → OCR evaluation → taxonomy diagnosis) end-to-end on synthetic data. Runnable from anywhere:

```bash
python3 homework-pilot/pilot-kit/tools/run_end_to_end.py
```

Expected: a series of `ok` lines ending in `ALL CHECKS PASSED`, exit code 0.

To regenerate the kit's synthetic papers (PDFs, page PNGs, manifest):

```bash
cd homework-pilot/pilot-kit
python3 tools/build_papers.py    # needs Pillow + Noto CJK fonts
```

Cross-package wiring (e.g. how `review` consumes `assembly` shapes, how `taxonomy` reads the `evidence` ledger) is documented in each package's own README — read there before wiring.

## Privacy

Student-ID-only: there is no name field anywhere in the repo. See `docs/privacy-governance.md` for the full governance doc.

## Still pending (not fabricated)

- Teacher sign-off on the skill taxonomy (#112) and on the validation protocol.
- Field materials (Phase 2 of #108): 5 **real** sample graded papers, the teacher's real assignment + reference answers, teacher consent + data-use consent forms. A synthetic stand-in kit exists (`pilot-kit/`) so engineering is not blocked meanwhile.
- Real question bank (current generator output is AI-drafted and unvalidated by the teacher).
- CJK font for print PDFs (PDF export is stdlib-only; Chinese typesetting needs a bundled font).
- Student UI wiring — a student-side MVP UI exists in `webui/` (#176, on the PR that began as the #167 teacher console) rendering demo fixtures; connecting it to the live upload → segmentation → transcription → verdict pipeline still waits on #108 field materials and the Phase 2 school-stance decision. Until then the pilot runs on scripts + generated PDFs.
