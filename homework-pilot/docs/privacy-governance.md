# Homework Pilot — Student Data Privacy & Governance

Date: 2026-09-27. Status: **policy draft — consents and several decisions are PENDING**
(see §7). Nothing here fabricates an approval that has not happened.

Context: the pilot serves ~80 students in 2 classes taught by the pilot
teacher (Daniel's mother). Students are minors (未成年人); their schoolwork
is sensitive data (敏感数据). The design doc
(`homwork-pilot/design.md`, "待确认事项") leaves open: who can access student
materials, which external processing services are used, retention periods,
and correction/deletion. This document answers those items; the items still
awaiting a human decision are marked **PENDING**.

Companion code: `homework-pilot/privacy/guard.py` enforces the rules that can
be encoded (ID-only validation, name-candidate scrubbing, external-service
payload allowlisting, deletion). Its documented heuristic limits apply.

## 1. ID-only principle （仅学号原则）

Student IDs (学号), never names (姓名), everywhere:

- **Storage （存储）**: every record is keyed by student ID. No `name`,
  `student_name`, `姓名`, or similar field may be written to any database,
  file, or in-memory store. `guard.assert_id_only()` must be called at every
  storage boundary; it raises `NameFieldError` on violation.
- **Logs （日志）**: log lines must not contain student names. Pass free text
  through `guard.sanitize_log_message()` before logging.
- **Exports （导出）**: student PDFs, CSVs, and batch exports carry student
  IDs only. `guard.assert_id_only()` runs on every export payload.
- **Prompts to external services （外部服务请求）**: OCR/LLM API payloads are
  filtered with `guard.scrub_for_external_service(payload, allowed_fields)`
  — allowlist only — after an ID-only check.

The ID→name roster (学号↔姓名对照表), if one exists, is kept by the teacher
offline and **never enters this repo, the codebase, or any prompt**. Scrubbing
heuristics therefore flag *candidates* for human review; a clean scan is not
proof of absence (see `guard.py` module docs).

## 2. Access-control matrix （访问权限矩阵）

| Data class | Pilot teacher （教师） | Developer （开发者） | Service providers （服务商） |
|---|---|---|---|
| Student work images/PDFs （学生作业原图） | Yes — full, by student ID | No production access; synthetic/test data only | Only the declared service for the declared purpose (§3) |
| Learning records by student ID （按学号的学习记录） | Yes — read/write/correct | No production access; schema-level work on anonymized fixtures | No |
| Aggregated / class-level stats （班级汇总统计） | Yes | Yes (no student IDs attached where avoidable) | No |
| ID→name roster （学号↔姓名对照表） | Yes (kept offline by teacher) | **Never** | **Never** |
| System logs （系统日志） | No | Yes — scrubbed, ID-only | No |
| Generated homework PDFs （生成的作业PDF） | Yes — approves before release | Yes (templates, no student data) | Print path only if declared in §3 |

Rules:
- The developer never sees real student papers or the roster; debugging uses
  synthetic data or teacher-redacted samples.
- Service providers receive the minimum fields for the declared purpose, via
  the allowlisted payload in §3 — nothing else.
- Every access exception is logged and disclosed to the teacher.

## 3. External-service data-flow disclosure （外部服务数据流披露）

No student data goes to any external service without **both**: a documented
reason below, and the teacher's knowledge/acknowledgement （教师知情确认）.

| Service （服务） | Data sent （发送的数据） | Why （原因） | Teacher acknowledged （教师已知情） |
|---|---|---|---|
| *(none declared yet)* | — | — | **PENDING** |

To add a service, copy this template, fill every column, and have the teacher
acknowledge before first use. The code counterpart is
`guard.scrub_for_external_service()` — the `allowed_fields` argument must match
the "Data sent" column exactly.

Current status: **PENDING** — no OCR or LLM provider has been selected yet
(design doc "待确认事项：外部处理服务选择").

## 4. Retention & deletion policy （保存期限与删除政策）

- **Default retention （默认保存期）**: learning records are kept for the
  duration of the pilot plus one school term for follow-up analysis, then
  deleted. **PENDING** teacher/school confirmation of the exact period.
- **Raw scans （原始扫描件）**: deleted once OCR results are verified by the
  teacher, unless the teacher opts to keep them for the pilot duration.
  **PENDING** confirmation.
- **Deletion on request （应请求删除）**: any time, no questions asked — see §5.
- **End of pilot （试点结束）**: all student data deleted within 30 days of
  the pilot's end unless the school requests otherwise in writing.
  **PENDING** confirmation.
- Deletion means complete removal from storage and backups within the
  backup-retention window; the deletion path is `guard.delete_student_records()`,
  which verifies nothing remains and raises on partial deletion.

## 5. Correction / deletion on request （更正/删除请求流程）

1. Request received from the teacher, parent/guardian （家长）, or school —
   by message to the teacher or developer; no formal form required.
2. The teacher confirms which student ID(s) the request covers (the roster
   stays with the teacher; the developer only ever receives student IDs).
3. The developer runs `guard.delete_student_records(store, student_id)` for
   deletion, or applies the teacher-supplied correction for correction
   requests. The function verifies completeness and raises on partial
   deletion.
4. The developer confirms back to the teacher: student ID, records removed
   (count), date. The confirmation itself carries no student data beyond the ID.
5. Target turnaround: within 7 days; urgent requests (e.g. a paper uploaded
   to the wrong student) within 24 hours.

## 6. Consent checklist （知情同意清单）

All items must be completed **before** real student papers are used in the
pilot. PENDING items are genuine blockers, not paperwork.

| # | Consent / confirmation （同意/确认事项） | Status |
|---|---|---|
| 1 | Pilot teacher agrees to the trial and the workflow （教师同意试用） | **PENDING** |
| 2 | School approves differentiated homework & data handling （学校批准） | **PENDING** |
| 3 | Parents/guardians informed; consent or opt-out collected as the school requires （家长知情同意） | **PENDING** |
| 4 | Teacher acknowledges the external-service data flows in §3 （教师知情外部服务） | **PENDING** (no services declared yet) |
| 5 | Retention periods confirmed （保存期限确认） | **PENDING** |
| 6 | Teacher confirms the access matrix in §2 （访问权限确认） | **PENDING** |

Notes: students are minors, so parent/guardian consent follows whatever the
school requires — the pilot does not set its own lower bar. Consent records
(names/signatures) stay with the teacher/school; the repo tracks only the
checklist status above.

## 7. Open decisions （待确认事项）

Inherited from the design doc, restated as the decisions that unblock this
policy:

- Which external processing services are used （外部处理服务选择） — §3.
- Exact retention periods （保存期限） — §4.
- Correction/deletion handling details （纠错和删除方式） — §5 turnaround
  targets proposed above, awaiting confirmation.
- Who uploads, and how paper maps to student ID at capture time — the
  highest-risk moment for a name entering the system; the capture step must
  use printed student IDs (§1 of the design doc) and the uploader must confirm
  no names are visible before upload.

## 8. What the code enforces vs. what stays human （代码与人工的分工）

Enforced in `homework-pilot/privacy/guard.py` (tested):
`assert_id_only`, `scrub_for_external_service` allowlisting,
`delete_student_records` with verification, `scrub_text`/`sanitize_log_message`
candidate flagging.

Stays human: consent collection, teacher acknowledgement of data flows,
review of flagged name candidates, roster custody, and the final decision on
retention periods. The code is a guardrail, not a substitute for these.
