"""Student-side MVP UI for homework-pilot (issue #176).

The product pivoted from the #167 teacher console to a student-side
MVP: a student uploads a scanned PDF of a completed paper and gets one
verdict per question （对 / 错 / 待确认）, with a confirmation queue for
the questions the system could not settle. One self-contained HTML
file in the Muse desktop design language, rendered from view models
over synthetic demo fixtures.

* :mod:`webui.models` -- view dataclasses + the verdict vocabulary,
  verdict sources, OCR reliability tiers, and the privacy rules they
  encode (ID-only students; reliability kept separate from verdicts).
* :mod:`webui.fixtures` -- invented demo data (one student, S-023).
* :mod:`webui.render` -- view-model builders + the single-file renderer.
* :mod:`webui.serve` -- the local web server (issue #179): the same
  views over the live ``grading`` pipeline, with uploads and a
  persistent confirmation store.

Render with ``python3 -m webui [output.html]`` from ``homework-pilot/``;
serve with ``python3 -m webui --serve [--port 8000]``.
"""

from .fixtures import build_demo_data
from .models import (
    PAPER_STATUSES,
    VERDICTS,
    VERDICT_SOURCES,
    PaperResult,
    QuestionResult,
    ReliabilityTier,
    StudentData,
    reliability_tier,
)
from .render import render_demo

__all__ = [
    "PAPER_STATUSES",
    "VERDICTS",
    "VERDICT_SOURCES",
    "PaperResult",
    "QuestionResult",
    "ReliabilityTier",
    "StudentData",
    "build_demo_data",
    "reliability_tier",
    "render_demo",
]
