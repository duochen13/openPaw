# homework-pilot/assembly — personalized assembly engine + question generation

Implements [#113](https://github.com/duochen13/openPaw/issues/113)
(personalized homework assembly rules engine) and
[#114](https://github.com/duochen13/openPaw/issues/114)
(question generation + pre-release validation).

## What it does

**Assembly engine** (`engine.py`) — `assemble(student_profile, teacher_config)`
builds one student's official homework from their evidence record:

- Dynamic per-student mix of 当前学习 (current), 薄弱点练习 (weak-point
  practice), 旧知识复习 (review) — no preset class ratios.
- Weak-point repetition is **bounded** and shrinks as evidence improves
  (正在改善 → fewer repeats + one different-context verification item).
- Recurring difficulty (same weak-point hypothesis persisting
  `recurring_difficulty_rounds` without improvement) → **exactly one**
  diagnostic/foundational item **plus** a teacher prompt
  （可能需要讲解 — an explanation may be needed). The question count
  never grows without bound.
- Teacher-configurable 共同题 (common questions) for unified class
  review; the teacher's `max_questions` / `max_minutes` budget is a hard
  cap — overflow is dropped **and recorded** in `plan.dropped_items`.

**Question generation** (`generate.py`) — the `Question` dataclass
carries full metadata (target skill, recommendation reason, expected
difficulty, answer, solution steps, scoring notes). `validate_question`
runs the pre-release checklist:

- sufficient conditions stated (all `required_inputs` present, target stated)
- unique answer, or documented acceptable alternatives
- SI units on every physics quantity (a bare `"5"` fails)
- figure–text consistency: a stem saying 如图 must not ship with
  `figure == NONE`

**Figures are text-first.** When no reliable figure can be produced, the
question ships with an explicit `FigureTask` placeholder routed to the
teacher review queue — flagged, never silently dropped, never shipped
wrong. `FigureNeedStats` tracks which skills genuinely need figures vs
work fine text-only.

**Review queue** (`review_queue.py`) — the teacher-facing gate:
reason / difficulty / answer / solution / scoring visible per entry;
approve / replace / adjust / reject decisions. Full UI is #115's job.

**Sample bank** (`question_bank.py`) — synthetic fixtures authored for
tests (ids prefixed `SYN-`), covering 6 chapter-3 skills. **Not
teacher-approved content.**

## Layout

```
assembly/
├── __init__.py        public surface
├── models.py          self-contained input dataclasses (see "Wiring" below)
├── engine.py          assemble() — the #113 rules engine
├── generate.py        Question, FigureStatus, validate_question, FigureNeedStats
├── review_queue.py    teacher-facing review queue
├── question_bank.py   synthetic sample questions + test-only bank selector
├── tests/             unittest suites
└── README.md          this file
```

## Running the tests

From `homework-pilot/`:

```bash
python3 -m unittest discover -s assembly/tests -t .
```

No dependencies beyond the Python 3 standard library.

## Wiring to #109 / #112 (intended, not yet connected)

This package is deliberately **self-contained**: its tests pass on this
branch alone, without the evidence ledger (#109) or the taxonomy (#112)
merged. `models.py` mirrors their schemas:

- `MasteryState` ← the five evidence-ledger judgments
  （证据不足 / 需要练习 / 正在改善 / 已有较充分掌握证据 / 待复习）
- `WeakPointHypothesis` ← `WeakPointProposal` (plus `consecutive_rounds`
  derived from the proposal's audit history)
- skill ids ← `taxonomy/skills_ch3_v1.json`

Once #109 and #112 land, add thin converters at the boundary
(`evidence.SkillAssessment` → `SkillEvidence`,
`taxonomy.WeakPointProposal` → `WeakPointHypothesis`) and a real
`QuestionSelector` backed by the teacher-approved bank (#115).

## What still needs the teacher / real materials

- **Taxonomy sign-off**: `skills_ch3_v1.json` (issue #112) is still
  `pending_teacher_confirmation` — the skill ids used here are only as
  authoritative as that file.
- **Real question bank**: every `SYN-*` question is a synthetic fixture.
  Real teacher-provided questions (原题) with reference answers must go
  through `review_queue` before the engine may select them.
- **Figure tasks**: `pending_figure_tasks()` is the explicit to-do list
  of figures the pipeline would not generate on its own (currently
  `ch3-work-phases` items).
- **Budget defaults**: `max_questions`, `max_minutes`,
  `weak_point_base_count`, and the `recurring_difficulty_rounds`
  threshold are teacher-configurable starting values, not validated
  policy.
- **Diagnostic question design**: the engine reserves exactly one
  diagnostic slot on recurring difficulty, but *which* foundational
  question fills it needs teacher-authored content.
