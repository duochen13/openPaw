#!/usr/bin/env python3
"""Explicit analyst coding of 100 YouTube top-level comments, one primary topic each.

Assignments recorded by collection rank for auditability. Categories describe
the primary topic, not sentiment. See coding-notes.md for rules.
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent))
from csv_sanitize import sanitize_csv_row

rows = json.loads((ROOT / 'data/youtube-comments.json').read_text())

TOPICS = {
    'humility': 'Gordon\u2019s humility: being a student, taking criticism, lifelong learning',
    'chef_standards': 'Head chef not lowering standards / not intimidated by celebrity',
    'score': 'The 45/100 vs 5/10 translation discrepancy',
    'language': 'Cantonese / translators / language observations and jokes',
    'professional': 'Culinary technique: dim sum craft, balance, training years',
    'chef_persona': 'Head chef demeanor, calm authority, appearance',
    'mutual_respect': 'Respect on both sides explicitly',
    'other': 'Meta, jokes, or references not fitting above',
}

# rank -> category (ranks are 1-based collection order)
ASSIGN = {
    1: 'humility', 2: 'chef_persona', 3: 'language', 4: 'chef_standards',
    5: 'chef_standards', 6: 'score', 7: 'humility', 8: 'other',
    9: 'humility', 10: 'chef_standards', 11: 'humility', 12: 'humility',
    13: 'mutual_respect', 14: 'humility', 15: 'language', 16: 'chef_persona',
    17: 'humility', 18: 'chef_standards', 19: 'score', 20: 'chef_persona',
    21: 'professional', 22: 'humility', 23: 'mutual_respect', 24: 'chef_persona',
    25: 'chef_persona', 26: 'humility', 27: 'chef_persona', 28: 'chef_persona',
    29: 'other', 30: 'humility', 31: 'score', 32: 'humility',
    33: 'chef_standards', 34: 'humility', 35: 'mutual_respect', 36: 'score',
    37: 'score', 38: 'score', 39: 'chef_persona', 40: 'chef_persona',
    41: 'language', 42: 'professional', 43: 'professional', 44: 'score',
    45: 'humility', 46: 'chef_standards', 47: 'other', 48: 'humility',
    49: 'language', 50: 'humility', 51: 'professional', 52: 'humility',
    53: 'humility', 54: 'humility', 55: 'humility', 56: 'chef_persona',
    57: 'score', 58: 'chef_persona', 59: 'chef_persona', 60: 'humility',
    61: 'humility', 62: 'chef_persona', 63: 'chef_persona', 64: 'score',
    65: 'humility', 66: 'mutual_respect', 67: 'humility', 68: 'chef_persona',
    69: 'humility', 70: 'chef_standards', 71: 'professional', 72: 'score',
    73: 'humility', 74: 'chef_persona', 75: 'humility', 76: 'humility',
    77: 'mutual_respect', 78: 'chef_standards', 79: 'humility', 80: 'chef_persona',
    81: 'language', 82: 'mutual_respect', 83: 'humility', 84: 'humility',
    85: 'humility', 86: 'professional', 87: 'chef_persona', 88: 'humility',
    89: 'other', 90: 'chef_persona', 91: 'humility', 92: 'chef_persona',
    93: 'professional', 94: 'humility', 95: 'humility', 96: 'chef_persona',
    97: 'humility', 98: 'chef_persona', 99: 'score', 100: 'chef_standards',
}
assert set(ASSIGN) == set(range(1, 101)), 'ranks 1-100 must all be assigned'
assert len(rows) == 100

coded = []
for r in rows:
    cat = ASSIGN[r['rank']]
    coded.append({**r, 'primary_topic': cat,
                  'primary_topic_label': TOPICS[cat],
                  'language': 'English'})

counts = Counter(c['primary_topic'] for c in coded)
stats = {
    'method': ('Single analyst manual primary-topic classification; one category per comment; '
               'no independent second coder. Counts are comment frequencies in the retrieved '
               'sample, not population estimates.'),
    'denominator': 100,
    'primary_topics': [
        {'key': k, 'label': TOPICS[k], 'count': counts[k],
         'percent': round(counts[k] / 100 * 100, 1)}
        for k in sorted(counts, key=lambda k: -counts[k])
    ],
    'language': {'English': 100},
}
(DATA := ROOT / 'data')
(DATA / 'youtube-coded.json').write_text(
    json.dumps(coded, ensure_ascii=False, indent=2))
(DATA / 'sample-statistics.json').write_text(
    json.dumps(stats, ensure_ascii=False, indent=2))

with (DATA / 'youtube-coded.csv').open('w', newline='') as f:
    fields = ['rank', 'author', 'primary_topic', 'primary_topic_label',
              'language', 'likes_display', 'published_label', 'text', 'url']
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for c in coded:
        w.writerow(sanitize_csv_row({k: c.get(k, '') for k in fields}))

print('coded 100 comments')
for t in stats['primary_topics']:
    print(f"  {t['key']:15s} {t['count']:3d}  {t['percent']:.1f}%")
