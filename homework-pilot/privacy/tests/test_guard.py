"""Unit tests for homework-pilot privacy guard utilities.

Run from the homework-pilot directory:

    python3 -m unittest discover -s privacy/tests -t . -v

Also documents the honest limits of the name-detection heuristics.
"""

import unittest

from privacy.guard import (
    DictStudentStore,
    NameFieldError,
    assert_id_only,
    contains_cjk_name_candidate,
    delete_student_records,
    redact,
    sanitize_log_message,
    scrub_for_external_service,
    scrub_text,
)


class TestAssertIdOnly(unittest.TestCase):
    def test_clean_id_only_record_passes(self):
        assert_id_only({"student_id": "S001", "score": 85, "skill": "work-power"})

    def test_rejects_english_name_key(self):
        with self.assertRaises(NameFieldError):
            assert_id_only({"student_id": "S001", "name": "Alice"})

    def test_rejects_name_key_case_insensitive(self):
        with self.assertRaises(NameFieldError):
            assert_id_only({"student_id": "S001", "Student_Name": "Alice"})

    def test_rejects_chinese_name_key(self):
        with self.assertRaises(NameFieldError):
            assert_id_only({"student_id": "S001", "姓名": "张伟"})

    def test_rejects_compound_name_key(self):
        with self.assertRaises(NameFieldError):
            assert_id_only({"student_id": "S001", "parent_name": "张建国"})

    def test_rejects_nested_name_key(self):
        with self.assertRaises(NameFieldError):
            assert_id_only(
                {"student_id": "S001", "meta": {"reviewer": {"姓名": "李老师"}}},
                where="export",
            )

    def test_error_message_lists_offending_keys(self):
        try:
            assert_id_only({"name": "x", "姓名": "y"})
        except NameFieldError as exc:
            self.assertIn("name", str(exc))
            self.assertIn("姓名", str(exc))
        else:
            self.fail("NameFieldError not raised")

    def test_non_mapping_raises_type_error(self):
        with self.assertRaises(TypeError):
            assert_id_only(["not", "a", "dict"])


class TestCjkNameCandidates(unittest.TestCase):
    def test_flags_name_after_indicator_with_colon(self):
        hits = contains_cjk_name_candidate("学生：张伟 的作业")
        self.assertEqual(len(hits), 1)
        start, end, span = hits[0]
        self.assertEqual(span, "张伟")
        self.assertEqual("学生：张伟 的作业"[start:end], "张伟")

    def test_colon_required_no_colon_not_flagged(self):
        # Documented limitation: "姓名 李小明" (space, no colon) is NOT
        # flagged — the colon requirement keeps precision acceptable in a
        # domain full of 学生作业 / 学生答案 style text.
        self.assertEqual(contains_cjk_name_candidate("姓名 李小明"), [])

    def test_flags_name_before_tongxue(self):
        hits = contains_cjk_name_candidate("王芳同学 交了作业")
        self.assertTrue(any(span == "王芳" for _, _, span in hits))

    def test_no_indicator_no_flag(self):
        # A bare name in prose is NOT caught — documented limitation.
        self.assertEqual(contains_cjk_name_candidate("张伟 交了作业"), [])

    def test_generic_prose_not_flagged(self):
        self.assertEqual(
            contains_cjk_name_candidate("能量的转化与守恒是本章主题"), []
        )

    def test_empty_string(self):
        self.assertEqual(contains_cjk_name_candidate(""), [])


class TestRedactAndScrub(unittest.TestCase):
    def test_redact_replaces_span(self):
        cleaned, findings = scrub_text("学生：张伟 的作业已批改")
        self.assertNotIn("张伟", cleaned)
        self.assertIn("[REDACTED]", cleaned)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["review"], "human-review-required")

    def test_redact_merges_overlapping_spans(self):
        out = redact("abcdef", [(1, 3, "bc"), (2, 5, "cde")])
        self.assertEqual(out, "a[REDACTED]f")

    def test_scrub_clean_text_unchanged(self):
        cleaned, findings = scrub_text("第3题：计算重力做功")
        self.assertEqual(cleaned, "第3题：计算重力做功")
        self.assertEqual(findings, [])

    def test_sanitize_log_message(self):
        msg = sanitize_log_message("uploaded scan for 学生：张伟 page 3")
        self.assertNotIn("张伟", msg)


class TestScrubForExternalService(unittest.TestCase):
    def test_allowlist_filters_fields(self):
        payload = {
            "student_id": "S001",
            "ocr_text": "第3题答案…",
            "internal_note": "do not send",
        }
        out = scrub_for_external_service(payload, ["student_id", "ocr_text"])
        self.assertEqual(
            out, {"student_id": "S001", "ocr_text": "第3题答案…"}
        )

    def test_rejects_payload_with_name_field(self):
        with self.assertRaises(NameFieldError):
            scrub_for_external_service(
                {"student_id": "S001", "name": "Alice"}, ["student_id", "name"]
            )

    def test_filters_list_of_records(self):
        payload = [
            {"student_id": "S001", "ocr_text": "a", "extra": 1},
            {"student_id": "S002", "ocr_text": "b", "extra": 2},
        ]
        out = scrub_for_external_service(payload, ["student_id", "ocr_text"])
        self.assertEqual(
            out,
            [
                {"student_id": "S001", "ocr_text": "a"},
                {"student_id": "S002", "ocr_text": "b"},
            ],
        )

    def test_original_payload_not_mutated(self):
        payload = {"student_id": "S001", "secret": 1}
        scrub_for_external_service(payload, ["student_id"])
        self.assertIn("secret", payload)


class TestDeletion(unittest.TestCase):
    def _store(self):
        return DictStudentStore(
            {
                "S001": [
                    {"student_id": "S001", "item": "q3"},
                    {"student_id": "S001", "item": "q4"},
                ],
                "S002": [{"student_id": "S002", "item": "q3"}],
            }
        )

    def test_delete_removes_all_records(self):
        store = self._store()
        removed = delete_student_records(store, "S001")
        self.assertEqual(removed, 2)
        self.assertEqual(store.get_records("S001"), [])
        # Other students untouched.
        self.assertEqual(len(store.get_records("S002")), 1)
        self.assertNotIn("S001", list(store.list_student_ids()))

    def test_delete_unknown_id_returns_zero(self):
        store = self._store()
        self.assertEqual(delete_student_records(store, "S999"), 0)

    def test_partial_delete_raises(self):
        class BrokenStore(DictStudentStore):
            def delete_records(self, student_id):
                return 0  # claims to delete but removes nothing

        store = BrokenStore({"S001": [{"student_id": "S001"}]})
        with self.assertRaises(RuntimeError):
            delete_student_records(store, "S001")


if __name__ == "__main__":
    unittest.main()
