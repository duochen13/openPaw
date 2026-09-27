# evidence — student × skill evidence ledger

Per-student, per-skill long-term learning record for homework-pilot
(see `homwork-pilot/design.md`, section 学习记录). Students are identified
by ID only — there is no name field anywhere.

## What it stores

- `EvidenceRecord` — one dated evidence item: question & sub-question
  (题目/小题）, knowledge point, student answer, grading result
  (批改结果： 正确/错误/部分正确/无法辨认）, original image location,
  hint usage, correction linkage (订正）, teacher notes, subsequent
  verification, and dates.
- `SkillAssessment` — the current teaching judgment for one student × skill:
  one of five states — 证据不足 / 需要练习 / 正在改善 / 已有较充分掌握证据 /
  待复习 — plus a provisional weak-point hypothesis flag and qualitative
  mastery uncertainty (高/中/低； never a percentage in v1).
- `AuditEntry` — every state change and teacher action, so the teacher can
  always see *why* a judgment stands.

`ocr_reliability` (how well we read the handwriting/scan) lives on each
`EvidenceRecord` and is **separate** from the mastery judgment: an
`UNREADABLE` record is stored but never moves the state. "We couldn't read
it" is never conflated with "the student doesn't know it".

## State-machine rules (the doc's evidence rules, encoded)

| Evidence | Result |
|---|---|
| One wrong answer, no prior evidence | 需要练习 + provisional 薄弱点 hypothesis (待验证）, never a confirmed verdict |
| One right answer, nothing else | stays 证据不足 — one right ≠ long-term mastery |
| Correcting / repeating the SAME question | recorded, but excluded from mastery advancement |
| Correct with hint, or not independently completed | recorded, excluded from mastery advancement |
| ≥3 recent independent corrects on ≥2 different questions in ≥2 different contexts, no recent wrongs | 已有较充分掌握证据 |
| Recent wrong after strong evidence | drops below mastered; raises a provisional hypothesis |
| No new evidence for `stale_days` (default 45) | `flag_stale_assessments()` → 待复习 (schedules a review check; never claims forgetting) |

`record_evidence()` applies these rules and writes an audit entry on every
state change. `apply_teacher_correction()` lets the teacher override the
state directly (judgments are revisable, never fixed labels) — always
audited. `evidence_for(student_id, skill_id)` returns the current
assessment, the full dated history, the audit trail, and a Chinese summary
for the teacher.

"Recent" = `recency_days` (default 21). Both are v1 heuristics on the
`EvidenceLedger` constructor, documented and revisable — not calibrated
constants.

## Storage

JSON file backend (`JsonFileBackend`) with a `schema_version` field and a
`MIGRATIONS` registry for forward migration. The backend is isolated behind
the `LedgerBackend` protocol so a SQLite implementation can be swapped in
later without touching the ledger or the transition rules.

## Usage

```python
from evidence import EvidenceLedger, JsonFileBackend, EvidenceRecord, GradingResult, MasteryState

ledger = EvidenceLedger(JsonFileBackend("ledger.json"))
ledger.record_evidence(EvidenceRecord(
    student_id="s-001", skill_id="work-power",
    question_id="q-11", sub_question="(2)",
    knowledge_point="判断指定力是否做功",
    student_answer="...", grading_result=GradingResult.INCORRECT,
    image_location="scan-2026-09-27/p03.png",
    context="ch3-hw-05",
))
view = ledger.evidence_for("s-001", "work-power")  # assessment + history + audit
ledger.apply_teacher_correction("s-001", "work-power",
    MasteryState.IMPROVING, note="课堂观察已确认")
ledger.flag_stale_assessments()  # 待复习 for long-silent assessments
```

## Tests

22 unit tests on synthetic data, covering every acceptance criterion of
issue #109 (wrong-once → provisional hypothesis; right-once ≠ mastery;
same-question correction doesn't advance; teacher override is auditable;
teacher evidence view; OCR/mastery separation; stale → 待复习； ID-only
enforcement; JSON round-trip with schema version):

```
cd homework-pilot && python3 -m unittest evidence.tests.test_ledger
```
