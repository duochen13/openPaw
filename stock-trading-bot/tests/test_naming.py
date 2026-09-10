
import pytest

from stock_trading_bot.naming import safe_ticker_component


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("nvda", "NVDA"),
    ("NOW", "NOW"),
    ("BRK.B", "BRK.B"),
    ("0700.HK", "0700.HK"),
    ("  aapl  ", "AAPL"),
    ("A", "A"),
    ("A" * 12, "A" * 12),          # the last accepted length
    ("NVDA\n", "NVDA"),            # trailing whitespace is normalized, like "  aapl  "
])
def test_valid_tickers_are_normalized(raw, expected):
    assert safe_ticker_component(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize("hostile", [
    "../../etc/passwd",
    "..",
    "A..B",                        # regex alone would accept this
    "a/b",
    "a\\b",
    "NVDA;rm -rf /",
    "NVDA\x00",
    "NV\nDA",                      # interior newline; fullmatch rejects, strip cannot
    "",
    "   ",
    "A" * 13,                      # one past the limit
    "NVDA.",                       # Win32 strips a trailing dot
    "NVDA-",
    ".NVDA",
    "-NVDA",
])
def test_hostile_tickers_are_rejected(hostile):
    with pytest.raises(ValueError):
        safe_ticker_component(hostile)


@pytest.mark.unit
@pytest.mark.parametrize("homoglyph,collides_with", [
    ("ſnow", "SNOW"),         # noqa: RUF001 - LATIN SMALL LETTER LONG S -> 'S'
    ("ınvda", "INVDA"),       # noqa: RUF001 - DOTLESS I -> 'I'
    ("ﬀord", "FFORD"),        # ligature ff -> 'FF', also expands length
])
def test_unicode_that_uppercases_into_ascii_is_rejected(homoglyph, collides_with):
    """str.upper() maps some non-ASCII into ASCII. Validating before
    uppercasing stops two distinct symbols collapsing to one cache key."""
    assert homoglyph.upper() == collides_with     # the hazard is real
    with pytest.raises(ValueError):
        safe_ticker_component(homoglyph)


@pytest.mark.unit
def test_non_string_input_raises_type_error():
    with pytest.raises(TypeError):
        safe_ticker_component(None)


@pytest.mark.unit
@pytest.mark.parametrize("raw", [
    "nvda", "BRK.B", "0700.HK", "A" * 12, "  aapl  ",
])
def test_output_is_always_a_single_safe_path_component(tmp_path, raw):
    """The real contract, asserted directly rather than by enumerating attacks:
    whatever comes out cannot escape its parent directory."""
    base = tmp_path.resolve()
    resolved = (base / safe_ticker_component(raw)).resolve()
    assert resolved.parent == base
    assert base in resolved.parents


@pytest.mark.unit
def test_output_is_stable_under_repeated_application():
    for raw in ("nvda", "BRK.B", "  aapl  "):
        once = safe_ticker_component(raw)
        assert safe_ticker_component(once) == once
