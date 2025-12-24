"""Nox sessions for AGON."""

import nox

PYTHON_VERSIONS = ["3.11", "3.12", "3.13"]
LOCATIONS = ["src", "tests"]


@nox.session(python=PYTHON_VERSIONS[-1])
def lint(session: nox.Session) -> None:
    """Run linting and type checking."""
    # Install the project and runtime deps so type checking can resolve imports.
    session.install(".")
    session.install("ruff", "basedpyright", "codespell")
    session.run("ruff", "check", *LOCATIONS)
    session.run("ruff", "format", "--check", *LOCATIONS)
    session.run("basedpyright", "src")
    session.run("codespell", "src", "tests")


@nox.session(python=PYTHON_VERSIONS)
def unit(session: nox.Session) -> None:
    """Run unit tests."""
    session.install(".", "pytest", "pytest-cov", "pytest-sugar")
    session.run(
        "pytest",
        "--cov=agon",
        "--cov-report=term-missing",
        *session.posargs,
    )


@nox.session(python=PYTHON_VERSIONS[-1])
def coverage(session: nox.Session) -> None:
    """Generate coverage report."""
    session.install("coverage[toml]")
    # Combine coverage data and apply path mappings
    session.run("coverage", "combine", "--keep", success_codes=[0, 1])
    if session.posargs and session.posargs[0] == "xml":
        session.run("coverage", "xml")
    else:
        session.run("coverage", "report", "--show-missing")
