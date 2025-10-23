# Makefile for Tidal Cleanup development

.PHONY: help install install-dev clean lint format test test-cov test-all security docs build release pre-commit

# Default target
help:
	@echo "Available targets:"
	@echo "  help          Show this help message"
	@echo "  install       Install package in development mode"
	@echo "  install-dev   Install with development dependencies"
	@echo "  clean         Clean build artifacts and cache"
	@echo "  lint          Run all linting tools"
	@echo "  format        Run code formatters"
	@echo "  test          Run tests"
	@echo "  test-cov      Run tests with coverage"
	@echo "  test-all      Run tests across all environments"
	@echo "  security      Run security checks"
	@echo "  docs          Build documentation"
	@echo "  build         Build package"
	@echo "  release       Create release"
	@echo "  pre-commit    Install and run pre-commit hooks"

# Installation targets
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Cleaning
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .tox/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Code quality
lint:
	flake8 src/ tests/
	mypy --package tidal_cleanup
	bandit -r src/

format:
	black src/ tests/
	isort src/ tests/

# Testing
test:
	pytest

test-cov:
	pytest --cov=src/tidal_cleanup --cov-report=html --cov-report=term-missing

test-all:
	tox

# Security
security:
	bandit -r src/ -f json -o bandit-report.json
	safety check --json --output safety-report.json

# Documentation
docs:
	@echo "Documentation build would go here"

# Building and releasing
build:
	python -m build

release: clean build
	python -m twine check dist/*
	@echo "Ready for release. Run 'python -m twine upload dist/*' to publish"

# Pre-commit
pre-commit:
	pre-commit install
	pre-commit run --all-files

# Development workflow
dev-setup: install-dev pre-commit
	@echo "Development environment setup complete!"

# Run CLI in development mode
run-cli:
	python -m tidal_cleanup.cli.main

# Quick quality check
quick-check: format lint test
	@echo "Quick quality check complete!"

# Full check before PR
pr-check: clean format lint test-cov security
	@echo "PR check complete!"
