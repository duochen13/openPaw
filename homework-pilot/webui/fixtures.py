"""Synthetic demo fixtures for the student-side MVP UI (issue #176).

ALL data here is invented for demonstrating the UI: the student is an
ID only (``S-023``), the papers and answers are made up, and no real
student data appears anywhere. Real field materials are pending
issue #108 follow-up and must never be pasted into fixtures.

The main demo paper is the Chapter 3 test （浙教版九年级上册科学第三章
《能量的转化与守恒》）, with a deliberate spread of the situations the
MVP has to show honestly:

* verdicts: 4 对 / 2 错 / 2 待确认；
* all three verdict sources appear （红笔标记 / 答案比对 / 模型判定）;
* exactly one question (第7题） was read with low reliability -- it is
  待确认 because the *read* is shaky, which the UI shows separately
  from the verdict, never merged into it;
* 第8题 was read reliably but the *judgment* is uncertain, so it is
  待确认 for the other reason.
"""

from __future__ import annotations

from .models import PaperResult, QuestionResult, StudentData


def _main_paper() -> PaperResult:
    questions = [
        QuestionResult(
            number=1,
            question_text="下列过程属于动能转化为重力势能的是（ ）",
            student_answer="B（滚上斜坡的小车）",
            verdict="对", source="红笔标记",
            ocr_reliability=0.97,
            image_location="scan-ch3-test/p01-q1.png", page_label="第 1 页",
        ),
        QuestionResult(
            number=2,
            question_text="关于功和功率，下列说法正确的是（ ）",
            student_answer="D",
            verdict="对", source="答案比对",
            ocr_reliability=0.95,
            image_location="scan-ch3-test/p01-q2.png", page_label="第 1 页",
        ),
        QuestionResult(
            number=3,
            question_text="质量为 2 kg 的物体从离地 5 m 高处自由下落，"
                          "重力做功为 ______ J（g 取 10 N/kg）。",
            student_answer="100 J",
            verdict="对", source="模型判定",
            ocr_reliability=0.93,
            image_location="scan-ch3-test/p02-q3.png", page_label="第 2 页",
        ),
        QuestionResult(
            number=4,
            question_text="起跳蹬地阶段，地面对脚的支持力是否做功？说明理由。",
            student_answer="不做功，脚在支持力方向上没有移动距离",
            verdict="对", source="红笔标记",
            ocr_reliability=0.90,
            image_location="scan-ch3-test/p02-q4.png", page_label="第 2 页",
        ),
        QuestionResult(
            number=5,
            question_text="用 30 N 的水平推力推动木箱在水平地面上匀速前进 4 m，"
                          "推力做功为 ______ J，克服摩擦力做功为 ______ J。",
            student_answer="推力做功 60 J；克服摩擦力做功 120 J",
            verdict="错", source="答案比对",
            reference_answer="推力做功 120 J；克服摩擦力做功 120 J",
            ocr_reliability=0.96,
            image_location="scan-ch3-test/p03-q5.png", page_label="第 3 页",
        ),
        QuestionResult(
            number=6,
            question_text="甲机器在 10 s 内做功 2000 J，乙机器在 5 s 内做功 "
                          "800 J，做功更快的是（ ）",
            student_answer="乙",
            verdict="错", source="模型判定",
            reference_answer="甲（P甲 = 200 W > P乙 = 160 W）",
            ocr_reliability=0.94,
            image_location="scan-ch3-test/p03-q6.png", page_label="第 3 页",
        ),
        QuestionResult(
            number=7,
            question_text="一位同学在 20 s 内爬上 3 m 高的楼层，"
                          "估算他爬楼的平均功率约为 ______ W。",
            student_answer="75 W（末位数字字迹潦草）",
            verdict="待确认", source="模型判定", proposed_verdict="对",
            ocr_reliability=0.62,
            image_location="scan-ch3-test/p04-q7.png", page_label="第 4 页",
        ),
        QuestionResult(
            number=8,
            question_text="物体在光滑水平面上匀速滑动时，动能不变，"
                          "所以合力做功为零。这一说法是否正确？说明理由。",
            student_answer="错误，物体在运动，合力一定做功",
            verdict="待确认", source="模型判定", proposed_verdict="错",
            reference_answer="说法正确：动能不变，合力做功为零（动能定理）",
            ocr_reliability=0.91,
            image_location="scan-ch3-test/p04-q8.png", page_label="第 4 页",
        ),
    ]
    return PaperResult(
        id="paper-ch3-test",
        title="第三章《能量的转化与守恒》测试卷",
        date_label="10月24日",
        status="已出结果",
        questions=questions,
    )


def _quiz_paper() -> PaperResult:
    questions = [
        QuestionResult(
            number=1,
            question_text="功率的单位是（ ）",
            student_answer="C（瓦特）",
            verdict="对", source="红笔标记",
            ocr_reliability=0.98,
            image_location="scan-ch3-quiz/p01-q1.png", page_label="第 1 页",
        ),
        QuestionResult(
            number=2,
            question_text="功率是表示物体做功 ______ 的物理量。",
            student_answer="快慢",
            verdict="对", source="答案比对",
            ocr_reliability=0.95,
            image_location="scan-ch3-quiz/p01-q2.png", page_label="第 1 页",
        ),
        QuestionResult(
            number=3,
            question_text="一台机器的功率是 500 W，它表示这台机器每秒做功 ______ J。",
            student_answer="50 J",
            verdict="错", source="模型判定",
            reference_answer="500 J",
            ocr_reliability=0.93,
            image_location="scan-ch3-quiz/p01-q3.png", page_label="第 1 页",
        ),
        QuestionResult(
            number=4,
            question_text="下列关于能量的说法，正确的是（ ）",
            student_answer="A",
            verdict="对", source="答案比对",
            ocr_reliability=0.96,
            image_location="scan-ch3-quiz/p01-q4.png", page_label="第 1 页",
        ),
    ]
    return PaperResult(
        id="paper-ch3-quiz",
        title="第三章随堂小测",
        date_label="10月21日",
        status="已出结果",
        questions=questions,
    )


def _processing_paper() -> PaperResult:
    return PaperResult(
        id="paper-ch2-practice",
        title="第二章章节练习",
        date_label="10月25日",
        status="处理中",
        questions=[],
    )


def build_demo_data() -> StudentData:
    """The student demo dataset: one student, three papers, synthetic."""
    return StudentData(
        student_id="S-023",
        student_context="科学 · 九年级上册",
        papers=[_main_paper(), _quiz_paper(), _processing_paper()],
    )
