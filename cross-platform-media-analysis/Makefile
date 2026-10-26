# cross-platform-media-analysis — Makefile shortcuts for the commands
# documented in README.md ("Run / rebuild reports"). The raw commands
# stay canonical; every target below wraps one of them and adds no
# behavior of its own.
#
# The README documents its commands from the openPaw repo ROOT
# (python3 cross-platform-media-analysis/build_html.py). These targets
# run the same commands from inside the project directory — the scripts
# resolve their paths from their own location, so the results are
# identical. Targets assume cwd = cross-platform-media-analysis/.
# From the repo root:  make -C cross-platform-media-analysis <target>
#
# collect_youtube.py and the per-case build_report.py scripts are NOT
# targets: the README documents no invocation for them (out of scope in
# issue #181 until it does).

PYTHON ?= python3

.DEFAULT_GOAL := help

.PHONY: help build build-grantham code-sample

help:
	@echo "cross-platform-media-analysis — make targets (each wraps the README command shown):"
	@echo "  make build           $(PYTHON) build_html.py   [rebuild the current (sailing) report at the entry point]"
	@echo "  make build-grantham  $(PYTHON) build_html.py --case grantham   [restore the Grantham report at the entry point]"
	@echo "  make code-sample     $(PYTHON) cases/sailing/code_sample.py   [run before editing sailing topic codes]"

build:
	$(PYTHON) build_html.py

build-grantham:
	$(PYTHON) build_html.py --case grantham

code-sample:
	$(PYTHON) cases/sailing/code_sample.py
