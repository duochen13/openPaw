# tests/test_naming.py
import pytest

from portfolio_analysis.naming import safe_ticker_component


@pytest.mark.unit
def test_uppercases_a_valid_ticker():
    assert safe_ticker_component("meta") == "META"


@pytest.mark.unit
def test_allows_dots_and_hyphens_inside():
    assert safe_ticker_component("BRK.B") == "BRK.B"


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["../etc", "A..B", "", "NVDA.", ".NVDA", "A" * 13, "a/b"])
def test_rejects_path_unsafe_input(bad):
    with pytest.raises(ValueError):
        safe_ticker_component(bad)


@pytest.mark.unit
def test_rejects_non_string():
    with pytest.raises(TypeError):
        safe_ticker_component(123)


@pytest.mark.unit
def test_validates_before_uppercasing():
    """U+017F uppercases to 'S', so 'snow' and its long-s spelling would
    otherwise collapse to the same cache key and serve one company's data
    for another's. Validating first means upper() only ever runs on ASCII.

    Written as an escape, not as the literal glyph: ruff's RUF001 flags
    ambiguous unicode in string literals, and the ambiguity is the whole
    point of this test. The escape is the same string to Python and names
    the codepoint under test instead of hiding it in a homoglyph."""
    with pytest.raises(ValueError):
        safe_ticker_component("\u017fnow")
