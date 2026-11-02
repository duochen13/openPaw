"""Bundled CJK font for print PDFs (issue #185) -- stdlib only.

The print writer in :mod:`review.export` used to typeset Chinese as
pinyin because the PDF built-in fonts (Helvetica) are Latin-1 only.
This module bundles a real CJK font and parses just enough of it with
the standard library to embed it in a PDF:

* **Font**: Noto Sans SC, version 2.004-H2 (Google Fonts / Adobe),
  SIL Open Font License 1.1 -- license text in
  ``assets/fonts/OFL.txt``, regeneration script (fontTools, build-time
  only) in ``tools/build_cjk_fonts.py``.
* **Files**: ``assets/fonts/NotoSansSC-Regular.ttf`` (wght 400) and
  ``assets/fonts/NotoSansSC-Bold.ttf`` (wght 700), subset to printable
  ASCII + Latin-1, general/CJK punctuation, common math symbols, and
  the full GB2312-80 Han repertoire (6,763 characters). ~2.1 MB each,
  down from the ~17 MB upstream variable font.
* **PDF embedding**: each weight becomes a Type0 font with a
  CIDFontType2 descendant, ``/Identity-H`` encoding, the subset TTF
  embedded as a FlateDecode ``/FontFile2`` stream, glyph widths in
  ``/W``, and a ``/ToUnicode`` CMap so text extraction (and therefore
  the tests) sees the real Chinese characters, not glyph IDs.

Characters outside the subset have no glyph: :func:`render_text` maps
the few known cases (superscript digits the upstream font itself
lacks) and any other uncovered character degrades to ``"?"`` -- the
same visible failure the old writer had, now limited to text outside
the documented GB2312-based repertoire instead of all Chinese.
Callers can check coverage up front with :func:`missing_glyphs`.
"""

from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass, field

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "assets", "fonts")

#: Bundled weights: PDF font-resource suffix -> (file, BaseFont name).
FONT_FILES = {
    "Regular": ("NotoSansSC-Regular.ttf", "NotoSansSC-Regular"),
    "Bold": ("NotoSansSC-Bold.ttf", "NotoSansSC-Bold"),
}

