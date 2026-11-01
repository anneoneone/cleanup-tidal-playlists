# Makefile for Cratekeeper development

.PHONY: help install install-dev format lint typecheck test check clean

help:
	@echo "Targets:"
	@echo "  install      Install Cratekeeper (editable)"
	@echo "  install-dev  Install with development tools and pre-commit hooks"
	@echo "  format       Run black and isort"
	@echo "  lint         Run flake8"
	@echo "  typecheck    Run mypy"
	@echo "  test         Run pytest with coverage"
	@echo "  check        format check + lint + typecheck + test (same as CI)"
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

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
