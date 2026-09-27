"""Student-ID + assignment-number labels for round-trip matching (#110).

The generated PDFs must carry the student ID and assignment number so
the next upload can be matched back to the student. Stdlib-only, so we
do not do full typeset PDF rendering (that comes with #115's export
work). Instead this module provides:

1. ``id_manifest(assignments)`` — a JSON-serializable manifest mapping
   each generated file/page to its (student_id, assignment_number).
   This is the machine-readable round-trip record.
2. ``write_id_label_pdf(path, student_id, assignment_number, ...)`` —
   a minimal but VALID single-page PDF (hand-written PDF 1.4, Helvetica)
   rendering the ID block as printable text. It is a real, openable PDF;
   it is NOT a full assignment typeset — print it as a cover sheet or
   glue its text block onto the #115 export later.

Both are honest about their limits; see README.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Dict, List


def id_manifest(entries: List[Dict[str, str]]) -> Dict:
    """Build the round-trip manifest.

    entries: [{"file": "S001_A-CH3-01.pdf", "student_id": "S001",
               "assignment_number": "A-CH3-01", "pages": 2}, ...]
    """
    return {
        "version": 1,
        "entries": entries,
    }


def write_manifest(path: str, entries: List[Dict[str, str]]) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(id_manifest(entries), f, ensure_ascii=False, indent=2)
    return path


def _escape_pdf_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_id_label_pdf(path: str, student_id: str, assignment_number: str,
                       title: str = "", note: str = "") -> str:
    """Write a minimal valid PDF with the ID block as printable text.

    Layout: title line, then "Student ID: <id>" and "Assignment: <number>"
    in large type, plus an optional note line. ASCII-safe: non-ASCII
    characters in title/note are transliterated to keep the PDF valid
    with the built-in Helvetica font.
    """
    def ascii_safe(s: str) -> str:
        return s.encode("ascii", "replace").decode("ascii")

    lines = [
        ("Homework ID label", 20, 48),
        ("Student ID: %s" % ascii_safe(student_id), 28, 28),
        ("Assignment: %s" % ascii_safe(assignment_number), 24, 28),
    ]
    if title:
        lines.append(("Title: %s" % ascii_safe(title), 20, 14))
    if note:
        lines.append(("Note: %s" % ascii_safe(note), 20, 12))

    y = 700
    content_ops = []
    for text, size, gap in lines:
        content_ops.append(
            f"BT /F1 {size} Tf 72 {y} Td ({_escape_pdf_text(text)}) Tj ET")
        y -= size + gap
    content = "\n".join(content_ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
         b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode("latin-1")
    pdf += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode("latin-1")

    with open(path, "wb") as f:
        f.write(bytes(pdf))
    return path


def label_for_assignment(student_id: str, assignment_number: str,
                         title: str, out_dir: str) -> Dict[str, str]:
    """Convenience: manifest entry + label PDF paths for one student's file."""
    import os
    base = f"{student_id}_{assignment_number}"
    pdf_path = os.path.join(out_dir, f"{base}_id-label.pdf")
    write_id_label_pdf(pdf_path, student_id, assignment_number, title=title,
                       note="Keep this page on top when uploading scans.")
    return {"file": f"{base}.pdf", "label_pdf": pdf_path,
            "student_id": student_id, "assignment_number": assignment_number}
