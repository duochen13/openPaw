# Teacher review + PDF export (issue #115)

The last mile of the homework pipeline: the teacher reviews （审核）
assembled homework at the **shared-question level** （共同题 semantics --
one decision covers every student assigned the question), an approval gate
blocks anything unreviewed from becoming official homework, and the
approved plans export to print-ready PDFs -- one sheet per student plus a
separate teacher key （教师版） with answers and scoring notes （评分说明）.

## Modules

| File | What it does |
|---|---|
| `models.py` | Self-contained input dataclasses (`Question`, `HomeworkPlan`, `PublishedPlan`) mirroring the assembly shapes. See the module docstring for the intended wiring once `assembly` lands on main. |
| `review.py` | `ReviewSession`: `approve` / `reject` / `replace` / `adjust` at shared-question level, per-student overrides (`replace_for_student`, `adjust_for_student`), `approve_all()`, the approval gate (`is_approved`, `publish` raises `ApprovalError` unless every question cleared), and a full audit trail. |
| `export.py` | Stdlib-only PDF 1.4 writer: `export_student_sheet`, `export_teacher_key`, `export_class` (whole-class batch + round-trip manifest). |
| `cjk_font.py` | Bundled CJK font for the print PDFs (issue #185): stdlib TrueType parsing + Type0/CIDFontType2 embedding with a ToUnicode map. |
| `assets/fonts/` | Noto Sans SC subset TTFs (Regular + Bold) and the font license (`OFL.txt`). |
| `tools/build_cjk_fonts.py` | Build-time-only regeneration of the font subsets (needs fontTools; the export path never imports it). |

## Review workflow

```python
from review import ReviewSession, ApprovalError
from review import export_class

session = ReviewSession(plans, assignment_number="A-CH3-01")

session.approve("SYN-Q1")                       # 审核通过， class-wide
session.reject("SYN-Q2", "stem uses the wrong g")  # blocks the gate
session.adjust("SYN-Q2", {"stem": "fixed stem"})    # fix propagates to all
session.replace("SYN-Q3", teacher_question)        # swap class-wide
session.replace_for_student("S007", "SYN-Q1", easier_variant)  # one student only

try:
    plans = session.publish_class()   # raises ApprovalError if anything pending
except ApprovalError as e:
    print("still blocked:", e)

out = export_class(plans, "out/")
# out.student_files       -> [(student_id, pdf_path), ...]
# out.teacher_key_path    -> separate 教师版 PDF
# out.manifest_path       -> {"version": 1, "entries": [...]} round-trip manifest
```

Decisions and their propagation:

* **Shared level** (`approve`/`reject`/`adjust`/`replace`): applies to every
  student assigned that question. `adjust` edits fields in place (unknown
  fields raise); `replace` swaps in a different question id class-wide and
  auto-approves the replacement (it was the teacher's own choice).
* **Per-student overrides**: replace/adjust one student's instance without
  touching other students or the shared review status. An override counts
  as teacher-handled for that student's gate.
* **Gate**: a question clears the gate when approved, adjusted, or replaced.
  Rejected or pending questions block `publish()` / `publish_class()` with
  an `ApprovalError` naming the blocking questions.
* **Audit trail**: `session.audit_trail()` returns every teacher action with
  sequence number, UTC timestamp, question id, student id ("" = shared), and
  detail.

## Export details

Student sheet: title header with 学号 (student ID) + 作业编号 (assignment
number) on every page, numbered stems with skill tags and category
（共同题 → "common question"), figure placeholders as labeled boxes
("FIGURE NEEDED / 图待补充" + the teacher's figure description),
ruled answer space (5–8 lines by difficulty), page numbers, and a
keep-together rule so a question's stem block never splits awkwardly
across pages.

Teacher key: a **separate document** -- answers, numbered solution steps,
and 评分说明 per question, marked "TEACHER KEY — jiao shi ban (do not
distribute)". It never contains answer space or student IDs.

Batch: `export_class` renders every student sheet, one teacher key over
the union of questions, and a manifest in the same envelope shape as
`ingestion.id_manifest` (`{"version": 1, "entries": [...]}` with
`file`/`student_id`/`assignment_number`/`pages`/`kind`), so the #110/#111
upload-matching pipeline can map printed pages back to students.

## Honest limits of the PDF writer

* **Fonts** (issue #185): Latin body text uses the built-in
  Helvetica/Helvetica-Bold; Chinese (and CJK punctuation / math symbols)
  uses a **bundled Noto Sans SC subset** -- Noto Sans SC, version
  2.004-H2, SIL Open Font License 1.1 (license text in
  `assets/fonts/OFL.txt`) -- embedded in every PDF, so Chinese renders
  verbatim in both the student sheet and the teacher key. The subset
  (Regular 2,158,288 bytes; Bold 2,155,896 bytes) covers printable ASCII
  + Latin-1, general/CJK punctuation, common math symbols, and the full
  GB2312-80 Han repertoire (6,763 characters; all Chapter 3 vocabulary).
  Characters outside the subset render as "?"; superscript digits render
  as `^n` (the upstream font itself lacks most of them). Glyph coverage
  for the Chapter 3 sample set is asserted in `tests/test_cjk_font.py`;
  regenerate or widen the subset with `tools/build_cjk_fonts.py`.
* **Figures**: labeled placeholder boxes only. No raster/vector figure
  rendering -- real artwork comes from the teacher (flagged upstream by
  the PLACEHOLDER figure status).
* **Typesetting**: no hyphenation, justification, or widow/orphan control
  beyond the keep-together rule. Pagination is deterministic (same plan
  renders byte-identical).
* **Verification**: tests validate PDF structure for real (header, xref
  offsets, trailer `/Root`, `%%EOF`, page count) and, where
  `pdftotext`/`pdfinfo` exist, extract the rendered text to confirm the
  expected strings survived typesetting. This does not prove a viewer
  draws every glyph perfectly -- visual spot-check of the first print run
  is still the teacher's call.

## What still needs the teacher / real materials

* All question content in tests is synthetic (`SYN-` prefix). Real 原题
  (original teacher materials) are pending #108 field work.
* Figure placeholder boxes ("FIGURE NEEDED") are tasks for the teacher:
  supply or draw the figure, then re-export.
* The bundled font subset covers the GB2312-80 repertoire (all of
  Chapter 3 and common Simplified Chinese); a future chapter needing
  characters outside GB2312 would need the subset widened
  (`tools/build_cjk_fonts.py`) -- `review.cjk_font.missing_glyphs` is
  the coverage check to run first.
* `ReviewSession` is the data/API layer; the clickable teacher UI is a
  separate piece (this issue's scope was review logic + export).
