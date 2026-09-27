"""Privacy guard utilities: ID-only enforcement, text scrubbing, and deletion.

Design principles (see homework-pilot/docs/privacy-governance.md):

* Student records are keyed by student ID (学号) only. Names (姓名) never enter
  storage, logs, exports, or payloads sent to external services.
* The ID→name roster, if one ever exists, stays off-repo and is never passed
  to these functions. ``scrub_text`` therefore detects *likely* name mentions
  heuristically and flags them for human review rather than claiming perfect
  detection.
* Deletion is a first-class path: ``delete_student_records`` removes every
  record for a student and verifies nothing remains.

What these heuristics CAN and CANNOT do (documented limitation):

CAN:
  - Reject any record carrying a name-like field key (``assert_id_only``),
    e.g. ``name``, ``student_name``, ``姓名`` — recursively through nested
    dicts/lists.
  - Flag CJK name candidates that appear in a name-indicator context
    (``contains_cjk_name_candidate``), e.g. ``学生：张伟``, ``姓名：李小明``,
    ``王芳同学``. Candidates are returned as spans for ``redact`` and always
    marked "human-review-required" because a 2–4 character CJK run can also be
    an ordinary word (e.g. ``能量转化``).
  - Strip a payload down to an allowlist of fields before it leaves for an
    external service (``scrub_for_external_service``).

CANNOT:
  - Reliably find a Chinese name with no indicator words nearby (``张伟`` alone
    in a sentence is indistinguishable from ordinary text). Do not treat a
    clean ``scrub_text`` result as proof that no name is present.
  - Detect names in handwriting, images, or scanned PDFs — OCR output must go
    through ``scrub_text`` and then human review before storage.
  - Redact Latin-script names with high precision; the indicator list covers
    both scripts conservatively but plain ``John`` in prose will be missed.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Iterable, List, Mapping, MutableMapping, Tuple

__all__ = [
    "NameFieldError",
    "StudentStore",
    "DictStudentStore",
    "assert_id_only",
    "contains_cjk_name_candidate",
    "redact",
    "scrub_text",
    "sanitize_log_message",
    "scrub_for_external_service",
    "delete_student_records",
]


# ---------------------------------------------------------------------------
# ID-only enforcement
# ---------------------------------------------------------------------------

#: Field keys that must never appear in a student record. Compared after
#: lower-casing and stripping whitespace. Anything ending in ``_name`` /
#: ``-name`` / ``姓名`` is also rejected by :func:`assert_id_only`.
NAME_FIELD_KEYS = frozenset(
    {
        "name",
        "names",
        "student_name",
        "studentname",
        "full_name",
        "fullname",
        "given_name",
        "family_name",
        "first_name",
        "last_name",
        "display_name",
        "nickname",
        "username",
        "姓名",
        "学生姓名",
        "学生名",
        "名字",
        "全名",
        "花名",
    }
)


class NameFieldError(ValueError):
    """Raised when a record contains a name-like field (violates ID-only rule)."""


def _normalize_key(key: Any) -> str:
    return str(key).strip().lower()


def _is_name_key(key: Any) -> bool:
    """True if a field key looks like it carries a person's name."""
    norm = _normalize_key(key)
    if norm in NAME_FIELD_KEYS:
        return True
    # Catch compound keys such as "parent_name", "teacher-name", "家长姓名".
    for suffix in ("_name", "-name", "姓名", "名字"):
        if norm.endswith(suffix) and norm != suffix.strip("_-"):
            return True
    return False


def _find_name_keys(obj: Any, path: str = "$") -> List[str]:
    """Recursively collect dotted paths of name-like keys in nested data."""
    found: List[str] = []
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            child = f"{path}.{key}"
            if _is_name_key(key):
                found.append(child)
            found.extend(_find_name_keys(value, child))
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            found.extend(_find_name_keys(value, f"{path}[{i}]"))
    return found


def assert_id_only(record: Mapping[str, Any], *, where: str = "record") -> None:
    """Validate that a record carries no name-like fields.

    Raises :class:`NameFieldError` listing every offending key path if any
    name-like key (e.g. ``name``, ``student_name``, ``姓名``) is found,
    recursively. Call this at every storage, log, and export boundary.
    """
    if not isinstance(record, Mapping):
        raise TypeError(f"{where}: expected a mapping, got {type(record).__name__}")
    offenders = _find_name_keys(record)
    if offenders:
        raise NameFieldError(
            f"{where}: ID-only violation — name-like fields must not be stored: "
            + ", ".join(offenders)
        )


# ---------------------------------------------------------------------------
# Name-candidate detection (heuristic; flags for human review)
# ---------------------------------------------------------------------------

_CJK = "\u4e00-\u9fff"

#: Words that signal a name is nearby. A 2–4 character CJK run is flagged only
#: in one of these contexts — this keeps precision acceptable at the cost of
#: recall (a name with no indicator nearby is NOT flagged; see module docs).
_NAME_INDICATORS = (
    "姓名",
    "学生姓名",
    "学生",
    "同学",
    "名字",
    "考生",
)

# Indicator + colon, then a 2–4 CJK-char run, e.g. "学生：张伟".
# The colon is required on purpose: in this domain, phrases like 学生作业
# ("student homework") are everywhere, and matching indicator+CJK without a
# colon would flag ordinary words ("作业") as name candidates constantly.
# Consequence (documented limitation): "姓名 李小明" (space, no colon) is
# NOT flagged.
_INDICATOR_BEFORE = re.compile(
    rf"(?:{'|'.join(_NAME_INDICATORS)})\s*[：:]\s*([{_CJK}]{{2,4}})"
)
# A 2–4 CJK-char run followed by 同学/学生, e.g. "王芳同学".
_INDICATOR_AFTER = re.compile(rf"([{_CJK}]{{2,4}})(?:同学|学生)")


