"""Synthetic demo fixtures for the teacher console (issue #167).

ALL data here is invented for demonstrating the UI: student IDs are
fictional (``S-0xx``), questions carry the repo's ``SYN-`` prefix, and
answers / grading reads are made up. No real student data, no names --
real field materials are pending issue #108 and must never be pasted
into fixtures.

Content is grounded in design.md's Chapter 3 skill table and the
``taxonomy/skills_ch3_v1.json`` skill ids/names （做功判断， 摩擦力做功，
平均功率估算， 功与功率比较， 重力做功， 做功阶段， 最高点动能， 弹性势能）.
The demo deliberately mixes the two uncertainties the design doc keeps
separate: some reads are reliable but the answer is wrong (S-023 第3题）,
some reads are doubtful, and one is effectively unread （需手录）.
"""

from __future__ import annotations

from .models import (
    ClassData,
    ConsoleData,
    EvidenceSnippet,
    ExportInfo,
    RecognitionItem,
    ReviewQuestionView,
    SkillHypothesisView,
    StudentMix,
)

_CHAPTER = "第三章《能量的转化与守恒》"
_ASSIGNMENT = "A-CH3-06"


def _class_one() -> ClassData:
    recognition = [
        RecognitionItem(
            student_id="S-023", question_label="第3题", sub_question="（2）",
            skill_name="判断推下木板所需的位移并结合摩擦力计算功",
            recognized_answer="克服摩擦力做功 W = 20 × 6 = 120 J",
            grading_result="错误", ocr_reliability=0.93,
            image_location="scan-2026-10-12/p03.png", page_label="第 3 页",
            observed_date="10月12日",
        ),
        RecognitionItem(
            student_id="S-023", question_label="第3题", sub_question="（1）",
            skill_name="判断推下木板所需的位移并结合摩擦力计算功",
            recognized_answer="木板被推下需要的位移是 0.8 m（末位数字模糊，疑似 0.8）",
            grading_result="部分正确", ocr_reliability=0.71,
            image_location="scan-2026-10-12/p03.png", page_label="第 3 页",
            observed_date="10月12日",
        ),
        RecognitionItem(
            student_id="S-011", question_label="第4题",
            skill_name="估算物理量并计算平均功率",
            recognized_answer="P = W/t = 60 × 10 × 3 ÷ 1 = 1800 W",
            grading_result="错误", ocr_reliability=0.95,
            image_location="scan-2026-10-12/p05.png", page_label="第 5 页",
            observed_date="10月12日",
        ),
        RecognitionItem(
            student_id="S-019", question_label="第6题",
            skill_name="估算物理量并计算平均功率",
            recognized_answer="平均功率约为 3×10² W（指数部分字迹较淡）",
            grading_result="部分正确", ocr_reliability=0.66,
            image_location="scan-2026-10-12/p06.png", page_label="第 6 页",
            observed_date="10月12日",
        ),
        RecognitionItem(
            student_id="S-008", question_label="第12题", sub_question="（1）",
            skill_name="弹性势能",
            recognized_answer="弹性势能转化为动能和重力势能",
            grading_result="正确", ocr_reliability=0.97,
            image_location="scan-2026-10-12/p08.png", page_label="第 8 页",
            observed_date="10月12日",
        ),
        RecognitionItem(
            student_id="S-031", question_label="第11题", sub_question="（2）",
            skill_name="最高点动能",
            recognized_answer="",
            grading_result="无法辨认", ocr_reliability=0.32,
            image_location="scan-2026-10-12/p07.png", page_label="第 7 页",
            observed_date="10月12日",
        ),
    ]
    hypotheses = [
        SkillHypothesisView(
            student_id="S-023", skill_id="ch3-friction-work",
            skill_name="判断推下木板所需的位移并结合摩擦力计算功",
            state="需要练习", provisional=True, confidence="中",
            hypothesis_note="两次涉及摩擦力的题目都错在摩擦力大小的判断上；"
                            "位移判断基本正确。仍属待验证假设，需教师确认。",
            evidence=[
                EvidenceSnippet("第3题（2）", "10月12日", "错误",
                                "摩擦力取了推力的一半，未判断匀速条件"),
                EvidenceSnippet("第3题（1）", "10月12日", "部分正确",
                                "位移判断对，计算未完成"),
            ],
        ),
        SkillHypothesisView(
            student_id="S-011", skill_id="ch3-estimate-average-power",
            skill_name="估算物理量并计算平均功率",
            state="需要练习", provisional=True, confidence="中",
            hypothesis_note="估算题连续两次在时间单位换算上出错，"
                            "公式本身选用正确。",
            evidence=[
                EvidenceSnippet("第4题", "10月12日", "错误",
                                "1 分钟未换算为 60 秒"),
                EvidenceSnippet("第6题", "10月10日", "部分正确",
                                "估算数量级合理，单位换算漏一步"),
            ],
        ),
        SkillHypothesisView(
            student_id="S-034", skill_id="ch3-work-vs-power",
            skill_name="比较功与功率，排除无关条件",
            state="正在改善", provisional=False, confidence="中",
            hypothesis_note="上周同类题答错，本次变式题已能排除无关条件；"
                            "还需一次间隔后的独立作答来确认。",
            evidence=[
                EvidenceSnippet("第7题", "10月5日", "错误",
                                "把做功多误判为做功快"),
                EvidenceSnippet("第7题变式", "10月12日", "正确",
                                "先算功率再比较，理由完整"),
            ],
        ),
        SkillHypothesisView(
            student_id="S-005", skill_id="ch3-gravitational-work",
            skill_name="计算重力做功",
            state="待复习", provisional=False, confidence="低",
            hypothesis_note="最近一次证据为 4 周前。长期没有新证据时安排"
                            "复习检查，不代表学生已经遗忘。",
            evidence=[
                EvidenceSnippet("第8题", "9月18日", "正确",
                                "W = Gh 计算完整，单位正确"),
            ],
        ),
    ]
    questions = [
        ReviewQuestionView(
            id="SYN-Q1", category="共同题", difficulty="medium",
            stem="甲、乙两台机器，甲在 10 s 内做功 2000 J，乙在 5 s 内做功 "
                 "800 J。比较两台机器做功的多少和做功的快慢。",
            skill_names=["比较功与功率，排除无关条件"],
            recommendation_reason="全班共同题，便于统一讲评；上周第7题显示多名"
                                  "学生混淆做功多少与做功快慢。",
            answer="甲做功多；P甲 = 200 W，P乙 = 160 W，甲做功更快。",
            solution_steps=[
                "比较做功：W甲 = 2000 J > W乙 = 800 J，甲做功多。",
                "比较功率：P甲 = 2000 J / 10 s = 200 W；"
                "P乙 = 800 J / 5 s = 160 W，甲做功更快。",
            ],
            scoring_notes="做功比较 1 分，功率计算各 1 分，结论 1 分；"
                          "只写结论无过程给一半分。",
            assigned_count=41,
        ),
        ReviewQuestionView(
            id="SYN-Q2", category="当前学习", difficulty="medium",
            stem="质量为 2 kg 的物体从离地 5 m 高处自由下落（g 取 10 N/kg），"
                 "求重力做的功。",
            skill_names=["计算重力做功"],
            recommendation_reason="本周新课内容，全班当前学习题。",
            answer="W = Gh = mgh = 2 × 10 × 5 = 100 J。",
            solution_steps=[
                "重力 G = mg = 2 kg × 10 N/kg = 20 N。",
                "重力做功 W = Gh = 20 N × 5 m = 100 J。",
            ],
            scoring_notes="公式正确给一半分；数值与单位齐全给满分；"
                          "漏写单位扣 1 分。",
            assigned_count=38,
        ),
        ReviewQuestionView(
            id="SYN-Q3", category="薄弱点练习", difficulty="easy",
            stem="用 30 N 的水平推力推动木箱在水平地面上匀速前进 4 m，"
                 "木箱受到的摩擦力为 30 N。求推力做的功和克服摩擦力做的功。",
            skill_names=["判断推下木板所需的位移并结合摩擦力计算功"],
            recommendation_reason="针对已确认的摩擦力做功薄弱点：先判断匀速时"
                                  "摩擦力与推力的关系，再分别计算两个功。",
            answer="推力做功 120 J，克服摩擦力做功 120 J。",
            solution_steps=[
                "推力做功 W = Fs = 30 N × 4 m = 120 J。",
                "克服摩擦力做功 W = fs = 30 N × 4 m = 120 J。",
            ],
            scoring_notes="两个功各 2 分；若摩擦力取值错误但方法正确，"
                          "方法分照给。",
            assigned_count=6,
        ),
        ReviewQuestionView(
            id="SYN-Q4", category="旧知识复习", difficulty="easy",
            stem="一位质量约 50 kg 的同学在 20 s 内爬上 3 m 高的楼层，"
                 "估算他爬楼的平均功率（g 取 10 N/kg）。",
            skill_names=["估算物理量并计算平均功率"],
            recommendation_reason="间隔复习：平均功率估算上次出现于 3 周前，"
                                  "安排一道同类题检查是否保持。",
            answer="W = mgh = 1500 J，P = W/t = 75 W。",
            solution_steps=[
                "克服重力做功 W = mgh = 50 × 10 × 3 = 1500 J。",
                "平均功率 P = 1500 J / 20 s = 75 W。",
            ],
            scoring_notes="估算值在 60–90 W 之间均可接受；"
                          "须写出估算所用的质量与高度。",
            assigned_count=12,
        ),
        ReviewQuestionView(
            id="SYN-Q5", category="当前学习", difficulty="hard",
            stem="如图所示为小明原地纵跳摸高的过程示意图。判断起跳蹬地阶段"
                 "地面对脚的支持力是否做功，并说明理由。",
            skill_names=["判断做功阶段", "最高点动能"],
            recommendation_reason="综合题，分别考查做功阶段判断；图示无法可靠"
                                  "生成，已标记图待补充，需教师确认或补图。",
            answer="不做功。蹬地阶段脚没有离开地面，脚在支持力方向上没有"
                   "移动距离，因此支持力不做功。",
            solution_steps=[
                "做功的两个必要因素：作用在物体上的力、物体在力的方向上"
                "移动的距离。",
                "蹬地阶段脚与地面接触但未移动，沿支持力方向的位移为零，"
                "故支持力不做功。",
            ],
            scoring_notes="判断 1 分，理由须提到“沿力的方向没有位移”给 2 分；"
                          "只答“不做功”无理由给 1 分。",
            figure_note="纵跳过程示意图：蹬地、腾空、最高点三个阶段（图待补充）",
            assigned_count=38,
        ),
    ]
    mix = [
        StudentMix("S-005", {"共同题": 2, "当前学习": 2, "薄弱点练习": 0, "旧知识复习": 2}),
        StudentMix("S-008", {"共同题": 2, "当前学习": 3, "薄弱点练习": 0, "旧知识复习": 1}),
        StudentMix("S-011", {"共同题": 2, "当前学习": 2, "薄弱点练习": 2, "旧知识复习": 0}),
        StudentMix("S-019", {"共同题": 2, "当前学习": 2, "薄弱点练习": 1, "旧知识复习": 1}),
        StudentMix("S-023", {"共同题": 2, "当前学习": 2, "薄弱点练习": 2, "旧知识复习": 1}),
        StudentMix("S-034", {"共同题": 2, "当前学习": 3, "薄弱点练习": 1, "旧知识复习": 1}),
    ]
    export = ExportInfo(
        assignment_number=_ASSIGNMENT,
        students=[("S-005", 3), ("S-008", 3), ("S-011", 4), ("S-019", 3),
                  ("S-023", 4), ("S-031", 3), ("S-034", 4), ("S-041", 3)],
        teacher_key_pages=7,
        last_export="A-CH3-05 · 10月16日 · 全班 41 份学生卷 + 教师版",
    )
    return ClassData(
        key="g9-1", label="九年级1班", chapter_label=_CHAPTER,
        assignment_number=_ASSIGNMENT, recognition=recognition,
        hypotheses=hypotheses, review_questions=questions, mix=mix,
        export=export,
    )


