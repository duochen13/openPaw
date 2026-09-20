import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('bearish_app', ROOT / 'app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ResearchTests(unittest.TestCase):
    def test_after_close_window_uses_next_benchmark_session(self):
        benchmark = {'2026-09-09': 100, '2026-09-10': 102, '2026-09-11': 103}
        asset = {'2026-09-09': 100, '2026-09-10': 95, '2026-09-11': 96}
        r = app.window_return(asset, benchmark, '2026-09-09', 'after_close', 1)
        self.assertEqual(r['baseline'], '2026-09-09')
        self.assertEqual(r['end'], '2026-09-10')
        self.assertAlmostEqual(r['excess_return'], -.07)

    def test_missing_asset_session_does_not_shift_event_window(self):
        benchmark = {'2026-09-09': 100, '2026-09-10': 102, '2026-09-11': 103}
        asset = {'2026-09-09': 100, '2026-09-11': 96}
        r = app.window_return(asset, benchmark, '2026-09-09', 'after_close', 1)
        self.assertEqual(r['status'], 'unavailable')

    def test_incomplete_horizon_is_not_partial_return(self):
        prices = {'2026-09-09': 100, '2026-09-10': 95}
        self.assertEqual(app.window_return(prices, prices, '2026-09-09', 'after_close', 5)['status'], 'unavailable')

    def test_unknown_publication_time_is_explicit(self):
        prices = {'2026-09-09': 100, '2026-09-10': 95}
        r = app.window_return(prices, prices, '2026-09-10', 'unknown', 1)
        self.assertIn('proxy', r['timing'])

    def test_reddit_cannot_establish_self_disclosed_position(self):
        data = app.load_research()
        data['positions'][0]['sources'] = ['burry-list']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'research.json'
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'primary'):
                app.load_research(path)

    def test_rss_and_atom_leads_stay_unreviewed(self):
        rss = b'<rss><channel><item><title>Short claim</title><link>https://example.com/a</link><pubDate>today</pubDate></item></channel></rss>'
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Discussion</title><link href="https://example.com/b"/><updated>today</updated></entry></feed>'
        for raw in [rss, atom]:
            row = app.parse_feed(raw, 'test')[0]
            self.assertEqual(row['status'], 'unreviewed_lead')
        bad = b'<rss><item><title>bad</title><link>javascript:alert(1)</link></item></rss>'
        self.assertEqual(app.parse_feed(bad, 'test'), [])

    def test_missing_db_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing.sqlite'
            self.assertEqual(app.market_data(app.load_research(), path)['status'], 'unavailable')
            self.assertFalse(path.exists())

    def test_checked_in_evidence_has_valid_sources(self):
        data = app.load_research()
        self.assertEqual(len(data['investors']), 3)
        self.assertFalse(any(p['status'] == 'self_disclosed' and p['investor'] == 'grantham' for p in data['positions']))


if __name__ == '__main__':
    unittest.main()
