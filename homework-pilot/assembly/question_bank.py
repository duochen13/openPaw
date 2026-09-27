"""Synthetic question bank + sample generated set (issue #114).

Every question below is a SYNTHETIC fixture authored for tests and demos
(ids carry the ``SYN-`` prefix). None of them is teacher-approved content:
the teacher review queue (``review_queue``) is the gate they must pass
before entering any real bank. Real teacher materials still need to be
provided -- see the README section "What still needs the teacher".

The skill ids and Chinese names mirror the chapter-3 taxonomy
(``skills_ch3_v1.json``, issue #112):

* ch3-gravitational-work -- 计算重力做功
* ch3-estimate-average-power -- 估算物理量并计算平均功率
* ch3-work-vs-power -- 比较功与功率，排除无关条件
* ch3-judge-work -- 根据力与沿力方向的位移判断指定力做功
* ch3-work-phases -- 判断做功阶段
* ch3-friction-work -- 判断推下木板所需的位移并结合摩擦力计算功
"""

from __future__ import annotations

from .generate import (
    Difficulty,
    FigureStatus,
    FigureTask,
    Question,
    QuestionType,
    create_question,
)

# -- sample generated set: >= 3 chapter skills, each passing validation -----

SAMPLE_GENERATED_SET: list[Question] = [
    create_question(
        id="SYN-GW-01",
        skill_ids=["ch3-gravitational-work"],
        stem=(
            "质量为 2 kg 的物体从 5 m 高处自由下落（g 取 10 N/kg），"
            "求重力对物体做的功。"
        ),
        question_type=QuestionType.CALCULATION,
        figure=FigureStatus.NONE,
        given_quantities={"mass": "2 kg", "height": "5 m", "g": "10 N/kg"},
        required_inputs=["mass", "height", "g"],
        target="重力做的功 W",
        answer="100 J",
        answer_is_unique=True,
        solution_steps=[
            "重力 G = m·g = 2 kg × 10 N/kg = 20 N",
            "重力做功 W = G·h = 20 N × 5 m = 100 J（位移沿重力方向）",
        ],
        scoring_notes="公式正确得一半分；数值与单位（J）正确得满分。g 取 10 N/kg 已在题干中说明。",
        difficulty=Difficulty.EASY,
        recommendation_reason="计算重力做功（ch3-gravitational-work）的基础题：W = G·h，位移沿重力方向。",
    ),
    create_question(
        id="SYN-AP-01",
        skill_ids=["ch3-estimate-average-power"],
        stem=(
            "一名体重约 50 kg 的学生，用 20 s 从一楼匀速走到三楼"
            "（一楼到三楼竖直高度约 6 m，g 取 10 N/kg）。"
            "估算该学生上楼过程中克服重力做功的平均功率。"
        ),
        question_type=QuestionType.ESTIMATION,
        figure=FigureStatus.NONE,
        given_quantities={
            "mass": "50 kg",
            "height": "6 m",
            "time": "20 s",
            "g": "10 N/kg",
        },
        required_inputs=["mass", "height", "time", "g"],
        target="克服重力做功的平均功率 P",
        answer="约 150 W（估算值，140–160 W 均可接受）",
        answer_is_unique=False,
        acceptable_alternatives=[
            "140–160 W 范围内的估算结果（取决于对身高/楼高的估算）",
        ],
        solution_steps=[
            "估算克服重力做的功：W = m·g·h = 50 kg × 10 N/kg × 6 m = 3000 J",
            "平均功率 P = W / t = 3000 J / 20 s = 150 W",
            "说明：楼高为估算值，答案在合理范围内即正确",
        ],
        scoring_notes="估算思路正确是关键：能说明楼高/体重的估算依据即给主要分数；功率公式与单位（W）正确给满分。",
        difficulty=Difficulty.MEDIUM,
        recommendation_reason="估算物理量并计算平均功率（ch3-estimate-average-power）的典型情境：先估算缺失量，再用 P = W / t。",
    ),
    create_question(
        id="SYN-WP-01",
        skill_ids=["ch3-work-vs-power"],
        stem=(
            "甲机器在 10 s 内做功 1000 J，乙机器在 5 s 内做功 800 J。"
            "（两台机器的颜色、体积与本题比较无关。）"
            "请比较：哪台机器做的功多？哪台机器的功率大？"
        ),
        question_type=QuestionType.COMPARISON,
        figure=FigureStatus.NONE,
        given_quantities={
            "work_A": "1000 J",
            "time_A": "10 s",
            "work_B": "800 J",
            "time_B": "5 s",
        },
        required_inputs=["work_A", "time_A", "work_B", "time_B"],
        target="做功多少与功率大小的比较结论",
        answer="甲做功多（1000 J > 800 J）；乙功率大（P_乙 = 160 W > P_甲 = 100 W）",
        answer_is_unique=True,
        solution_steps=[
            "做功比较：1000 J > 800 J，甲做功多",
            "P_甲 = 1000 J / 10 s = 100 W；P_乙 = 800 J / 5 s = 160 W",
            "功率比较：160 W > 100 W，乙功率大",
            "颜色、体积等条件与比较无关，已排除",
        ],
        scoring_notes="两个比较结论各占一半分；能明确指出无关条件不影响比较的可给表述分。",
        difficulty=Difficulty.MEDIUM,
        recommendation_reason="比较功与功率（ch3-work-vs-power）：区分“做功多少”与“做功快慢”，并排除无关条件。",
    ),
    create_question(
        id="SYN-JW-01",
        skill_ids=["ch3-judge-work"],
        stem=(
            "用 20 N 的水平推力推一张桌子，桌子沿推力方向移动了 3 m。"
            "求：推力做的功是多少？桌子受到的重力做的功是多少？"
        ),
        question_type=QuestionType.JUDGMENT,
        figure=FigureStatus.NONE,
        given_quantities={"force": "20 N", "displacement": "3 m"},
        required_inputs=["force", "displacement"],
        target="推力做功与重力做功",
        answer="推力做功 60 J；重力做功 0 J（位移方向与重力方向垂直）",
        answer_is_unique=True,
        solution_steps=[
            "推力做功：W = F·s = 20 N × 3 m = 60 J（位移沿推力方向）",
            "重力方向竖直向下，桌子位移水平，重力方向上无位移",
            "重力做功为 0 J",
        ],
        scoring_notes="推力做功计算正确一半分；能判断重力不做功并说明理由得满分。",
        difficulty=Difficulty.EASY,
        recommendation_reason="判断指定力是否做功（ch3-judge-work）：力做功要求沿力方向有位移。",
    ),
    create_question(
        id="SYN-WPHS-01",
        skill_ids=["ch3-work-phases"],
        stem=(
            "如图所示为立定跳远的三个阶段：下蹲、蹬地起跳、腾空上升。"
            "在蹬地起跳阶段，地面对人的支持力是否做功？说明理由。"
        ),
        question_type=QuestionType.JUDGMENT,
        figure=FigureStatus.PLACEHOLDER,
        figure_task=FigureTask(
            question_id="SYN-WPHS-01",
            skill_id="ch3-work-phases",
            description="立定跳远三阶段示意图：下蹲、蹬地起跳、腾空上升（人物简笔画 + 阶段标注）",
            why_needed="阶段判断依赖对动作过程的直观理解，纯文字描述易产生歧义；"
                       "文本优先生成无法可靠产出人物动作示意图。",
        ),
        given_quantities={},
        required_inputs=[],
        target="蹬地阶段支持力是否做功及理由",
        answer="做功：蹬地阶段人体重心上升，支持力方向上有位移",
        answer_is_unique=True,
        solution_steps=[
            "判断依据：力做功要求物体沿力的方向发生位移",
            "蹬地阶段：人体重心向上移动，支持力竖直向上，位移沿支持力方向",
            "结论：支持力做正功",
        ],
        scoring_notes="结论正确一半分；能用“沿力方向有位移”说明理由得满分。",
        difficulty=Difficulty.MEDIUM,
        recommendation_reason="判断做功阶段（ch3-work-phases）：多阶段运动中识别力做功的阶段。",
    ),
    create_question(
        id="SYN-FW-01",
        skill_ids=["ch3-friction-work"],
        stem=(
            "如图所示，长 2 m 的均匀木板放在水平桌面上，木板与桌面间的"
            "滑动摩擦力为 5 N。用水平推力将木板缓慢推下桌面，直到木板"
            "重心到达桌面边缘（即推出 1 m）。求推力克服摩擦力做的功。"
        ),
        question_type=QuestionType.CALCULATION,
        figure=FigureStatus.PROVIDED,
        figure_description=(
            "示意图：水平桌面（阴影线表示桌沿），长 2 m 的矩形木板置于桌面上，"
            "右端与桌沿对齐；水平向右箭头标注推力 F；虚线标出木板重心初始位置"
            "（距右端 1 m）与推出后位置（重心到达桌沿）。"
        ),
        given_quantities={
            "board_length": "2 m",
            "push_distance": "1 m",
            "friction": "5 N",
        },
        required_inputs=["push_distance", "friction"],
        target="推力克服摩擦力做的功",
        answer="5 J",
        answer_is_unique=True,
        solution_steps=[
            "判断有效位移：木板重心到达桌沿需推出 1 m（不是整块木板长度 2 m）",
            "缓慢推动：推力大小等于摩擦力，克服摩擦力做功 W = f·s",
            "W = 5 N × 1 m = 5 J",
        ],
        scoring_notes="能正确判断有效位移为 1 m 是关键（误用 2 m 则公式分扣半）；单位 J 正确。",
        difficulty=Difficulty.HARD,
        recommendation_reason="判断有效位移并结合摩擦力计算功（ch3-friction-work）：多步推理，先判断位移再算功。",
    ),
]

#: skill_id -> questions, backing the test selector below.
QUESTION_BANK: dict[str, list[Question]] = {}
for _q in SAMPLE_GENERATED_SET:
    for _sid in _q.skill_ids:
        QUESTION_BANK.setdefault(_sid, []).append(_q)
del _q, _sid


def bank_selector(skill_id: str, kind: str, count: int) -> list[str]:
    """A :class:`engine.QuestionSelector` backed by the synthetic bank.

    Cycles through the skill's questions when ``count`` exceeds supply;
    falls back to a deterministic synthetic id for skills with no
    questions yet. Test-only: the real selector uses the teacher-approved
    bank (issue #115).
    """
    questions = QUESTION_BANK.get(skill_id, [])
    if not questions:
        return [f"SYN-{skill_id}-{kind}-{i + 1}" for i in range(count)]
    return [questions[i % len(questions)].id for i in range(count)]
