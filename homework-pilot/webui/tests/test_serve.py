"""Request-level tests for the local student MVP server (issue #179).

Each test runs a real server on an ephemeral port (port 0) against a
throwaway data dir, and drives it with http.client -- the same bodies
a browser would send. The kit papers are the upload fixtures: the
verdicts on the results page must equal the grading pipeline's own
output for that paper, confirmations must survive a store reload and
a full server restart, and the privacy guard must refuse name-carrying
uploads.
"""

from __future__ import annotations

import http.client
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path

from ..serve import PaperStore, make_server

KIT = Path(__file__).resolve().parents[2] / "pilot-kit"

BOUNDARY = "----webui-serve-test-boundary"


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    chunks = []
    for name, value in fields.items():
        chunks.append(
            f"--{BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    for name, (filename, content) in files.items():
        chunks.append(
            f"--{BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n".encode("utf-8")
            + content
            + b"\r\n"
        )
    chunks.append(f"--{BOUNDARY}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={BOUNDARY}"


def _verdict_on_page(page: str, item_key: str) -> str | None:
    match = re.search(
        rf'data-item-key="{re.escape(item_key)}".*?'
        r'<span class="pill [^"]+">([^<]+)</span>',
        page,
        re.S,
    )
    return match.group(1) if match else None


class ServeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name) / "data"
        self.server = make_server(
            "127.0.0.1", 0, data_dir=self.data_dir, kit_dir=KIT
        )
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)
        self._tmp.cleanup()

    # -- HTTP helpers --------------------------------------------------
    def request(self, method: str, path: str, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            data = response.read()
            return response.status, dict(response.getheaders()), data
        finally:
            conn.close()

    def get(self, path: str) -> tuple[int, str]:
        status, _headers, data = self.request("GET", path)
        return status, data.decode("utf-8")

    def upload(self, student_id: str, content: bytes, extra_fields=None):
        fields = {"student_id": student_id}
        fields.update(extra_fields or {})
        body, content_type = _multipart(
            fields, {"file": ("paper.pdf", content)}
        )
        return self.request(
            "POST", "/papers", body=body, headers={"Content-Type": content_type}
        )

    def upload_kit_paper(self, student_id: str) -> str:
        """Upload the kit's own PDF for a student; return the paper ID."""
        content = (KIT / "papers" / student_id / "paper.pdf").read_bytes()
        status, headers, _data = self.upload(student_id, content)
        self.assertEqual(status, 303)
        location = headers["Location"]
        self.assertTrue(location.startswith("/papers/"))
        return location.rsplit("/", 1)[1]

    def confirm(self, paper_id: str, item_key: str, **fields):
        from urllib.parse import urlencode

        body = urlencode(
            {"paper_id": paper_id, "item_key": item_key, **fields}
        ).encode("utf-8")
        return self.request(
            "POST",
            "/confirm",
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )


class TestPapersAndResults(ServeTestCase):
    def test_papers_page_empty_store(self):
        status, page = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('enctype="multipart/form-data"', page)
        self.assertIn("还没有上传的试卷", page)

    def test_upload_kit_paper_results_match_pipeline(self):
        from grading.pipeline import grade_kit_paper

        paper_id = self.upload_kit_paper("S-001")
        self.assertEqual(paper_id, "S-001-01")
        status, page = self.get(f"/papers/{paper_id}")
        self.assertEqual(status, 200)
        expected = grade_kit_paper(KIT, "S-001")
        self.assertEqual(len(expected.items), 18)
        for item in expected.items:
            self.assertEqual(
                _verdict_on_page(page, item.item_key),
                item.verdict,
                f"{item.item_key} verdict on results page",
            )
        # Summary chips + the honest provenance banner (bytes matched).
        self.assertIn("对 17", page)
        self.assertIn("待确认 1", page)
        self.assertIn("与试卷包原件一致", page)
        # The upload itself was stored under the data dir.
        self.assertTrue((self.data_dir / "uploads" / "S-001-01.pdf").exists())

    def test_upload_tampered_pdf_grades_via_kit_with_banner(self):
        content = (KIT / "papers" / "S-002" / "paper.pdf").read_bytes() + b"\n%tampered"
        status, headers, _ = self.upload("S-002", content)
        self.assertEqual(status, 303)
        _status, page = self.get(headers["Location"])
        self.assertIn("与试卷包原件不一致", page)
        self.assertIn("测试替身后端", page)

    def test_unknown_student_upload_stored_unrecognized(self):
        status, headers, _ = self.upload("S-999", b"%PDF-1.4 fake scan")
        self.assertEqual(status, 303)
        status, page = self.get(headers["Location"])
        self.assertEqual(status, 200)
        self.assertIn("未识别", page)
        self.assertNotIn("data-item-key", page)  # nothing judged, nothing faked
        _status, listing = self.get("/")
        self.assertIn("S-999-01", listing)
        self.assertIn("未识别", listing)

    def test_unknown_paper_404(self):
        status, _page = self.get("/papers/S-001-99")
        self.assertEqual(status, 404)


class TestUploadValidation(ServeTestCase):
    def test_name_field_rejected_by_privacy_guard(self):
        content = (KIT / "papers" / "S-001" / "paper.pdf").read_bytes()
        status, _headers, data = self.upload(
            "S-001", content, extra_fields={"student_name": "张伟"}
        )
        self.assertEqual(status, 400)
        self.assertIn("ID-only", data.decode("utf-8"))
        # Nothing was stored.
        _status, page = self.get("/")
        self.assertIn("还没有上传的试卷", page)

    def test_name_as_student_id_rejected(self):
        status, _headers, _data = self.upload("张伟", b"%PDF-1.4 x")
        self.assertEqual(status, 400)

    def test_non_pdf_rejected(self):
        status, _headers, _data = self.upload("S-001", b"not a pdf at all")
        self.assertEqual(status, 400)


class TestConfirmFlow(ServeTestCase):
    def test_accept_proposal_persists_and_exports(self):
        paper_id = self.upload_kit_paper("S-005")
        status, queue_page = self.get("/confirm")
        self.assertEqual(status, 200)
        self.assertIn('data-item-key="Q11#c"', queue_page)
        self.assertIn("确认系统倾向（错）", queue_page)

        status, _headers, _data = self.confirm(paper_id, "Q11#c", action="accept")
        self.assertEqual(status, 303)

        # Persisted at the store level (fresh store, same directory)...
        store = PaperStore(self.data_dir)
        loaded = store.load(paper_id)
        self.assertIsNotNone(loaded)
        paper, _meta = loaded
        item = next(i for i in paper.items if i.item_key == "Q11#c")
        self.assertTrue(item.confirmed)
        self.assertEqual(item.verdict, "错")
        self.assertEqual(item.source, "学生确认")
        self.assertEqual(item.system_verdict, "待确认")
        self.assertEqual(item.system_proposed_verdict, "错")

        # ...and in the exported JSONL.
        status, _headers, data = self.request("GET", "/export")
        self.assertEqual(status, 200)
        records = [json.loads(line) for line in data.decode("utf-8").splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["item_key"], "Q11#c")
        self.assertEqual(records[0]["student_id"], "S-005")
        self.assertEqual(records[0]["verdict"], "错")

    def test_confirmation_survives_server_restart(self):
        paper_id = self.upload_kit_paper("S-005")
        status, _h, _d = self.confirm(paper_id, "Q11#c", action="accept")
        self.assertEqual(status, 303)
        # A brand-new server over the same data dir sees the decision.
        other = make_server("127.0.0.1", 0, data_dir=self.data_dir, kit_dir=KIT)
        thread = threading.Thread(target=other.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection(
                "127.0.0.1", other.server_address[1], timeout=10
            )
            conn.request("GET", f"/papers/{paper_id}")
            response = conn.getresponse()
            page = response.read().decode("utf-8")
            conn.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(_verdict_on_page(page, "Q11#c"), "错")
            self.assertIn("来源：学生确认", page)
        finally:
            other.shutdown()
            other.server_close()
            thread.join(timeout=5)

    def test_manual_verdict_for_no_lean_item(self):
        paper_id = self.upload_kit_paper("S-001")
        # Q10 has no system proposal: wrong without a reference fails...
        status, _h, _d = self.confirm(paper_id, "Q10", action="wrong")
        self.assertEqual(status, 400)
        # ...and deciding it manually, with a reference answer, works.
        status, _h, _d = self.confirm(
            paper_id,
            "Q10",
            action="wrong",
            reference_answer="（1）1.2×10⁷ J；（2）4×10⁴ W",
        )
        self.assertEqual(status, 303)
        store = PaperStore(self.data_dir)
        paper, _meta = store.load(paper_id)
        item = next(i for i in paper.items if i.item_key == "Q10")
        self.assertTrue(item.confirmed)
        self.assertEqual(item.verdict, "错")
        self.assertEqual(item.system_proposed_verdict, "")

    def test_transcription_fix_keeps_verdict(self):
        paper_id = self.upload_kit_paper("S-005")
        # Q3#a: decided 对 by red mark, but its read is unreliable --
        # it sits in the queue for its transcription only.
        status, _h, _d = self.confirm(
            paper_id,
            "Q3#a",
            action="fix",
            corrected_answer="动能转化为电能",
        )
        self.assertEqual(status, 303)
        store = PaperStore(self.data_dir)
        paper, _meta = store.load(paper_id)
        item = next(i for i in paper.items if i.item_key == "Q3#a")
        self.assertEqual(item.student_answer, "动能转化为电能")
        self.assertEqual(item.verdict, "对")  # the verdict never moved
        self.assertFalse(item.needs_transcription_confirmation)
        self.assertTrue(item.confirmed)

    def test_confirm_item_not_in_queue_rejected(self):
        paper_id = self.upload_kit_paper("S-001")
        status, _h, _d = self.confirm(paper_id, "Q1", action="right")
        self.assertEqual(status, 400)

    def test_export_empty_store(self):
        status, _headers, data = self.request("GET", "/export")
        self.assertEqual(status, 200)
        self.assertEqual(data, b"")


if __name__ == "__main__":
    unittest.main()
