#!/usr/bin/env python3
"""Collect rednote (Xiaohongshu) posts via the gstack `browse` headless browser.

WHY THIS WAY (expected gotchas, mirror of collect_reddit.py):
  - Xiaohongshu has NO public content API and signs requests (x-s/x-t). Do not
    try the JSON endpoints — use the rendered web pages via `browse`.
  - Most content is login-walled. Import a logged-in xiaohongshu.com session with
    /setup-browser-cookies first. If not logged in, the search page renders a login
    modal and yields 0 note cards -> the caller (SKILL.md) falls back to WebSearch.
  - DOM selectors below are BEST-EFFORT and MUST be verified live (see Task 3).
"""
import subprocess, json, os, re, time, argparse, glob, urllib.parse
from datetime import datetime, timezone

def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    return s.strip("_")

def dedup_by_url(items):
    seen, out = set(), []
    for i in items:
        u = i.get("url")
        if u and u not in seen:
            seen.add(u); out.append(i)
    return out

def rank_by_likes(items):
    return sorted(items, key=lambda x: int(x.get("likes", 0) or 0), reverse=True)
