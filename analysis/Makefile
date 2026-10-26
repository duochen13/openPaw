# analysis — Makefile shortcuts for the chart-regeneration commands
# documented in the two sub-projects' READMEs (cds-spreads/README.md and
# true-ai-capex/README.md, "Regenerate" sections). The raw commands stay
# canonical; every target wraps one of them and adds no behavior.
#
# ONE Makefile at the analysis/ level with prefixed targets (the choice
# recorded in issue #181): each target cds into its sub-project and runs
# that sub-project's build_chart.py, exactly as its README documents.
# Targets assume cwd = analysis/. From the repo root:
#   make -C analysis <target>

PYTHON ?= python3
OUT ?=

.DEFAULT_GOAL := help

.PHONY: help cds-chart capex-chart

help:
	@echo "analysis — make targets (each wraps the sub-project README command shown):"
	@echo "  make cds-chart    cd cds-spreads && $(PYTHON) build_chart.py [--out OUT]   [regenerates cds-spreads/chart.png]"
	@echo "  make capex-chart  cd true-ai-capex && $(PYTHON) build_chart.py [--out OUT]   [regenerates true-ai-capex/chart.png]"
	@echo "  OUT=/tmp/test.png writes to that path instead of the committed chart.png."

cds-chart:
	cd cds-spreads && $(PYTHON) build_chart.py $(if $(OUT),--out $(OUT))

capex-chart:
	cd true-ai-capex && $(PYTHON) build_chart.py $(if $(OUT),--out $(OUT))
