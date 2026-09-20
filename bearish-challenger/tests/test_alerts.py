import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from alerts import qualifying, fingerprint, format_alert

TRACK=json.loads((ROOT/'track.json').read_text())
NOW=datetime(2026,9,19,18,tzinfo=timezone.utc)
BASE=dict(event_key='original-123',investor='burry',topic='ai_capex',signal_type='new_commentary',
          direction='bearish_confirmation',reviewed=True,recycled=False,substantive=True,
          language='English',holdings=['NVDA','MSFT'],what_happened='An investor warned about AI funding risk.',
          why_it_matters='Slower spending could pressure chip and cloud demand.',
          sources=[dict(title='Original statement',url='https://example.com/original')],
          occurred_at='2026-09-19T10:00:00Z',original_statement='A new statement about funding risk.',original_verified=True)

class AlertTests(unittest.TestCase):
    def test_fresh_reviewed_bearish_commentary_qualifies(self):
        self.assertEqual(len(qualifying([BASE],TRACK,now=NOW)),1)
        self.assertEqual(len(format_alert(BASE).splitlines()),3)

    def test_recycled_neutral_unverified_unrelated_are_silent(self):
        for key,value in [('recycled',True),('substantive',False),('reviewed',False),
                          ('direction','neutral'),('original_verified',False),('holdings',['FICO']),
                          ('topic','credit_scoring')]:
            with self.subTest(key=key):
                s=deepcopy(BASE);s[key]=value
                self.assertEqual(qualifying([s],TRACK,now=NOW),[])

    def test_age_uses_original_timestamp_and_rejects_future(self):
        for date in ['2026-09-01T10:00:00Z','2026-09-20T10:00:00Z','2026-09-19T10:00:00']:
            s=dict(BASE,occurred_at=date,reposted_at='2026-09-19T17:00:00Z')
            self.assertEqual(qualifying([s],TRACK,now=NOW),[])

    def test_syndication_dedup_and_delivered_suppression(self):
        repost=dict(BASE,event_key='different-repost-id')
        self.assertEqual(len(qualifying([BASE,repost],TRACK,now=NOW)),1)
        self.assertEqual(qualifying([BASE],TRACK,[fingerprint(BASE)],now=NOW),[])

    def test_same_day_market_move_requires_attribution(self):
        s=dict(BASE,signal_type='attributed_market_reaction')
        self.assertEqual(qualifying([s],TRACK,now=NOW),[])
        s.update(attribution_verified=True,attribution_detail='The linked report explicitly attributes the move to the statement.')
        self.assertEqual(len(qualifying([s],TRACK,now=NOW)),1)

if __name__=='__main__':unittest.main()
