"""homework-pilot evidence ledger: per-student × per-skill learning records.

Public surface (add ``homework-pilot/`` to ``sys.path``, then)::

    from evidence import (
        EvidenceLedger, JsonFileBackend,
        EvidenceRecord, SkillAssessment, AuditEntry,
        MasteryState, GradingResult, Confidence,
    )
"""

from .ledger import EvidenceLedger, JsonFileBackend, LedgerBackend
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

__all__ = [
    "EvidenceLedger",
    "JsonFileBackend",
    "LedgerBackend",
    "EvidenceRecord",
    "SkillAssessment",
    "AuditEntry",
    "MasteryState",
    "GradingResult",
    "Confidence",
    "AuditKind",
    "SCHEMA_VERSION",
]
