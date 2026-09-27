# taxonomy — skill taxonomy and weak-point diagnosis

Chapter skill taxonomy plus diagnosis logic that proposes weak points
（薄弱点） from evidence for homework-pilot (issue #112).

## What it does

1. **`skills_ch3_v1.json`** — the chapter skill list as a versioned file
   (`version`, `chapter`, `source` fields), formalized from the design doc's
   sample table (`homwork-pilot/design.md`, 本章的技能粒度示例）.
   **Status: `pending_teacher_confirmation`.** The doc's table is preliminary
   （基于样本的初步标签）, not the full curriculum — the teacher must review
   it against her actual materials and sign off before it is authoritative.
2. **`tagging.py`** — question/sub-question → skill-id tags, with multi-skill
   tags for composite questions. The sample assignment Q2–Q12 is tagged as a
   fixture (`SAMPLE_ASSIGNMENT_TAGS`). Q11 sub-parts and Q12 blanks are
   tagged (and recorded) separately, per the doc's 各小题/各填空分别记录 rule.
3. **`diagnose.py`** — `propose_weak_points(evidence_records, taught_skills)`:
   diagnosis rules from the doc, encoded.
4. **`models.py`** — lightweight `EvidenceInput` (mirrors the #109 evidence
   record shape) and the `WeakPointProposal` teacher-confirmation workflow.

## The v1 skill list (Chapter 3 《能量的转化与守恒》)

| id | 技能 | English |
|---|---|---|
| `ch3-judge-work` | 根据力与沿力方向的位移判断指定力做功 | judge whether a given force does work from force + displacement along force direction |
| `ch3-friction-work` | 判断推下木板所需的位移并结合摩擦力计算功 | displacement to push board off + work against friction |
| `ch3-estimate-average-power` | 估算物理量并计算平均功率 | estimate quantities and compute average power |
| `ch3-work-vs-power` | 比较功与功率，排除无关条件 | compare work vs power, exclude irrelevant conditions |
| `ch3-gravitational-work` | 计算重力做功 | gravitational work |
| `ch3-work-phases` | 判断做功阶段 | work phases (Q11 sub-parts) |
| `ch3-apex-kinetic-energy` | 最高点动能 | kinetic energy at apex (Q11 sub-parts) |
| `ch3-repeated-jump-power` | 重复跳跃功率 | repeated-jump power (Q11 sub-parts) |
| `ch3-elastic-potential-energy` | 弹性势能 | elastic potential energy (Q12 blanks) |
| `ch3-force-velocity-changes` | 受力与速度变化 | force and velocity changes (Q12 blanks) |

## Diagnosis rules (the doc's rules, encoded)

| Evidence | Result |
|---|---|
| One wrong answer on a taught skill | Provisional weak-point **hypothesis** (`status=proposed`, `is_provisional=True`) — never a verdict |
| Repeated wrong answers | Still provisional, flagged `repeated_errors` — the system never self-promotes to a verdict |
| Partially correct only | Weaker hypothesis (`partial_credit`) — teacher still confirms |
| Skill with no readable evidence | **Never labeled weak** — reported under `no_evidence` |
| Skill not in the teacher's `taught_skills` set | **Never proposed** — reported under `excluded_untaught` |
| Only correct answers | No proposal |
| `无法辨认` (unreadable) or `ocr_reliability < 0.5` | Carries no mastery signal (readability ≠ mastery) |
| Student later corrected the error （订正） | Noted on the proposal; hypothesis stays provisional until the teacher acts |

`MIN_OCR_RELIABILITY = 0.5` is a v1 heuristic, documented and revisable —
not a calibrated constant (same stance as #109's ledger thresholds).

## Teacher workflow

Every proposal starts at `proposed` and **must** be moved by the teacher —
confirm, modify (optionally redirecting to a different skill id), or reject.
Every action appends to the proposal's `audit` trail (kind, from/to status,
note, timestamp), so overrides are always reviewable. Judgments stay
revisable; a teacher can change their mind and the trail keeps every step.

```python
from taxonomy import propose_weak_points

result = propose_weak_points(records, taught_skills={"ch3-judge-work", ...},
                             student_ids=["s-001", ...])
for p in result.proposals:
    print(p.skill_id, p.basis_note)   # hypothesis, provisional
    p.confirm("课堂观察已确认")          # or p.modify(...), p.reject(...)
```

## Tagging usage

```python
from taxonomy import tags_for, skill_ids_for, validate_tags, load_taxonomy

skill_ids_for("Q11", "(2)")   # ("ch3-apex-kinetic-energy",)
skill_ids_for("Q11")          # all three sub-skills (composite whole-question tag)
skill_ids_for("Q9")           # () — not in the doc's sample table, pending teacher materials
validate_tags(SAMPLE_ASSIGNMENT_TAGS, load_taxonomy())  # [] = all tags reference known skills
```

Composite questions (Q3, whole-question Q11/Q12) carry multiple tags: a wrong
final answer alone cannot identify which step failed, so the diagnosis tags
the sub-parts separately and the teacher localizes the failure.

## Intended wiring with #109 (evidence ledger)

This package is self-contained on purpose (its tests pass without #109
merged). The intended wiring once both are in:

```python
from evidence import EvidenceLedger, JsonFileBackend
from taxonomy import EvidenceInput, propose_weak_points

ledger = EvidenceLedger(JsonFileBackend("ledger.json"))
records = [EvidenceInput.from_dict(r.to_dict())
           for r in ledger.records_for_student("s-001")]  # field names match exactly
result = propose_weak_points(records, taught_skills=teacher.taught_skills())
```

Mapping: a `CONFIRMED` proposal corresponds to
`SkillAssessment(state=需要练习, provisional_hypothesis=True)` in the ledger;
a `REJECTED` proposal maps to keeping/returning to the prior judgment.

## Acceptance criteria status (issue #112)

- [x] Taxonomy file covering the chapter — `skills_ch3_v1.json` (v1)
- [x] Sample assignment questions tagged, incl. multi-skill composite tags
- [x] Diagnosis unit tests: single-error → hypothesis not verdict; no-evidence
      → no weak label; teacher override recorded and auditable; untaught
      skill never proposed — 26 tests, all passing
- [ ] **Built but unconfirmed, needs teacher/field materials:**
  - Taxonomy reviewed against the teacher's actual materials
    (currently `pending_teacher_confirmation`)
  - Teacher sign-off on the taxonomy
  - Tagging of Q9/Q10 and any re-tagging the teacher's materials require
  - Validation of the `taught_skills` set against real teaching progress

## Tests

26 unit tests on synthetic data (add `homework-pilot/` to `sys.path` first):

```
cd homework-pilot && python3 -m unittest taxonomy.tests.test_diagnose
```

Covers: taxonomy loading + validation, fixture-tag integrity against the
taxonomy, separate sub-part/blank tagging, multi-skill composite tagging,
hypothesis-not-verdict (single and repeated errors), no-evidence → no label,
unreadable/low-OCR → no signal, untaught exclusion, teacher
confirm/modify/reject with audit trail, and the `EvidenceInput.from_dict`
adapter against the #109 record shape.
