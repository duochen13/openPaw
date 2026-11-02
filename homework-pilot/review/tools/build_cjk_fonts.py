"""Regenerate the bundled CJK font subsets in ``review/assets/fonts/``.

This is a *build-time* tool only: it needs ``fontTools`` and the upstream
font file. The PDF export itself (``review/export.py`` and
``review/cjk_font.py``) is stdlib-only and never imports this module.

Bundled font (issue #185):

* **Noto Sans SC**, version **2.004-H2** (Google Fonts / Adobe),
  SIL Open Font License 1.1 -- see ``review/assets/fonts/OFL.txt``.
* Upstream file: ``NotoSansSC[wght].ttf`` (variable font, wght 100-900),
  google/fonts revision ``2894aab31764f10f29c421bdfd2340d3b382d384``,
  path ``ofl/notosanssc/NotoSansSC[wght].ttf``,
  SHA-256 ``a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da``.
* The subsets below instantiate wght=400 (Regular) and wght=700 (Bold)
  and keep: printable ASCII + Latin-1, general/CJK punctuation and common
  math symbols, and every Han character in the **GB2312-80** repertoire
  (6,763 characters -- the standard Simplified Chinese character set,
  which covers all Chapter 3 vocabulary). Hinting and layout tables are
  dropped; the result is ~2.1 MB per weight instead of ~17 MB upstream.

Usage:

    pip install fonttools
    python3 review/tools/build_cjk_fonts.py /path/to/NotoSansSC[wght].ttf

With no argument the upstream file is looked for at
``/tmp/NotoSansSC[wght].ttf``.
"""

from __future__ import annotations

import hashlib
import os
import sys

EXPECTED_SHA256 = (
    "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da"
)

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(_HERE, "..", "assets", "fonts")


def subset_charset() -> set[str]:
    """The documented subset repertoire (see module docstring)."""
    chars = {chr(c) for c in range(0x20, 0x7F)}            # printable ASCII
    for lo, hi in (
        (0xA0, 0x100),      # Latin-1 supplement
        (0x2000, 0x2070),   # general punctuation
        (0x2070, 0x209D),   # superscript / subscript digits and letters
        (0x2100, 0x2140),   # letterlike symbols (℃ etc.)
        (0x2190, 0x2200),   # arrows
        (0x2200, 0x2265),   # math operators, incl. × ÷ ≈ <
        (0x226A, 0x226B),   # ≤ ≥
        (0x3000, 0x3040),   # CJK punctuation
        (0xFF00, 0xFF66),   # fullwidth forms
        (0xFFE0, 0xFFE7),   # fullwidth signs
    ):
        chars.update(chr(c) for c in range(lo, hi))
    # GB2312-80 Han repertoire, enumerated through the codec: lead bytes
    # 0xA1-0xF7 / trail bytes 0xA1-0xFE define the standard set.
    for lead in range(0xA1, 0xF8):
        for trail in range(0xA1, 0xFF):
            try:
                text = bytes([lead, trail]).decode("gb2312")
            except UnicodeDecodeError:
                continue
            chars.update(c for c in text if "一" <= c <= "鿿")
    return chars


def build(source: str) -> list[str]:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    with open(source, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(
            f"upstream font SHA-256 mismatch: {digest} "
            f"(expected {EXPECTED_SHA256}); refusing to subset an "
            "unverified font file"
        )
    text = "".join(sorted(subset_charset()))
    written = []
    os.makedirs(OUT_DIR, exist_ok=True)
    for wght, name in ((400, "Regular"), (700, "Bold")):
        font = TTFont(source)
        instantiateVariableFont(font, {"wght": wght}, inplace=True,
                                updateFontNames=True)
        options = subset.Options()
        options.hinting = False
        options.layout_features = []
        options.notdef_outline = True
        options.recalc_bounds = True
        options.drop_tables += [
            "GSUB", "GPOS", "GDEF", "BASE", "vhea", "vmtx", "VORG",
        ]
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(text=text)
        subsetter.subset(font)
        out = os.path.normpath(
            os.path.join(OUT_DIR, f"NotoSansSC-{name}.ttf"))
        font.save(out)
        written.append(out)
        print(f"wrote {out} ({os.path.getsize(out)} bytes, "
              f"{len(font.getGlyphOrder())} glyphs)")
    return written


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/NotoSansSC[wght].ttf"
    build(src)
