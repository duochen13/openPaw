# Teacher console UI (issue #167)

The first teacher-facing frontend for homework-pilot: a **single
self-contained HTML file** (no external stylesheets, scripts, fonts, or
images) styled after the **Muse desktop app**. It covers the five
screens of the teacher's loop from `design.md`:

| View | What the teacher does there |
|---|---|
| 工作台 | To-do overview: 待确认识别 / 待确认薄弱点 / 待审核题目 counts, 最近一次导出， and the round's flow checklist. Class switcher （九年级1班 / 九年级2班） in the sidebar. |
| 识别确认 | Per student-ID × 小题： recognized answer, grading mark, reliability badge （可靠 / 存疑 / 需手录）, original-image placeholder, 确认 / 修改 / 手录. |
| 薄弱点确认 | Per student-ID skill hypotheses with the five teaching-judgment states, dated evidence snippets, 确认 / 修改状态 / 驳回. |
| 作业审核 | Shared-question cards （题干 / 目标技能 / 推荐原因 / 预期难度 / 参考答案 / 解题过程 / 评分说明 / mix tag), per-student mix summary, 通过 / 替换 / 移除. |
| 导出 | Student PDF list by ID with page counts, 全班批量导出， and the separate 教师版 (answer key) card. |

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
| Paper background | `#F9F8F6` (sidebar `#F1EEE6`) |
| Card surface | `#FFFFFF` |
| Border | `#E7E3D9` (1px), radius 12–16px, very soft shadow |
| Ink / secondary text | `#1F1E1C` / `#6B675F` |
| Accent (only) | Muse clay `#D97757` — primary buttons, active nav, key highlights |
| State tones | muted sage `#4C6B45`, amber `#8A5E14`, soft red `#A34A3A`, blue-gray `#47617A` — never neon |
| Display font | `"Tiempos Text", "Source Serif 4", Georgia, "Songti SC", "Noto Serif SC", serif` |
| UI font | `"Söhne", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif` |
| Layout | fixed 252px left sidebar; centered content column ≤ 1020px; pill badges; no gradients, no dark mode |

Fonts are system stacks only — the file must stay self-contained, so no
webfonts are loaded.

## Scope limits

* Demo fixtures only; no live pipeline wiring, no persistence, no
  backend behavior changes. All existing homework-pilot packages are
  untouched by this package.
* The original-image region is a placeholder until scanned pages are
  plumbed through from `ingestion`.
* Wiring the console to `ReviewSession` decisions and real exports is
  follow-up work, gated on #108 field materials and teacher sign-off.
