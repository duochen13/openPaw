# Travel-assistant dev workflow — everything runs inside .venv so contributors
# never depend on the system python3 / pip3 (see README.md "Setup" and
# "Troubleshooting: broken Homebrew Python (pyexpat symbol error)").
#
#   make setup                      create .venv and install requirements
#   make test                       run the test suite in .venv
#   make run ARGS="research --help" run the pipeline CLI in .venv
#   make ui                         local map dashboard in .venv
#   make api                        async API service in .venv (http://127.0.0.1:8000)

VENV := .venv
PY   := $(VENV)/bin/python

.PHONY: setup test run ui api clean

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

clean:
	rm -rf $(VENV)
