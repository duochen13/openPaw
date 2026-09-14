import pytest


@pytest.mark.unit
def test_package_imports():
    import portfolio_analysis  # noqa: F401
