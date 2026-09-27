"""Weak-point （薄弱点） diagnosis: propose hypotheses from evidence.

Rules, taken from the design doc (homwork-pilot/design.md):

  * One wrong answer -> a PROVISIONAL weak-point hypothesis, never a verdict.
  * Untaught content and content without evidence are NEVER labeled weak:
    untaught skills are excluded via the ``taught_skills`` set, and skills
    with no readable evidence get no proposal.
  * UNREADABLE records carry no mastery signal ("we could not read it" is
    not "the student does not know it"); records below
    ``MIN_OCR_RELIABILITY`` are excluded from the signal for the same reason.
  * Every proposal requires teacher confirm / modify / reject — the system
    never promotes a hypothesis to a verdict by itself.

Mapping to the #109 ledger: a CONFIRMED proposal corresponds to
``SkillAssessment(state=NEEDS_PRACTICE, provisional_hypothesis=True)``; a
REJECTED proposal maps to keeping/returning to the prior judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import (
    RESULT_CORRECT,
    RESULT_INCORRECT,
    RESULT_PARTIAL,
    AuditEntry,
    EvidenceInput,
    ProposalStatus,
    WeakPointProposal,
)

#: Records read worse than this are excluded from the diagnosis signal.
#: A v1 heuristic, documented and revisable — not a calibrated constant.
MIN_OCR_RELIABILITY = 0.5


@dataclass
class DiagnosisResult:
    """Everything ``propose_weak_points`` decided, including the skills it
    deliberately did NOT label."""

    proposals: list[WeakPointProposal] = field(default_factory=list)
    # (student_id, skill_id) pairs: taught skill, but no readable evidence —
    # deliberately never labeled weak.
    no_evidence: list[tuple[str, str]] = field(default_factory=list)
    # skill ids with evidence that are NOT in the taught set — never proposed.
    excluded_untaught: list[str] = field(default_factory=list)
    assessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def for_student(self, student_id: str) -> list[WeakPointProposal]:
        return [p for p in self.proposals if p.student_id == student_id]


def _signal_records(records: list[EvidenceInput]) -> list[EvidenceInput]:
    """Records that carry a mastery signal for diagnosis."""
    return [
        r for r in records
        if r.readable() and r.ocr_reliability >= MIN_OCR_RELIABILITY
    ]


def _corrected_record_ids(records: list[EvidenceInput]) -> set[str]:
    """record_ids of errors later corrected by the student (订正）. Kept as
    context in the proposal note; a correction weakens the hypothesis but the
    teacher still has to confirm or reject it."""
    ids = {r.record_id for r in records}
    return {r.correction_of for r in records if r.correction_of in ids}


def propose_weak_points(
    records: list[EvidenceInput],
    taught_skills: set[str],
    *,
    student_ids: list[str] | None = None,
) -> DiagnosisResult:
    """Propose provisional weak points （薄弱点假设） from evidence.

    ``records`` are evidence items tagged with taxonomy skill ids;
    ``taught_skills`` is the set of skill ids the teacher has actually taught.
    Skills outside that set are never proposed, no matter the evidence.

    ``student_ids`` optionally supplies the class roster: every taught skill
    with no records at all for a rostered student is reported under
    ``no_evidence``. Without it, only student x skill pairs seen in
    ``records`` are reported.
    """
    result = DiagnosisResult()
    seen_pairs = {(r.student_id, r.skill_id) for r in records}

    # Group by student x skill, preserving first-seen order.
    groups: dict[tuple[str, str], list[EvidenceInput]] = {}
    for rec in records:
        groups.setdefault((rec.student_id, rec.skill_id), []).append(rec)

    for (student_id, skill_id), recs in groups.items():
        if skill_id not in taught_skills:
            if skill_id not in result.excluded_untaught:
                result.excluded_untaught.append(skill_id)
            continue

        signal = _signal_records(recs)
        if not signal:
            result.no_evidence.append((student_id, skill_id))
            continue

        errors = [r for r in signal if r.grading_result == RESULT_INCORRECT]
        partials = [r for r in signal if r.grading_result == RESULT_PARTIAL]
        corrects = [r for r in signal if r.grading_result == RESULT_CORRECT]

        if not errors and not partials:
            continue  # nothing but correct evidence: no hypothesis

        corrected = _corrected_record_ids(signal)
        corrected_errors = [r for r in errors if r.record_id in corrected]

        if errors:
            strength = "repeated_errors" if len(errors) > 1 else "single_error"
            n = len(errors)
            verb = "wrong answer" if n == 1 else "wrong answers"
            basis_note = (
                f"{n} {verb} on skill {skill_id} (question(s): "
                + ", ".join(sorted({r.question_id or '?' for r in errors})) + "). "
                "Single/repeated errors support a PROVISIONAL hypothesis only — "
                "teacher confirmation required."
            )
        else:
            strength = "partial_credit"
            basis_note = (
                f"{len(partials)} partially-correct answer(s) on skill {skill_id}, "
                "no fully wrong answer. Weaker hypothesis — teacher confirmation required."
            )

        if corrected_errors:
            basis_note += (
                f" Note: {len(corrected_errors)} error(s) were later corrected "
                "(订正） by the student; suggest follow-up verification."
            )
        if corrects:
            basis_note += (
                f" Mixed evidence: {len(corrects)} correct answer(s) also on record."
            )

        proposal = WeakPointProposal(
            student_id=student_id,
            skill_id=skill_id,
            status=ProposalStatus.PROPOSED,
            is_provisional=True,
            hypothesis_strength=strength,
            basis_record_ids=[r.record_id for r in (errors or partials)],
            basis_note=basis_note,
        )
        proposal.audit.append(
            AuditEntry(
                kind="auto_proposed",
                from_status=None,
                to_status=ProposalStatus.PROPOSED,
                note=basis_note,
            )
        )
        result.proposals.append(proposal)

    # Deterministic output order.
    result.proposals.sort(key=lambda p: (p.student_id, p.skill_id))
    result.no_evidence.sort()
    result.excluded_untaught.sort()

    # Roster sweep: taught skills with no records at all for a known student.
    if student_ids:
        for sid in student_ids:
            for sk in sorted(taught_skills):
                if (sid, sk) not in seen_pairs and (sid, sk) not in result.no_evidence:
                    result.no_evidence.append((sid, sk))
        result.no_evidence.sort()

    return result
