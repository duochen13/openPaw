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


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["meta", "BRK.B", "0700.HK", "A" * 12, "  aapl  "])
def test_output_is_always_a_single_safe_path_component(tmp_path, raw):
    """The real contract, asserted directly rather than by enumerating attacks:
    whatever comes out cannot escape its parent directory."""
    base = tmp_path.resolve()
    resolved = (base / safe_ticker_component(raw)).resolve()
    assert resolved.parent == base
    assert base in resolved.parents


@pytest.mark.unit
def test_output_is_stable_under_repeated_application():
    for raw in ("meta", "BRK.B", "  aapl  "):
        once = safe_ticker_component(raw)
        assert safe_ticker_component(once) == once


@pytest.mark.unit
def test_rejects_an_interior_newline():
    """fullmatch, not strip, is what rejects this: strip only removes
    leading/trailing whitespace and would let 'NV\\nDA' straight through."""
    with pytest.raises(ValueError):
        safe_ticker_component("NV\nDA")


@pytest.mark.unit
def test_accepts_the_maximum_length_of_twelve_characters():
    ticker = "A" * 12
    assert safe_ticker_component(ticker) == ticker


@pytest.mark.unit
def test_rejects_the_ff_ligature_homoglyph():
    """Distinct from the long-s case: uppercasing this ligature EXPANDS its
    length to 'FF' rather than substituting one character for another.
    Written as an escape for the same reason as the long-s test above."""
    ligature_ticker = "\ufb00ord"
    assert ligature_ticker.upper() == "FFORD"
    with pytest.raises(ValueError):
        safe_ticker_component(ligature_ticker)
