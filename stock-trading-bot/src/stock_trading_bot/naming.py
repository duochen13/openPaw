"""Ticker sanitization.

Tickers reach filesystem paths (data/raw/{ticker}_*.json) and cache keys, so an
unsanitized symbol is a path-traversal vector. Every ticker crossing an I/O
boundary passes through here first.
"""
from __future__ import annotations

import re

_ALLOWED = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")


def safe_ticker_component(raw: str) -> str:
    """Normalize a ticker to uppercase and reject anything path-unsafe.

    Raises ValueError rather than sanitizing silently: a ticker we cannot
    recognize is a bug upstream, not something to paper over.
    """
    if not isinstance(raw, str):
        raise ValueError(f"ticker must be a string, got {type(raw).__name__}")
    candidate = raw.strip().upper()
    if ".." in candidate:
        raise ValueError(f"unsafe ticker component: {raw!r}")
    if not _ALLOWED.match(candidate):
        raise ValueError(f"unsafe ticker component: {raw!r}")
    return candidate
