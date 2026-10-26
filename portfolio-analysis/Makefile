# portfolio-analysis — Makefile shortcuts for the commands documented in
# README.md. The raw commands in the README stay canonical; every target
# below wraps one of them and adds no behavior of its own.
#
# Targets assume cwd = portfolio-analysis/. From the repo root:
#   make -C portfolio-analysis <target>
#
# Setup and tests run from this directory (README "Setup"); the CLI
# targets wrap the ./run launcher, which is how the README invokes them
# from the repo root (./portfolio-analysis/run ...). The launcher resolves
# its own paths, so the commands are identical from here. It also replaces
# the README's module form (PYTHONPATH=src .venv/bin/python -m
# portfolio_analysis.cli ...) — the launcher does exactly that.
#
# Requires uv (README: do NOT use pip — broken on this machine's
# Homebrew Python).

TICKER ?=
DATE ?=
FLAGS ?= --keyless

.DEFAULT_GOAL := help

.PHONY: help setup test test-network test-network-verbose ingest-prices \
	detect-moves collect-events chart render dashboard factor-dashboard \
	fetch-fundamentals ai-trade-dashboard open open-ai-trade

help:
	@echo "portfolio-analysis — make targets (each wraps the README command shown):"
	@echo "  make setup               uv venv -p 3.13 && uv pip install -e \".[dev]\""
	@echo "  make test                .venv/bin/pytest   [offline; network tests excluded by default]"
	@echo "  make test-network        .venv/bin/pytest -m network"
	@echo "  make test-network-verbose  .venv/bin/pytest -m network -rs   [live-anchor validation]"
	@echo "  make ingest-prices       ./run ingest-prices"
	@echo "  make detect-moves        ./run detect-moves"
	@echo "  make collect-events      ./run collect-events TICKER [--date DATE]   [load the Alpha Vantage key first — see README 'Event collection'; TICKER defaults to META]"
	@echo "  make chart               ./run chart TICKER $(FLAGS)   [FLAGS defaults to --keyless; TICKER defaults to META; use FLAGS=\"--refresh-prices --keyless\" to update prices]"
	@echo "  make render              ./run render [TICKER]   [no TICKER re-renders every configured stock]"
	@echo "  make dashboard           ./run dashboard"
	@echo "  make factor-dashboard    ./run factor-dashboard"
	@echo "  make fetch-fundamentals  ./run fetch-fundamentals   [needed for P/E + KPI sections]"
	@echo "  make ai-trade-dashboard  ./run ai-trade-dashboard"
	@echo "  make open                open out/index.html   [macOS]"
	@echo "  make open-ai-trade       open out/ai-trade.html   [macOS]"

setup:
	uv venv -p 3.13
	uv pip install -e ".[dev]"

test:
	.venv/bin/pytest

test-network:
	.venv/bin/pytest -m network

test-network-verbose:
	.venv/bin/pytest -m network -rs

ingest-prices:
	./run ingest-prices

detect-moves:
	./run detect-moves

collect-events:
	./run collect-events $(if $(TICKER),$(TICKER),META) $(if $(DATE),--date $(DATE))

chart:
	./run chart $(if $(TICKER),$(TICKER),META) $(FLAGS)

render:
	./run render $(TICKER)

dashboard:
	./run dashboard

factor-dashboard:
	./run factor-dashboard

fetch-fundamentals:
	./run fetch-fundamentals

ai-trade-dashboard:
	./run ai-trade-dashboard

open:
	open out/index.html

open-ai-trade:
	open out/ai-trade.html
