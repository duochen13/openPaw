"""Question/sub-question -> skill-id tags, with multi-skill support.

The design doc requires that composite questions may carry several skill
tags, because a wrong final answer alone cannot identify which step failed.
Q11 sub-parts and Q12 blanks are tagged (and recorded) separately, following
the doc's 各小题/各填空分别记录 rule.

Tag validation only checks tags against the taxonomy structure; whether a
tag is *pedagogically correct* is the teacher's call during sign-off.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .taxonomy import Taxonomy

#: Questions in the Q2-Q12 sample assignment that the design doc's table does
#: not map to any skill. They stay untagged until the teacher's real materials
#: are available.
UNMAPPED_SAMPLE_QUESTIONS = ("Q9", "Q10")


@dataclass(frozen=True)
class QuestionTag:
    """Skill tags for one question or sub-question/blank."""

    question_id: str                      # e.g. "Q11"
    sub_question: str = ""                # e.g. "(2)"; "" for whole-question tags
    skill_ids: tuple[str, ...] = ()        # one or more taxonomy skill ids
    note: str = ""                        # why this tagging was chosen
    composite: bool = False               # True: whole-question tag spanning
                                          # several skills (final-answer-only
                                          # errors cannot localize the step)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.question_id:
            problems.append("question_id is required")
        if self.composite and len(self.skill_ids) < 2:
            problems.append(
                f"{self.question_id}: composite tags must span >= 2 skills"
            )
        return problems


#: The sample assignment from the design doc (Q2-Q12), tagged against
#: skills_ch3_v1. This is a fixture, not a curriculum: the teacher's real
#: materials may re-tag anything here.
SAMPLE_ASSIGNMENT_TAGS: tuple[QuestionTag, ...] = (
    QuestionTag("Q2", skill_ids=("ch3-judge-work",),
                note="Single skill: judge whether the specified force does work."),
    # Q3 is composite in two steps: judging the effective displacement where
    # the force acts (work-judgment) and then computing the work against
    # friction. A wrong answer here cannot say which step failed.
    QuestionTag("Q3", skill_ids=("ch3-judge-work", "ch3-friction-work"),
                composite=True,
                note="Two-step composite: displacement judgment + friction work."),
    QuestionTag("Q4", skill_ids=("ch3-estimate-average-power",),
                note="Single skill: estimate quantities, compute average power."),
    QuestionTag("Q6", skill_ids=("ch3-estimate-average-power",),
                note="Same skill as Q4 on a different context."),
    QuestionTag("Q7", skill_ids=("ch3-work-vs-power",),
                note="Single skill: compare work vs power, exclude irrelevant conditions."),
    QuestionTag("Q8", skill_ids=("ch3-gravitational-work",),
                note="Single skill: gravitational work."),
    # Q11: each sub-part recorded and tagged separately (doc: 各小题分别记录).
    QuestionTag("Q11", "(1)", ("ch3-work-phases",),
                note="Sub-part 1: identify the phases in which work is done."),
    QuestionTag("Q11", "(2)", ("ch3-apex-kinetic-energy",),
                note="Sub-part 2: kinetic energy at the apex."),
    QuestionTag("Q11", "(3)", ("ch3-repeated-jump-power",),
                note="Sub-part 3: average power of repeated jumps."),
    # Q11 as a whole: a wrong total/final answer alone cannot localize the
    # failed sub-skill -> composite tag.
    QuestionTag("Q11", skill_ids=("ch3-work-phases", "ch3-apex-kinetic-energy",
                                  "ch3-repeated-jump-power"),
                composite=True,
                note="Whole-question composite tag: sub-part errors cannot be "
                     "localized from a final-answer error alone."),
    # Q12: each blank recorded and tagged separately (doc: 各填空分别记录).
    QuestionTag("Q12", "(1)", ("ch3-gravitational-work",),
                note="Blank 1: gravitational work."),
    QuestionTag("Q12", "(2)", ("ch3-elastic-potential-energy",),
                note="Blank 2: elastic potential energy."),
    QuestionTag("Q12", "(3)", ("ch3-force-velocity-changes",),
                note="Blank 3: force and velocity changes."),
    # Q12 as a whole: composite tag for the same final-answer localization
    # reason as Q11.
    QuestionTag("Q12", skill_ids=("ch3-gravitational-work",
                                  "ch3-elastic-potential-energy",
                                  "ch3-force-velocity-changes"),
                composite=True,
                note="Whole-question composite tag: a wrong final answer alone "
                     "cannot identify which blank/skill failed."),
    # Not in the design doc's sample table: present but untagged, pending the
    # teacher's actual materials.
    QuestionTag("Q9", note="Not mapped in the design doc's sample table; "
                           "pending teacher materials."),
    QuestionTag("Q10", note="Not mapped in the design doc's sample table; "
                            "pending teacher materials."),
)


def tags_for(question_id: str, sub_question: str = "") -> tuple[QuestionTag, ...]:
    """Return all tags for a question (optionally restricted to a sub-part).

    With ``sub_question=""`` this returns whole-question tags; pass the
    sub-part (e.g. ``"(2)"``) for that sub-part's tag.
    """
    return tuple(
        t for t in SAMPLE_ASSIGNMENT_TAGS
        if t.question_id == question_id and t.sub_question == sub_question
    )


def skill_ids_for(question_id: str, sub_question: str = "") -> tuple[str, ...]:
    """Flattened skill ids for a question / sub-question ("" if untagged)."""
    ids: list[str] = []
    for tag in tags_for(question_id, sub_question):
        ids.extend(tag.skill_ids)
    return tuple(dict.fromkeys(ids))  # de-duplicated, order-preserving


def validate_tags(tags: tuple[QuestionTag, ...],
                  taxonomy: Taxonomy) -> list[str]:
    """Check that every tag is well-formed and references known skill ids."""
    problems: list[str] = []
    known = set(taxonomy.skill_ids())
    for tag in tags:
        problems.extend(tag.validate())
        for sid in tag.skill_ids:
            if sid not in known:
                problems.append(
                    f"{tag.question_id}{tag.sub_question}: unknown skill id {sid!r}"
                )
    return problems
