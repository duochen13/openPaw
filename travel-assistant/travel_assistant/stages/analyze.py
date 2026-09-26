"""Analyze stage: raw discussions -> structured places object.

In the v1 skill workflow this step is performed by an LLM subagent (SKILL.md
Step 3: dedup/rank with verbatim cited quotes), not a script — there is
deliberately no default analyzer implementation here. This module defines the
stage interface so the pipeline, run store, and future API/MCP layers treat it
uniformly:

    analyzer(raw: dict, *, destination: str, vibe: str) -> places_obj: dict

`places_obj` must carry destination, generated_at, source_mode, places[] per
schema.py (it is validated by the next stage). Pass `analyzer=` explicitly, or
use research(..., from_analysis=<path>) to replay a previously produced
analysis file — that is also how tests exercise the pipeline with no LLM call.
"""
import json


def analyze_raw(raw, *, destination, vibe="all", analyzer=None):
    if analyzer is None:
        raise NotImplementedError(
            "No analyzer configured: the analyze step is the LLM subagent pass "
            "(SKILL.md Step 3). Pass analyzer=<callable> or replay a saved "
            "analysis with research(..., from_analysis=<path>).")
    return analyzer(raw, destination=destination, vibe=vibe)


def load_analysis(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_analysis(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    return str(path)
