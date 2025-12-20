# Makefile for easy development workflows.
# Note GitHub Actions call uv directly, not this Makefile.

.DEFAULT_GOAL := default

.PHONY: default install fix test test-unit nox nox-unit upgrade build clean help

default: install fix test

install:
	uv sync --dev

fix:
	uv run python devtools/lint.py

test: test-unit
	@echo "✅ All tests passed"

test-unit: install
	uv run pytest tests -s

nox:
	uv run nox

nox-unit:
	uv run nox -s unit

nox-lint:
	uv run nox -s lint

upgrade:
	uv sync --upgrade --dev

build:
	uv build

clean:
	-rm -rf dist/
	-rm -rf *.egg-info/
	-rm -rf .pytest_cache/
	-rm -rf .mypy_cache/
	-rm -rf .nox/
	-rm -rf .venv/
	-rm -rf htmlcov/
	-rm -rf .coverage*
	-rm -rf coverage.xml
	-find . -type d -name "__pycache__" -exec rm -rf {} +

pre-commit:
	uv run pre-commit install
	uv run pre-commit run --all-files

help:
	@echo "AGON Development Makefile"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  make               - Install deps, lint, run tests"
	@echo ""
	@echo "📦 Installation:"
	@echo "  make install       - Install all dependencies"
	@echo "  make upgrade       - Upgrade all dependencies"
	@echo ""
	@echo "🔍 Code Quality:"
	@echo "  make fix           - Auto-fix linting and formatting issues"
	@echo "  make pre-commit    - Install and run pre-commit hooks"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  make test          - Run all tests (single Python version)"
	@echo "  make test-unit     - Run unit tests (single Python version)"
	@echo "  make nox           - Run all nox sessions (all Python versions)"
	@echo "  make nox-unit      - Run unit tests (all Python versions)"
	@echo "  make nox-lint      - Run lint session via nox"
	@echo ""
	@echo "🧹 Cleanup:"
	@echo "  make clean         - Clean build/cache files"
	@echo ""
	@echo "🔧 Build:"
	@echo "  make build         - Build distribution packages"
