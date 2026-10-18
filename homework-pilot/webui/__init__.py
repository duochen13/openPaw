"""Teacher console UI for homework-pilot (issue #167).

The first teacher-facing frontend: a self-contained HTML console in the
Muse desktop design language (warm ivory paper, white cards, one clay
accent), rendered from view models that mirror the upstream package
shapes. Five views -- 工作台 / 识别确认 / 薄弱点确认 / 作业审核 / 导出 --
bound to synthetic demo fixtures until real field materials land (#108).

* :mod:`webui.models` -- view dataclasses + the five teaching-judgment
  states, OCR reliability tiers, and the privacy rules they encode.
* :mod:`webui.fixtures` -- invented demo data (S-0xx IDs, SYN- questions).
* :mod:`webui.render` -- view-model builders + the single-file renderer.

Render with ``python3 -m webui [output.html]`` from ``homework-pilot/``.
"""

from .fixtures import build_demo_data
from .models import (
    GRADING_RESULTS,
    MASTERY_STATES,
    MIX_CATEGORIES,
    ClassData,
    ConsoleData,
    EvidenceSnippet,
    ExportInfo,
    RecognitionItem,
    ReliabilityTier,
    ReviewQuestionView,
    SkillHypothesisView,
    StudentMix,
    reliability_tier,
)
from .render import render_console

__all__ = [
    "GRADING_RESULTS",
    "MASTERY_STATES",
    "MIX_CATEGORIES",
    "ClassData",
    "ConsoleData",
    "EvidenceSnippet",
    "ExportInfo",
    "RecognitionItem",
    "ReliabilityTier",
    "ReviewQuestionView",
    "SkillHypothesisView",
    "StudentMix",
    "build_demo_data",
    "reliability_tier",
    "render_console",
]
