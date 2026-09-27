"""Candidate question generation model + pre-release validation (issue #114).

Generation here is *structured authoring support*, not an LLM call: the
:class:`Question` dataclass carries everything a generated question needs
(full metadata: target skill, recommendation reason, expected difficulty,
answer, solution process, scoring notes), and
:func:`validate_question` runs the pre-release checklist before anything
reaches the teacher review queue.

Pre-release checks enforced:
  * sufficient conditions -- every declared ``required_input`` is present
    in ``given_quantities`` and the question states its target;
  * unique answer -- ``answer_is_unique`` or explicitly documented
    acceptable alternatives;
  * SI units -- every physics quantity carries a recognized SI unit
    (a bare ``"5"`` fails);
  * figure-text consistency -- a stem that says "如图"/"figure" must not
    ship with ``FigureStatus.NONE``; a ``PLACEHOLDER`` figure auto-creates
    a :class:`FigureTask` routed to the teacher (flagged, never silently
    dropped, never shipped wrong).

Source rule: internet-derived material is only allowed as a supplementary
source when explicitly permitted -- ``source="internet"`` requires
``allow_internet=True`` and a ``source_attribution`` string, otherwise
:func:`create_question` rejects it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

#: Question id prefix for the synthetic samples in ``question_bank`` --
#: anything carrying it is a fixture, NOT teacher-approved content.
SYNTHETIC_PREFIX = "SYN-"

#: Recognized SI unit tokens (base, derived, and common compound forms).
#: Values in ``given_quantities`` must end with one of these.
SI_UNITS = {
    "m", "km", "cm", "mm",
    "kg", "g",
    "s", "min", "h",
    "N", "J", "W", "Pa",
    "m/s", "m/s^2", "m/s²", "km/h",
    "N/kg", "kg/m^3", "kg/m³",
    "°C", "K",
}


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionType(str, Enum):
    CALCULATION = "calculation"
    JUDGMENT = "judgment"        # e.g. 判断做功阶段
    COMPARISON = "comparison"    # e.g. 比较功与功率
    ESTIMATION = "estimation"    # e.g. 估算平均功率
    MULTIPLE_CHOICE = "multiple_choice"


class FigureStatus(str, Enum):
    NONE = "none"                # text-only question; no figure needed
    PROVIDED = "provided"        # a reliable figure ships with the question
    PLACEHOLDER = "placeholder"  # FIGURE NEEDED: reliable figure could not be
                                 # produced; explicit task for the teacher


@dataclass
class FigureTask:
    """An explicit "figure needed" placeholder task for the teacher.

    Figure generation is the highest-risk part of question generation, so
    the pipeline is text-first: when no reliable figure can be produced,
    the question ships with this task instead of a wrong figure. The task
    is routed to the teacher review queue -- flagged, never silently
    dropped.
    """

    question_id: str
    skill_id: str
    description: str  # what figure the teacher should provide/draw
    why_needed: str = ""  # why text alone is insufficient for this skill


@dataclass
class Question:
    """A candidate question with full metadata, pre-teacher-review."""

    id: str
    skill_ids: list[str]
    stem: str
    question_type: QuestionType = QuestionType.CALCULATION
    figure: FigureStatus = FigureStatus.NONE
    figure_description: str = ""  # required when figure == PROVIDED
    figure_task: FigureTask | None = None  # set when figure == PLACEHOLDER
    given_quantities: dict[str, str] = field(default_factory=dict)  # name -> "value unit"
    required_inputs: list[str] = field(default_factory=list)  # must all be given
    target: str = ""  # what the question asks for
    answer: str = ""
    answer_is_unique: bool = True
    acceptable_alternatives: list[str] = field(default_factory=list)
    solution_steps: list[str] = field(default_factory=list)
    scoring_notes: str = ""
    difficulty: Difficulty = Difficulty.MEDIUM
    recommendation_reason: str = ""
    source: str = "generated"  # "generated" | "internet"
    source_attribution: str = ""  # required when source == "internet"

    def __post_init__(self) -> None:
        if isinstance(self.question_type, str):
            self.question_type = QuestionType(self.question_type)
        if isinstance(self.figure, str):
            self.figure = FigureStatus(self.figure)
        if isinstance(self.difficulty, str):
            self.difficulty = Difficulty(self.difficulty)
        if self.source not in ("generated", "internet"):
            raise ValueError("source must be 'generated' or 'internet'")
        if self.figure == FigureStatus.PLACEHOLDER and self.figure_task is None:
            self.figure_task = FigureTask(
                question_id=self.id,
                skill_id=self.skill_ids[0] if self.skill_ids else "",
                description="（待教师补充图示说明）",
            )
        if self.figure == FigureStatus.PLACEHOLDER and self.figure_task is not None:
            self.figure_task.question_id = self.id


def create_question(*, allow_internet: bool = False, **kwargs) -> Question:
    """Build a :class:`Question`, enforcing the source-attribution rule.

    Internet materials are only supplementary sources when explicitly
    allowed: ``source="internet"`` without ``allow_internet=True`` (or
    without ``source_attribution``) is rejected here, not downstream.
    """
    source = kwargs.get("source", "generated")
    if source == "internet":
        if not allow_internet:
            raise ValueError(
                "internet-derived questions require explicit allow_internet=True; "
                "no default scraping/copying"
            )
        if not kwargs.get("source_attribution"):
            raise ValueError(
                "internet-derived questions must carry source_attribution"
            )
    return Question(**kwargs)


# -- validation ---------------------------------------------------------------

#: Stem phrases that promise a figure the text must actually be consistent with.
FIGURE_MENTION_RE = re.compile(r"如图|下图|附图|figure|diagram|shown", re.IGNORECASE)

_UNIT_RE = re.compile(r"^\s*[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?\s*(\S+)\s*$")


def _unit_of(value: str) -> str | None:
    m = _UNIT_RE.match(value)
    return m.group(1) if m else None


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationReport:
    question_id: str
    checks: list[CheckResult] = field(default_factory=list)
    teacher_figure_task: FigureTask | None = None  # auto-flagged, never dropped

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> list[str]:
        return [c.name for c in self.checks if not c.passed]


def validate_question(q: Question) -> ValidationReport:
    """Run the pre-release checklist on one candidate question.

    A PLACEHOLDER figure never fails validation by itself -- it is routed
    to the teacher via ``report.teacher_figure_task`` instead, so it can
    be flagged rather than silently dropped or shipped wrong.
    """
    report = ValidationReport(question_id=q.id)

    # 1. Sufficient conditions: every required input is actually given,
    #    and the question states what it asks for.
    missing = [name for name in q.required_inputs if name not in q.given_quantities]
    if missing:
        report.checks.append(CheckResult(
            "sufficient_conditions", False,
            f"required inputs missing from given_quantities: {missing}",
        ))
    elif not q.target:
        report.checks.append(CheckResult(
            "sufficient_conditions", False,
            "question does not state its target （求什么未说明）",
        ))
    else:
        report.checks.append(CheckResult(
            "sufficient_conditions", True,
            f"all {len(q.required_inputs)} required inputs given; target: {q.target}",
        ))

    # 2. Unique answer, or explicitly documented acceptable alternatives.
    if q.answer_is_unique:
        report.checks.append(CheckResult(
            "unique_answer", True, "answer declared unique",
        ))
    elif q.acceptable_alternatives:
        report.checks.append(CheckResult(
            "unique_answer", True,
            f"non-unique answer with documented alternatives: {q.acceptable_alternatives}",
        ))
    else:
        report.checks.append(CheckResult(
            "unique_answer", False,
            "answer not unique and no acceptable alternatives documented",
        ))

    # 3. SI units on every physics quantity.
    bad_units = []
    for name, value in q.given_quantities.items():
        unit = _unit_of(value)
        if unit is None or unit not in SI_UNITS:
            bad_units.append(f"{name}={value!r}")
    if bad_units:
        report.checks.append(CheckResult(
            "si_units", False,
            f"quantities with missing/unrecognized units: {bad_units}",
        ))
    else:
        report.checks.append(CheckResult(
            "si_units", True,
            f"{len(q.given_quantities)} quantities carry SI units",
        ))

    # 4. Figure-text consistency.
    mentions_figure = bool(FIGURE_MENTION_RE.search(q.stem))
    if q.figure == FigureStatus.NONE and mentions_figure:
        report.checks.append(CheckResult(
            "figure_text_consistency", False,
            "stem refers to a figure （如图/figure) but figure status is NONE",
        ))
    elif q.figure == FigureStatus.PROVIDED and not q.figure_description:
        report.checks.append(CheckResult(
            "figure_text_consistency", False,
            "figure marked PROVIDED but figure_description is empty",
        ))
    else:
        note = "no figure referenced or needed"
        if q.figure == FigureStatus.PLACEHOLDER:
            note = "figure placeholder: routed to teacher, not shipped"
            report.teacher_figure_task = q.figure_task
        elif q.figure == FigureStatus.PROVIDED:
            note = "figure provided with description"
        report.checks.append(CheckResult("figure_text_consistency", True, note))

    return report


# -- per-skill figure-need statistics ------------------------------------------


class FigureNeedStats:
    """Track which skills genuinely need figures vs work fine text-only.

    Feeds the challenge in #114: figure generation is the highest-risk
    part, so the pipeline keeps score of where figures actually matter.
    """

    def __init__(self) -> None:
        self._needs_figure: dict[str, int] = {}
        self._text_only_ok: dict[str, int] = {}

    def record(self, q: Question) -> None:
        for skill_id in q.skill_ids:
            if q.figure in (FigureStatus.PROVIDED, FigureStatus.PLACEHOLDER):
                self._needs_figure[skill_id] = self._needs_figure.get(skill_id, 0) + 1
            else:
                self._text_only_ok[skill_id] = self._text_only_ok.get(skill_id, 0) + 1

    def skills_needing_figures(self) -> list[str]:
        """Skills where at least one question needed a figure."""
        return sorted(self._needs_figure)

    def text_only_skills(self) -> list[str]:
        """Skills where every recorded question worked text-only."""
        return sorted(s for s in self._text_only_ok if s not in self._needs_figure)

    def summary(self) -> dict[str, dict[str, int]]:
        skills = set(self._needs_figure) | set(self._text_only_ok)
        return {
            s: {
                "needs_figure": self._needs_figure.get(s, 0),
                "text_only_ok": self._text_only_ok.get(s, 0),
            }
            for s in sorted(skills)
        }
