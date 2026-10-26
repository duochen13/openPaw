# Travel-assistant dev workflow — everything runs inside .venv so contributors
# never depend on the system python3 / pip3 (see README.md "Setup" and
# "Troubleshooting: broken Homebrew Python (pyexpat symbol error)").
#
#   make setup                      create .venv and install requirements
#   make test                       run the test suite in .venv
#   make run ARGS="research --help" run the pipeline CLI in .venv
#   make ui                         local map dashboard in .venv
#   make api                        async API service in .venv (http://127.0.0.1:8000)
#   make research ARGS="..."        research pipeline module in .venv
#   make runs-list                  list past runs in .venv
#   make runs-show N=3              show one run + its places in .venv
#   make apikeys-create NAME=dev    mint an API key in .venv (printed once)
#   make api-docs                   regenerate docs/api-reference.md + openapi.json
#   make test-research              end-to-end research test module in .venv
#   make test-mcp                   MCP server end-to-end test module in .venv
#   make install                    pip install -e . in .venv (console script)
#   make help                       list all targets (default goal)

VENV := .venv
PY   := $(VENV)/bin/python

ARGS ?=
N    ?= 3
NAME ?= dev

.DEFAULT_GOAL := help

.PHONY: help setup test run ui api research runs-list runs-show \
	apikeys-create api-docs test-research test-mcp install clean

help:
	@echo "travel-assistant — make targets:"
	@echo "  make setup                      create .venv + pip install -r requirements.txt"
	@echo "  make test                       install requirements-dev.txt + run the test suite in .venv"
	@echo "  make run ARGS=\"...\"             run the pipeline CLI in .venv, e.g. ARGS=\"runs list\""
	@echo "  make ui                         local map dashboard in .venv (http://127.0.0.1:8000) [long-running]"
	@echo "  make api                        async API service in .venv (http://127.0.0.1:8000) [long-running]"
	@echo "  make research ARGS=\"...\"        $(PY) -m travel_assistant.research ARGS, e.g. ARGS=\"--from-analysis data/analysis/<file>.json\""
	@echo "  make runs-list                  $(PY) -m travel_assistant.runs list"
	@echo "  make runs-show N=3              $(PY) -m travel_assistant.runs show N --places"
	@echo "  make apikeys-create NAME=dev    $(PY) -m travel_assistant.apikeys create --name NAME [raw key printed once]"
	@echo "  make api-docs                   $(PY) docs/generate_api_docs.py [after changing any /v1 route]"
	@echo "  make test-research              $(PY) -m travel_assistant.tests.test_research [end-to-end, Vancouver fixture]"
	@echo "  make test-mcp                   $(PY) -m travel_assistant.tests.test_mcp_server [end-to-end via stdio client]"
	@echo "  make install                    pip install -e . in .venv [travel-assistant console script]"
	@echo "  make clean                      remove .venv"

setup: $(VENV)
	$(PY) -m pip install -r requirements.txt

$(VENV):
	python3 -m venv $(VENV)

test: setup
	$(PY) -m pip install -r requirements-dev.txt
	$(PY) -m pytest travel_assistant/tests/

run: setup
	$(PY) -m travel_assistant $(ARGS)

ui: setup
	$(PY) -m travel_assistant ui

api: setup
	$(PY) -m travel_assistant.service --port 8000

research: setup
	$(PY) -m travel_assistant.research $(ARGS)

runs-list: setup
	$(PY) -m travel_assistant.runs list

runs-show: setup
	$(PY) -m travel_assistant.runs show $(N) --places

apikeys-create: setup
	$(PY) -m travel_assistant.apikeys create --name $(NAME)

api-docs: setup
	$(PY) docs/generate_api_docs.py

test-research: setup
	$(PY) -m travel_assistant.tests.test_research

test-mcp: setup
	$(PY) -m travel_assistant.tests.test_mcp_server

install: setup
	$(PY) -m pip install -e .

clean:
	rm -rf $(VENV)
