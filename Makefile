PY ?= python3

.PHONY: install format lint test check run dry-run

install:                ## install deps and enable the commit hooks
	$(PY) -m pip install -e ".[dev]"
	git config core.hooksPath .githooks
	@echo "commit hooks enabled"

format:
	$(PY) -m black src tests

lint:
	$(PY) -m black --check src tests
	$(PY) -m mypy

test:
	$(PY) -m pytest

check: lint test

dry-run:
	$(PY) -m school_job_scraper.main --dry-run --show-rejections

run:
	$(PY) -m school_job_scraper.main
