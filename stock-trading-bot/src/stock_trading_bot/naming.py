"""Ticker sanitization.

Tickers reach filesystem paths (data/raw/{ticker}_*.json) and cache keys, so an
unsanitized symbol is both a path-traversal vector and an aliasing hazard.
Every ticker crossing an I/O boundary passes through here first.

Order matters: validate the raw input, THEN uppercase. Doing it the other way
lets `str.upper()` launder non-ASCII into ASCII - U+017F LATIN SMALL LETTER
LONG S uppercases to 'S', so 'snow' and its long-s spelling collapse to the same
cache key and one company's data could be served for another's. Validating
first means `upper()` only ever runs on ASCII, where it is pure and
length-preserving.
"""
from __future__ import annotations

import re

# One to twelve chars. Must start and end alphanumeric: a trailing dot is
# stripped by the Win32 API, which would make 'NVDA.' and 'NVDA' the same file.
# fullmatch (not match with $) because $ also matches before a trailing newline.
_ALLOWED = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,10}[A-Za-z0-9])?")


def safe_ticker_component(raw: str) -> str:
    """Normalize a ticker to uppercase and reject anything path-unsafe.

    Raises rather than sanitizing silently: a ticker we cannot recognize is a
    bug upstream, not something to paper over.
    """
    if not isinstance(raw, str):
        raise TypeError(f"ticker must be a string, got {type(raw).__name__}")
    candidate = raw.strip()
    # The regex alone accepts 'A..B', so this check is load-bearing.
    if ".." in candidate or not _ALLOWED.fullmatch(candidate):
        raise ValueError(f"unsafe ticker component: {raw!r}")
    return candidate.upper()