def contains_cjk_name_candidate(text: str) -> List[Tuple[int, int, str]]:
    """Find likely Chinese-name spans in text.

    Returns a list of ``(start, end, span_text)`` candidates found next to
    name-indicator words (e.g. ``学生：张伟``). Every hit is a *candidate*:
    callers must treat these as "flag for human review", never as certain
    names, and must not assume that the absence of hits means no name is
    present.
    """
    hits: List[Tuple[int, int, str]] = []
    for pattern in (_INDICATOR_BEFORE, _INDICATOR_AFTER):
        for match in pattern.finditer(text or ""):
            start, end = match.span(1)
            hits.append((start, end, match.group(1)))
    hits.sort()
    return hits


def redact(text: str, spans: Iterable[Tuple[int, int, str]]) -> str:
    """Replace flagged spans with ``[REDACTED]``. Overlapping spans are merged."""
    ordered = sorted((s, e) for s, e, _ in spans)
    merged: List[List[int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    out: List[str] = []
    cursor = 0
    for start, end in merged:
        out.append(text[cursor:start])
        out.append("[REDACTED]")
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def scrub_text(text: str) -> Tuple[str, List[dict]]:
    """Detect likely name mentions, redact them, and report findings.

    Returns ``(redacted_text, findings)`` where each finding is
    ``{"span": (start, end), "text": <redacted span>, "reason": ...,
    "review": "human-review-required"}``. The redaction is a safety net for
    logs/prompts — it does not prove the text is name-free.
    """
    candidates = contains_cjk_name_candidate(text)
    cleaned = redact(text, candidates)
    findings = [
        {
            "span": (start, end),
            "text": span_text,
            "reason": "CJK run (2-4 chars) adjacent to a name-indicator word",
            "review": "human-review-required",
        }
        for start, end, span_text in candidates
    ]
    return cleaned, findings


def sanitize_log_message(text: str) -> str:
    """Scrub a log line before it is emitted. Convenience wrapper."""
    cleaned, _ = scrub_text(text)
    return cleaned


# ---------------------------------------------------------------------------
# External-service payload filtering
# ---------------------------------------------------------------------------

def _require_id_only_payload(payload: Any, where: str) -> None:
    if isinstance(payload, Mapping):
        assert_id_only(payload, where=where)
    elif isinstance(payload, (list, tuple)):
        for i, item in enumerate(payload):
            if isinstance(item, Mapping):
                assert_id_only(item, where=f"{where}[{i}]")
    else:
        raise TypeError(f"{where}: expected a mapping or list of mappings")


def scrub_for_external_service(
    payload: Any,
    allowed_fields: Iterable[str],
) -> Any:
    """Allowlist-filter a payload before it leaves for an external service.

    * First runs :func:`assert_id_only` on the whole payload, so a payload
      that *contains* a name field is rejected rather than silently dropped.
    * Then returns a copy containing only ``allowed_fields`` (exact key
      match). Nested dicts/lists are filtered recursively; non-mapping items
      inside lists are passed through unchanged.

    The caller is responsible for having a documented reason and the teacher's
    acknowledgement for the service (see privacy-governance.md).
    """
    _require_id_only_payload(payload, "payload")
    allowed = set(allowed_fields)

    def _filter(obj: Any) -> Any:
        if isinstance(obj, Mapping):
            return {k: _filter(v) for k, v in obj.items() if k in allowed}
        if isinstance(obj, list):
            return [_filter(item) for item in obj]
        if isinstance(obj, tuple):
            return tuple(_filter(item) for item in obj)
        return obj

    return _filter(payload)


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

class StudentStore(ABC):
    """Minimal storage interface the privacy layer operates against.

    Implementations keep records keyed by student ID only. This interface is
    deliberately tiny so the deletion path does not depend on any particular
    storage backend (or on other homework-pilot modules).
    """

    @abstractmethod
    def list_student_ids(self) -> Iterable[str]:
        """Return all student IDs currently in the store."""
        ...

    @abstractmethod
    def get_records(self, student_id: str) -> List[Mapping[str, Any]]:
        """Return all records for one student (empty list if unknown)."""
        ...

    @abstractmethod
    def delete_records(self, student_id: str) -> int:
        """Remove every record for one student; return the number removed."""
        ...


class DictStudentStore(StudentStore):
    """In-memory :class:`StudentStore` backed by ``{student_id: [records]}``.

    Used by tests and as a reference implementation. Real backends implement
    :class:`StudentStore` themselves.
    """

    def __init__(self, data: MutableMapping[str, List[Mapping[str, Any]]] | None = None):
        self._data: MutableMapping[str, List[Mapping[str, Any]]] = data if data is not None else {}

    def list_student_ids(self) -> Iterable[str]:
        return list(self._data.keys())

    def get_records(self, student_id: str) -> List[Mapping[str, Any]]:
        return list(self._data.get(student_id, []))

    def delete_records(self, student_id: str) -> int:
        records = self._data.pop(student_id, [])
        return len(records)


def delete_student_records(store: StudentStore, student_id: str) -> int:
    """Delete every record for ``student_id`` and verify the deletion.

    Returns the number of records removed (0 if the ID was unknown).
    Raises :class:`RuntimeError` if verification finds records still present
    after deletion — a partial delete must never be reported as complete.
    """
    removed = store.delete_records(student_id)
    remaining = store.get_records(student_id)
    if remaining:
        raise RuntimeError(
            f"deletion verification failed for student {student_id!r}: "
            f"{len(remaining)} record(s) still present"
        )
    return removed
