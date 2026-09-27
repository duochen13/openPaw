"""Loading and validation for the versioned skill-taxonomy file.

The taxonomy file itself (``skills_ch3_v1.json``) carries the chapter skill
list; this module only guarantees the file's *shape* is correct — it cannot
guarantee the skill list matches the teacher's real curriculum. That review
is the teacher's sign-off step (``status == "pending_teacher_confirmation"``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

#: Default location of the v1 taxonomy file, next to this module.
DEFAULT_TAXONOMY_PATH = Path(__file__).with_name("skills_ch3_v1.json")

#: Top-level fields every taxonomy file must carry.
REQUIRED_TOP_LEVEL_FIELDS = ("version", "chapter", "source", "status", "skills")

#: Per-skill fields every entry must carry.
REQUIRED_SKILL_FIELDS = ("id", "name_zh", "name_en")


class TaxonomyValidationError(ValueError):
    """Raised when a taxonomy file is structurally invalid."""


@dataclass
class Skill:
    """One entry in the taxonomy: a teachable skill (技能）."""

    id: str
    name_zh: str
    name_en: str
    description: str = ""
    question_samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name_zh": self.name_zh,
            "name_en": self.name_en,
            "description": self.description,
            "question_samples": list(self.question_samples),
        }


@dataclass
class Taxonomy:
    """A versioned chapter skill taxonomy."""

    version: str
    chapter: str
    source: str
    status: str
    skills: list[Skill] = field(default_factory=list)
    textbook: str = ""

    def skill_ids(self) -> list[str]:
        return [s.id for s in self.skills]

    def get(self, skill_id: str) -> Skill:
        for skill in self.skills:
            if skill.id == skill_id:
                return skill
        raise KeyError(f"unknown skill id: {skill_id!r}")

    def teacher_confirmed(self) -> bool:
        """True only after the teacher has reviewed and signed off the list."""
        return self.status == "confirmed"


def validate_taxonomy_dict(data: dict) -> list[str]:
    """Return a list of structural problems; empty means valid."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["taxonomy root must be a JSON object"]
    for f in REQUIRED_TOP_LEVEL_FIELDS:
        if f not in data:
            problems.append(f"missing top-level field: {f}")
    skills = data.get("skills")
    if skills is not None and not isinstance(skills, list):
        problems.append("'skills' must be a list")
        return problems
    seen: set[str] = set()
    for i, skill in enumerate(skills or []):
        where = f"skills[{i}]"
        if not isinstance(skill, dict):
            problems.append(f"{where} must be an object")
            continue
        for f in REQUIRED_SKILL_FIELDS:
            if not skill.get(f):
                problems.append(f"{where} missing required field: {f}")
        sid = skill.get("id")
        if sid:
            if sid in seen:
                problems.append(f"duplicate skill id: {sid!r}")
            seen.add(sid)
    return problems


def load_taxonomy(path: str | Path = DEFAULT_TAXONOMY_PATH) -> Taxonomy:
    """Load and validate the taxonomy file. Raises TaxonomyValidationError."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise TaxonomyValidationError(f"taxonomy file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise TaxonomyValidationError(f"taxonomy file is not valid JSON: {e}") from e

    problems = validate_taxonomy_dict(data)
    if problems:
        raise TaxonomyValidationError(
            "invalid taxonomy file:\n- " + "\n- ".join(problems)
        )
    skills = [
        Skill(
            id=s["id"],
            name_zh=s["name_zh"],
            name_en=s["name_en"],
            description=s.get("description", ""),
            question_samples=list(s.get("question_samples", [])),
        )
        for s in data["skills"]
    ]
    return Taxonomy(
        version=data["version"],
        chapter=data["chapter"],
        source=data["source"],
        status=data["status"],
        skills=skills,
        textbook=data.get("textbook", ""),
    )
