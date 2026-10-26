# community-discussion-analysis — Makefile shortcuts for the collection
# commands documented in SKILL.md (Step 2 — this project's doc of record;
# it has no README). The raw commands in SKILL.md stay canonical; every
# target below wraps one of them and adds no behavior of its own.
#
# Targets assume cwd = community-discussion-analysis/. From the repo
# root:  make -C community-discussion-analysis <target>
#
# The rest of the skill workflow (scope, identify players, merge,
# analyze via subagents, report) is agent work, not shell commands, and
# is deliberately not wrapped here.

PYTHON ?= python3
DOMAIN ?=
QUERIES ?=
CONFIG ?=

.DEFAULT_GOAL := help

.PHONY: help collect-hn collect-reddit

help:
	@echo "community-discussion-analysis — make targets (each wraps the SKILL.md command shown):"
	@echo "  make collect-hn     $(PYTHON) scripts/collect_hn.py --domain DOMAIN --queries \"term1,term2,...\""
	@echo "                      [usage: make collect-hn DOMAIN=ai_wearables QUERIES=\"term1,term2,term3\" — 8-12 short focused queries]"
	@echo "  make collect-reddit $(PYTHON) scripts/collect_reddit.py --config CONFIG"
	@echo "                      [usage: make collect-reddit CONFIG=/tmp/reddit_<slug>.json — write the config first;"
	@echo "                       schema is at the top of scripts/collect_reddit.py; needs the gstack browse"
	@echo "                       headless browser against old.reddit.com]"
	@echo "  Both write into data/raw/ (override the base dir with the MR_DATA_RAW env var)."

collect-hn:
	@test -n "$(DOMAIN)" || { echo "Usage: make collect-hn DOMAIN=<slug> QUERIES=\"term1,term2,...\""; exit 1; }
	$(PYTHON) scripts/collect_hn.py --domain $(DOMAIN) --queries "$(QUERIES)"

collect-reddit:
	@test -n "$(CONFIG)" || { echo "Usage: make collect-reddit CONFIG=/tmp/reddit_<slug>.json (write the config first; schema at the top of scripts/collect_reddit.py)"; exit 1; }
	$(PYTHON) scripts/collect_reddit.py --config $(CONFIG)
