# openPaw — root Makefile: convenience delegation to the per-project
# Makefiles, plus the repo-level githooks install.
#
# Each project directory has its own Makefile wrapping ALL of that
# project's documented commands; those files are canonical for their
# full target lists — run `make -C <project> help` (or `make <prefix>-help`
# below). This root file only forwards the common targets and adds the
# one repo-level command (hooks) that belongs to no single project.
#
# Command-line variables propagate to the project Makefiles, e.g.
#   make pa-chart TICKER=NVDA FLAGS="--refresh-prices --keyless"
#   make hp-serve PORT=8123

.DEFAULT_GOAL := help

.PHONY: help hooks \
	hp-help hp-serve hp-demo hp-test \
	pa-help pa-setup pa-test pa-chart pa-render pa-dashboard pa-ai-trade \
	stb-help stb-setup stb-test stb-check stb-ingest \
	bc-help bc-build bc-report bc-alerts bc-collect bc-test \
	dr-help dr-install dr-test dr-build \
	an-help an-cds an-capex \
	cpm-help cpm-build cpm-grantham \
	cda-help \
	ta-help ta-setup ta-test ta-ui ta-api

help:
	@echo "openPaw — root make targets (delegation to per-project Makefiles + hooks):"
	@echo ""
	@echo "  make hooks            install the docs-sync pre-push hook (git config core.hooksPath githooks && chmod +x githooks/pre-push)"
	@echo ""
	@echo "  homework-pilot/        prefix hp-   (make hp-help for its full list)"
	@echo "    hp-serve hp-demo hp-test"
	@echo "  portfolio-analysis/    prefix pa-   (make pa-help for its full list)"
	@echo "    pa-setup pa-test pa-chart pa-render pa-dashboard pa-ai-trade"
	@echo "  stock-trading-bot/     prefix stb-  (make stb-help for its full list)"
	@echo "    stb-setup stb-test stb-check stb-ingest"
	@echo "  bearish-challenger/    prefix bc-   (make bc-help for its full list)"
	@echo "    bc-build bc-report bc-alerts bc-collect bc-test"
	@echo "  daily-report/          prefix dr-   (make dr-help for its full list)"
	@echo "    dr-install dr-test dr-build"
	@echo "  analysis/              prefix an-   (make an-help for its full list)"
	@echo "    an-cds an-capex"
	@echo "  cross-platform-media-analysis/  prefix cpm-  (make cpm-help for its full list)"
	@echo "    cpm-build cpm-grantham"
	@echo "  community-discussion-analysis/  prefix cda-  (make cda-help for its commands)"
	@echo "  travel-assistant/      prefix ta-   (make ta-help for its full list)"
	@echo "    ta-setup ta-test ta-ui ta-api"
	@echo ""
	@echo "  data/, docs/ and reports/ are support directories and have no Makefile."

hooks:
	git config core.hooksPath githooks && chmod +x githooks/pre-push

hp-help:
	$(MAKE) -C homework-pilot help

hp-serve:
	$(MAKE) -C homework-pilot serve

hp-demo:
	$(MAKE) -C homework-pilot demo

hp-test:
	$(MAKE) -C homework-pilot test

pa-help:
	$(MAKE) -C portfolio-analysis help

pa-setup:
	$(MAKE) -C portfolio-analysis setup

pa-test:
	$(MAKE) -C portfolio-analysis test

pa-chart:
	$(MAKE) -C portfolio-analysis chart

pa-render:
	$(MAKE) -C portfolio-analysis render

pa-dashboard:
	$(MAKE) -C portfolio-analysis dashboard

pa-ai-trade:
	$(MAKE) -C portfolio-analysis ai-trade-dashboard

stb-help:
	$(MAKE) -C stock-trading-bot help

stb-setup:
	$(MAKE) -C stock-trading-bot setup

stb-test:
	$(MAKE) -C stock-trading-bot test

stb-check:
	$(MAKE) -C stock-trading-bot check

stb-ingest:
	$(MAKE) -C stock-trading-bot ingest

bc-help:
	$(MAKE) -C bearish-challenger help

bc-build:
	$(MAKE) -C bearish-challenger build

bc-report:
	$(MAKE) -C bearish-challenger report

bc-alerts:
	$(MAKE) -C bearish-challenger alerts

bc-collect:
	$(MAKE) -C bearish-challenger collect

bc-test:
	$(MAKE) -C bearish-challenger test

dr-help:
	$(MAKE) -C daily-report help

dr-install:
	$(MAKE) -C daily-report install

dr-test:
	$(MAKE) -C daily-report test

dr-build:
	$(MAKE) -C daily-report build

an-help:
	$(MAKE) -C analysis help

an-cds:
	$(MAKE) -C analysis cds-chart

an-capex:
	$(MAKE) -C analysis capex-chart

cpm-help:
	$(MAKE) -C cross-platform-media-analysis help

cpm-build:
	$(MAKE) -C cross-platform-media-analysis build

cpm-grantham:
	$(MAKE) -C cross-platform-media-analysis build-grantham

cda-help:
	$(MAKE) -C community-discussion-analysis help

ta-help:
	$(MAKE) -C travel-assistant help

ta-setup:
	$(MAKE) -C travel-assistant setup

ta-test:
	$(MAKE) -C travel-assistant test

ta-ui:
	$(MAKE) -C travel-assistant ui

ta-api:
	$(MAKE) -C travel-assistant api
