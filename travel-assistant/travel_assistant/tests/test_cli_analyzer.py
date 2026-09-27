"""CLI behavior for the missing-analyzer case (issue #133).

- main() without analyzer/--from-analysis exits 2 with a clean, actionable
  message (no traceback) and names the saved collection output.
- --no-analyze stops after collection and prints the raw path.
- Zero-post collection emits a visible WARNING (not an early exit: per
  SKILL.md Step 2 the analyzer is expected to fall back to web search).
- stages/analyze.analyze_raw still raises NotImplementedError (library
  behavior unchanged; only the CLI layer translates it).
"""
import contextlib
import io
import json
import os
import tempfile

os.environ["TA_OFFLINE"] = "1"

from travel_assistant import paths
from travel_assistant import collectors as collectors_mod
from travel_assistant import research as research_mod
from travel_assistant.research import main as cli_main
from travel_assistant.research import research as research_fn
from travel_assistant.stages import analyze as st_analyze
from travel_assistant import store as store_mod


def _fresh_env():
    d = tempfile.mkdtemp(prefix="ta_cli133_")
    old = os.environ.get("TA_DATA_ROOT")
    os.environ["TA_DATA_ROOT"] = d
    return d, old


def _restore_env(old):
    if old is None:
        os.environ.pop("TA_DATA_ROOT", None)
    else:
        os.environ["TA_DATA_ROOT"] = old


def _write_raw(path, destination, n):
    raw = {"destination": destination, "slug": "x", "source": "rednote",
           "timestamp": "2026-01-01T00:00:00",
           "discussions": [{"id": f"p{i}", "text": "t"} for i in range(n)]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    return path


class _StubCollector:
    """Collector class stub: writes a raw file with n_discussions posts."""
    n_discussions = 0
    out_path = None

    def __call__(self, destination, queries, n_per_query=6):
        return _write_raw(self.out_path, destination, self.n_discussions)


def _patch_collector(n_discussions, out_path):
    real = collectors_mod.collector_for

    class Stub(_StubCollector):
        pass
    Stub.n_discussions = n_discussions
    Stub.out_path = out_path
    collectors_mod.collector_for = lambda name: Stub
    return real, Stub


def _unpatch_collector(real):
    collectors_mod.collector_for = real


def test_cli_no_analyzer_exits_cleanly():
    d, old = _fresh_env()
    raw_path = os.path.join(d, "raw_empty.json")
    real, _stub = _patch_collector(0, raw_path)
    try:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli_main(["--destination", "Nowhere",
                           "--queries", "nothing here"])
        assert rc == 2, f"expected exit 2, got {rc}"
        msg = err.getvalue()
        assert "Traceback" not in msg, "must not dump a traceback"
        assert "NotImplementedError" not in msg
        assert "SKILL.md" in msg
        assert "--from-analysis" in msg
        assert raw_path in msg, "must name the saved collection output"
        # the failed run is recorded with its raw_path
        st = store_mod.RunStore()
        try:
            latest = st.latest_run()
            assert latest["status"] == "failed"
            assert latest["raw_path"] == raw_path
        finally:
            st.close()
    finally:
        _unpatch_collector(real)
        _restore_env(old)


def test_cli_no_analyze_flag():
    d, old = _fresh_env()
    raw_path = os.path.join(d, "raw_two.json")
    real, _stub = _patch_collector(2, raw_path)
    try:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli_main(["--destination", "Somewhere",
                           "--queries", "food", "--no-analyze"])
        assert rc == 0, f"expected exit 0, got {rc}: {err.getvalue()}"
        text = out.getvalue()
        assert "collection only (--no-analyze)" in text
        assert raw_path in text
        st = store_mod.RunStore()
        try:
            latest = st.latest_run()
            assert latest["status"] == "complete"
            assert latest["n_places"] == 0
            assert latest["raw_path"] == raw_path
        finally:
            st.close()
    finally:
        _unpatch_collector(real)
        _restore_env(old)


def test_zero_post_collection_warns():
    d, old = _fresh_env()
    raw_path = os.path.join(d, "raw_zero.json")
    real, stub = _patch_collector(0, raw_path)
    try:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rec = research_fn(destination="Nowhere", queries=["q"],
                              collector=stub(),
                              no_analyze=True)
        assert rec["status"] == "complete"
        assert rec["raw_path"] == raw_path
        assert "WARNING" in err.getvalue()
        assert "0 posts" in err.getvalue()
    finally:
        _unpatch_collector(real)
        _restore_env(old)


def test_analyze_raw_still_raises_not_implemented():
    try:
        st_analyze.analyze_raw({"discussions": []}, destination="X", vibe="x")
    except NotImplementedError as e:
        assert "No analyzer configured" in str(e)
    else:
        raise AssertionError("analyze_raw must keep raising NotImplementedError")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all passed")
