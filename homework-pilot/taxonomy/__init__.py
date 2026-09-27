"""homework-pilot skill taxonomy and weak-point diagnosis (issue #112).

A teacher-confirmed (pending sign-off) skill taxonomy for Chapter 3
《能量的转化与守恒》, question -> skill tagging with multi-skill support,
and diagnosis logic that proposes provisional weak points （薄弱点假设）
from evidence — never verdicts.

Public surface (add ``homework-pilot/`` to ``sys.path``, then)::

    from taxonomy import (
        load_taxonomy, Taxonomy,
        tags_for, skill_ids_for, validate_tags, SAMPLE_ASSIGNMENT_TAGS,
        propose_weak_points, DiagnosisResult,
        EvidenceInput, WeakPointProposal, ProposalStatus,
    )

Deliberately self-contained: the ``EvidenceInput`` shape mirrors
``evidence.EvidenceRecord`` (issue #109) but does not import it; see
``EvidenceInput.from_dict`` for the intended wiring once #109 merges.
"""

from .diagnose import DiagnosisResult, propose_weak_points
from .models import (
    RESULT_CORRECT,
    RESULT_INCORRECT,
    RESULT_PARTIAL,
    RESULT_UNREADABLE,
    AuditEntry,
    EvidenceInput,
    ProposalStatus,
    WeakPointProposal,
)
from .tagging import (
    QuestionTag,
    SAMPLE_ASSIGNMENT_TAGS,
    skill_ids_for,
    tags_for,
    validate_tags,
)
from .taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    Skill,
    Taxonomy,
    TaxonomyValidationError,
    load_taxonomy,
    validate_taxonomy_dict,
)

__all__ = [
    "load_taxonomy",
    "validate_taxonomy_dict",
    "TaxonomyValidationError",
    "Taxonomy",
    "Skill",
    "DEFAULT_TAXONOMY_PATH",
    "QuestionTag",
    "SAMPLE_ASSIGNMENT_TAGS",
    "tags_for",
    "skill_ids_for",
    "validate_tags",
    "propose_weak_points",
    "DiagnosisResult",
    "EvidenceInput",
    "WeakPointProposal",
    "ProposalStatus",
    "AuditEntry",
    "RESULT_CORRECT",
    "RESULT_INCORRECT",
    "RESULT_PARTIAL",
    "RESULT_UNREADABLE",
]
