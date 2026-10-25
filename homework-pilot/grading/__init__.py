"""Student-side MVP grading pipeline (issue #176).

Pipeline: ingest -> segment -> transcribe -> judge -> confirm/export.

The output records (:mod:`grading.models`) mirror ``webui.models`` field
names and vocabularies so a graded paper can drop into the student web UI.
Two honesty rules are structural, not conventional:

* recognition reliability (how legible the handwriting read was) never
  enters the judge -- :func:`grading.judge.judge_item` does not accept a
  reliability argument at all;
* anything the pipeline cannot decide lands in 待确认 with a stated
  reason, never as a guessed 对/错.
"""