def _class_two() -> ClassData:
    recognition = [
        RecognitionItem(
            student_id="S-102", question_label="第8题",
            skill_name="计算重力做功",
            recognized_answer="W = Gh = 100 × 2 = 200 J",
            grading_result="正确", ocr_reliability=0.96,
            image_location="scan-2026-10-12/p11.png", page_label="第 2 页",
            observed_date="10月12日",
        ),
        RecognitionItem(
            student_id="S-117", question_label="第11题", sub_question="（1）",
            skill_name="判断做功阶段",
            recognized_answer="蹬地和上升阶段都做功（“上升”二字模糊）",
            grading_result="部分正确", ocr_reliability=0.63,
            image_location="scan-2026-10-12/p13.png", page_label="第 4 页",
            observed_date="10月12日",
        ),
        RecognitionItem(
            student_id="S-126", question_label="第4题",
            skill_name="估算物理量并计算平均功率",
            recognized_answer="",
            grading_result="无法辨认", ocr_reliability=0.28,
            image_location="scan-2026-10-12/p12.png", page_label="第 3 页",
            observed_date="10月12日",
        ),
    ]
    hypotheses = [
        SkillHypothesisView(
            student_id="S-117", skill_id="ch3-work-phases",
            skill_name="判断做功阶段",
            state="需要练习", provisional=True, confidence="低",
            hypothesis_note="做功阶段判断含糊：把腾空上升阶段也计入支持力"
                            "做功。仅一次证据，待验证。",
            evidence=[
                EvidenceSnippet("第11题（1）", "10月12日", "部分正确",
                                "未区分蹬地与腾空阶段"),
            ],
        ),
        SkillHypothesisView(
            student_id="S-109", skill_id="ch3-apex-kinetic-energy",
            skill_name="最高点动能",
            state="证据不足", provisional=False, confidence="低",
            hypothesis_note="该技能目前只有一次订正后的作答，不能算独立证据，"
                            "需在下次作业中安排一道独立题。",
            evidence=[
                EvidenceSnippet("第11题（2）", "10月12日", "正确",
                                "订正后完成，非独立作答"),
            ],
        ),
    ]
    questions = [
        ReviewQuestionView(
            id="SYN-Q1", category="共同题", difficulty="medium",
            stem="甲、乙两台机器，甲在 10 s 内做功 2000 J，乙在 5 s 内做功 "
                 "800 J。比较两台机器做功的多少和做功的快慢。",
            skill_names=["比较功与功率，排除无关条件"],
            recommendation_reason="全班共同题，便于统一讲评（与1班同一道共同题）。",
            answer="甲做功多；P甲 = 200 W，P乙 = 160 W，甲做功更快。",
            solution_steps=[
                "比较做功：W甲 = 2000 J > W乙 = 800 J，甲做功多。",
                "比较功率：P甲 = 200 W，P乙 = 160 W，甲做功更快。",
            ],
            scoring_notes="做功比较 1 分，功率计算各 1 分，结论 1 分。",
            assigned_count=39,
        ),
        ReviewQuestionView(
            id="SYN-Q6", category="薄弱点练习", difficulty="easy",
            stem="运动员从蹬地起跳到落回地面，依次经历蹬地、腾空、落地三个"
                 "阶段。指出地面对脚的支持力做功的阶段，并说明理由。",
            skill_names=["判断做功阶段"],
            recommendation_reason="针对做功阶段判断的待验证薄弱点，用不同情境"
                                  "再验证一次。",
            answer="三个阶段支持力都不做功：各阶段脚在支持力方向上均无位移"
                   "（腾空阶段不受支持力）。",
            solution_steps=[
                "蹬地、落地阶段：脚与地面接触但不移动，位移为零。",
                "腾空阶段：脚已离地，不受地面支持力。",
            ],
            scoring_notes="每阶段判断与理由各 1 分；腾空阶段须答出“不受力”。",
            assigned_count=4,
        ),
        ReviewQuestionView(
            id="SYN-Q2", category="当前学习", difficulty="medium",
            stem="质量为 2 kg 的物体从离地 5 m 高处自由下落（g 取 10 N/kg），"
                 "求重力做的功。",
            skill_names=["计算重力做功"],
            recommendation_reason="本周新课内容，全班当前学习题。",
            answer="W = Gh = mgh = 2 × 10 × 5 = 100 J。",
            solution_steps=[
                "重力 G = mg = 20 N。",
                "重力做功 W = Gh = 20 N × 5 m = 100 J。",
            ],
            scoring_notes="公式正确给一半分；数值与单位齐全给满分。",
            assigned_count=36,
        ),
    ]
    mix = [
        StudentMix("S-102", {"共同题": 2, "当前学习": 3, "薄弱点练习": 0, "旧知识复习": 1}),
        StudentMix("S-109", {"共同题": 2, "当前学习": 2, "薄弱点练习": 1, "旧知识复习": 1}),
        StudentMix("S-117", {"共同题": 2, "当前学习": 2, "薄弱点练习": 2, "旧知识复习": 0}),
        StudentMix("S-126", {"共同题": 2, "当前学习": 3, "薄弱点练习": 0, "旧知识复习": 1}),
    ]
    export = ExportInfo(
        assignment_number=_ASSIGNMENT,
        students=[("S-102", 3), ("S-109", 3), ("S-117", 4), ("S-126", 3),
                  ("S-133", 3)],
        teacher_key_pages=6,
        last_export="A-CH3-05 · 10月16日 · 全班 39 份学生卷 + 教师版",
    )
    return ClassData(
        key="g9-2", label="九年级2班", chapter_label=_CHAPTER,
        assignment_number=_ASSIGNMENT, recognition=recognition,
        hypotheses=hypotheses, review_questions=questions, mix=mix,
        export=export,
    )


def build_demo_data() -> ConsoleData:
    """The console's demo dataset: two classes, fully synthetic."""
    return ConsoleData(classes=[_class_one(), _class_two()])
