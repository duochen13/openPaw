# homework-pilot — Makefile shortcuts for the commands documented in
# README.md ("How to run"). The raw commands in the README stay canonical;
# every target below wraps one of them and adds no behavior of its own.
#
# Targets assume cwd = homework-pilot/. From the repo root:
#   make -C homework-pilot <target>
#
#   make serve            local web server (long-running)
#   make demo             static demo render (student-mvp.html)
#   make test             whole suite via pytest
#   make test-<pkg>       one package's unittest discover
#   make e2e              pilot-kit end-to-end smoke run
#   make student-mvp      student MVP pipeline end-to-end check
#   make papers           regenerate the synthetic pilot papers

PYTHON ?= python3
PORT ?= 8000
OUT ?=

.DEFAULT_GOAL := help

.PHONY: help serve demo test test-evidence test-ingestion test-taxonomy \
	test-assembly test-privacy test-webui test-grading test-review \
	test-kit e2e student-mvp papers

help:
	@echo "homework-pilot — make targets (each wraps the README command shown):"
	@echo "  make serve           $(PYTHON) -m webui --serve --port $(PORT)   [long-running server; PORT=8123 overrides]"
	@echo "  make demo            $(PYTHON) -m webui $(OUT)                    [writes ./student-mvp.html; OUT=path overrides]"
	@echo "  make test            $(PYTHON) -m pytest                          [whole suite; needs pytest]"
	@echo "  make test-evidence   $(PYTHON) -m unittest discover -s evidence/tests -t ."
	@echo "  make test-ingestion  $(PYTHON) -m unittest discover -s ingestion/tests -t ."
	@echo "  make test-taxonomy   $(PYTHON) -m unittest discover -s taxonomy/tests -t ."
	@echo "  make test-assembly   $(PYTHON) -m unittest discover -s assembly/tests -t ."
	@echo "  make test-privacy    $(PYTHON) -m unittest discover -s privacy/tests -t ."
	@echo "  make test-webui      $(PYTHON) -m unittest discover -s webui/tests -t ."
	@echo "  make test-grading    $(PYTHON) -m unittest discover -s grading/tests -t ."
	@echo "  make test-review     $(PYTHON) -m pytest review/tests             [pytest-style; unittest finds 0 there — expected]"
	@echo "  make test-kit        cd pilot-kit && $(PYTHON) -m unittest discover -s tests"
	@echo "  make e2e             $(PYTHON) pilot-kit/tools/run_end_to_end.py"
	@echo "  make student-mvp     $(PYTHON) pilot-kit/tools/run_student_mvp.py"
	@echo "  make papers          cd pilot-kit && $(PYTHON) tools/build_papers.py   [needs Pillow + Noto CJK fonts]"

serve:
	$(PYTHON) -m webui --serve --port $(PORT)

demo:
	$(PYTHON) -m webui $(OUT)

test:
	$(PYTHON) -m pytest

test-evidence:
	$(PYTHON) -m unittest discover -s evidence/tests -t .

test-ingestion:
	$(PYTHON) -m unittest discover -s ingestion/tests -t .

test-taxonomy:
	$(PYTHON) -m unittest discover -s taxonomy/tests -t .

test-assembly:
	$(PYTHON) -m unittest discover -s assembly/tests -t .

test-privacy:
	$(PYTHON) -m unittest discover -s privacy/tests -t .

test-webui:
	$(PYTHON) -m unittest discover -s webui/tests -t .

test-grading:
	$(PYTHON) -m unittest discover -s grading/tests -t .

test-review:
	$(PYTHON) -m pytest review/tests

test-kit:
	cd pilot-kit && $(PYTHON) -m unittest discover -s tests

e2e:
	$(PYTHON) pilot-kit/tools/run_end_to_end.py

student-mvp:
	$(PYTHON) pilot-kit/tools/run_student_mvp.py

papers:
	cd pilot-kit && $(PYTHON) tools/build_papers.py
