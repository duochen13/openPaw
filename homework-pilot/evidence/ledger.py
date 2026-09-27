"""The evidence ledger: storage schema + the state machine for skill judgments.

Storage layout (JSON file)::

    {
      "schema_version": 1,
      "records":      [EvidenceRecord...],
      "assessments":  {"<student_id>|<skill_id>": SkillAssessment...},
      "audit":        [AuditEntry...]
    }

The file backend is deliberately isolated in :class:`JsonFileBackend` behind
the tiny :class:`LedgerBackend` protocol, so a SQLite backend can be swapped
in later without touching :class:`EvidenceLedger` or the transition rules.

Evidence rules encoded here (from ``homwork-pilot/design.md``, 学习记录):
  * One wrong answer -> provisional weak-point hypothesis only (``NEEDS_PRACTICE``
    + ``provisional_hypothesis=True``). Never a confirmed verdict.
  * One right answer != long-term mastery. A single correct answer on its own
    leaves the state at 证据不足; ``FAIRLY_WELL_MASTERED`` requires several
    recent, independently completed correct answers on *different* questions in
    *different* contexts.
  * Correcting or repeating the SAME question (``correction_of`` / repeated
    ``question_id``) records evidence but does NOT advance mastery -- it is
    explicitly excluded from the independent-correct count.
  * A correct answer produced with a hint (``hint_used=True``) or not completed
    independently is also excluded from mastery advancement.
  * ``UNREADABLE`` grading (low ``ocr_reliability``) records the evidence but
    never moves the state -- "couldn't read it" != "doesn't know it".
  * Long gaps without evidence -> :meth:`EvidenceLedger.flag_stale_assessments`
    moves the assessment to 待复习 ("schedule a review check"), never to a
    claim of forgetting.
  * Teacher corrections override via :meth:`apply_teacher_correction` and are
    always written to the audit log.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from .models import (
    SCHEMA_VERSION,
    AuditEntry,
    AuditKind,
    Confidence,
    EvidenceRecord,
    GradingResult,
    MasteryState,
    SkillAssessment,
)

#: Migrations keyed by the schema_version they upgrade FROM. Add an entry here
#: whenever SCHEMA_VERSION is bumped; each function receives the raw stored
#: dict and returns the migrated dict.
MIGRATIONS: dict[int, "callable"] = {}


class LedgerBackend(Protocol):
    """Minimal storage contract. Implement this to swap in SQLite later."""

    def load(self) -> dict: ...
    def save(self, data: dict) -> None: ...


class JsonFileBackend:
    """JSON-file implementation of :class:`LedgerBackend`, with schema-version
    checking and forward migration."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return self._empty_store()
        with self.path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return self._migrate(data)

    def save(self, data: dict) -> None:
        data = dict(data)
        data["schema_version"] = SCHEMA_VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    @staticmethod
    def _empty_store() -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "records": [],
            "assessments": {},
            "audit": [],
        }

    def _migrate(self, data: dict) -> dict:
        version = data.get("schema_version", 1)
        while version < SCHEMA_VERSION:
            migration = MIGRATIONS.get(version)
            if migration is None:
                raise ValueError(
                    f"no migration registered from schema_version={version}"
                )
            data = migration(data)
            version = data.get("schema_version", version + 1)
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"store schema_version={version} is newer than this code "
                f"understands (max {SCHEMA_VERSION})"
            )
        return data


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceLedger:
    """Per-student × per-skill evidence store with explicit state transitions.

    ``recency_days`` defines "recent" for the independent-evidence rule; v1
    heuristic, documented and revisable -- not a calibrated constant.
    ``stale_days`` defines "long gap without evidence" for the 待复习 flag.
    """

    def __init__(
        self,
        backend: LedgerBackend,
        recency_days: int = 21,
        stale_days: int = 45,
    ):
        self._backend = backend
        self.recency_days = recency_days
        self.stale_days = stale_days
        raw = backend.load()
        self._records: list[EvidenceRecord] = [
            EvidenceRecord.from_dict(d) for d in raw.get("records", [])
        ]
        self._assessments: dict[str, SkillAssessment] = {
            key: SkillAssessment.from_dict(d)
            for key, d in raw.get("assessments", {}).items()
        }
        self._audit: list[AuditEntry] = [
            AuditEntry.from_dict(d) for d in raw.get("audit", [])
        ]

    # -- persistence -------------------------------------------------------
    @staticmethod
    def _key(student_id: str, skill_id: str) -> str:
        return f"{student_id}|{skill_id}"

    def save(self) -> None:
        self._backend.save(
            {
                "records": [r.to_dict() for r in self._records],
                "assessments": {
                    key: a.to_dict() for key, a in self._assessments.items()
                },
                "audit": [e.to_dict() for e in self._audit],
            }
        )

    # -- reads --------------------------------------------------------------
    def assessment_for(self, student_id: str, skill_id: str) -> SkillAssessment:
        """Current judgment for one student × one skill."""
        key = self._key(student_id, skill_id)
        if key not in self._assessments:
            self._assessments[key] = SkillAssessment(
                student_id=student_id, skill_id=skill_id
            )
        return self._assessments[key]

    def records_for(self, student_id: str, skill_id: str) -> list[EvidenceRecord]:
        return sorted(
            (
                r
                for r in self._records
                if r.student_id == student_id and r.skill_id == skill_id
            ),
            key=lambda r: r.observed_at,
        )

    def evidence_for(self, student_id: str, skill_id: str) -> dict:
        """Everything behind a judgment: the current assessment, the full dated
        evidence history, and the audit trail (teacher corrections included).
        This is what the teacher reviews."""
        assessment = self.assessment_for(student_id, skill_id)
        records = self.records_for(student_id, skill_id)
        audit = [
            e
            for e in self._audit
            if e.student_id == student_id and e.skill_id == skill_id
        ]
        return {
            "student_id": student_id,
            "skill_id": skill_id,
            "assessment": assessment.to_dict(),
            "records": [r.to_dict() for r in records],
            "audit": [e.to_dict() for e in audit],
            "summary": self._summarize(assessment, records),
        }

    @staticmethod
    def _summarize(
        assessment: SkillAssessment, records: list[EvidenceRecord]
    ) -> str:
        lines = [f"当前判断：{assessment.state.value}"]
        if assessment.provisional_hypothesis:
            lines.append(f"薄弱点假设（待验证）：{assessment.hypothesis_note or '—'}")
        lines.append(f"掌握不确定性：{assessment.confidence.value}（定性，非百分比）")
        lines.append(f"证据共 {len(records)} 条：")
        for r in records:
            hint = "（使用提示）" if r.hint_used else ""
            corr = "（订正/重复）" if r.correction_of else ""
            unread = f"（识别可靠度 {r.ocr_reliability:.2f}）" if (
                r.grading_result is GradingResult.UNREADABLE
            ) else ""
            lines.append(
                f"  - {r.observed_at.date()} {r.question_id}{r.sub_question} "
                f"{r.grading_result.value}{hint}{corr}{unread}"
            )
        return "\n".join(lines)

    # -- writes --------------------------------------------------------------
    def record_evidence(
        self, record: EvidenceRecord, *, at: datetime | None = None
    ) -> SkillAssessment:
        """Append one evidence record and recompute the judgment.

        Returns the updated assessment. Emits an audit entry when the state
        actually changes.
        """
        now = at or _utcnow()
        self._records.append(record)
        assessment = self.assessment_for(record.student_id, record.skill_id)
        previous = assessment.state
        self._recompute(assessment, now=now)
        assessment.last_evidence_at = record.observed_at
        assessment.updated_at = now
        if assessment.state is not previous:
            self._audit.append(
                AuditEntry(
                    student_id=record.student_id,
                    skill_id=record.skill_id,
                    kind=AuditKind.STATE_CHANGE,
                    from_state=previous,
                    to_state=assessment.state,
                    note=self._transition_note(record),
                    at=now,
                )
            )
        self.save()
        return assessment

    def apply_teacher_correction(
        self,
        student_id: str,
        skill_id: str,
        new_state: MasteryState,
        note: str,
        *,
        clear_hypothesis: bool = True,
        at: datetime | None = None,
    ) -> SkillAssessment:
        """Teacher override: set the state directly. Always auditable.

        Judgments are revisable, so the teacher can also clear or restate the
        provisional hypothesis here.
        """
        now = at or _utcnow()
        if isinstance(new_state, str):
            new_state = MasteryState(new_state)
        assessment = self.assessment_for(student_id, skill_id)
        previous = assessment.state
        assessment.state = new_state
        assessment.state_before_review = None
        if clear_hypothesis:
            assessment.provisional_hypothesis = False
            assessment.hypothesis_note = ""
        assessment.updated_at = now
        self._audit.append(
            AuditEntry(
                student_id=student_id,
                skill_id=skill_id,
                kind=AuditKind.TEACHER_OVERRIDE,
                from_state=previous,
                to_state=new_state,
                note=note,
                at=now,
            )
        )
        self.save()
        return assessment

    def add_teacher_note(
        self,
        student_id: str,
        skill_id: str,
        note: str,
        *,
        at: datetime | None = None,
    ) -> None:
        """Annotate without changing the state (still auditable)."""
        now = at or _utcnow()
        assessment = self.assessment_for(student_id, skill_id)
        self._audit.append(
            AuditEntry(
                student_id=student_id,
                skill_id=skill_id,
                kind=AuditKind.TEACHER_NOTE,
                from_state=assessment.state,
                to_state=assessment.state,
                note=note,
                at=now,
            )
        )
        self.save()

    def flag_stale_assessments(
        self, *, as_of: datetime | None = None
    ) -> list[SkillAssessment]:
        """Move assessments with no new evidence for ``stale_days`` to 待复习.

        This schedules a review check -- it never claims the student forgot.
        The pre-flag state is kept in ``state_before_review``.
        """
        now = as_of or _utcnow()
        flagged: list[SkillAssessment] = []
        for assessment in self._assessments.values():
            if assessment.state in (
                MasteryState.INSUFFICIENT_EVIDENCE,
                MasteryState.DUE_FOR_REVIEW,
            ):
                continue
            last = assessment.last_evidence_at
            if last is None or (now - last) > timedelta(days=self.stale_days):
                previous = assessment.state
                assessment.state_before_review = previous
                assessment.state = MasteryState.DUE_FOR_REVIEW
                assessment.updated_at = now
                self._audit.append(
                    AuditEntry(
                        student_id=assessment.student_id,
                        skill_id=assessment.skill_id,
                        kind=AuditKind.STALE_FLAG,
                        from_state=previous,
                        to_state=MasteryState.DUE_FOR_REVIEW,
                        note=(
                            f"超过 {self.stale_days} 天无新证据，安排复习检查；"
                            "不代表已遗忘"
                        ),
                        at=now,
                    )
                )
                flagged.append(assessment)
        if flagged:
            self.save()
        return flagged

    # -- the state machine ----------------------------------------------------
    def _recompute(self, assessment: SkillAssessment, *, now: datetime) -> None:
        records = self.records_for(assessment.student_id, assessment.skill_id)
        # UNREADABLE records carry no mastery signal at all.
        usable = [r for r in records if r.grading_result is not GradingResult.UNREADABLE]
        cutoff = now - timedelta(days=self.recency_days)

        # Independent corrects: recent, independently completed, no hint, and
        # NOT a correction/repeat of an already-seen question.
        seen_questions: set[str] = set()
        independent_corrects: list[EvidenceRecord] = []
        for r in usable:
            qid = r.question_id or r.record_id
            is_repeat = qid in seen_questions
            seen_questions.add(qid)
            if (
                r.grading_result is GradingResult.CORRECT
                and r.observed_at >= cutoff
                and r.independently_completed
                and not r.hint_used
                and not r.correction_of
                and not is_repeat
            ):
                independent_corrects.append(r)

        recent_negatives = [
            r
            for r in usable
            if r.grading_result
            in (GradingResult.INCORRECT, GradingResult.PARTIAL)
            and r.observed_at >= cutoff
        ]
        any_negatives = any(
            r.grading_result in (GradingResult.INCORRECT, GradingResult.PARTIAL)
            for r in usable
        )

        if not usable:
            assessment.state = MasteryState.INSUFFICIENT_EVIDENCE
            assessment.confidence = Confidence.LOW
            assessment.provisional_hypothesis = False
            return

        distinct_questions = {r.question_id or r.record_id for r in independent_corrects}
        distinct_contexts = {r.context or r.record_id for r in independent_corrects}

        # Fairly well-mastered: several recent, independent corrects on
        # DIFFERENT questions in DIFFERENT contexts, no recent negatives.
        if (
            len(independent_corrects) >= 3
            and len(distinct_questions) >= 2
            and len(distinct_contexts) >= 2
            and not recent_negatives
        ):
            assessment.state = MasteryState.FAIRLY_WELL_MASTERED
            assessment.confidence = Confidence.HIGH
            assessment.provisional_hypothesis = False
            assessment.state_before_review = None
            return

        # Improving: real positive signal beyond a single data point --
        # either recovering from a wrong answer, or repeated independent
        # corrects with no history of weakness. A *recent* wrong still raises
        # a provisional hypothesis (one wrong = hypothesis only, never a
        # confirmed verdict), even when the overall trend is positive.
        if len(independent_corrects) >= 2 or (independent_corrects and any_negatives):
            assessment.state = MasteryState.IMPROVING
            assessment.confidence = Confidence.MEDIUM
            assessment.state_before_review = None
            if recent_negatives:
                assessment.provisional_hypothesis = True
                assessment.hypothesis_note = "近期出现答错，薄弱点假设待验证"
            else:
                assessment.provisional_hypothesis = False
            return

        # Needs practice: wrong/partial evidence. One wrong answer supports a
        # provisional weak-point hypothesis ONLY -- never a confirmed verdict.
        if any_negatives:
            assessment.state = MasteryState.NEEDS_PRACTICE
            assessment.confidence = Confidence.LOW
            assessment.provisional_hypothesis = True
            if not assessment.hypothesis_note:
                assessment.hypothesis_note = "一次答错形成的待验证假设，需更多证据确认"
            assessment.state_before_review = None
            return

        # A single correct answer on its own: positive signal, but one right
        # answer != long-term mastery. Stays at 证据不足.
        assessment.state = MasteryState.INSUFFICIENT_EVIDENCE
        assessment.confidence = Confidence.LOW
        assessment.provisional_hypothesis = False
        assessment.state_before_review = None

    @staticmethod
    def _transition_note(record: EvidenceRecord) -> str:
        if record.grading_result is GradingResult.UNREADABLE:
            return "无法辨认的作答已记录（识别可靠度低），不改变掌握判断"
        if record.correction_of:
            return "同一题目的订正/重复，已记录但不计入独立掌握证据"
        if record.hint_used and record.grading_result is GradingResult.CORRECT:
            return "使用提示后答对，已记录但不计入独立掌握证据"
        return f"新证据：{record.question_id}{record.sub_question} {record.grading_result.value}"
