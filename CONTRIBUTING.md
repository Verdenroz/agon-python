# Contributing to AGON

Thank you for your interest in contributing to AGON! This document provides guidelines and instructions for contributing to the project.

## Development Setup

AGON uses [uv](https://github.com/astral-sh/uv) for dependency management and development workflows.

### Prerequisites

- Python 3.11 or higher
- uv installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Git

### Setup Instructions

```bash
# Clone the repository
git clone https://github.com/Verdenroz/agon-python.git
cd agon-python

# Install dependencies (including dev dependencies)
uv sync --dev

# Install pre-commit hooks
uv run pre-commit install
```

### Running Tests

```bash
# Shortcut
make test

# Run all tests
uv run pytest

# Run tests with coverage report
uv run pytest --cov=agon --cov-report=html --cov-report=term

# Run specific test file
uv run pytest tests/test_core.py -v

# Run tests matching a pattern
uv run pytest -k "test_encode" -v
```

### Code Quality

The project uses several tools to maintain code quality:

```bash
# Lint + format + fix
make fix

# Run linter (ruff)
uv run ruff check src tests

# Auto-fix linting issues
uv run ruff check --fix src tests

# Format code
uv run ruff format src tests

# Type checking (basedpyright)
uv run basedpyright src tests

# Run all quality checks (pre-commit)
uv run pre-commit run --all-files
```

### Building Documentation

```bash
# Serve documentation locally
make docs

# Build documentation
uv run mkdocs build
```

## Contribution Guidelines

### Code Style

- Follow PEP 8 style guidelines (enforced by ruff)
- Use type hints for all function signatures
- Write descriptive variable and function names
- Keep functions focused and concise (prefer single responsibility)

### Testing Requirements

- All new features must include tests
- Maintain or improve code coverage (currently >95%)
- Tests should cover:
  - Happy path functionality
  - Edge cases
  - Error conditions
  - Round-trip encoding/decoding

Example test structure:

```python
def test_feature_name() -> None:
    """Brief description of what this test validates."""
    # Arrange
    data = {"key": "value"}

    # Act
    result = AGON.encode(data, format="auto")

    # Assert
    assert result.format == "json"
    assert AGON.decode(result) == data
```

### Commit Messages

Follow conventional commits format:

- `feat: add new format detection heuristic`
- `fix: handle empty arrays in struct encoder`
- `docs: update API reference for project_data`
- `test: add edge cases for columnar encoding`
- `refactor: simplify auto-selection logic`
- `perf: optimize token counting for large datasets`

### Pull Request Process

1. **Create a feature branch** from `master`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** following the guidelines above

3. **Run all quality checks**:
   ```bash
   uv run pytest
   uv run ruff check src tests
   uv run basedpyright src tests
   ```

4. **Commit your changes** with descriptive messages

5. **Push to your fork** and create a pull request

6. **Describe your changes** in the PR:
   - What problem does this solve?
   - What approach did you take?
   - Are there any breaking changes?
   - Have you added tests?

7. **Wait for review** - maintainers will review and provide feedback

### Pull Request Requirements

Before submitting a PR, ensure:

- [ ] All tests pass (`uv run pytest`)
- [ ] Code coverage is maintained or improved
- [ ] Linting passes (`uv run ruff check`)
- [ ] Type checking passes (`uv run basedpyright`)
- [ ] Documentation is updated (if applicable)
- [ ] Commit messages follow conventional commits format

## Areas of Interest

We welcome contributions in these areas:

### Format Implementations

- **New encoding formats**: Implement additional specialized formats (e.g., markdown tables, CSV variants)
- **Format optimizations**: Improve token efficiency of existing formats
- **Format detection**: Enhance heuristics for auto-selection

### Performance

- **Large dataset optimization**: Improve encoding/decoding speed for datasets >1MB
- **Memory efficiency**: Reduce memory footprint during processing
- **Streaming support**: Add support for streaming large datasets

### Reliability

- **LLM parsing tests**: Validate that LLMs can reliably parse AGON formats
- **Fuzzing**: Add property-based testing for edge cases
- **Error handling**: Improve error messages and recovery

### Cross-Language Support

- **Go implementation**: Port AGON to Go
- **Rust implementation**: Port AGON to Rust
- **TypeScript/JavaScript**: Port AGON to Node.js/Deno/Bun
- **Language interop**: Ensure format compatibility across implementations

### Tooling

- **VS Code extension**: Syntax highlighting and format preview
- **CLI tool**: Standalone command-line encoder/decoder
- **Web playground**: Interactive demo site for testing encodings
- **CI/CD improvements**: Enhance automated testing and release workflows

### Documentation

- **Additional examples**: Real-world use cases and patterns
- **Performance guides**: Best practices for different data shapes
- **Video tutorials**: Walkthrough of key features
- **Blog posts**: Deep dives into format design decisions

## Code Review Process

Pull requests are reviewed by project maintainers. We aim to:

- Provide initial feedback within 48 hours
- Complete reviews within 1 week for standard PRs
- Merge approved PRs promptly

During review, we evaluate:

- **Correctness**: Does the code work as intended?
- **Tests**: Are edge cases covered?
- **Performance**: Does this introduce performance regressions?
- **Maintainability**: Is the code clear and well-documented?
- **Compatibility**: Are there breaking changes?

## Reporting Issues

When reporting bugs or requesting features:

### Bug Reports

Include:
- AGON version (`python -c "import agon; print(agon.__version__)"`)
- Python version (`python --version`)
- Minimal reproduction code
- Expected vs actual behavior
- Error messages or stack traces

### Feature Requests

Include:
- Use case description
- Proposed API (if applicable)
- Alternative solutions considered
- Willingness to implement (if you plan to contribute)

## Questions?

- **Documentation**: Check [docs/](docs/) for detailed guides
- **Issues**: Search [existing issues](https://github.com/Verdenroz/agon-python/issues)
- **Discussions**: Start a [discussion](https://github.com/Verdenroz/agon-python/discussions)

## License

By contributing to AGON, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to AGON! Your contributions help make LLM prompt optimization more accessible and reliable.
