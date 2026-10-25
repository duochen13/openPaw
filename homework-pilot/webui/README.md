# Teacher console UI (issue #167)

The first teacher-facing frontend for homework-pilot: a **single
self-contained HTML file** (no external stylesheets, scripts, fonts, or
images) styled after the **Muse desktop app**. It covers the five
screens of the teacher's loop from `design.md`:

| View | What the teacher does there |
|---|---|
| 工作台 | Just the key loop: the single next action, plus the three pending counts （待确认识别 / 待确认薄弱点 / 待审核题目）. Class switcher （九年级1班 / 九年级2班） in the sidebar. |
| 识别确认 | Per student-ID × 小题： recognized answer, grading mark, reliability badge （可靠 / 存疑 / 需手录）, compact original-image placeholder, icon actions 确认 / 修改 / 手录. |
| 薄弱点确认 | Per student-ID skill hypotheses with the five teaching-judgment states, dated evidence snippets, icon actions 确认 / 修改状态 / 驳回. |
| 作业审核 | Shared-question cards （题干 / 参考答案 up front; 目标技能 / 推荐原因 / 预期难度 / 解题过程 / 评分说明 folded into a 详情 expander), per-student mix summary, icon actions 通过 / 替换 / 移除. |
| 导出 | Student PDF list by ID with page counts and per-row download icons, 全班批量导出， and the separate 教师版 (answer key) card. |

## Render

```bash
cd homework-pilot
python3 -m webui teacher-console.html   # or: python3 -m webui (defaults to ./teacher-console.html)
python3 -m unittest discover -s webui/tests -t .
```

View switching, the class switcher, and the nav count badges are small
vanilla-JS interactions inside the file. Action buttons are **demo
placeholders**: a click stamps the card as handled (client-side only,
nothing is saved). Export buttons are inert too — each carries a
`data-export-fn` attribute and a title naming the `review/export.py`
function it will call (`export_class`, `export_student_sheet`,
`export_teacher_key`).

**Icon buttons, key features first** (2026-10-24 simplification pass,
per Daniel: simpler, like the Muse app, icons over text). Card actions
are inline-SVG icon buttons — 确认 / 通过 = check, 修改 / 修改状态 =
pencil, 手录 = keyboard, 驳回 = ×, 替换 = swap arrows, 移除 = trash,
下载 = download — and the action word is carried in `title` (tooltip)
and `aria-label` only, never as visible text. Two spots keep visible
text because an icon alone would be ambiguous: the **全班批量导出**
button (its scope is the whole class, not one row) and the sidebar nav
/ class switcher (there the label *is* the identity). Views show only
their decision-carrying elements: the dashboard is the next action plus
the three counts (the flow checklist and instructions cards are gone);
recognition cards keep the answer, reliability tier and grading mark
(the image placeholder shrank to a slim strip); hypothesis cards keep
the note, the qualitative 把握 and the evidence list; review-question
details （目标技能 / 推荐原因 / 预期难度 / 解题过程 / 评分说明） fold
into a native `<details>` expander under the stem + 参考答案. Only
decision-carrying pills remain: reliability tiers, grading results,
the five skill states, and the mix category.

## Data contract

`webui/models.py` holds view dataclasses that **mirror** (not import)
the upstream shapes, per the repo's per-package pattern:

| View model | Mirrors | Notes |
|---|---|---|
| `RecognitionItem` | `evidence.EvidenceRecord` + ingestion reliability | One student × one 小题 read awaiting confirmation. |
| `SkillHypothesisView` | `evidence.SkillAssessment` | Five states only; `confidence` is 高/中/低， never a number. |
| `ReviewQuestionView` | `review.models.Question` + `assembly` review-queue summary | `assigned_count` = students one decision covers. |
| `StudentMix` | `assembly` per-student plan | Counts per 共同题 / 当前学习 / 薄弱点练习 / 旧知识复习. |
| `ExportInfo` | `review.export.export_class` manifest entries | (student ID, pages) + teacher-key pages. |

Renderers consume plain dicts from the view-model builders in
`render.py` (`recognition_vm`, `hypothesis_vm`, `review_vm`,
`dashboard_vm`, `export_vm`); templates never touch dataclasses.

`webui/fixtures.py` ships **synthetic demo data** grounded in
design.md's Ch.3 skill table: invented student IDs (`S-0xx`), invented
questions (`SYN-` ids) and answers. No real student data, no names —
real materials are pending #108 and must never be pasted into fixtures.

## Binding rules (enforced by tests)

* **ID-only students.** There is no name field anywhere; tests walk the
  fixtures and fail on any name-like key or non-`S-\d{3}` student
  reference.
* **No mastery percentages.** Skill state is one of the five teaching
  judgments （证据不足 / 需要练习 / 正在改善 / 已有较充分掌握证据 /
  待复习）; tests fail if a `%` appears in fixture or rendered text.
* **Two uncertainties, kept separate.** OCR reliability (how well the
  system *read* the page) is bucketed into 可靠 / 存疑 / 需手录 using
  the ingestion pipeline's own thresholds (≥ 0.8 reliable — its
  recognition threshold; 0.5–0.8 doubtful; < 0.5 manual). It is never
  merged with the mastery judgment, and recognition items carry no
  mastery field at all.

## Design tokens (Muse desktop)

| Token | Value |
|---|---|
| Paper background | `#F7F7F7` (sidebar `#EFEFEF`) |
| Card surface | `#FFFFFF` |
| Border | `#E5E5E5` (1px), radius 12–16px, very soft shadow |
| Ink / secondary text | `#1A1A1A` / `#737373` |
| Accent (only) | Charcoal `#262626` — primary buttons, active nav, key highlights (revised 2026-10-21 per Daniel: grey + white, replacing Muse clay `#D97757`) |
| State tones | muted sage `#5C6B58`, amber `#7D6A2F`, soft red `#9E4A3C`, blue-gray `#47617A` — never neon |
| Display font | `"Tiempos Text", "Source Serif 4", Georgia, "Songti SC", "Noto Serif SC", serif` |
| UI font | `"Söhne", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif` |
| Layout | fixed 252px left sidebar; centered content column ≤ 1020px; pill badges; no gradients, no dark mode |
| Buttons | icon-only 38px squares (inline SVG: check / pencil / keyboard / × / swap / trash / download), charcoal-filled for the primary action; visible text kept only on 全班批量导出 |

Fonts are system stacks only — the file must stay self-contained, so no
webfonts are loaded.

## Scope limits

* Demo fixtures only; no live pipeline wiring, no persistence, no
  backend behavior changes. All existing homework-pilot packages are
  untouched by this package.
* The original-image region is a placeholder until scanned pages are
  plumbed through from `ingestion`.
* Wiring the console to `ReviewSession` decisions and real exports is
  follow-up work, gated on #108 Phase 1 (templates + test dataset); the live pilot still requires #108 Phase 2 real materials + teacher sign-off.
