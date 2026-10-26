# daily-report — Makefile shortcuts for the commands documented in
# README.md (and README-PDF.md). The raw commands stay canonical; every
# target below wraps one of them and adds no behavior of its own.
#
# Targets assume cwd = daily-report/. From the repo root:
#   make -C daily-report <target>
#
# Prerequisites (README): Node.js 18.x, AWS CLI configured, AWS SAM CLI
# installed. The one-off AWS provisioning commands in SETUP.md
# (create-secret, lambda invoke, logs tail, sam delete) are deliberately
# NOT targets — they are run-once ops with real secrets, not workflow.

.DEFAULT_GOAL := help

.PHONY: help install test test-watch test-coverage test-receipts build \
	deploy env

help:
	@echo "daily-report — make targets (each wraps the documented command shown):"
	@echo "  make install        npm install"
	@echo "  make test           npm test"
	@echo "  make test-watch     npm run test:watch   [INTERACTIVE / long-running: jest --watch]"
	@echo "  make test-coverage  npm run test:coverage"
	@echo "  make test-receipts  npm test -- receiptParser.test.js   [PDF receipt parser tests only]"
	@echo "  make build          npm run build   [sam build; needs the AWS SAM CLI]"
	@echo "  make deploy         npm run deploy   [INTERACTIVE: sam deploy --guided — prompts and DEPLOYS TO AWS]"
	@echo "  make env            cp .env.example .env   [then fill in secrets by hand; refuses to overwrite an existing .env]"

install:
	npm install

test:
	npm test

test-watch:
	npm run test:watch

test-coverage:
	npm run test:coverage

test-receipts:
	npm test -- receiptParser.test.js

build:
	npm run build

deploy:
	npm run deploy

env:
	@test -f .env && echo ".env already exists — not overwriting it." || cp .env.example .env
