"""Synthetic graded-paper data for the Phase 1 pilot starter kit (#108).

Single source of truth for the five test papers: ``build_papers.py``
renders the page images AND emits the per-paper ``answer-records.json``
(ingestion ``AnswerRecord`` dicts) and ``evidence-records.json``
(evidence-ledger ``EvidenceRecord`` dicts) from this data, so the
'papers' and the machine-readable records can never drift apart.

EVERYTHING HERE IS INVENTED. Students are IDs only (S-001 .. S-005);
no names, no real handwriting, no real scores. The marks follow the
rubric in ``assignment/questions.json``: correct -> full points,
wrong -> 0, score marks carry their own ``x/y``, comment marks carry an
explicit ``earned``.

Item keys follow the ingestion ``item_key`` convention
(``question_id`` or ``question_id#part_id``).
"""

from __future__ import annotations

# Full points per item_key (mirrors assignment/questions.json).
ITEM_POINTS = {
    "Q1": 3, "Q2": 3, "Q3#a": 4, "Q3#b": 4, "Q4": 10,
    "Q5#blank1": 3, "Q5#blank2": 3, "Q6": 8, "Q7": 4, "Q8": 8,
    "Q9": 6, "Q10": 12, "Q11#a": 6, "Q11#b": 6, "Q11#c": 6,
    "Q12#blank1": 4, "Q12#blank2": 5, "Q12#blank3": 5,
}

# Skill per item_key (taxonomy/skills_ch3_v1.json question_samples).
# Items absent here are not in the v1 taxonomy samples and produce no
# evidence record (answer records still cover them).
ITEM_SKILLS = {
    "Q1": "ch3-judge-work",
    "Q2": "ch3-judge-work",
    "Q3#a": "ch3-friction-work",
    "Q3#b": "ch3-friction-work",
    "Q4": "ch3-estimate-average-power",
    "Q6": "ch3-estimate-average-power",
    "Q7": "ch3-work-vs-power",
    "Q8": "ch3-gravitational-work",
    "Q11#a": "ch3-work-phases",
    "Q11#b": "ch3-apex-kinetic-energy",
    "Q11#c": "ch3-repeated-jump-power",
    "Q12#blank1": "ch3-gravitational-work",
    "Q12#blank2": "ch3-elastic-potential-energy",
    "Q12#blank3": "ch3-force-velocity-changes",
}

