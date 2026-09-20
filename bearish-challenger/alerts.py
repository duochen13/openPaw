"""Reviewed bearish-confirmation alert gate. No message transport or scheduler."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Signal timestamps must include timezone')
    return dt.astimezone(timezone.utc)


def fingerprint(signal):
    # event_key identifies the original statement or distinct attributed reaction.
    # Keep it unchanged for syndicated stories/reposts of the same underlying event.
    return hashlib.sha256((signal['investor'] + '\n' + signal['event_key']).encode()).hexdigest()


def text_fingerprint(signal):
    text = re.sub(r'\W+', ' ', signal.get('original_statement', '').casefold()).strip()
    return hashlib.sha256((signal['investor'] + '\n' + text).encode()).hexdigest() if text else None


def qualifying(signals, track, delivered=(), now=None):
    now = now or datetime.now(timezone.utc)
    seen = set(delivered)
    accepted = []
    for signal in signals:
        if signal.get('reviewed') is not True or signal.get('direction') != track['direction']:
            continue
        if signal.get('investor') not in track['investors'] or signal.get('topic') not in track['topics']:
            continue
        if signal.get('signal_type') not in track['signals'] or signal.get('recycled') is not False:
            continue
        if signal.get('substantive') is not True or not signal.get('event_key'):
            continue
        if signal.get('language') != 'English':
            continue
        holdings = signal.get('holdings', [])
        if not holdings or any(h not in track['holdings'] for h in holdings):
            continue
        if not signal.get('what_happened') or not signal.get('why_it_matters'):
            continue
        if len(signal['what_happened'].split()) > 55 or len(signal['why_it_matters'].split()) > 40:
            continue
        sources = signal.get('sources', [])
        if not sources or any(urlparse(s.get('url', '')).scheme != 'https' or not s.get('title') for s in sources):
            continue
        try:
            age = (now - timestamp(signal['occurred_at'])).total_seconds() / 3600
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= age <= track['max_age_hours']:
            continue
        if signal['signal_type'] == 'new_commentary':
            if not signal.get('original_statement') or signal.get('original_verified') is not True:
                continue
        elif signal.get('attribution_verified') is not True or not signal.get('attribution_detail'):
            continue
        key, text_key = fingerprint(signal), text_fingerprint(signal)
        if key in seen or (text_key and text_key in seen):
            continue
        seen.add(key)
        if text_key:
            seen.add(text_key)
        accepted.append(signal)
    return accepted


def format_alert(signal):
    source = signal['sources'][0]
    return (f"{signal['what_happened']}\n"
            f"Source: [{source['title']}]({source['url']})\n"
            f"Why it matters ({', '.join(signal['holdings'])}): {signal['why_it_matters']}")
