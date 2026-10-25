# Template Confirmation Checklist （模板确认清单） — Issue #108, Phase 1

> **What this is.** The design doc (`design.md`, 待确认事项） and issue #108 leave a set of
> questions that only the pilot teacher can answer. Phase 1 cannot wait for those answers, so
> the test kit in this folder is built on **assumed** answers. Every assumed answer below is
> marked **ASSUMED （假设）** and states what the test kit did with it, so Phase 2 can replace
> each assumption with the teacher's real answer **without changing any file shape** — only
> contents change.
>
> **What this is not.** It is not the field-materials collection checklist — that lives in
> `../docs/field-materials-checklist.md` (PR #120) and remains the Phase 2 collection tool,
> including consent and anonymization. This checklist is about the *template-level* questions
> the test kit had to decide on its own.
>
> Two items are deliberately **NOT assumed**: success criteria and acceptable review time.
> Issue #108 Phase 2 requires them to be set by the teacher before the pilot runs, with no
> fabricated numbers — so they are listed as open, with no test-data value.

## 1. Textbook version （教材版本）

- **Question:** Which textbook and printing does the class actually use?
- **Test-data answer: ASSUMED** — 浙教版 (Zhejiang Education Press) Science, Grade 9 Vol. 1,
  Chapter 3 《能量的转化与守恒》, following `design.md` and `taxonomy/skills_ch3_v1.json`.
- **What the kit did with it:** the template assignment (`assignment/questions.json`) is
  written to that chapter's scope; question stems reference the sample questions in
  `design.md`'s skill table (Q2–Q4, Q6–Q8, Q11, Q12).
- **Phase 2 must confirm:** exact edition/printing （版次）; whether the teacher's real
  Chapter 3 assignment matches this scope and ordering.

## 2. Answers on the original paper vs separate sheets （答案写在原卷还是另纸）

- **Question:** Do students write answers on the printed assignment itself, or on separate
  answer sheets?
- **Test-data answer: ASSUMED** — on the original paper （写在原卷上）, each question's
  answers directly under its stem.
- **What the kit did with it:** `assignment/template.json` regions are laid out for answers
  under each stem on the same sheet, and the five test papers are rendered that way
  (`papers/S-00x/page-*.png`). The ingestion segmentation is driven by this layout.
- **Phase 2 must confirm:** if the school uses separate answer sheets, the template regions
  (not the record shapes) are what changes.

## 3. Who uploads （谁负责上传）

- **Question:** Who photographs/scans the graded papers and uploads them?
- **Test-data answer: ASSUMED** — the teacher photographs the papers herself with a phone
  and uploads them (manifest entries say `uploaded_by: "TEST (synthetic)"`, standing in for
  "teacher").
- **What the kit did with it:** nothing structural — `Upload.uploaded_by` is a free field;
  the kit only fixes the value's placeholder.
- **Phase 2 must confirm:** teacher vs teaching assistant vs Daniel; and whether upload
  happens per class or per batch.

## 4. Typical photo quality （典型照片质量）

- **Question:** What do the photos typically look like (lighting, angle, blur, cropping)?
- **Test-data answer: ASSUMED** — phone photos under ordinary classroom lighting: mostly
  legible, occasional tilt and uneven light; one paper in five is a genuinely poor photo.
- **What the kit did with it:** S-001…S-004 are rendered as clean-to-average sheets;
  **S-005 is the low-quality case** (rotated ≈2°, blurred, darkened, noisy) with two items
  unreadable (`papers/S-005/`, reliability 0.31 / 0.38 in its answer records), so OCR
  evaluation and the review-queue path can be exercised now.
- **Phase 2 must confirm:** real phone model(s), typical failure modes, whether a scanner
  is available as an alternative.

## 5. School tolerance for differentiated homework （学校对差异化作业的态度）

- **Question:** May personalized (differentiated) homework be assigned as the official
  homework, and within what limits?
- **Test-data answer: ASSUMED** — differentiated homework is allowed as the official
  assignment （正式作业）, per the product direction in `design.md` （个性化作业作为正式作业，
  而非额外加量）. The kit assumes no specific cap on per-student question counts.
- **What the kit did with it:** nothing in the test data depends on a numeric cap; the
  assembly engine's teacher budget cap stays a teacher-set parameter.
- **Phase 2 must confirm:** the school's stance **in writing** (see
  `../docs/field-materials-checklist.md` §3.4) — this assumption is the one with policy
  consequences and must not ship to a live pilot unconfirmed.

## 6. Assignment size and question types （题量与题型）

- **Question:** How many questions, of which types, and what total score?
- **Test-data answer: ASSUMED** — 12 questions / 100 points: 3 multiple-choice, 1
  multi-blank fill-in, 8 calculation/judgment/estimation items with separately recorded
  sub-parts (Q3, Q11, Q12), modeled on the sample paper in `design.md` (which references
  第2题…第12题）.
- **What the kit did with it:** `assignment/questions.json` + `teacher-key.md`.
- **Phase 2 must confirm:** the real assignment's count/types/score allocation (checklist
  §1.1 A4 in `../docs/field-materials-checklist.md`).

## 7. Grading style （批改形式）

- **Question:** How does the teacher mark papers （对错符号、分数、评语）?
- **Test-data answer: ASSUMED** — red pen: √ / × for whole items, partial scores as `x/y`
  on the item's points, short written comments for partial credit — the four
  `GradingMarkKind` shapes the ingestion pipeline already models
  (correct / wrong / score / comment).
- **What the kit did with it:** all five test papers are marked in exactly those shapes
  (`papers/*/answer-records.json`, `grading_mark`).
- **Phase 2 must confirm:** the teacher's real marking habits, especially whether partial
  scores are written per sub-question.

## Deliberately NOT assumed （不假设，等教师定）

| Item | Status |
|---|---|
| Success criteria for the pilot （成功标准） | **OPEN** — teacher sets before the pilot (issue #108 Phase 2; `../docs/field-materials-checklist.md` §3.3). No test-data value exists, on purpose. |
| Acceptable per-session review time （可接受审核时间） | **OPEN** — same as above. The kit records no target minutes anywhere. |
| Consent / data-use permissions （知情同意） | **OPEN** — real-student materials only; the synthetic kit needs none and grants none. See the field checklist §4. |