# Entry fields:
#   answer      student answer text as read from the paper (None = unreadable)
#   mark        "correct" | "wrong" | "score" | "comment" | None (unreadable)
#   score       "x/y" for mark == "score"
#   comment     teacher's red-pen note (also the evidence teacher_note)
#   earned      points earned (required for "comment"; derived otherwise)
#   reliability OCR reliability of the read, 0..1
#   crossed_out text the student crossed out before writing `answer`
PAPERS = {
    "S-001": {
        "style": {"font": "serif", "size": 33, "color": (25, 25, 120),
                  "defects": ["neat handwriting",
                              "one self-correction with cross-out (Q10)"]},
        "items": {
            "Q1": dict(answer="C", mark="correct", reliability=0.99),
            "Q2": dict(answer="B", mark="correct", reliability=0.99),
            "Q3#a": dict(answer="0.8 m，木板重心在中点，重心越过桌边木板就会下落",
                         mark="correct", reliability=0.97),
            "Q3#b": dict(answer="W = fs = 20 × 0.8 = 16 J",
                         mark="correct", reliability=0.98),
            "Q4": dict(answer="W = mgh = 50×10×12 = 6000 J；P = W/t = 6000÷30 = 200 W",
                       mark="correct", reliability=0.96),
            "Q5#blank1": dict(answer="重力势", mark="correct", reliability=0.98),
            "Q5#blank2": dict(answer="动", mark="correct", reliability=0.98),
            "Q6": dict(answer="W1 = mgh = 60×10×0.5 = 300 J；W = 300×12 = 3600 J；P = 3600÷60 = 60 W",
                       mark="correct", reliability=0.97),
            "Q7": dict(answer="B", mark="correct", reliability=0.99),
            "Q8": dict(answer="G = 5×10 = 50 N；W = Gh = 50×8 = 400 J",
                       mark="correct", reliability=0.98),
            "Q9": dict(answer="重力势能转化为动能；机械能守恒，因为只有重力做功",
                       mark="correct", reliability=0.95),
            "Q10": dict(answer="F = f = 2000 N；s = 20×300 = 6000 m；W = 1.2×10⁷ J；P = 4×10⁴ W",
                        mark="score", score="9/12",
                        comment="过程完整；(1) 中先把 5 min 写成 5 s，已自行划改订正，卷面扣分",
                        crossed_out="s = 20×5 = 100 m", reliability=0.93),
            "Q11#a": dict(answer="不做功。蹬地时脚没有离开地面，沿支持力方向没有位移",
                          mark="correct", reliability=0.96),
            "Q11#b": dict(answer="0 J，最高点速度为零", mark="correct", reliability=0.97),
            "Q11#c": dict(answer="W1 = 300 J；W = 6000 J；P = 100 W",
                          mark="correct", reliability=0.96),
            "Q12#blank1": dict(answer="重力势", mark="correct", reliability=0.98),
            "Q12#blank2": dict(answer="弹性势", mark="correct", reliability=0.98),
            "Q12#blank3": dict(answer="增大；上升初期弹力大于重力，速度增大；弹力小于重力后速度减小",
                               mark="correct", reliability=0.94),
        },
    },
    "S-002": {
        "style": {"font": "sans", "size": 32, "color": (30, 30, 30),
                  "defects": ["average handwriting", "one overwritten digit (Q4)"]},
        "items": {
            "Q1": dict(answer="C", mark="correct", reliability=0.98),
            "Q2": dict(answer="B", mark="correct", reliability=0.98),
            "Q3#a": dict(answer="0.8 m，重心移到桌边以外就会掉下去",
                         mark="correct", reliability=0.95),
            "Q3#b": dict(answer="W = fs = 20 × 1.6 = 32 J", mark="score", score="2/4",
                         comment="公式对，但位移没有用（1）的 0.8 m", reliability=0.96),
            "Q4": dict(answer="楼高约 9 m；W = 50×10×9 = 4500 J；P = 4500÷30 = 150 W",
                       mark="score", score="6/10",
                       comment="方法正确；楼高估算依据不足", reliability=0.94),
            "Q5#blank1": dict(answer="重力势", mark="correct", reliability=0.97),
            "Q5#blank2": dict(answer="动", mark="correct", reliability=0.97),
            "Q6": dict(answer="W1 = 60×10×0.4 = 240 J；W = 2880 J；P = 48 W",
                       mark="score", score="6/8",
                       comment="上升高度取 0.4 m，未说明估算依据", reliability=0.95),
            "Q7": dict(answer="B", mark="correct", reliability=0.98),
            "Q8": dict(answer="W = Gh = 50×8 = 400 J", mark="correct", reliability=0.97),
            "Q9": dict(answer="重力势能转化为动能", mark="comment", earned=3,
                       comment="未回答机械能是否守恒", reliability=0.93),
            "Q10": dict(answer="F = 2000 N；s = 6000 m；W = 1.2×10⁷ J；P = 4×10⁴ W",
                        mark="correct", reliability=0.96),
            "Q11#a": dict(answer="不做功，蹬地时脚在原地没有移动",
                          mark="correct", reliability=0.95),
            "Q11#b": dict(answer="0 J，最高点速度为零", mark="correct", reliability=0.96),
            "Q11#c": dict(answer="W1 = 300 J；W = 6000 J；P = 6000÷20 = 300 W",
                          mark="score", score="4/6",
                          comment="总时间应为 60 s，不是 20 次的 20", reliability=0.95),
            "Q12#blank1": dict(answer="重力势", mark="correct", reliability=0.97),
            "Q12#blank2": dict(answer="弹性势", mark="correct", reliability=0.97),
            "Q12#blank3": dict(answer="减小，因为弹力越来越小", mark="wrong",
                               comment="上升初期弹力大于重力，速度先增大", reliability=0.94),
        },
    },
    "S-003": {
        "style": {"font": "sans", "size": 31, "color": (20, 20, 100),
                  "defects": ["fast, slanted handwriting",
                              "several answers without units"]},
        "items": {
            "Q1": dict(answer="C", mark="correct", reliability=0.97),
            "Q2": dict(answer="A", mark="wrong",
                       comment="重力方向竖直向下，沿水平方向没有位移，重力不做功",
                       reliability=0.98),
            "Q3#a": dict(answer="0.8 m", mark="correct", reliability=0.94),
            "Q3#b": dict(answer="W = 20×0.8 = 16 J", mark="correct", reliability=0.95),
            "Q4": dict(answer="W = 6000 J；P = W×t = 6000×30 = 180000 W", mark="wrong",
                       comment="功率公式用反了：P = W÷t", reliability=0.96),
            "Q5#blank1": dict(answer="重力势", mark="correct", reliability=0.96),
            "Q5#blank2": dict(answer="势", mark="wrong",
                              comment="应为动能", reliability=0.95),
            "Q6": dict(answer="W = 60×10×0.5 = 300 J", mark="score", score="3/8",
                       comment="只算了 1 次的功，且把功当作功率", reliability=0.94),
            "Q7": dict(answer="A", mark="wrong",
                       comment="做功多不等于功率大，还要看时间", reliability=0.97),
            "Q8": dict(answer="W = Gh = 50×8 = 400 J", mark="correct", reliability=0.96),
            "Q9": dict(answer="重力势能变成动能，机械能不变", mark="score", score="4/6",
                       comment="未说明机械能守恒的理由", reliability=0.9),
            "Q10": dict(answer="F = 2000 N；s = 6000 m；W = 1.2×10⁷ J；P = 2000 W",
                        mark="score", score="8/12",
                        comment="（2）功率计算错误：P = W÷t = 4×10⁴ W", reliability=0.93),
            "Q11#a": dict(answer="不做功，因为脚没有离开地面", mark="score", score="3/6",
                          comment="判断对；理由要说清“沿支持力的方向没有位移”",
                          reliability=0.92),
            "Q11#b": dict(answer="0 J", mark="correct", reliability=0.95),
            "Q11#c": dict(answer="W1 = 300 J；W = 6000 J；P = 100 W",
                          mark="correct", reliability=0.94),
            "Q12#blank1": dict(answer="重力势", mark="correct", reliability=0.96),
            "Q12#blank2": dict(answer="动", mark="score", score="2/5",
                              comment="应为弹性势能", reliability=0.93),
            "Q12#blank3": dict(answer="增大，弹力先大于重力，后小于重力",
                               mark="correct", reliability=0.92),
        },
    },
    "S-004": {
        "style": {"font": "serif", "size": 30, "color": (40, 40, 40),
                  "defects": ["heavy cross-outs and rewrites (Q3, Q8)",
                              "one answer corrected after cross-out (Q8; the evidence records keep the crossed-out attempt linked via correction_of)",
                              "cramped writing, answers run into the margins"]},
        "items": {
            "Q1": dict(answer="C", mark="correct", reliability=0.93),
            "Q2": dict(answer="B", mark="correct", reliability=0.94),
            "Q3#a": dict(answer="1.6 m，木板要全部推过桌边", mark="wrong",
                         comment="重心越过桌边即可开始下落，只需推 0.8 m",
                         crossed_out="0.8 m", reliability=0.9),
            "Q3#b": dict(answer="W = 20 × 1.6 = 32 J", mark="wrong",
                         comment="位移应取 0.8 m，W = 16 J", reliability=0.91),
            "Q4": dict(answer="W = 5×10×12 = 600 J；P = 600÷30 = 20 W",
                       mark="score", score="5/10",
                       comment="公式对，质量数值误写为 5 kg", reliability=0.9),
            "Q5#blank1": dict(answer="动", mark="wrong",
                              comment="第一空应为重力势能", reliability=0.92),
            "Q5#blank2": dict(answer="动", mark="correct", reliability=0.92),
            "Q6": dict(answer="W1 = 300 J；P = 300÷60 = 5 W", mark="score", score="4/8",
                       comment="只算了 1 次，未把 12 次累加", reliability=0.9),
            "Q7": dict(answer="A", mark="wrong",
                       comment="还要比较功率，乙的功率更大", reliability=0.93),
            "Q8": dict(answer="G = 50 N；W = Gh = 50×8 = 400 J", mark="correct",
                       comment="自行订正后正确",
                       crossed_out="W = 5 × 8 = 40 J", reliability=0.88),
            "Q9": dict(answer="重力势能转化为动能，机械能不守恒", mark="comment", earned=2,
                       comment="转化方向对；不计空气阻力时机械能守恒", reliability=0.89),
            "Q10": dict(answer="W = 2000×20 = 40000 J；P = 40000÷5 = 8000 W",
                        mark="score", score="3/12",
                        comment="未先算行驶距离，时间也没有换算成秒", reliability=0.9),
            "Q11#a": dict(answer="做功，因为他的重心上升了", mark="wrong",
                          comment="蹬地阶段脚沿支持力方向没有位移，支持力不做功",
                          reliability=0.91),
            "Q11#b": dict(answer="动能最小，但不是零", mark="wrong",
                          comment="最高点速度为零，动能为零", reliability=0.9),
            "Q11#c": dict(answer="W1 = 300 J；20 次共 6000 J；P = 6000÷20 = 300 W",
                          mark="score", score="4/6",
                          comment="总时间应为 60 s", reliability=0.9),
            "Q12#blank1": dict(answer="动", mark="wrong",
                               comment="下落时重力势能转化为动能", reliability=0.91),
            "Q12#blank2": dict(answer="弹性", mark="score", score="2/5",
                               comment="应为弹性势能，表述不完整", reliability=0.9),
            "Q12#blank3": dict(answer="减小，因为弹力一直小于重力", mark="wrong",
                               comment="上升初期弹力大于重力，速度先增大", reliability=0.89),
        },
    },
    "S-005": {
        "style": {"font": "sans", "size": 34, "color": (60, 60, 60),
                  "defects": ["LOW-QUALITY PHOTO: blurred, dark, rotated about 2 degrees, low contrast (the kit's low-quality OCR stress case)",
                              "messy handwriting",
                              "two items unreadable (Q9, Q12 blank3)"]},
        "items": {
            "Q1": dict(answer="C", mark="correct", reliability=0.88),
            "Q2": dict(answer="B", mark="correct", reliability=0.9),
            "Q3#a": dict(answer="0.8 m", mark="correct", reliability=0.72),
            "Q3#b": dict(answer="W = 20 × 0.8 = 16", mark="score", score="3/4",
                         comment="结果对，漏写单位 J", reliability=0.8),
            "Q4": dict(answer="W = 50×10×12 = 6000 J；P = ……（后半字迹模糊）",
                       mark="score", score="5/10",
                       comment="后半部分字迹不清，功率结果无法确认", reliability=0.55),
            "Q5#blank1": dict(answer="重力势", mark="correct", reliability=0.8),
            "Q5#blank2": dict(answer="动", mark="correct", reliability=0.8),
            "Q6": dict(answer="P = 60×10×0.5 = 300 W", mark="wrong",
                       comment="300 J 是一次的功，不是功率", reliability=0.78),
            "Q7": dict(answer="B", mark="correct", reliability=0.9),
            "Q8": dict(answer="W = 50×8 = 400 J", mark="correct", reliability=0.84),
            "Q9": dict(answer=None, mark=None, reliability=0.31),
            "Q10": dict(answer="F = 2000 N；W = 2000×6000 = 1.2×10⁷ J；P = 1.2×10⁷÷5 = 2.4×10⁶ W",
                        mark="score", score="9/12",
                        comment="（2）时间未换算成秒", reliability=0.76),
            "Q11#a": dict(answer="不做功，脚没有移动", mark="correct", reliability=0.8),
            "Q11#b": dict(answer="动能最大，因为速度最快", mark="wrong",
                          comment="最高点速度为零，动能为零", reliability=0.82),
            "Q11#c": dict(answer="W1 = 300 J；P = 300÷60 = 5 W", mark="score", score="2/6",
                          comment="未把 20 次累加", reliability=0.77),
            "Q12#blank1": dict(answer="重力势", mark="correct", reliability=0.85),
            "Q12#blank2": dict(answer="动能", mark="wrong",
                               comment="应为弹性势能", reliability=0.79),
            "Q12#blank3": dict(answer=None, mark=None, reliability=0.38),
        },
    },
}


def earned_points(item_key: str, entry: dict) -> int:
    """Points earned for one entry, following the kit rubric."""
    full = ITEM_POINTS[item_key]
    mark = entry.get("mark")
    if mark == "correct":
        return full
    if mark == "wrong" or mark is None:
        return 0
    if mark == "score":
        return int(entry["score"].split("/")[0])
    if mark == "comment":
        return int(entry["earned"])
    raise ValueError(f"unknown mark {mark!r} for {item_key}")
