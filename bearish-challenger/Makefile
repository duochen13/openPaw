# bearish-challenger — Makefile shortcuts for the commands documented in
# README.md. The raw commands in the README stay canonical; every target
# below wraps one of them and adds no behavior of its own.
#
# The README documents its commands from the openPaw repo ROOT
# (./bearish-challenger/run build, node bearish-challenger/tests/...,
# portfolio-analysis/.venv/bin/python -m unittest discover
# -s bearish-challenger/tests). These targets run the same commands from
# inside bearish-challenger/ — the ./run launcher and the test files
# resolve their own paths, and the root-relative paths below are the
# project-relative equivalents. Targets assume cwd = bearish-challenger/.
# From the repo root:  make -C bearish-challenger <target>
#
# Standard library only; the launcher reuses the portfolio-analysis
# interpreter if present, otherwise Python 3.10+.

DB ?=
VENV_PY ?= ../portfolio-analysis/.venv/bin/python

.DEFAULT_GOAL := help

.PHONY: help build open report alerts collect test check-dashboard

help:
	@echo "bearish-challenger — make targets (each wraps the README command shown):"
	@echo "  make build            ./run build [--db DB]   [reads ../portfolio-analysis/data/prices.sqlite read-only]"
	@echo "  make open             open index.html   [macOS]"
	@echo "  make report           ./run report"
	@echo "  make alerts           ./run alerts   [preview reviewed alerts; prints nothing when none qualify; does not send]"
	@echo "  make collect          ./run collect   [hits the network: public RSS/Atom + Reddit search metadata]"
	@echo "  make test             $(VENV_PY) -m unittest discover -s tests   [offline; VENV_PY=python3 overrides the interpreter]"
	@echo "  make check-dashboard  node tests/check_dashboard.cjs   [needs local Playwright + Chrome]"

build:
	./run build $(if $(DB),--db $(DB))

open:
	open index.html

report:
	./run report

alerts:
	./run alerts

collect:
	./run collect

test:
	$(VENV_PY) -m unittest discover -s tests

check-dashboard:
	node tests/check_dashboard.cjs
