#!/usr/bin/env python3
"""Build the Phase 1 synthetic graded papers (issue #108).

Reads ``assignment/questions.json`` + ``tools/paper_data.py`` and emits,
per synthetic student (S-001 .. S-005):

* ``papers/<S>/page-1.png`` / ``page-2.png`` — rendered 'photos' of the
  printed-and-marked sheets (printed questions, handwritten-style
  answers, red-pen grading marks; defects per paper_data: cross-outs,
  corrections, and for S-005 a low-quality-photo degradation pass);
* ``papers/<S>/paper.pdf`` — the same two pages as one PDF;
* ``papers/<S>/answer-records.json`` — ingestion ``AnswerRecord`` dicts
  (the ground truth of what is on the paper + the grading marks);
* ``papers/<S>/evidence-records.json`` — evidence-ledger
  ``EvidenceRecord`` dicts for the skill-mapped items (taxonomy input);
* ``papers/manifest.json`` — the five uploads, score totals, defects.

Deterministic (seeded). Re-running regenerates identical JSON; PNG
bytes may vary slightly across Pillow versions.

Usage:  python3 tools/build_papers.py [--kit-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_data import ITEM_POINTS, ITEM_SKILLS, PAPERS, earned_points  # noqa: E402

KIT_DIR = Path(__file__).resolve().parent.parent
OBSERVED_AT = "2026-10-12T14:00:00+08:00"
ASSIGNMENT_NUMBER = "A-CH3-01"

SANS = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
SERIF = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"

PAGE_W, PAGE_H = 1240, 2100
MARGIN = 70
RED = (196, 30, 30)
PRINT_COLOR = (20, 20, 20)


def _sc_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load the Simplified-Chinese face from a Noto CJK .ttc."""
    for index in range(8):
        try:
            font = ImageFont.truetype(path, size, index=index)
        except Exception:
            break
        if "SC" in font.getname()[0]:
            return font
    return ImageFont.truetype(path, size)


# Noto CJK (Sans and Serif) has no superscript-digit glyphs (⁵, ⁷, ...)
# and silently draws .notdef boxes. DejaVu Sans has them; draw those
# characters with a same-size DejaVu fallback so 10⁵ / 10⁷ render.
_SUPERSCRIPTS = set("⁰¹²³⁴⁵⁶⁷⁸⁹")
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_fallback_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _fallback_font(size: int):
    if size not in _fallback_cache:
        _fallback_cache[size] = ImageFont.truetype(_DEJAVU, size)
    return _fallback_cache[size]


def text_len(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    total = 0.0
    for ch in text:
        f = _fallback_font(font.size) if ch in _SUPERSCRIPTS else font
        total += draw.textlength(ch, font=f)
    return total


def draw_text(draw: ImageDraw.ImageDraw, xy, text: str, font, fill) -> None:
    x, y = xy
    for ch in text:
        f = _fallback_font(font.size) if ch in _SUPERSCRIPTS else font
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f)


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Character-wise wrap (CJK-safe), honoring explicit newlines."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if text_len(draw, cur + ch, font) <= max_width:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def item_parts(question: dict) -> list[tuple[str, str]]:
    """(item_key, part_id) pairs for one question, in display order."""
    qid = question["id"]
    if question["parts"]:
        return [(f"{qid}#{p}", p) for p in question["parts"]]
    return [(qid, "")]


