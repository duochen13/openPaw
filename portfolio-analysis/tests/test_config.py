# tests/test_config.py
import pytest

from portfolio_analysis.config import PROJECT_ROOT, load_portfolio, resolve_path


@pytest.mark.unit
def test_loads_the_default_portfolio():
    portfolio = load_portfolio()
    assert portfolio.symbols == ("META",)
    assert portfolio.benchmark == "QQQ"
    assert portfolio.price_years == 6


@pytest.mark.unit
def test_move_params_come_from_config():
    params = load_portfolio().move_params
    assert params.beta_window == 250
    assert params.sigma_window == 60
    assert params.z_threshold == 2.5


@pytest.mark.unit
def test_entry_lookup_is_case_insensitive():
    entry = load_portfolio().entry("meta")
    assert entry.cik == 1326801
    assert entry.name == "Meta Platforms, Inc."


@pytest.mark.unit
def test_entry_lookup_raises_on_unknown_symbol():
    with pytest.raises(KeyError):
        load_portfolio().entry("TSLA")


@pytest.mark.unit
def test_resolve_maps_names_and_aliases_to_symbols():
    portfolio = load_portfolio()
    assert portfolio.resolve("Facebook") == "META"
    assert portfolio.resolve("meta platforms, inc.") == "META"
    assert portfolio.resolve("TSLA") is None


@pytest.mark.unit
def test_paths_resolve_against_the_project_root_not_the_cwd():
    """The CLI must write to the same database regardless of invocation dir."""
    assert resolve_path("data/prices.sqlite") == PROJECT_ROOT / "data" / "prices.sqlite"
    assert (PROJECT_ROOT / "pyproject.toml").exists()


@pytest.mark.unit
def test_sigma_window_must_be_smaller_than_beta_window():
    """compute_moves derives sigma inside the beta window, so a sigma window
    at least as large as the beta window would index before the series start."""
    from portfolio_analysis.config import MoveParams

    with pytest.raises(ValueError):
        MoveParams(beta_window=60, sigma_window=60, z_threshold=2.5)
