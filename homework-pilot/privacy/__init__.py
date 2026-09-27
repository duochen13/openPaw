"""Privacy guard utilities for homework-pilot.

Students are minors (未成年人); all records are keyed by student ID only
(学号), never by name. This package enforces that rule at storage, logging,
export, and external-service boundaries, and provides the deletion path for
correction/deletion-on-request (更正/删除请求).

See homework-pilot/docs/privacy-governance.md for the full policy.
"""

from .guard import (  # noqa: F401
    DictStudentStore,
    NameFieldError,
    StudentStore,
    assert_id_only,
    contains_cjk_name_candidate,
    delete_student_records,
    redact,
    sanitize_log_message,
    scrub_for_external_service,
    scrub_text,
)

__all__ = [
    "DictStudentStore",
    "NameFieldError",
    "StudentStore",
    "assert_id_only",
    "contains_cjk_name_candidate",
    "delete_student_records",
    "redact",
    "sanitize_log_message",
    "scrub_for_external_service",
    "scrub_text",
]
