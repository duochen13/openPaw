# homework-pilot — personalized science homework pilot （个性化科学作业试点）

A pilot for generating **personalized science homework** driven by a long-term per-student learning record （学习记录）.
The pilot teacher is Daniel's mother: she teaches **2 classes, ~80 students**, and the initial content scope is
**Chapter 3 《能量的转化与守恒》 (Energy Conversion and Conservation)** of **浙教版 Science, Grade 9 Vol. 1**
(浙教版科学九年级上册） — bound to the teacher's actual textbook and teaching pace.

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

## Running tests

Each PR branch is self-contained: run its package tests from `homework-pilot/` with

```bash
python3 -m unittest discover -s <pkg>/tests -t .
```

Cross-PR wiring (e.g. how `review` consumes `assembly` shapes, how `taxonomy` reads the `evidence` ledger) is documented in each package's README on its PR branch — read there before wiring. Intended merge order: #122 (evidence) → #124 (taxonomy) → #125 (assembly) → #127 (review); #123 (ingestion), #121 (privacy), #119/#120 (docs) are independent. (As of writing, no homework-pilot module has merged to `main`.)

## Privacy

Student-ID-only: there is no name field anywhere in the repo. See `docs/privacy-governance.md` for the full governance doc.

## Still pending (not fabricated)

- Teacher sign-off on the skill taxonomy (#112) and on the validation protocol.
- Field materials (Phase 2 of #108): 5 **real** sample graded papers, the teacher's real assignment + reference answers, teacher consent + data-use consent forms. A synthetic stand-in kit exists (`pilot-kit/`) so engineering is not blocked meanwhile.
- Real question bank (current generator output is AI-drafted and unvalidated by the teacher).
- CJK font for print PDFs (PDF export is stdlib-only; Chinese typesetting needs a bundled font).
- Clickable teacher UI — the pilot runs on scripts + generated PDFs; review happens via the `ReviewSession` API until a UI is built.
