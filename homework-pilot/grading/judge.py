"""The verdict judge: three sources, strict priority, never blended.

Priority (issue #176, binding):

1. **Red-pen marks** read from the paper itself. A decisive mark
   (correct/wrong) decides. A *score* mark is the teacher recording
   partial credit (步骤分): v1 must not crush that into a binary
   verdict, so the item goes to 待确认 with reason ``partial_credit``
   (a key comparison, when one is well-defined, may still supply the
   *proposal* the student confirms -- labeled as such, never the
   verdict). A comment-only mark decides nothing and falls through.
2. **Answer-key comparison**, only where the comparison is
   well-defined: a multiple-choice letter, a fill-blank's exact short
   value, or a single numeric final value with a unit. Free-text keys
   (worked solutions, estimation ranges, explanations) are not
   comparable in v1 and never produce a verdict here.
3. **Model self-solve**, determinate-answer questions only, via the
   :class:`~grading.backends.SelfSolver` interface. The v1 backend
   always declines, so this source currently decides nothing -- by
   design, not by omission.

Anything undecided is 待确认 with a reason. The judge never sees the
recognition reliability: legibility is a separate axis handled by the
pipeline, so a shaky read cannot soften or harden a verdict.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from .backends import SelfSolver, Transcription
from .models import (
    REASON_OPEN_TYPE,
    REASON_PARTIAL_CREDIT,
    REASON_UNCERTAIN,
    REASON_UNREADABLE,
)

# Pending-reason codes are re-exported for callers' convenience.
__all__ = [
    "REASON_OPEN_TYPE",
    "REASON_PARTIAL_CREDIT",
    "REASON_UNCERTAIN",
    "REASON_UNREADABLE",
    "JudgeOutcome",
    "comparison_mode",
    "compare_with_key",
    "judge_item",
    "resolve_key_answers",
]


@dataclass(frozen=True)
class JudgeOutcome:
    verdict: str                       # 对 / 错 / 待确认
    source: str                        # deciding (or blocking) source
    proposed_verdict: str = ""
    proposal_source: str = ""
    reference_answer: str = ""
    pending_reason: str = ""
    mark_kind: str = ""


# ---------------------------------------------------------------------------
# Answer-key resolution: whole-question key text -> per-item key answers
# ---------------------------------------------------------------------------

_BLANK_SEGMENT = re.compile(r"blank\d+\s*[：:]\s*([^；;]+)")
_NUMBERED_SEGMENT = re.compile(r"（\d+）")


def resolve_key_answers(question: dict) -> dict[str, str]:
    """Map item_key -> the key's answer for that item.

    Whole-question questions take the full key text. Part keys are
    resolved from the kit's two key formats: ``blank1：X；blank2：Y``
    segments, or ``（1）X；（2）Y`` segments in part order. If neither
    format splits cleanly, every part falls back to the full key text
    (a superset reference, never a fabricated per-part answer).
    """
    qid = question["id"]
    answer = (question.get("answer") or "").strip()
    parts = question.get("parts") or []
    if not parts:
        return {qid: answer}
    blank_segments = _BLANK_SEGMENT.findall(answer)
    if len(blank_segments) == len(parts) and all(
        p.startswith("blank") for p in parts
    ):
        return {
            f"{qid}#{part}": seg.strip()
            for part, seg in zip(parts, blank_segments)
        }
    numbered = [s.strip("；; ").strip() for s in _NUMBERED_SEGMENT.split(answer)]
    numbered = [s for s in numbered if s]
    if len(numbered) == len(parts):
        return {f"{qid}#{part}": seg for part, seg in zip(parts, numbered)}
    return {f"{qid}#{part}": answer for part in parts}


# ---------------------------------------------------------------------------
# Key comparison (verdict source 2)
# ---------------------------------------------------------------------------

_SENTENCE_MARKS = "。；;、——…"
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
_VALUE_UNIT = re.compile(
    r"(-?\d+(?:\.\d+)?(?:\s*[×x*]\s*10\^?-?\d+|\s*[×x*]\s*10[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)?)"
    r"\s*([A-Za-z%°/]+|[米秒千克焦瓦牛])?"
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"[\s。．.，,；;：:、（）()]+", "", text)


def _number_value(token: str) -> float:
    token = unicodedata.normalize("NFKC", token).replace(" ", "")
    if "×10" in token or "x10" in token or "*10" in token:
        base, _, exp = token.replace("*10", "×10").replace("x10", "×10").partition("×10")
        exp = exp.lstrip("^").translate(_SUPERSCRIPTS)
        return float(base) * (10 ** int(exp))
    return float(token)


def _value_units(text: str) -> list[tuple[float, str]]:
    """All (value, unit) pairs in a text, in order of appearance."""
    pairs: list[tuple[float, str]] = []
    for match in _VALUE_UNIT.finditer(text or ""):
        try:
            value = _number_value(match.group(1))
        except ValueError:
            continue
        unit = (match.group(2) or "").strip().lower()
        pairs.append((value, unit))
    return pairs


def _key_numeric(key_answer: str) -> tuple[float, str] | None:
    """Parse a key that is exactly one numeric value + optional unit."""
    text = unicodedata.normalize("NFKC", key_answer).strip()
    match = re.fullmatch(
        r"(-?\d+(?:\.\d+)?(?:\s*[×x*]\s*10\^?-?\d+|\s*[×x*]\s*10[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)?)"
        r"\s*([A-Za-z%°/]+|[米秒千克焦瓦牛])?",
        text,
    )
    if not match:
        return None
    try:
        return _number_value(match.group(1)), (match.group(2) or "").lower()
    except ValueError:
        return None


def comparison_mode(question: dict, key_answer: str) -> str | None:
    """How (if at all) source 2 may compare against this key.

    Returns "letter" (multiple choice), "numeric" (single final
    value), "text" (fill-blank exact value), "phrase" (short verdict
    phrase inside a longer answer; one-directional), or None when the
    key is free text and v1 comparison is not well-defined.
    """
    kind = question.get("kind", "")
    key = _normalize(key_answer)
    if kind == "multiple_choice" and re.fullmatch(r"[A-D]", key):
        return "letter"
    if key and not any(mark in key_answer for mark in "约（(") \
            and _key_numeric(key_answer) is not None:
        return "numeric"
    if kind == "fill_blank" and key and len(key) <= 8 \
            and not any(mark in key for mark in _SENTENCE_MARKS):
        return "text"
    if key and len(key) <= 4 \
            and not any(mark in key for mark in _SENTENCE_MARKS) \
            and not any(ch.isdigit() for ch in key):
        return "phrase"
    return None


def compare_with_key(
    mode: str, key_answer: str, student_answer: str
) -> str | None:
    """Compare a transcription against the key. None = inconclusive."""
    if mode == "letter":
        found = re.search(r"(?<![A-Za-z])[A-D](?![A-Za-z])",
                          unicodedata.normalize("NFKC", student_answer))
        if not found:
            return None
        return "对" if found.group(0) == _normalize(key_answer) else "错"
    if mode == "numeric":
        parsed = _key_numeric(key_answer)
        if parsed is None:
            return None
        key_value, key_unit = parsed
        candidates = _value_units(student_answer)
        same_unit = [v for v, u in candidates if u == key_unit] if key_unit \
            else [v for v, _ in candidates]
        if not same_unit:
            return None
        if any(math.isclose(v, key_value, rel_tol=1e-6) for v in same_unit):
            return "对"
        return "错"
    if mode == "text":
        return "对" if _normalize(student_answer) == _normalize(key_answer) else "错"
    if mode == "phrase":
        # One-directional: finding the key's verdict phrase in the
        # student's words confirms it; not finding it proves nothing
        # about a free-text answer, so it stays inconclusive.
        if _normalize(key_answer) in _normalize(student_answer):
            return "对"
        return None
    return None


# ---------------------------------------------------------------------------
# The judge
# ---------------------------------------------------------------------------

def judge_item(
    *,
    question: dict,
    key_answer: str,
    transcription: Transcription,
    solver: SelfSolver,
) -> JudgeOutcome:
    """Decide one item's verdict from the three sources, in priority.

    Recognition reliability is deliberately *not* a parameter: the
    judge cannot see it, so legibility can never leak into a verdict.
    """
    mark_kind = transcription.mark_kind if transcription else ""
    text = transcription.student_answer if transcription else None

    # Source 1: red-pen marks.
    if mark_kind == "correct":
        return JudgeOutcome("对", "红笔标记", mark_kind=mark_kind)
    if mark_kind == "wrong":
        return JudgeOutcome(
            "错", "红笔标记", reference_answer=key_answer, mark_kind=mark_kind
        )
    if mark_kind == "score":
        # Partial credit （步骤分）: the teacher's judgment is "partly
        # right", which v1 does not binarize. A well-defined key
        # comparison may still lean, as a labeled proposal only.
        if text is None:
            return JudgeOutcome(
                "待确认", "红笔标记",
                pending_reason=REASON_UNREADABLE, mark_kind=mark_kind,
            )
        proposal = ""
        mode = comparison_mode(question, key_answer)
        if mode:
            leaned = compare_with_key(mode, key_answer, text)
            if leaned:
                proposal = leaned
        return JudgeOutcome(
            "待确认", "红笔标记",
            proposed_verdict=proposal,
            proposal_source="答案比对" if proposal else "",
            reference_answer=key_answer if proposal == "错" else "",
            pending_reason=REASON_PARTIAL_CREDIT, mark_kind=mark_kind,
        )
    # A comment-only mark decides nothing: fall through.

    if text is None:
        return JudgeOutcome(
            "待确认", "模型判定",
            pending_reason=REASON_UNREADABLE, mark_kind=mark_kind,
        )

    # Source 2: answer-key comparison, where well-defined.
    mode = comparison_mode(question, key_answer)
    if mode:
        compared = compare_with_key(mode, key_answer, text)
        if compared:
            return JudgeOutcome(
                compared, "答案比对",
                reference_answer=key_answer if compared == "错" else "",
                mark_kind=mark_kind,
            )

    # Source 3: model self-solve, determinate-answer questions only.
    if mode is not None or question.get("answer_is_unique"):
        solved = solver.solve(question.get("stem", ""), text)
        if solved in ("对", "错"):
            return JudgeOutcome(
                solved, "模型判定",
                reference_answer=key_answer if solved == "错" else "",
                mark_kind=mark_kind,
            )
        reason = REASON_UNCERTAIN
    else:
        # Process-credit / open-ended types are not auto-judged in v1.
        reason = REASON_OPEN_TYPE
    return JudgeOutcome(
        "待确认", "模型判定", pending_reason=reason, mark_kind=mark_kind
    )
