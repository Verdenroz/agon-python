# Makefile for easy development workflows.
# Note GitHub Actions call uv directly, not this Makefile.

.DEFAULT_GOAL := default

.PHONY: default install fix test nox upgrade build docs clean pre-commit help

default: install fix test

install:
	uv sync --dev

fix:
	uv run python devtools/lint.py

test: install
	uv run pytest tests -s
	@echo "✅ All tests passed"

nox:
	uv run nox

upgrade:
	uv sync --upgrade --dev

build:
	uv build

docs: install
	uv run mkdocs serve --livereload

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
	@echo ""
	@echo "📚 Docs:"
	@echo "  make docs          - Serve docs locally (http://127.0.0.1:8000/)"