def render_page(student_id: str, page_index: int, questions: list[dict],
                entries: dict, style: dict, seed: int) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    print_font = _sc_font(SANS, 26)
    print_bold = _sc_font(SANS_BOLD, 26)
    hand_path = SERIF if style["font"] == "serif" else SANS
    hand_font = _sc_font(hand_path, style["size"])
    mark_font = _sc_font(SANS_BOLD, 36)
    comment_font = _sc_font(SANS, 22)
    hand_color = style["color"]
    width = PAGE_W - 2 * MARGIN
    y = 46

    header = (f"学生编号：{student_id}　　作业编号：{ASSIGNMENT_NUMBER}　　"
              f"第三章《能量的转化与守恒》（第 {page_index + 1} 页 / 共 2 页）")
    draw_text(draw, (MARGIN, y), header, _sc_font(SANS, 24), PRINT_COLOR)
    y += 44
    draw.line([(MARGIN, y), (PAGE_W - MARGIN, y)], fill=(120, 120, 120), width=2)
    y += 26

    for q in questions:
        qid = q["id"]
        num = int(qid[1:])
        stem_lines = wrap(draw, f"{num}. {q['stem']}", print_font, width)
        for line in stem_lines:
            draw_text(draw, (MARGIN, y), line, print_font, PRINT_COLOR)
            y += 37
        y += 10
        for item_key, part_id in item_parts(q):
            entry = entries[item_key]
            label = ""
            if q["parts"]:
                idx = q["parts"].index(part_id) + 1
                label = f"（{idx}）" if qid != "Q5" else f"空{idx}："
            xoff = rng.randint(-3, 3)
            # crossed-out first attempt
            if entry.get("crossed_out"):
                txt = label + entry["crossed_out"]
                draw_text(draw, (MARGIN + 30 + xoff, y), txt, hand_font, hand_color)
                tw = text_len(draw, txt, hand_font)
                for dy in (-4, 5):
                    draw.line([(MARGIN + 28 + xoff, y + style["size"] // 2 + dy),
                               (MARGIN + 32 + xoff + tw, y + style["size"] // 2 + dy - 3)],
                              fill=hand_color, width=3)
                y += style["size"] + 14
            # final answer (or a scribble when unreadable)
            if entry.get("answer") is None:
                for s in range(3):
                    pts = [(MARGIN + 30 + i * 14,
                            y + s * 16 + 8 * math.sin(i / 2.4)) for i in range(38)]
                    draw.line(pts, fill=(150, 150, 150), width=3)
                y += 58
            else:
                ans_lines = wrap(draw, label + entry["answer"], hand_font, width - 150)
                for line in ans_lines:
                    draw_text(draw, (MARGIN + 30 + xoff, y), line, hand_font,
                              hand_color)
                    y += style["size"] + 12
            # teacher's red-pen mark, right side of the answer block
            mark = entry.get("mark")
            mx = PAGE_W - MARGIN - 120
            my = y - style["size"] - 16
            if mark == "correct":
                draw.text((mx, my), "√", font=mark_font, fill=RED)
            elif mark == "wrong":
                draw.text((mx, my), "×", font=mark_font, fill=RED)
            elif mark == "score":
                draw.text((mx - 30, my), entry["score"], font=mark_font, fill=RED)
            if entry.get("comment"):
                for line in wrap(draw, entry["comment"], comment_font, width - 160):
                    draw_text(draw, (MARGIN + 30, y), line, comment_font, RED)
                    y += 30
                y += 4
            y += 8
        y += 22
    return img


def degrade(img: Image.Image) -> Image.Image:
    """Low-quality photo pass (S-005): rotate, downscale, blur, darken, noise."""
    img = img.rotate(-2.1, resample=Image.BICUBIC, expand=False,
                     fillcolor=(205, 200, 190))
    small = img.resize((img.width // 2, img.height // 2), Image.BILINEAR)
    img = small.resize(img.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))
    img = img.point(lambda v: int(v * 0.82))
    rng = random.Random(5)
    px = img.load()
    for _ in range(9000):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        v = rng.randrange(90, 150)
        px[x, y] = (v, v, v)
    return img


# ---------------------------------------------------------------------------
# JSON emission
# ---------------------------------------------------------------------------

GRADING_ZH = {"correct": "正确", "wrong": "错误",
              "score": "部分正确", "comment": "部分正确", None: "无法辨认"}

# Which rendered page each question sits on (mirrors questions.json `page`).
QUESTION_PAGE = {}


def question_of(item_key: str) -> str:
    return item_key.split("#")[0]


def part_of(item_key: str) -> str | None:
    return item_key.split("#")[1] if "#" in item_key else None


def answer_records(student_id: str, entries: dict) -> list[dict]:
    records = []
    for item_key in ITEM_POINTS:
        e = entries[item_key]
        mark = e.get("mark")
        grading = None
        if mark is not None:
            grading = {"kind": mark,
                       "score": e.get("score") if mark == "score" else None,
                       "comment": e.get("comment")}
        records.append({
            "student_id": student_id,
            "assignment_number": ASSIGNMENT_NUMBER,
            "question_id": question_of(item_key),
            "part_id": part_of(item_key),
            "item_key": item_key,
            "student_answer": e.get("answer"),
            "grading_mark": grading,
            "source": "ocr",
            "reliability": e["reliability"],
            "page_ref": f"papers/{student_id}/page-{QUESTION_PAGE[question_of(item_key)] + 1}.png",
        })
    return records


def evidence_records(student_id: str, entries: dict, questions: dict) -> list[dict]:
    records = []
    for item_key, skill_id in ITEM_SKILLS.items():
        e = entries[item_key]
        qid = question_of(item_key)
        rec = {
            "record_id": f"TEST-{student_id}-{item_key.replace('#', '-')}",
            "student_id": student_id,
            "skill_id": skill_id,
            "question_id": qid,
            "sub_question": part_of(item_key) or "",
            "knowledge_point": questions[qid]["knowledge_point"],
            "student_answer": e.get("answer") or "",
            "grading_result": GRADING_ZH[e.get("mark")],
            "image_location": f"papers/{student_id}/page-{QUESTION_PAGE[qid] + 1}.png",
            "ocr_reliability": e["reliability"],
            "hint_used": False,
            "correction_of": "",
            "teacher_note": e.get("comment") or "",
            "followup_verified": False,
            "followup_note": "",
            "independently_completed": True,
            "context": ASSIGNMENT_NUMBER,
            "observed_at": OBSERVED_AT,
            "created_at": OBSERVED_AT,
        }
        # S-004 Q8 keeps its crossed-out first attempt as a linked record:
        # the attempt carries the error, the final record is its correction.
        if student_id == "S-004" and item_key == "Q8":
            attempt = dict(rec)
            attempt["record_id"] = "TEST-S-004-Q8-try1"
            attempt["student_answer"] = entries[item_key]["crossed_out"]
            attempt["grading_result"] = "错误"
            attempt["teacher_note"] = "第一次作答：未先求重力，直接用质量乘高度"
            records.append(attempt)
            rec["correction_of"] = "TEST-S-004-Q8-try1"
        records.append(rec)
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit-dir", default=str(KIT_DIR))
    args = ap.parse_args()
    kit = Path(args.kit_dir)

    qdata = json.loads((kit / "assignment" / "questions.json").read_text(encoding="utf-8"))
    questions = {q["id"]: q for q in qdata["questions"]}
    QUESTION_PAGE.update({q["id"]: q["page"] for q in qdata["questions"]})

    manifest_papers = []
    for idx, (student_id, paper) in enumerate(sorted(PAPERS.items())):
        entries = paper["items"]
        assert set(entries) == set(ITEM_POINTS), student_id
        out_dir = kit / "papers" / student_id
        out_dir.mkdir(parents=True, exist_ok=True)

        pages = []
        for page_index in (0, 1):
            qs = [questions[qid] for qid in
                  sorted(questions, key=lambda s: int(s[1:]))
                  if questions[qid]["page"] == page_index]
            img = render_page(student_id, page_index, qs, entries,
                              paper["style"], seed=100 + idx * 7 + page_index)
            if student_id == "S-005":
                img = degrade(img)
            img.save(out_dir / f"page-{page_index + 1}.png")
            pages.append(img)
        pages[0].save(out_dir / "paper.pdf", save_all=True, append_images=pages[1:])

        (out_dir / "answer-records.json").write_text(
            json.dumps(answer_records(student_id, entries),
                       ensure_ascii=False, indent=1), encoding="utf-8")
        (out_dir / "evidence-records.json").write_text(
            json.dumps(evidence_records(student_id, entries, questions),
                       ensure_ascii=False, indent=1), encoding="utf-8")

        points = {k: earned_points(k, entries[k]) for k in ITEM_POINTS}
        manifest_papers.append({
            "student_id": student_id,
            "upload_id": f"UP-{student_id}",
            "uploaded_by": "TEST (synthetic)",
            "media_type": "photo",
            "files": [
                {"path": f"papers/{student_id}/page-1.png", "media_type": "photo", "page_count": 1},
                {"path": f"papers/{student_id}/page-2.png", "media_type": "photo", "page_count": 1},
                {"path": f"papers/{student_id}/paper.pdf", "media_type": "pdf_scan", "page_count": 2},
            ],
            "total_score": sum(points.values()),
            "total_points": sum(ITEM_POINTS.values()),
            "points_earned": points,
            "defects": paper["style"]["defects"],
        })
        print(f"{student_id}: total {sum(points.values())}/100")

    manifest = {
        "synthetic": True,
        "kit": "homework-pilot Phase 1 pilot starter kit (issue #108)",
        "assignment_number": ASSIGNMENT_NUMBER,
        "note": "All five papers are invented test data (student IDs only). "
                "Phase 2 replaces them with real anonymized papers in the same shapes.",
        "papers": manifest_papers,
    }
    (kit / "papers" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("manifest written")


if __name__ == "__main__":
    main()
