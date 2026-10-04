#!/usr/bin/env python3
"""Build the Gordon dumplings comparison report (Bilibili vs YouTube)."""
import csv
import datetime
import html
import json
from pathlib import Path
from zoneinfo import ZoneInfo

CASE = Path(__file__).resolve().parent
PROJECT = CASE.parents[1]
DATA = CASE / 'data'
read = lambda n: json.loads((DATA / n).read_text())
esc = lambda s: html.escape(str(s), quote=True)

y = read('youtube-comments.json')
b = read('bilibili-comments.json')
stats = read('sample-statistics.json')
ym = read('youtube-metadata.json')
bm = read('bilibili-metadata.json')

yt_by_rank = {r['rank']: r for r in y}
b_by_id = {r['id']: r for r in b}
now = datetime.datetime.fromisoformat(max(ym['collected_utc'], bm['collected_utc']))
stamp = now.astimezone(ZoneInfo('America/Vancouver')).strftime('%B %d, %Y')

examples = []
def example(platform, key, topic, emotion, meaning, uncertainty):
    r = b_by_id[str(key)] if platform == 'bilibili' else yt_by_rank[key]
    src = 'Bilibili' if platform == 'bilibili' else 'YouTube'
    examples.append({'platform': r['platform'], 'id': r['id'], 'sample': src,
                     'topic': topic, 'expressed_emotion': emotion,
                     'english_paraphrase': meaning, 'uncertainty': uncertainty,
                     'url': r['url']})

# YouTube examples
example('youtube', 1, 'Humility', 'Admiration',
        'The top comment (104K likes): Gordon is the big dog in his own kitchen but becomes a respectful student in someone else\u2019s.',
        'Like count is engagement, not a vote on the claim.')
example('youtube', 3, 'Language as authenticity', 'Amusement / approval',
        'The dim sum is legit because the London chef does not speak English and answers in Cantonese.',
        'Treats language as an authenticity signal; not verified.')
example('youtube', 5, 'Unlowered standards', 'Approval',
        'Glad the head chef did not drop standards just because cameras were around.',
        '38K likes; endorsement visible, not universal.')
example('youtube', 19, 'Score discrepancy', 'Amusement',
        'Henry actually said 45 points; the translator generously rounded up to 5/10.',
        'Multiple commenters corroborate the 45/100 hearing; translation not independently verified.')
example('youtube', 21, 'Professional critique', 'Analytical',
        'Long technical comment: Cantonese cooking prizes subtlety; roast duck overwhelms shrimp/scallop; the garlic was overkill. It is all about balance.',
        'Self-presented expertise; the most-liked technical comment (9.1K).')
example('youtube', 15, 'Translation chain', 'Amusement',
        'Two translators: Cantonese to Mandarin, then Mandarin to English for Gordon. "This is gold."',
        'Describes the on-screen interpretation relay.')
example('youtube', 66, 'Mutual respect + identity', 'Pride',
        'Fair play to both sides; the chefs judge only the food. "Makes me proud to be Cantonese!"',
        'Self-identified Cantonese commenter on YouTube; identity is self-reported.')
example('youtube', 24, 'Chef appearance', 'Admiration (playful)',
        '"The young chef is so handsome." One of several appearance comments about Henry.',
        'Appearance remarks are a visible sub-thread, not the main discussion.')
# Bilibili examples
example('bilibili', '291284368945', 'Facial expressions', 'Amusement',
        'Root (17,778 likes): "I really can\u2019t hold it together\u2014those four people\u2019s expressions."',
        'The thread\u2019s amusement anchor; replies develop it into critique.')
example('bilibili', '293572481968', 'Saving face', 'Amusement / knowing',
        '"They already gave him face; the chefs at the back look pained (面露难色)."',
        'Reads politeness into expressions; interpretation, not fact.')
example('bilibili', '293411415664', 'Professional claim', 'Confident / casual',
        'Root (8,136 likes): "It\u2019s simple\u2014I\u2019m a cutting-board chef with 15 years." The thread becomes a 277-reply technique deep-dive.',
        'Credential is self-claimed; the thread treats it as authoritative.')
example('bilibili', '291138526641', 'Technique detail', 'Instructive',
        'Making shrimp-dumpling filling, opening and patting the skin are not simple home tasks; enormous effort hides behind one dumpling.',
        'Detailed craft knowledge shared as peer instruction.')
