# Makefile for Cratekeeper development

.PHONY: help install install-dev format lint typecheck test check clean ui ui-dev ui-check openapi

help:
	@echo "Targets:"
	@echo "  install      Install Cratekeeper (editable)"
	@echo "  install-dev  Install with development tools and pre-commit hooks"
	@echo "  format       Run black and isort"
	@echo "  lint         Run flake8"
	@echo "  typecheck    Run mypy"
	@echo "  test         Run pytest with coverage"
	@echo "  check        format check + lint + typecheck + test (same as CI)"
	@echo "  ui           Build the web UI into src/cratekeeper/web/dist"
	@echo "  ui-dev       Run the Vite dev server (start cratekeeper ui --dev next to it)"
	@echo "  ui-check     eslint, tsc, vitest and build for the web UI"
	@echo "  openapi      Export the API contract and regenerate UI types"
	@echo "  clean        Remove build and cache files"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

format:
	black src/ tests/
	isort src/ tests/

lint:
	flake8 src/ tests/

typecheck:
	mypy --package cratekeeper --config-file=pyproject.toml

test:
	pytest

check:
	black --check src/ tests/
	isort --check-only src/ tests/
	flake8 src/ tests/
	mypy --package cratekeeper --config-file=pyproject.toml
	pytest

ui:
	npm --prefix frontend ci
	npm --prefix frontend run build

ui-dev:
	npm --prefix frontend run dev

ui-check:
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend run test
	npm --prefix frontend run build

openapi:
	python scripts/export_openapi.py
	npm --prefix frontend run gen:api

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
