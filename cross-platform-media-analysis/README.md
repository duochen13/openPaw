# Cross-platform media analysis

Compare how public comment communities interpret the same media, starting with Jeremy Grantham's interview on The Diary Of A CEO.

- [Latest visual report: sailing](index.html) — open directly in a browser; works offline
- [Sailing case: report, data and coding](cases/sailing/)
- [Previous visual report: Grantham](reports/grantham-comparison.html)
- [First comparison](reports/grantham-comparison.md)
- [Coding framework](CODEBOOK.md)
- [Collected evidence](data/)
- [Selected annotated examples](data/annotated-examples.csv)

The Grantham pilot is an exploratory reading, not a representative audience survey. Bilibili access was limited to three top-level threads. YouTube includes multiple languages; platform and language are not nationality labels.

Collection: September 16, 2026, Vancouver time / September 17 UTC. Original comment text and source IDs are retained for checking interpretations. Usernames and profile information are omitted from the normalized datasets; source links still identify public comments.

`collect_youtube.py` is a bounded collection helper using YouTube's undocumented public web continuation endpoint. It needs previously downloaded watch HTML and an initial comments response; its usage is in the file. Temporary session context is not stored in this project. It is not yet a general collector for arbitrary video pairs.

For a stronger second pass, obtain the remaining Bilibili comments through a permitted export or a user-controlled logged-in browser, preserve thread structure, and compare matching publication windows and sort modes. Do not substitute comments from another reupload.

Reports use simple tables and diagrams with source-linked examples. The sailing case adds manually coded topic and language counts. Keep the project folder together for linked reports and downloads; each HTML report can also be read offline on its own.

## Run / rebuild reports

The current entry point shows the sailing case (YouTube `zxhsbfEgRiU`, Bilibili `BV1zYSvBHE3U`). Its raw normalized data, explicit manual coding, and generated HTML are isolated in `cases/sailing/`. The original Grantham data remain in `data/`.

Run `python3 cross-platform-media-analysis/build_html.py` to rebuild the current sailing report; use `--case grantham` to restore the Grantham report at the workspace entry point. For sailing topic-code edits, first run `python3 cross-platform-media-analysis/cases/sailing/code_sample.py`. The code assignments are case-specific, not an automatic sentiment classifier.
