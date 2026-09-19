import json

import pytest

from portfolio_analysis.artifacts import MovesArtifact, read_moves, write_moves
from portfolio_analysis.config import MoveParams
from portfolio_analysis.moves import Coverage, Move

MOVE = Move(
    ticker="META", date="2024-04-25", ret=-0.105613, benchmark="QQQ",
    benchmark_return=-0.004830, beta=1.490, alpha=0.000312,
    abnormal_return=-0.098419, sigma_60=0.026083, z=-3.77,
)
COVERAGE = Coverage(
    price_series=("2020-09-14", "2026-09-11"),
    evaluated=("2021-09-13", "2026-09-11"),
    evaluated_days=1255,
    flagged_days=30,
)
PARAMS = MoveParams(beta_window=250, sigma_window=60, z_threshold=2.5)


@pytest.mark.unit
def test_round_trips_through_disk(tmp_path):
    path = write_moves(tmp_path, MovesArtifact("META", "QQQ", PARAMS, COVERAGE, [MOVE]))
    assert path.name == "META.json"
    loaded = read_moves(path)
    assert loaded.ticker == "META"
    assert loaded.coverage.flagged_days == 30
    assert loaded.moves[0].date == "2024-04-25"
    assert loaded.moves[0].z == pytest.approx(-3.77)


@pytest.mark.unit
def test_the_written_json_records_the_parameters(tmp_path):
    """A move list without its threshold is not reproducible."""
    path = write_moves(tmp_path, MovesArtifact("META", "QQQ", PARAMS, COVERAGE, [MOVE]))
    raw = json.loads(path.read_text())
    assert raw["params"] == {
        "beta_window": 250, "sigma_window": 60, "z_threshold": 2.5
    }
    assert raw["coverage"]["evaluated_days"] == 1255


@pytest.mark.unit
def test_the_filename_is_a_sanitized_ticker(tmp_path):
    with pytest.raises(ValueError):
        write_moves(tmp_path, MovesArtifact("../etc", "QQQ", PARAMS, COVERAGE, []))
