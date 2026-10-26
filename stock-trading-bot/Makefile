# stock-trading-bot — Makefile shortcuts for the commands documented in
# README.md. The raw commands in the README stay canonical; every target
# below wraps one of them and adds no behavior of its own.
#
# Targets assume cwd = stock-trading-bot/. From the repo root:
#   make -C stock-trading-bot <target>
#
# Requires uv (README: do NOT use pip — broken on this machine's
# Homebrew Python).

TICKER ?= NVDA

.DEFAULT_GOAL := help

.PHONY: help setup ingest test lint typecheck check

help:
	@echo "stock-trading-bot — make targets (each wraps the README command shown):"
	@echo "  make setup       uv venv -p 3.13 && uv pip install -e \".[dev]\""
	@echo "  make ingest      PYTHONPATH=src .venv/bin/python -m stock_trading_bot.cli ingest $(TICKER)   [TICKER accepts a ticker, company name, or watchlist alias]"
	@echo "  make test        .venv/bin/pytest   [offline; network is mocked]"
	@echo "  make lint        .venv/bin/ruff check ."
	@echo "  make typecheck   .venv/bin/mypy   [strict]"
	@echo "  make check       test + lint + typecheck   [README: all three must be clean]"

setup:
	uv venv -p 3.13
	uv pip install -e ".[dev]"

ingest:
	PYTHONPATH=src .venv/bin/python -m stock_trading_bot.cli ingest $(TICKER)

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

typecheck:
	.venv/bin/mypy

check: test lint typecheck
