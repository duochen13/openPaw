"""Evaluation harness for recognition accuracy (issue #111 acceptance).

``evaluate(recognizer, labeled_set)`` runs a recognizer over labeled
items and reports accuracy overall and per item type (handwriting vs
grading marks), plus a reliability-calibration breakdown so we can tell
whether the review queue actually catches the errors that matter.

The 5 real sample papers do not exist yet (field work in #108); the
harness runs on synthetic labeled data now and on the real set later
with zero code changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from models import GradingMarkKind, Recognition, SegmentedItem
from recognizer import GRADING_MARK, HANDWRITING, Recognizer


@dataclass
class LabeledItem:
    """One ground-truth item for evaluation."""
    item: SegmentedItem
    item_type: str  # "handwriting" | "grading_mark"
    expected_text: Optional[str] = None
    expected_mark: Optional[GradingMarkKind] = None
    expected_score: Optional[str] = None


@dataclass
class EvalReport:
    total: int = 0
    correct: int = 0
    per_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # reliability calibration: bucket -> {"n": int, "correct": int}
    calibration: Dict[str, Dict[str, int]] = field(default_factory=dict)
    errors: List[Dict] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def accuracy_for(self, item_type: str) -> float:
        d = self.per_type.get(item_type, {"correct": 0, "total": 0})
        return d["correct"] / d["total"] if d["total"] else 0.0

    def to_dict(self) -> Dict:
        return {
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "per_type": {
                t: {**d, "accuracy": round(d["correct"] / d["total"], 4) if d["total"] else 0.0}
                for t, d in self.per_type.items()
            },
            "calibration": self.calibration,
            "error_count": len(self.errors),
        }


def _bucket(reliability: float) -> str:
    if reliability < 0.5:
        return "0.0-0.5"
    if reliability < 0.8:
        return "0.5-0.8"
    if reliability < 0.95:
        return "0.8-0.95"
    return "0.95-1.0"


def is_correct(rec: Recognition, labeled: LabeledItem) -> bool:
    if labeled.item_type == HANDWRITING:
        return (rec.text or "").strip() == (labeled.expected_text or "").strip()
    mark_ok = rec.mark == labeled.expected_mark
    score_ok = (rec.score or "").strip() == (labeled.expected_score or "").strip()
    return bool(mark_ok and score_ok)


def evaluate(recognizer: Recognizer, labeled_set: List[LabeledItem]) -> EvalReport:
    report = EvalReport()
    for labeled in labeled_set:
        rec = recognizer.recognize(labeled.item, labeled.item_type)
        ok = is_correct(rec, labeled)
        report.total += 1
        report.correct += int(ok)
        d = report.per_type.setdefault(labeled.item_type, {"correct": 0, "total": 0})
        d["total"] += 1
        d["correct"] += int(ok)
        b = report.calibration.setdefault(_bucket(rec.reliability), {"n": 0, "correct": 0})
        b["n"] += 1
        b["correct"] += int(ok)
        if not ok:
            report.errors.append({
                "item_key": labeled.item.sub_question.item_key,
                "item_type": labeled.item_type,
                "reliability": rec.reliability,
                "got_text": rec.text, "expected_text": labeled.expected_text,
                "got_mark": rec.mark.value if rec.mark else None,
                "expected_mark": labeled.expected_mark.value if labeled.expected_mark else None,
            })
    return report


# ---------------------------------------------------------------------------
# Go / no-go report
# ---------------------------------------------------------------------------

GO_NO_GO_TEMPLATE = """# Recognition go/no-go — {date}

Evaluated on: {dataset}
Recognizer under test: {recognizer_name}

## Accuracy (per item type)
{accuracy_lines}

## Reliability calibration
{calibration_lines}

## Review-queue effectiveness
Errors with reliability >= threshold ({threshold}): {missed_errors}  <- these would slip through silently
Errors caught by the queue: {caught_errors}

## Verdict
{verdict_lines}

## Notes
{notes}
"""


def go_no_go_report(report: EvalReport, *, recognizer_name: str, dataset: str,
                     threshold: float = 0.8,
                     handwriting_target: float = 0.95,
                     grading_mark_target: float = 0.98) -> str:
    """Render the go/no-go note required by #111.

    Targets are placeholders to be set with the teacher before the pilot;
    the verdict lines state explicitly which recognition tasks are
    pilot-ready vs need more work.
    """
    hw_acc = report.accuracy_for(HANDWRITING)
    gm_acc = report.accuracy_for(GRADING_MARK)
    missed = sum(1 for e in report.errors if e["reliability"] >= threshold)
    caught = len(report.errors) - missed

    accuracy_lines = "\n".join(
        f"- {t}: {d['correct']}/{d['total']} = {d['correct']/d['total']:.1%}" if d["total"]
        else f"- {t}: no labeled items"
        for t, d in sorted(report.per_type.items()))

    calibration_lines = "\n".join(
        f"- reliability {b}: {d['correct']}/{d['n']} correct"
        for b, d in sorted(report.calibration.items())) or "- (no data)"

    verdicts = []
    hw_n = report.per_type.get(HANDWRITING, {}).get("total", 0)
    gm_n = report.per_type.get(GRADING_MARK, {}).get("total", 0)
    if hw_n == 0:
        verdicts.append("- handwriting recognition: UNEVALUATED (no labeled data — "
                        "the 5 sample papers from #108 do not exist yet). NOT pilot-ready by default.")
    elif hw_acc >= handwriting_target:
        verdicts.append(f"- handwriting recognition: PILOT-READY ({hw_acc:.1%} >= {handwriting_target:.0%} target).")
    else:
        verdicts.append(f"- handwriting recognition: NEEDS MORE WORK ({hw_acc:.1%} < {handwriting_target:.0%} target). "
                        "Use the manual-entry fallback for the pilot.")
    if gm_n == 0:
        verdicts.append("- grading-mark recognition （批改痕迹）: UNEVALUATED (no labeled data). NOT pilot-ready by default.")
    elif gm_acc >= grading_mark_target:
        verdicts.append(f"- grading-mark recognition: PILOT-READY ({gm_acc:.1%} >= {grading_mark_target:.0%} target).")
    else:
        verdicts.append(f"- grading-mark recognition: NEEDS MORE WORK ({gm_acc:.1%} < {grading_mark_target:.0%} target). "
                        "Use the manual-entry fallback for the pilot.")
    if missed > 0:
        verdicts.append(f"- WARNING: {missed} error(s) had reliability >= threshold and would slip past "
                        "the review queue — threshold or calibration needs work.")

    from datetime import date
    return GO_NO_GO_TEMPLATE.format(
        date=date.today().isoformat(),
        dataset=dataset,
        recognizer_name=recognizer_name,
        accuracy_lines=accuracy_lines or "- (no data)",
        calibration_lines=calibration_lines,
        threshold=threshold,
        missed_errors=missed,
        caught_errors=caught,
        verdict_lines="\n".join(verdicts),
        notes=("The eval set is SYNTHETIC until the 5 real sample papers from #108 land. "
               "Re-run evaluate() + go_no_go_report() on the real set before trusting any verdict."),
    )