example('bilibili', '293637400496', 'Duck skin moment', 'Amusement',
        'When Gordon removed the roast-duck skin, the masters behind looked murderous (面露凶相).',
        'Specific video moment; humor from imagined reactions.')
example('bilibili', '293417952784', 'Gordon\u2019s character', 'Defensive / warm',
        'Root (7,929 likes): Gordon is actually decent\u2014respectful to serious chefs and generous with praise; his harsh TV persona comes from absurd contestants.',
        'Character defense; separates persona from person.')
example('bilibili', '291142993681', 'Hell\u2019s Kitchen mechanics', 'Knowing',
        'The sous-chefs set traps for trainees, which is why things are under/overcooked.',
        'Behind-the-scenes claim, unverified.')
example('bilibili', '291356942401', 'Apprentice standard', 'Wry',
        '"They gave him plenty of face. A normal apprentice with my Cantonese-training experience would have been scolded a dozen times over."',
        'Uses own training history to calibrate how polite the chefs were.')
example('bilibili', '293568724912', 'Chefs\u2019 looks', 'Playful',
        'The three masters at the back look like brothers.',
        '3,217 likes; light observation, cf. YouTube "handsome chef" comments.')

with (DATA / 'annotated-examples.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(examples[0]))
    w.writeheader(); w.writerows(examples)

manifest = {
    'collected_utc': now.isoformat(),
    'youtube': {'video_id': ym['videoId'], 'records': len(y),
                'unique_comments': 100, 'sort': 'top',
                'reply_threads_collected': False,
                'displayed_comments': ym.get('comments_shown', '5,867'),
                'complete_corpus_claim': False,
                'sample_limit': 'Top sort only, ~100 top-level comments via browser transcription.'},
    'bilibili': {'bvid': bm['bvid'], 'records': len(b), 'top_level': 3,
                 'replies': 406,
                 'uploader_comments': sum(r['creator'] for r in b),
                 'unique_author_keys': len({r['author_key'] for r in b}),
                 'displayed_comments': bm['stat']['reply'],
                 'complete_corpus_claim': False,
                 'access_limit': ('Hot endpoint exposed 3 roots. Retrieved all 406 replies '
                                  'reported across those roots.'),
                 'danmaku_collected': False},
    'classification': stats['method'],
    'selected_examples': len(examples),
    'pair_verification': ('Same program (The F Word) and premise: Gordon cooks Chinese food, '
                          'judged by Chinese chefs; 45/100 score and Henry Chow appear in both '
                          'discussions. YouTube clip is 4:12, Bilibili re-upload is 10:38; '
                          'exact edit equivalence unverified.'),
}
(DATA / 'collection-manifest.json').write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2))

bar_rows = ''.join(
    f'<div class="bar-row"><span>{esc(t["label"])}</span>'
    f'<div class="track"><div class="bar" style="width:{t["count"]}%;"></div></div>'
    f'<strong>{t["count"]}</strong><span>{t["percent"]:.1f}%</span></div>'
    for t in stats['primary_topics'])

evidence = ''.join(
    '<tr><td><a href="' + esc(r['url']) + '" target="_blank" rel="noopener noreferrer">'
    + esc(r['sample']) + ' \u2197</a></td><td>' + esc(r['topic']) + '<br><small>'
    + esc(r['expressed_emotion']) + '</small></td><td>' + esc(r['english_paraphrase'])
    + '</td><td>' + esc(r['uncertainty']) + '</td></tr>'
    for r in examples)

links = {}
for name, key in [('humility', 1), ('cantonese', 3), ('score45', 19), ('technique', 21)]:
    links[name] = yt_by_rank[key]['url']
for name, key in [('faces', '291284368945'), ('chef15', '293411415664')]:
    links[name] = b_by_id[str(key)]['url']

template = (CASE / 'template.html').read_text()
values = {'DATE': stamp,
          'BILI_VIEWS': f'{bm["stat"]["view"]:,}',
          'YT_VIEWS': ym['viewCount'],
          'TOPIC_BARS': bar_rows,
          'EVIDENCE': evidence,
          **{k.upper() + '_URL': esc(v) for k, v in links.items()}}
for k, v in values.items():
    template = template.replace('{{' + k + '}}', v)
assert '{{' not in template
(CASE / 'index.html').write_text(template)
print('Built gordon-dumplings/index.html')
print(f'{len(examples)} examples, manifest written')
