# 个性化科学作业试点验证方案 · Pilot Validation Protocol

**Project:** personalized science homework teacher pilot (homework-pilot)
**Related issue:** #116
**Design doc:** `homwork-pilot/design.md` on main (folder name keeps its current spelling; this document lives under the correctly-spelled `homework-pilot/` folder per the issue instructions)
**Status:** DRAFT — pending pre-pilot sign-off (see §10). Nothing below takes effect until the teacher and Daniel sign off on the targets.

---

## 1. Objective · 目标

This is a **pre-registered validation protocol** for the pilot. It is written **before** any student data is collected so that success cannot be redefined after the results are in.

The pilot validates two things, in this order:

1. **Operational feasibility (流程可行性):** can a teacher run the full loop — 上传 (upload) → 核对 (check/verify) → 出题 (generate questions) → 打印 (print) — reliably and within an acceptable review-time budget?
2. **Learning signal (学习信号):** is there any evidence that personalized homework moves student learning, without the result being explained away by "more homework"?

What this pilot does **not** claim: proof that the product causes long-term score gains. The first pilot can only validate the short-term flow and short-term learning change; a full school year of learning records is a product requirement that this pilot cannot verify.

---

## 2. Stages and entry criteria · 阶段与进入条件

### Stage 1 — small pilot · 小范围试点

- **Scope:** one small section of 浙教版科学九年级上册第三章《能量的转化与守恒》 (actual textbook and teaching pace per the teacher) + **8–10 students**.
- **What must work end-to-end:** the full flow — upload graded paper homework (photos or scanned PDF) → system associates students, homework, page numbers, and items, and recognizes answers and grading marks → teacher verifies what cannot be reliably recognized and confirms or corrects the system's skill judgments (薄弱点) → teacher sets current scope and homework length → system generates per-student mixed homework (current learning + weak-skill practice + review of old knowledge) → teacher reviews, swaps, or adjusts questions → teacher approves → per-student PDFs and separate teacher answer/scoring notes are exported and printed.
- **Students need no online account and do not answer online; they complete homework on paper.**
- Student ID numbers are used instead of names (学生编号代替姓名). Printed IDs on homework pages are recommended to help next-time upload matching; **when matching is uncertain, the teacher must confirm.**

### Stage 2 — full 2 classes · 两个班全量

- **Scope:** both classes of the pilot teacher, ≈80 students.
- **Entry criteria (all must hold):**
  1. Stage 1 completed with complete tracking records (see §4 and the tracking sheet).
  2. The **go/no-go decision rule in §8** produced an explicit **GO**, recorded in writing.
  3. Pre-pilot confirmations are on file for Stage 2 scale (§10).
  4. The comparable evaluation design (§7) is finalized **before** Stage 2 starts.

---

## 3. Metrics · 指标

"Target set by" is always the pilot teacher (or Daniel where marked). **No targets are invented in this protocol** — every numeric target below is a blank to be filled at sign-off. Empty target = cannot start.

| # | Metric · 指标 | How measured · 测量方式 | Target set by · 目标设定人 |
|---|---|---|---|
| M1 | Recognition errors · 识别错误 | Per session: count of misrecognized answers/grading marks found during teacher verification; error rate = errors per page (or per student paper). Distinguish **recognition uncertainty** (OCR failed) from **judgment uncertainty** (skill mastery) — they are separate. | Teacher (sign-off, §10) |
| M2 | Student/page matching errors · 学生/页码匹配错误 | Per session: count of uploads matched to the wrong student or the wrong page/item. Denominator: total uploaded papers/pages. | Teacher (sign-off) |
| M3 | Teacher-corrected skill judgments · 教师修正的技能判断 | Per session: number of system-proposed skill assessments (薄弱点判断) the teacher changed, overturned, or marked "insufficient evidence". These are teaching judgments, not fixed labels on students. | Teacher (sign-off) |
| M4 | Generated-question modifications/rejections · 生成题被修改或拒绝 | Per session: number of generated questions modified or rejected, with the **reason logged for each** (categories: 条件不充分 condition insufficient; 答案不唯一 answer non-unique; 评分不接受合理替代解法 scoring rejects reasonable alternatives; 公式单位错误 formula/unit errors; 图文不一致 figure–text mismatch; 难度不匹配 wrong difficulty; 超出已教范围 untaught content; 其他 other). Target is an acceptable modification/rejection rate. | Teacher (sign-off) |
| M5 | Review time per session · 每次审核所用时间 | Minutes from the start of teacher review (审核开始) to approval for release (批准发布). Includes verifying unrecognized content, confirming/correcting skill judgments, and reviewing/adjusting questions. **This is the single hardest budget constraint.** | Teacher, in writing before the pilot (sign-off) |
| M6 | Learning-check scores · 学习检查成绩 | Per student: pre-check, post-check, and delayed-review-check scores (see §5). Reported per student and per stage; never as precise "mastery percentages" without calibration evidence. | Teacher + Daniel (sign-off) |
| M7 | Homework completion time and volume · 完成时间与作业量 | Per student per assignment: completion minutes and number of questions/items (see §6). Used to rule out the "more homework" confound. | Teacher + Daniel (sign-off) |
| M8 | Student-material exceptions · 学生材料异常 | Per session: unrecognizable answers, missing pages, missing reference answers, non-independent completion (hint use, corrections, help). Logged as flags on the evidence, not silently dropped. | Teacher (sign-off) |