#: Display name / version / license, recorded in the README (issue #185
#: requires the font name, version, and license to be documented).
FONT_NAME = "Noto Sans SC"
FONT_VERSION = "2.004-H2"
FONT_LICENSE = "SIL Open Font License 1.1 (OFL.txt in assets/fonts/)"


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _i16(data: bytes, off: int) -> int:
    return struct.unpack_from(">h", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


@dataclass
class TrueTypeFont:
    """The handful of TrueType tables PDF embedding needs."""

    data: bytes
    units_per_em: int
    ascent: int
    descent: int
    bbox: tuple[int, int, int, int]
    cmap: dict[int, int] = field(default_factory=dict)   # codepoint -> GID
    widths: list[int] = field(default_factory=list)      # GID -> advance

    # -- table access -------------------------------------------------
    def _table(self, tag: str) -> tuple[int, int]:
        num = _u16(self.data, 4)
        for i in range(num):
            off = 12 + i * 16
            if self.data[off:off + 4] == tag.encode("ascii"):
                return _u32(self.data, off + 8), _u32(self.data, off + 12)
        raise ValueError(f"TrueType table {tag!r} not found")

    @classmethod
    def parse(cls, data: bytes) -> "TrueTypeFont":
        font = cls(data=data, units_per_em=1000, ascent=0, descent=0,
                   bbox=(0, 0, 0, 0))
        head, _ = font._table("head")
        font.units_per_em = _u16(data, head + 18)
        font.bbox = tuple(_i16(data, head + 36 + 2 * i) for i in range(4))
        hhea, _ = font._table("hhea")
        font.ascent = _i16(data, hhea + 4)
        font.descent = _i16(data, hhea + 6)
        num_h = _u16(data, hhea + 34)
        maxp, _ = font._table("maxp")
        num_glyphs = _u16(data, maxp + 4)
        hmtx, _ = font._table("hmtx")
        font.widths = [
            _u16(data, hmtx + min(g, num_h - 1) * 4)
            for g in range(num_glyphs)
        ]
        font.cmap = font._parse_cmap()
        return font

    def _parse_cmap(self) -> dict[int, int]:
        off, _ = self._table("cmap")
        subs = []
        for i in range(_u16(self.data, off + 2)):
            base = off + 4 + i * 8
            sub_off = off + _u32(self.data, base + 4)
            subs.append((_u16(self.data, base), _u16(self.data, sub_off),
                         sub_off))
        for _plat, fmt, sub_off in subs:      # prefer format 12 (full UCS)
            if fmt == 12:
                return self._cmap_fmt12(sub_off)
        for _plat, fmt, sub_off in subs:
            if fmt == 4:
                return self._cmap_fmt4(sub_off)
        raise ValueError("no format-12/4 cmap subtable")

    def _cmap_fmt12(self, off: int) -> dict[int, int]:
        cmap: dict[int, int] = {}
        for i in range(_u32(self.data, off + 12)):
            start, end, gid = struct.unpack_from(
                ">III", self.data, off + 16 + i * 12)
            for cp in range(start, end + 1):
                cmap[cp] = gid + (cp - start)
        return cmap

    def _cmap_fmt4(self, off: int) -> dict[int, int]:
        cmap: dict[int, int] = {}
        seg = _u16(self.data, off + 6) // 2
        end_at = off + 14
        start_at = end_at + 2 * seg + 2
        delta_at = start_at + 2 * seg
        range_at = delta_at + 2 * seg
        for i in range(seg):
            end = _u16(self.data, end_at + 2 * i)
            start = _u16(self.data, start_at + 2 * i)
            delta = _i16(self.data, delta_at + 2 * i)
            ro = _u16(self.data, range_at + 2 * i)
            for cp in range(start, min(end, 0xFFFE) + 1):
                if ro == 0:
                    gid = (cp + delta) % 65536
                else:
                    at = range_at + 2 * i + ro + 2 * (cp - start)
                    gid = _u16(self.data, at)
                    if gid:
                        gid = (gid + delta) % 65536
                if gid:
                    cmap[cp] = gid
        return cmap

    # -- queries --------------------------------------------------------
    def glyph_id(self, ch: str) -> int:
        """Glyph ID for a character; 0 (.notdef) when uncovered."""
        return self.cmap.get(ord(ch), 0)

    def width(self, text: str, size: float) -> float:
        """Advance width of ``text`` at ``size`` points."""
        total = 0
        for ch in text:
            total += self.widths[self.glyph_id(ch)]
        return total * size / self.units_per_em


_CACHE: dict[str, TrueTypeFont] = {}
_STREAM_CACHE: dict[str, bytes] = {}


def _compressed(weight: str) -> bytes:
    """FlateDecode stream bytes for a weight (compressed once, cached).

    A class batch re-embeds the same fonts in ~80 PDFs; re-compressing
    ~2 MB per document would dominate the export time.
    """
    if weight not in _STREAM_CACHE:
        _STREAM_CACHE[weight] = zlib.compress(load_font(weight).data, 9)
    return _STREAM_CACHE[weight]


def load_font(weight: str = "Regular") -> TrueTypeFont:
    """Load (and cache) one bundled weight."""
    if weight not in _CACHE:
        filename, _name = FONT_FILES[weight]
        with open(os.path.join(_ASSETS, filename), "rb") as f:
            _CACHE[weight] = TrueTypeFont.parse(f.read())
    return _CACHE[weight]


def bundled_fonts() -> dict[str, TrueTypeFont]:
    return {weight: load_font(weight) for weight in FONT_FILES}


# ---------------------------------------------------------------------------
# Render-text normalization: characters the bundled subset cannot draw
# ---------------------------------------------------------------------------

#: Superscript digits: the upstream Noto Sans SC font itself has glyphs
#: only for ¹²³⁴, so *all* superscript digits use the explicit ``^n``
#: form (the convention the old pinyin writer already used for ²/³) --
#: consistent typesetting instead of a mix of real and missing glyphs.
_SUPERSCRIPTS = {
    "⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4",
    "⁵": "^5", "⁶": "^6", "⁷": "^7", "⁸": "^8", "⁹": "^9",
}


def render_text(text: str) -> str:
    """Map ``text`` to exactly what the bundled font can draw.

    Every character of the result has a non-.notdef glyph in the bundled
    subset: covered characters pass through verbatim (Chinese included),
    superscript digits become ``^n``, anything else uncovered becomes
    ``"?"``.
    """
    font = load_font("Regular")
    out: list[str] = []
    for ch in text:
        if ch.isspace():
            out.append(" ")          # newlines/tabs lay out as spaces
        elif ch in _SUPERSCRIPTS:
            out.append(_SUPERSCRIPTS[ch])
        elif font.glyph_id(ch):
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


def missing_glyphs(text: str) -> list[str]:
    """Sorted characters of ``text`` the bundled font cannot draw.

    Superscript digits are *not* reported: :func:`render_text` draws
    them as ``^n``, so they are a normalization, not a missing glyph.
    """
    font = load_font("Regular")
    return sorted({ch for ch in text
                   if not ch.isspace() and ch not in _SUPERSCRIPTS
                   and not font.glyph_id(ch)})


# ---------------------------------------------------------------------------
# PDF objects for one embedded weight
# ---------------------------------------------------------------------------

def _widths_array(font: TrueTypeFont) -> bytes:
    """``/W`` array: ``[0 [w0 w1 ...]]`` over all glyph IDs (CIDs)."""
    widths = " ".join(str(w) for w in font.widths)
    return f"[0 [{widths}]]".encode("ascii")


def _to_unicode_cmap(font: TrueTypeFont) -> bytes:
    """ToUnicode CMap: glyph ID (CID) -> Unicode, for text extraction."""
    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) "
        "/Supplement 0 >> def",
        "/CMapName /Adobe-Identity-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    pairs = sorted((gid, cp) for cp, gid in font.cmap.items() if gid)
    for i in range(0, len(pairs), 100):          # <=100 entries per block
        chunk = pairs[i:i + 100]
        lines.append(f"{len(chunk)} beginbfchar")
        for gid, cp in chunk:
            lines.append(f"<{gid:04X}> <{cp:04X}>")
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop",
              "end", "end"]
    return "\n".join(lines).encode("ascii")


