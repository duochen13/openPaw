# Student-side MVP UI (issue #176)

The homework-pilot frontend, **pivoted from the #167 teacher console
to a student-side MVP** (2026-10-25, per issue #176): a student uploads
a scanned PDF of a paper they have already completed, and the system
returns one verdict per question. Still a **single self-contained HTML
file** (no external stylesheets, scripts, fonts, or images) styled
after the **Muse desktop app** — deliberately minimal: generous
whitespace, very few elements per view, one primary action per view,
no explainer cards, no stat dashboards.

| View | What the student does there |
|---|---|
| 试卷 | Home. One dashed upload card （上传已完成试卷（扫描 PDF）+ 选择 PDF 文件）, then the paper list: title, date, status, and compact verdict chips （对 n · 错 n · 待确认 n). A 处理中 paper is listed but not openable. |
| 结果 | One paper's per-question results (reached from a paper row; the sidebar stays on 试卷）. Each slim row: question-crop placeholder, 题号， transcribed 学生答案， a verdict chip, and a grey 来源 label. 错 rows also show the 参考答案. The header carries the summary chips and the single 导出标注 icon button. |
| 待确认 | The confirmation queue — the core loop. Each card: crop, transcription, the system's proposed verdict （系统倾向）, and icon actions 确认 (charcoal) / 改转写 (pencil) / 改为对 / 改为错. A footnote states that confirmations are saved as labeled data for improving recognition and judgment. The sidebar shows a pending-count badge. |

The teacher-console views （工作台 / 识别确认 / 薄弱点确认 / 作业审核 /
导出） are removed; git history on this branch preserves that design.

## Render

```bash
cd homework-pilot
python3 -m webui student-mvp.html   # or: python3 -m webui (defaults to ./student-mvp.html)
python3 -m unittest discover -s webui/tests -t .
```

View switching is a small vanilla-JS interaction inside the file. The
initial view can be deep-linked: `?view=papers|result|confirm` plus
`&paper=<paper-id>` for the result view. Action buttons are **demo
placeholders**: a click stamps the card as handled (client-side only,
nothing is saved). The 导出标注 button is inert too — it carries a
`data-export-fn="export_labeled_data"` attribute naming the hand-off
it will perform once wired (export of the confirmed transcriptions +
verdicts as labeled data).

**Icon buttons, key features first** (carried over from the #167
simplification pass, per Daniel: simpler, like the Muse app, icons
over text). Card actions are inline-SVG icon buttons — 确认 = check,
改转写 = pencil, 改为错 = ×, 导出标注 = download — and the action word
is carried in `title` (tooltip) and `aria-label` only, never as visible
text. Visible text is kept only where an icon alone would be ambiguous:
the 选择 PDF 文件 primary button (the papers view's single primary
action) and the sidebar nav (there the label *is* the identity).

## Verdicts and their sources

The verdict vocabulary is exactly **对 / 错 / 待确认** — there is no
skill-state or mastery UI anywhere on the student surface. Every
verdict names its source, tried in this priority order (issue #176)
and never blended silently:

1. **红笔标记** — the teacher's red-pen marks already on the paper;
2. **答案比对** — comparison against an answer key, when one exists;
3. **模型判定** — the model solves the question itself and compares
   (determinate-answer questions only).

Questions the system cannot settle — a shaky read, an uncertain
judgment, an open-ended answer — become 待确认 and carry a proposed
verdict （系统倾向） into the confirmation queue.

## Data contract

`webui/models.py` holds view dataclasses that **mirror** (not import)
the upstream shapes, per the repo's per-package pattern:

| View model | Mirrors | Notes |
|---|---|---|
| `QuestionResult` | ingestion pipeline output for one question | Crop location, transcribed 学生答案， `ocr_reliability`, verdict + source; 待确认 requires a `proposed_verdict`, 错 requires a `reference_answer` (validated). |
| `PaperResult` | one uploaded paper | `verdict_counts()` / `pending()` derive the chips and the queue. |
| `StudentData` | the demo as a whole | One student (ID only) and their papers; `pending_items()` spans papers. |

Renderers consume plain dicts from the view-model builders in
`render.py` (`question_vm`, `paper_vm`, `confirm_vm`); templates never
touch the dataclasses.

`webui/fixtures.py` ships **synthetic demo data**: one invented
student (`S-023`) and three invented papers. The main paper — 第三章
《能量的转化与守恒》测试卷 — deliberately mixes 4 对 / 2 错 / 2 待确认，
all three verdict sources, and exactly one low-reliability read. No
real student data, no names — real materials must never be pasted
into fixtures.

## Binding rules (enforced by tests)

* **ID-only students.** There is no name field anywhere; tests walk
  the fixtures and fail on any name-like key or any student reference
  that is not the demo ID.
* **Verdict vocabulary is closed.** Tests fail if a fixture verdict or
  source leaves `VERDICTS` / `VERDICT_SOURCES`, or if any of the five
  teacher-side teaching judgments （证据不足 / 需要练习 / 正在改善 /
  已有较充分掌握证据 / 待复习） or the old console's view names appear
  in the rendered page.
* **Two uncertainties, kept separate.** OCR reliability (how well the
  system *read* the handwriting) is bucketed with the ingestion
  pipeline's own thresholds (≥ 0.8 reliable — its recognition
  threshold; 0.5–0.8 doubtful; < 0.5 manual). Below-threshold reads
  show a small 识别可靠性低 note next to — never inside — the verdict,
  and route the question to 待确认； reliability alone never decides
  or flips a verdict （测试固定了这一点：第7题读得差，系统倾向仍为对）.
* **No percentages.** Tests fail if a `%` appears in fixture text or
  rendered visible text.

## Design tokens (Muse desktop)

| Token | Value |
|---|---|
| Paper background | `#F7F7F7` (sidebar `#EFEFEF`) |
| Card surface | `#FFFFFF` |
| Border | `#E5E5E5` (1px), radius 12–16px, very soft shadow |
| Ink / secondary text | `#1A1A1A` / `#737373` |
| Accent (only) | Charcoal `#262626` — primary buttons, active nav, key highlights |
| Verdict tones | muted sage `#5C6B58` on `#E9EDE7` （对）, soft red `#9E4A3C` on `#F5E7E2` （错）, amber `#7D6A2F` on `#F1EDDF` （待确认） — never neon |
| Display font | `"Tiempos Text", "Source Serif 4", Georgia, "Songti SC", "Noto Serif SC", serif` |
| UI font | `"Söhne", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif` |
| Layout | fixed 252px left sidebar; centered content column ≤ 1020px; pill badges; no gradients, no dark mode |
| Buttons | icon-only 38px squares (inline SVG: check / pencil / × / download / upload), charcoal-filled for the primary action; visible text kept only on 选择 PDF 文件 |

Fonts are system stacks only — the file must stay self-contained, so no
webfonts are loaded.

## Scope limits

* Demo fixtures only; no live pipeline wiring, no persistence, no
  backend behavior changes. The other homework-pilot packages are
  untouched by this package.
* The question-crop region is a placeholder until scanned pages are
  plumbed through from `ingestion`.
* Wiring the UI to the real upload → segmentation → transcription →
  verdict pipeline, and using real student papers at all, is follow-up
  work gated on the #108 Phase 2 school-stance / privacy question.
