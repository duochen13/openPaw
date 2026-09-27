"""Personalized homework assembly engine (issue #113).

``assemble(student_profile, teacher_config)`` builds one student's official
homework from their evidence record. Rules, taken from the design doc
(``homwork-pilot/design.md``, section 个性化作业规则):

* Per-student dynamic mix of 当前学习 (current), 薄弱点练习 (weak-point
  practice), 旧知识复习 (review) -- no preset class ratios.
* Weak-point improvement shrinks repetition; retention is verified via
  different-context or spaced questions, never plain repeats.
* New or recurring difficulty gets ONE diagnostic/foundational item AND a
  teacher prompt （可能需要讲解 -- an explanation may be needed). The
  question count never grows without bound.
* A few common questions （共同题） per assignment for unified class
  review and comparable checks.
* Personalized homework IS the official assignment: the teacher's total
  workload budget (``max_questions`` / ``max_minutes``) is a hard cap.
  When candidates exceed the budget, the lowest-priority items are
  dropped and recorded in ``HomeworkPlan.dropped_items``.

Fill priority (highest first) when the budget is tight:

1. 共同题 -- the teacher explicitly reserved these slots.
2. Diagnostic items for recurring-difficulty skills.
3. 薄弱点练习 for needs-practice skills (shrinks as evidence improves).
4. Retention-verification items for improving skills.
5. 旧知识复习 for due-for-review skills inside the review scope.
6. 当前学习 for insufficient-evidence skills in the current scope.

A student with no evidence anywhere (new student) therefore gets mostly
当前学习 questions: every other category produces nothing for them.
"""

from __future__ import annotations

from collections.abc import Callable

from .models import (
    HomeworkPlan,
    ItemCategory,
    MasteryState,
    PlannedItem,
    StudentProfile,
    TeacherConfig,
)

#: (skill_id, selection_kind, count) -> question ids.
#: Selection kinds: "current", "weak_point", "review", "verification",
#: "diagnostic", "common". The engine never invents question content;
#: plugging the real question bank in is #115's job.
QuestionSelector = Callable[[str, str, int], list[str]]


def default_selector(skill_id: str, kind: str, count: int) -> list[str]:
    """Deterministic fallback selector used by the unit tests.

    Produces stable synthetic ids (``{skill}-{kind}-{i}``); the real
    selector backed by the teacher-approved bank replaces this.
    """
    return [f"{skill_id}-{kind}-{i + 1}" for i in range(count)]


def _is_recurring(evidence_state: MasteryState, weak_point, threshold: int) -> bool:
    """Recurring difficulty = the weak hypothesis persists without
    improvement for ``threshold`` homework rounds."""
    return (
        weak_point is not None
        and evidence_state in (MasteryState.NEEDS_PRACTICE, MasteryState.IMPROVING)
        and weak_point.consecutive_rounds >= threshold
    )


def _weak_point_count(evidence_state: MasteryState, base: int, recurring: bool) -> int:
    """Bounded weak-point repetition, shrinking as evidence improves.

    Improving students get fewer repeats (base - 1, at least 1) and the
    freed slot becomes a different-context/spaced verification item.
    Recurring-difficulty students are capped at 2 on top of the single
    diagnostic item -- never unbounded growth.
    """
    if recurring:
        return min(2, base)
    if evidence_state == MasteryState.IMPROVING:
        return max(1, base - 1)
    return base