M1–M5, M8 come from the **session log**; M4 additionally from the **question-modification log**; M6 from the **learning-check log**; M7 from the **homework volume log** — all templates in `pilot-tracking-sheet.md`.

---

## 4. Data collection during the pilot · 试点数据记录

- Every session: date, class/student set, review minutes (M5), errors by category (M1, M2, M8), count of corrected skill judgments (M3), count + reasons of modified/rejected questions (M4).
- Every assignment: per-student completion time and question volume (M7), whether hints/corrections were used (订正/提示使用情况), whether completion was independent.
- Every learning check: per-student scores on pre/post/delayed checks (M6), check date, question-form identifier (to confirm parallel forms were used).
- **Diagrams (含图题) that cannot be reliably generated or recognized must be flagged for review — never silently ignored.**

---

## 5. Learning-check design · 学习检查设计

The goal is to measure **learning**, not memorization.

- **Pre/post checks with different but equally difficult questions (难度相近但不同的题目):** the pre-check and post-check cover the same target skills at the same difficulty band but use **different problem contexts**. Parallel forms are prepared in advance and labeled (e.g. Form A / Form B); which form a student takes pre vs. post is recorded. This avoids mistaking **remembering the original answer (记住原答案)** for **mastery (掌握)**.
- **Delayed review check (后续复习检查):** one additional check on the same skills, spaced roughly 1–2 weeks after the post-check (exact interval set by the teacher's teaching pace; to be fixed at sign-off). Fresh evidence from an independently completed, different-context problem counts as new mastery evidence; **re-doing or correcting the same question does not count as independent mastery**.
- A small set of **common questions (共同题)** may be kept across students for comparability, per the design doc; these are labeled as such and excluded from the "different questions" claim.
- One wrong answer supports only a **tentative** weak-skill hypothesis (待验证的薄弱点假设); one right answer does not prove long-term mastery. Long gaps without new evidence may trigger a review check, but **absence of evidence is not evidence of forgetting**.

---

## 6. Confound controls · 混杂因素控制

The single biggest confound: **"more homework"**. If personalized assignments are longer or take more time, any score change could be a workload effect, not a personalization effect.

- Log **student completion time (完成时间)** and **homework volume (题量)** for every assignment, personalized and (where applicable) comparison.
- Personalized homework is the student's **formal homework (正式作业), not extra on top of uniform homework** — total load must be held roughly constant by design. If in practice volume or time drifts up, that drift is recorded and reported alongside any score change.
- Record whether each assignment was completed independently, with hints, or with corrections — assisted evidence is labeled, not mixed with independent evidence.
- Analysis reports M6 (scores) **together with** M7 (time/volume): a gain that appears only alongside a large volume increase is reported as confounded, not as a win.

---

## 7. Analysis plan · 分析计划

**Honest small-sample limits — stated explicitly:**

- Stage 1 has **8–10 students and no control group**. Pre/post changes at this size **cannot prove the product caused the learning change** (causality). Report: direction and size of per-student change, error-rate metrics, review-time cost, and confound status. If any statistics are computed, they are reported with wide uncertainty and labeled descriptive — never as proof of effect.
- Before scaling to Stage 2, a **more comparable evaluation must be designed and written down** — e.g. matched comparison between the two classes, or a class-level comparison with documented baseline equivalence. The exact design is finalized before Stage 2 (§2 entry criterion 4); it is deliberately **not** fixed here because it depends on what Stage 1 reveals about feasibility and data quality.
- Primary read-out for Stage 1 is **operational** (M1–M5: does the flow work within the review-time budget?) with learning checks as a secondary signal.
- Skill-judgment history is kept per student with dated evidence; the teacher can view the basis for every judgment and correct wrong records. **No uncalibrated "mastery percentages" are shown in v1.**

---

## 8. Go/no-go decision rule for scaling · 扩量决策规则

The decision to scale from Stage 1 to Stage 2 (2 classes, ≈80 students) is made **by Daniel together with the pilot teacher**, on written evidence — not on a feeling.

**NO-GO (do not scale) if any of the following holds:**

1. Median (or teacher-agreed statistic) **review time per session exceeds the teacher's pre-signed acceptable budget** (§10), with no credible path to reduce it.
2. The teacher **withdraws willingness** to continue, for any reason.
3. Recognition or matching error rates are so high that corrected judgments dominate the teacher's review time (i.e. the system is creating work, not saving it) — threshold per teacher sign-off.
4. The school does not tolerate differentiated homework at 2-class scale (school stance re-confirmed in writing for Stage 2).
5. Stage 1 tracking records are incomplete to the point that no honest analysis is possible.

**GO (scale) only if all of the following hold:**

1. M1–M5 are within the teacher's pre-signed targets.
2. The teacher confirms in writing willingness to continue at 2-class scale and re-confirms an acceptable review-time budget for the larger scale.
3. The comparable evaluation design (§7) is finalized and on file.
4. Privacy/access/retention/deletion arrangements cover the larger student set.

**Borderline cases are NO-GO by default.** "Partially successful" is not a scale decision; it is a Stage-1-repeat decision (fix the blocking failure mode, re-run Stage 1).

---

## 9. Risks · 风险

| Risk · 风险 | Mitigation · 缓解 |
|---|---|
| Handwriting/formula/diagram recognition is unreliable | Teacher verification step is mandatory; uncertain content is flagged, never silently dropped; M1/M2 tracked every session |
| Students complete homework non-independently (hints, corrections, help) | Logged as evidence flags (M8); assisted work labeled separately from independent evidence |
| Review time exceeds the teacher's budget at 80-student scale | Per-session review time is the primary metric (M5); budget is set in writing before the pilot; Stage-1-repeat is the default on borderline results |
| School does not accept differentiated homework (差异化作业) | School stance confirmed in writing before Stage 1; re-confirmed before Stage 2 |
| Generated questions are wrong, off-difficulty, or use untaught content | Every question carries target skill, recommended reason, expected difficulty, answer, solution, and scoring notes; teacher approves before release; M4 reasons logged per question |
| Student data privacy (access, external processing, retention, deletion, corrections) | All arrangements confirmed with the teacher/school before the pilot; part of the sign-off checklist (§10) — still pending |
| Small-sample results get over-interpreted as proof | §7 states the limits explicitly; no causal claims from Stage 1 |
| Teacher is the user's mother — feedback may be softened out of politeness | Tracking is metric-based (minutes, error counts), not opinion-based; the go/no-go rule keys off numbers, not impressions |

---

## 10. Pre-pilot sign-off checklist · 试点前确认清单

All items must be confirmed **in writing before Stage 1 starts**. Blank fields are **pending** — they are not filled in by this protocol.

- [ ] **Teacher willingness · 教师愿意试用:** the pilot teacher confirms willingness to run the full flow for the pilot period and to do the review/verification work. ⏳ **PENDING — to be signed by the teacher**
- [ ] **Acceptable review time · 可接受的审核时间:** max minutes per review session: ______ min. ⏳ **PENDING — number to be set by the teacher; this protocol invents no number**
- [ ] **School stance on differentiated homework · 学校对差异化作业的态度:** ________________________________. ⏳ **PENDING — to be confirmed with the school**
- [ ] **Success criteria · 成功标准:** ________________________________ (e.g. review-time budget met, error rates within bounds, learning signal not confounded). ⏳ **PENDING — to be set by the teacher and Daniel**
- [ ] **Pilot scope confirmed · 试点范围确认:** chapter/section and the 8–10 students selected. ⏳ **PENDING**
- [ ] **Learning-check logistics · 学习检查安排:** parallel question forms prepared; pre/post/delayed timing fixed (delayed interval: ______). ⏳ **PENDING**
- [ ] **Student data arrangements · 学生材料安排:** who uploads, how paper maps to students, photo quality expectations; data access, external processing services, retention period, correction/deletion process; student ID numbers instead of names. ⏳ **PENDING**
- [ ] **Exception handling · 异常处理:** agreed handling for unrecognizable answers, missing pages, missing reference answers, non-independent completion. ⏳ **PENDING**

Signature lines (see `pilot-tracking-sheet.md` §5 for the printable form):

- Pilot teacher: ____________________  Date: __________
- Daniel (project owner): ____________________  Date: __________

---

*Docs-sync note: the docs ARE the deliverable for #116 (process deliverable, no code). No README or code changes accompany this PR.*
