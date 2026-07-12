#!/usr/bin/env python3
"""Attach a trip's map files to Notion as a "🗺️ Travel — <Destination> (Map)" page.

Reads the generated map files from disk and uploads their BYTES via the Notion File
Upload API (no hand-transcription of file content), then creates a page that holds
both files as downloadable blocks plus a how-to note and an optional link to the
places database.

Why this instead of the MCP `notion-create-attachment` tool: that tool takes inline
`content` (the caller must emit the whole file as text). For a ~30 KB HTML map that is
token-heavy and drift-prone. Here the bytes go straight from disk.

Setup (one time):
  1. Create an internal integration: https://www.notion.so/my-integrations  (copy its secret).
  2. Share the PARENT page with that integration (page ••• menu -> Connections -> add it).
  3. export NOTION_TOKEN=ntn_xxx

Usage:
  NOTION_TOKEN=ntn_xxx python3 upload_to_notion.py \
      --slug sunshine_coast_bc --dest "Sunshine Coast BC" \
      --parent-page <PARENT_PAGE_ID> [--db-url https://notion.so/...]

Prints the created page URL. Files under 20 MB use a single-part upload.
"""
import os, sys, json, argparse, urllib.request, urllib.error

API = "https://api.notion.com/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
MAPS_DIR = os.path.join(os.path.dirname(HERE), "data", "maps")
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2022-06-28")

# Extension -> (upload filename content_type). KML falls back to XML which Notion accepts.
MIME = {".html": "text/html", ".kml": "application/vnd.google-earth.kml+xml"}


def _token():
    t = os.environ.get("NOTION_TOKEN", "").strip()
    if not t:
        sys.exit("ERROR: set NOTION_TOKEN (create an internal integration at "
                 "https://www.notion.so/my-integrations and share the parent page with it).")
    return t


def _req(method, url, headers, data=None):
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise SystemExit("Notion API {} {}\n  {}\n  {}".format(e.code, url, method, body))


def _json_headers(tok, ct="application/json"):
    h = {"Authorization": "Bearer " + tok, "Notion-Version": NOTION_VERSION}
    if ct:
        h["Content-Type"] = ct
    return h


def upload_file(tok, path):
    """Create a single-part file upload, send the bytes, return the file_upload id."""
    fname = os.path.basename(path)
    mime = MIME.get(os.path.splitext(fname)[1].lower(), "application/octet-stream")
    with open(path, "rb") as f:
        raw = f.read()
    # 1) create the upload object
    created = _req("POST", API + "/file_uploads", _json_headers(tok),
                   json.dumps({"filename": fname, "content_type": mime}).encode())
    up_id = created["id"]
    send_url = created.get("upload_url") or (API + "/file_uploads/" + up_id + "/send")
    # 2) send the bytes as multipart/form-data
    boundary = "----travelAssistantBoundaryZ9x8"
    body = (
        ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
         "Content-Type: %s\r\n\r\n" % (boundary, fname, mime)).encode()
        + raw + ("\r\n--%s--\r\n" % boundary).encode()
    )
    sent = _req("POST", send_url,
                _json_headers(tok, "multipart/form-data; boundary=" + boundary), body)
    if sent.get("status") not in ("uploaded", None):
        raise SystemExit("upload not completed for {}: {}".format(fname, sent))
    print("uploaded {} ({} bytes) -> file_upload {}".format(fname, len(raw), up_id))
    return up_id, fname


def file_block(up_id, caption):
    return {"object": "block", "type": "file",
            "file": {"type": "file_upload", "file_upload": {"id": up_id},
                     "caption": [{"type": "text", "text": {"content": caption}}]}}


def para(rich):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich}}


def build_children(html_id, kml_id, db_url):
    kids = [para([{"type": "text", "text": {"content":
             "Interactive trip map. Download the HTML and open it in a browser for colored "
             "category pins, a category filter, the driving route with times, and place search. "
             "Or import the .kml into Google My Maps (Create map -> Import)."}}])]
    if html_id:
        kids.append(file_block(html_id, "Open in a browser for the interactive map"))
    if kml_id:
        kids.append(file_block(kml_id, "Import into Google My Maps"))
    if db_url:
        kids.append(para([{"type": "text",
                           "text": {"content": "Places database",
                                    "link": {"url": db_url}}}]))
    return kids


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--parent-page", required=True, help="Notion page id shared with the integration")
    ap.add_argument("--maps-dir", default=MAPS_DIR)
    ap.add_argument("--db-url", default=None)
    a = ap.parse_args(argv[1:])
    tok = _token()

    html = os.path.join(a.maps_dir, a.slug + "_map.html")
    kml = os.path.join(a.maps_dir, a.slug + ".kml")
    if not os.path.exists(html) and not os.path.exists(kml):
        sys.exit("ERROR: no map files for slug '{}' in {} (run build_map.py first).".format(a.slug, a.maps_dir))

    html_id = upload_file(tok, html)[0] if os.path.exists(html) else None
    kml_id = upload_file(tok, kml)[0] if os.path.exists(kml) else None

    page = _req("POST", API + "/pages", _json_headers(tok), json.dumps({
        "parent": {"page_id": a.parent_page},
        "icon": {"type": "emoji", "emoji": "🗺️"},
        "properties": {"title": {"title": [{"type": "text",
                       "text": {"content": "Travel — {} (Map)".format(a.dest)}}]}},
        "children": build_children(html_id, kml_id, a.db_url),
    }).encode())
    print("map page -> " + page.get("url", "(no url)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