def assemble(
    student_profile: StudentProfile,
    teacher_config: TeacherConfig,
    selector: QuestionSelector | None = None,
) -> HomeworkPlan:
    """Assemble one student's personalized homework.

    Returns a :class:`HomeworkPlan` that always respects the teacher's
    budget: ``len(items) <= max_questions`` and, when ``max_minutes`` is
    set, ``total_minutes <= max_minutes``.
    """
    select = selector or default_selector
    plan = HomeworkPlan(student_id=student_profile.student_id)
    remaining = teacher_config.max_questions
    minutes_left = teacher_config.max_minutes
    minutes_per_q = teacher_config.default_minutes_per_question

    def budget_ok(minutes: float) -> bool:
        if remaining < 1:
            return False
        return minutes_left is None or minutes <= minutes_left

    def add(item: PlannedItem, drop_reason: str) -> None:
        nonlocal remaining, minutes_left
        if budget_ok(item.estimated_minutes):
            plan.items.append(item)
            remaining -= 1
            if minutes_left is not None:
                minutes_left -= item.estimated_minutes
        else:
            plan.dropped_items.append(
                f"{item.question_id} ({item.category.value}): {drop_reason}"
            )

    # -- 1. Common questions (共同题): teacher-reserved slots -------------
    for qid in teacher_config.common_question_ids:
        if remaining < 1:
            plan.dropped_items.append(
                f"{qid} (共同题): budget exhausted, common slot dropped"
            )
            continue
        add(
            PlannedItem(
                question_id=qid,
                skill_id="",
                category=ItemCategory.COMMON,
                reason="共同题：统一讲评与可比的学习检查 (teacher-reserved)",
                estimated_minutes=minutes_per_q,
            ),
            "budget exhausted",
        )

    # -- Collect per-skill needs ------------------------------------------
    diagnostic: list[tuple] = []   # (skill_id, evidence)
    weak_needs: list[tuple] = []   # (skill_id, count, recurring)
    verify_needs: list[str] = []   # skill_ids needing retention verification
    review_needs: list[str] = []    # skill_ids due for review
    current_needs: list[str] = []   # skill_ids with insufficient evidence

    for skill_id in teacher_config.current_scope:
        ev = student_profile.evidence_for(skill_id)
        state = ev.state if ev else MasteryState.INSUFFICIENT
        weak = ev.weak_point if ev else None

        if _is_recurring(state, weak, teacher_config.recurring_difficulty_rounds):
            diagnostic.append((skill_id, ev))
            weak_needs.append(
                (skill_id, _weak_point_count(state, teacher_config.weak_point_base_count, True), True)
            )
            plan.teacher_prompts.append(
                f"可能需要讲解：{skill_id}（薄弱点假设已连续 {weak.consecutive_rounds} "
                f"轮未改善；已安排 1 道诊断性基础题，请确认是否需要课堂讲解）"
            )
        elif state == MasteryState.NEEDS_PRACTICE:
            weak_needs.append(
                (skill_id, _weak_point_count(state, teacher_config.weak_point_base_count, False), False)
            )
        elif state == MasteryState.IMPROVING:
            count = _weak_point_count(state, teacher_config.weak_point_base_count, False)
            weak_needs.append((skill_id, count, False))
            verify_needs.append(skill_id)
        elif state == MasteryState.DUE_REVIEW:
            review_needs.append(skill_id)
        elif state == MasteryState.INSUFFICIENT:
            current_needs.append(skill_id)
        # MASTERED: nothing -- no busywork.

    # Review-scope skills outside the current scope can still be due.
    for skill_id in teacher_config.review_scope:
        if skill_id in teacher_config.current_scope:
            continue
        ev = student_profile.evidence_for(skill_id)
        if ev is not None and ev.state == MasteryState.DUE_REVIEW:
            review_needs.append(skill_id)

    # -- 2. Diagnostic items (recurring difficulty): exactly one each -----
    for skill_id, ev in diagnostic:
        qids = select(skill_id, "diagnostic", 1)
        add(
            PlannedItem(
                question_id=qids[0],
                skill_id=skill_id,
                category=ItemCategory.WEAK_POINT,
                reason=f"诊断性基础题：{skill_id} 反复出现困难，先回到基础确认",
                estimated_minutes=minutes_per_q,
                is_diagnostic=True,
            ),
            "budget exhausted",
        )

    # -- 3. Weak-point practice (bounded, shrinks with improvement) -------
    for skill_id, count, recurring in weak_needs:
        qids = select(skill_id, "weak_point", count)
        for qid in qids:
            add(
                PlannedItem(
                    question_id=qid,
                    skill_id=skill_id,
                    category=ItemCategory.WEAK_POINT,
                    reason=(
                        f"薄弱点练习：{skill_id}（"
                        f"{'反复困难，数量已封顶' if recurring else '按改善程度控制重复量'}）"
                    ),
                    estimated_minutes=minutes_per_q,
                ),
                "budget exhausted",
            )

    # -- 4. Retention verification (different context / spaced) -----------
    for skill_id in verify_needs:
        qids = select(skill_id, "verification", 1)
        add(
            PlannedItem(
                question_id=qids[0],
                skill_id=skill_id,
                category=ItemCategory.WEAK_POINT,
                reason=f"掌握情况验证：{skill_id} 正在改善，用不同情境题目检查是否仍然掌握",
                estimated_minutes=minutes_per_q,
                verification_kind="different_context",
            ),
            "budget exhausted",
        )

    # -- 5. Review of stale knowledge (旧知识复习) -------------------------
    for skill_id in review_needs:
        qids = select(skill_id, "review", 1)
        add(
            PlannedItem(
                question_id=qids[0],
                skill_id=skill_id,
                category=ItemCategory.REVIEW,
                reason=f"旧知识复习：{skill_id} 证据已过期，安排复习检查",
                estimated_minutes=minutes_per_q,
            ),
            "budget exhausted",
        )

    # -- 6. Current learning (当前学习): fills the rest --------------------
    # A new student (everything 证据不足) lands here for every current-scope
    # skill, so their plan is mostly current-scope questions by construction.
    per_skill = max(1, remaining // max(1, len(current_needs))) if current_needs else 0
    for skill_id in current_needs:
        qids = select(skill_id, "current", per_skill)
        for qid in qids:
            add(
                PlannedItem(
                    question_id=qid,
                    skill_id=skill_id,
                    category=ItemCategory.CURRENT,
                    reason=f"当前学习：{skill_id} 证据不足，布置当前教学范围题目",
                    estimated_minutes=minutes_per_q,
                ),
                "budget exhausted",
            )

    plan.total_minutes = sum(i.estimated_minutes for i in plan.items)
    plan.within_budget = len(plan.items) <= teacher_config.max_questions and (
        teacher_config.max_minutes is None
        or plan.total_minutes <= teacher_config.max_minutes
    )
    return plan