_TO_UNICODE_CACHE: dict[str, bytes] = {}


def _to_unicode(weight: str) -> bytes:
    if weight not in _TO_UNICODE_CACHE:
        _TO_UNICODE_CACHE[weight] = _to_unicode_cmap(load_font(weight))
    return _TO_UNICODE_CACHE[weight]


def font_objects(add, weight: str) -> int:
    """Append one embedded Type0 font via ``add(body) -> object number``.

    ``add`` is :meth:`review.export._PdfWriter.add`. Returns the object
    number of the Type0 font dictionary.
    """
    font = load_font(weight)
    _filename, base_name = FONT_FILES[weight]

    stream = _compressed(weight)
    font_file = add(
        f"<< /Length {len(stream)} /Length1 {len(font.data)} "
        f"/Filter /FlateDecode >>\nstream\n".encode("ascii")
        + stream + b"\nendstream"
    )
    x_min, y_min, x_max, y_max = font.bbox
    descriptor = add(
        f"<< /Type /FontDescriptor /FontName /{base_name} /Flags 4 "
        f"/FontBBox [{x_min} {y_min} {x_max} {y_max}] "
        f"/Ascent {font.ascent} /Descent {font.descent} "
        f"/CapHeight {font.ascent} /StemV 80 "
        f"/FontFile2 {font_file} 0 R >>".encode("ascii")
    )
    descendant = add(
        f"<< /Type /Font /Subtype /CIDFontType2 "
        f"/BaseFont /{base_name} "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) "
        f"/Supplement 0 >> /FontDescriptor {descriptor} 0 R "
        f"/DW 1000 /W ".encode("ascii")
        + _widths_array(font) + b" >>"
    )
    to_unicode = _to_unicode(weight)
    cmap_obj = add(
        f"<< /Length {len(to_unicode)} >>\nstream\n".encode("ascii")
        + to_unicode + b"\nendstream"
    )
    return add(
        f"<< /Type /Font /Subtype /Type0 /BaseFont /{base_name} "
        f"/Encoding /Identity-H /DescendantFonts [{descendant} 0 R] "
        f"/ToUnicode {cmap_obj} 0 R >>".encode("ascii")
    )
