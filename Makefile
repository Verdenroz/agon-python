# Makefile for easy development workflows.
# Note GitHub Actions call uv directly, not this Makefile.

.DEFAULT_GOAL := default

.PHONY: default install fix test nox upgrade build docs clean pre-commit benchmarks help

default: install build fix test

install:
	uv sync --dev

build:
	uv run maturin develop --manifest-path crates/agon-core/Cargo.toml

fix:
	uv run python devtools/lint_rust.py & uv run python devtools/lint_python.py & wait

test: build
	@echo "🦀 Running Rust tests with coverage..."
	cargo llvm-cov --manifest-path crates/agon-core/Cargo.toml --fail-under-lines 70
	cargo llvm-cov report --manifest-path crates/agon-core/Cargo.toml --lcov --output-path rust-coverage.lcov
	@echo ""
	@echo "🐍 Running Python tests with coverage..."
	uv run pytest tests -v
	@echo ""
	@echo "✅ All tests passed"

nox: build
	uv run nox

benchmarks: build
	@echo "📊 Running AGON benchmarks..."
	uv run pytest tests/test_benchmarks.py -s --no-cov -o addopts=""

upgrade:
	uv sync --upgrade --dev

docs: install
	uv run mkdocs serve --livereload

clean:
	-rm -rf dist/ target/ *.egg-info/
	-rm -rf .pytest_cache/ .mypy_cache/ .nox/ htmlcov/
	-rm -rf .coverage* coverage.xml rust-coverage.lcov
	-find . -type d -name "__pycache__" -exec rm -rf {} +

pre-commit:
	uv run pre-commit install
	uv run pre-commit run --all-files

help:
	@echo "AGON Development Makefile"
	@echo ""
	@echo "Quick Start:"
	@echo "  make               - Install, build Rust, lint, test"
	@echo "  make test          - Build Rust and run tests"
	@echo ""
	@echo "Development:"
	@echo "  make install       - Install Python dependencies"
	@echo "  make build         - Build and install Rust extension"
	@echo "  make fix           - Format and lint (Python + Rust)"
	@echo ""
	@echo "Testing:"
	@echo "  make test          - Run Rust + Python tests with coverage"
	@echo "  make nox           - Run nox sessions (builds Rust first)"
	@echo "  make benchmarks    - Run performance benchmarks"
	@echo ""
	@echo "Other:"
	@echo "  make docs          - Serve docs locally"
	@echo "  make clean         - Clean build artifacts"
	@echo "  make upgrade       - Upgrade dependencies"
