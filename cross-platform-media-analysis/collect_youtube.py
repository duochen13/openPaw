"""Collect bounded public top/newest samples; requires curl, no login or packages.

Usage: python3 collect_youtube.py WATCH_HTML FIRST_COMMENTS_JSON OUTPUT_DIR
Inputs are saved public YouTube watch HTML and initial /youtubei/v1/next response.
This is a research helper using an undocumented endpoint, not a stable API.
"""
import json
import pathlib
import subprocess
import sys


def nodes(value, key):
    if isinstance(value, dict):
        if key in value:
            yield value[key]
        for child in value.values():
            yield from nodes(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child, key)


def next_token(data):
    for action in data.get('onResponseReceivedEndpoints', []):
        for command in action.values():
            if not isinstance(command, dict):
                continue
            for item in command.get('continuationItems', []):
                renderer = item.get('continuationItemRenderer', {})
                token = renderer.get('continuationEndpoint', {}).get('continuationCommand', {}).get('token')
                if token:
                    return token


def collect(html_path, first_path, output):
    output.mkdir(parents=True, exist_ok=True)
    html = html_path.read_text()
    player = json.JSONDecoder().raw_decode(html.split('var ytInitialPlayerResponse = ', 1)[1])[0]
    video_id = player['videoDetails']['videoId']
    context = json.JSONDecoder().raw_decode(html.split('"INNERTUBE_CONTEXT":', 1)[1])[0]
    client = {k: v for k, v in context['client'].items()
              if k in ['clientName', 'clientVersion', 'hl', 'gl', 'visitorData']}
    first = json.loads(first_path.read_text())
    menu = next(nodes(first, 'sortFilterSubMenuRenderer'))['subMenuItems']
    newest = next(x for x in menu if x['title'] == 'Newest')['serviceEndpoint']['continuationCommand']['token']
    rows = []
    for sort in ['top', 'newest']:
        data = first if sort == 'top' else None
        token = newest if sort == 'newest' else None
        seen = set()
        for page in range(1, 6):
            if data is None:
                body = json.dumps({'context': {'client': client}, 'continuation': token})
                result = subprocess.run(['curl', '-fL', '-sS', '--max-time', '30',
                    'https://www.youtube.com/youtubei/v1/next?prettyPrint=false',
                    '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                    input=body, text=True, capture_output=True, check=True)
                data = json.loads(result.stdout)
            count = 0
            for entity in nodes(data, 'commentEntityPayload'):
                props = entity['properties']
                cid = props['commentId']
                if cid in seen:
                    continue
                seen.add(cid)
                rows.append({'platform': 'youtube', 'id': cid, 'sort': sort, 'page': page,
                    'rank': len(seen), 'text': props['content']['content'],
                    'published_label': props.get('publishedTime'),
                    'reply_level': props.get('replyLevel'),
                    'creator': entity.get('author', {}).get('isCreator', False),
                    'likes_display': entity.get('toolbar', {}).get('likeCountNotliked', ''),
                    'replies_display': entity.get('toolbar', {}).get('replyCount', ''),
                    'url': 'https://www.youtube.com/watch?v=' + video_id + '&lc=' + cid})
                count += 1
            print(sort, page, count, flush=True)
            token = next_token(data)
            data = None
            if not token:
                break
    (output / 'youtube-comments.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    collect(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))
