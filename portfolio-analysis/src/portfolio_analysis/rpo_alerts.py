"""RPO growth deceleration alerts (issue #36).

The per-seat disruption thesis (private credit rotating out of SaaS direct
lending because AI agents erode per-seat licensing) has two equity-level
canaries for NOW: seat counts declining and RPO growth decelerating. Seat
counts are not disclosed, so the closest proxies are hand-entered
(``manual_kpis.py``); RPO *is* XBRL-tagged (``kpis.METRIC_DEFS["rpo"]``,
issue #29), so the deceleration flag can be computed from the EDGAR
series automatically.

A flag fires when RPO YoY growth:
- falls *below* ``yoy_floor_pct`` (Daniel's call 2026-09-20: 21% - any
  deceleration from the then-current ~21.3% level flags), OR
- drops *more than* ``qoq_drop_pp`` percentage points vs the prior
  quarter's YoY.

Both thresholds live in ``config/kpi_metrics.yaml`` under
``rpo_deceleration`` so Daniel can tune them without a code change; the
config is per-ticker so CRM (or any ticker) can get its own alert later.

Everything here is pure: no I/O except the config loader, no dashboard
or template code. ``render.py`` attaches a flagged result to the RPO
panel; the template renders it as a warning line. This module never
touches #29's EDGAR plumbing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: Same project-root resolution as kpis.py (no wheel install; paths
#: resolve against the source checkout). Shares the file with the metric
#: registry because the thresholds tune a metric-level behavior.
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "kpi_metrics.yaml"


class RpoAlertConfigError(ValueError):
    """config/kpi_metrics.yaml 'rpo_deceleration' section is malformed."""


#: Boundary tolerance for the strict comparisons ("below 21%", "more
#: than 5pp"): float arithmetic can land a hair above an exact boundary
#: (e.g. (0.27 - 0.22) * 100 == 5.000000000000004). Any genuine trigger
#: exceeds the threshold by far more than this.
_EPS = 1e-9


@dataclass(frozen=True)
class RpoDecelerationConfig:
    """Tunables for one ticker's RPO deceleration alert."""

    #: Flag when RPO YoY growth falls strictly below this, in percent
    #: (21.0 means "below 21% YoY").
    yoy_floor_pct: float
    #: Flag when RPO YoY drops strictly more than this many percentage
    #: points vs the prior quarter's YoY.
    qoq_drop_pp: float


@dataclass(frozen=True)
class RpoDecelerationFlag:
    """Result of evaluating one RPO YoY series."""

    flagged: bool
    #: Most recent quarter with a defined YoY, or None when unevaluable.
    latest_quarter: str | None
    #: Most recent YoY as a fraction (0.204 = 20.4%), or None.
    latest_yoy: float | None
    #: Prior quarter's YoY as a fraction, or None when unavailable.
    prior_yoy: float | None
    #: Human-readable trigger description; None when not flagged.
    reason: str | None


def load_rpo_deceleration_config(
    path: str | Path | None = None,
) -> dict[str, RpoDecelerationConfig]:
    """Per-ticker alert tunables from ``config/kpi_metrics.yaml``.

    The ``rpo_deceleration`` section is optional - a config without it
    means "no alerts", not an error - but a present-yet-malformed section
    raises :class:`RpoAlertConfigError` loudly so a typo never silently
    disables the canary.
    """
    source = Path(path) if path else _CONFIG_PATH
    raw = yaml.safe_load(source.read_text())
    if not isinstance(raw, dict):
        raise RpoAlertConfigError(f"{source}: top level must be a mapping")
    block = raw.get("rpo_deceleration") or {}
    if not isinstance(block, dict):
        raise RpoAlertConfigError(f"{source}: 'rpo_deceleration' must be a mapping")
    out: dict[str, RpoDecelerationConfig] = {}
    for ticker, spec in block.items():
        where = f"{source}: rpo_deceleration.{ticker}"
        if not isinstance(spec, dict):
            raise RpoAlertConfigError(f"{where}: must be a mapping")
        out[str(ticker).upper()] = RpoDecelerationConfig(
            yoy_floor_pct=_pct(spec.get("yoy_floor_pct"), "yoy_floor_pct", where),
            qoq_drop_pp=_pct(spec.get("qoq_drop_pp"), "qoq_drop_pp", where),
        )
    return out


def _pct(value: Any, name: str, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RpoAlertConfigError(f"{where}: {name} must be a number, got {value!r}")
    if not (0 <= value < 1000):  # NaN fails the comparison too
        raise RpoAlertConfigError(f"{where}: {name} must be a finite non-negative number")
    return float(value)


def rpo_deceleration_flag(
    yoy: Sequence[tuple[str, float | None]],
    config: RpoDecelerationConfig,
) -> RpoDecelerationFlag:
    """Evaluate the deceleration rule against an RPO YoY series.

    ``yoy`` is ``(quarter, yoy)`` oldest first, YoY as a fraction
    (0.213 = 21.3%) - the same shape ``kpis.kpi_panels`` puts on the RPO
    panel. The latest quarter with a defined YoY is compared against the
    floor; the quarter before it (also YoY-defined) feeds the
    quarter-over-quarter drop check. Missing YoY entries are skipped,
    never interpolated. With no defined YoY at all, or a missing latest
    quarter, there is nothing to evaluate - no flag, no crash.
    """
    defined = [(q, v) for q, v in yoy if v is not None]
    if not defined:
        return RpoDecelerationFlag(False, None, None, None, None)
    latest_q, latest = defined[-1]
    prior = defined[-2][1] if len(defined) >= 2 else None

    triggers: list[str] = []
    latest_pct = latest * 100
    # Comparisons are strict ("below 21%", "more than 5pp") but tolerate
    # float noise at the exact boundary (e.g. (0.27 - 0.22) * 100 is
    # 5.000000000000004, not 5).
    if latest_pct < config.yoy_floor_pct - _EPS:
        triggers.append(
            f"RPO YoY growth {latest_pct:.1f}% fell below the {config.yoy_floor_pct:.1f}% floor"
        )
    if prior is not None:
        drop_pp = (prior - latest) * 100
        if drop_pp > config.qoq_drop_pp + _EPS:
            triggers.append(
                f"RPO YoY growth dropped {drop_pp:.1f}pp vs the prior quarter "
                f"({latest_pct:.1f}% vs {prior * 100:.1f}%) - more than the "
                f"{config.qoq_drop_pp:.1f}pp threshold"
            )
    if not triggers:
        return RpoDecelerationFlag(False, latest_q, latest, prior, None)
    return RpoDecelerationFlag(True, latest_q, latest, prior, " and ".join(triggers))
