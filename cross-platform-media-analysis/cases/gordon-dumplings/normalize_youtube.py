#!/usr/bin/env python3
"""Normalize YouTube comments collected via browser into project format.

Input: a JSON file with a list of {author, text, likes, posted, replies}
written from the browser task handoff.
Output: cases/gordon-dumplings/data/youtube-comments.json + youtube-metadata.json
"""
import json
import sys
from pathlib import Path

CASE = Path(__file__).resolve().parent
DATA = CASE / 'data'
VIDEO_ID = 'e2xNUZAjQr4'

def main(src):
    raw = json.loads(Path(src).read_text())
    meta = raw['metadata']
    comments = raw['comments']
    out = []
    for i, c in enumerate(comments, 1):
        out.append({
            'platform': 'youtube',
            'id': f'yt-gordon-{i:03d}',
            'sort': 'top',
            'page': (i - 1) // 20 + 1,
            'rank': i,
            'author': c.get('author', ''),
            'text': c['text'],
            'published_label': c.get('posted', ''),
            'reply_level': 0,
            'creator': False,
            'likes_display': str(c.get('likes', '')),
            'replies_display': str(c.get('replies', '')),
            'url': f'https://www.youtube.com/watch?v={VIDEO_ID}',
        })
    (DATA / 'youtube-comments.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2))
    (DATA / 'youtube-metadata.json').write_text(json.dumps({
        'videoId': VIDEO_ID,
        'title': meta.get('title'),
        'channel': meta.get('channel'),
        'viewCount': meta.get('views'),
        'likeCount': meta.get('likes'),
        'duration': meta.get('duration'),
        'uploadDate': meta.get('upload_date'),
        'description_snippet': meta.get('description', '')[:300],
        'collected_utc': meta.get('collected_utc'),
    }, ensure_ascii=False, indent=2))
    print(f'wrote {len(out)} youtube comments')

if __name__ == '__main__':
    main(sys.argv[1])
