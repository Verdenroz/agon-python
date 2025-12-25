"""Shared error types for the AGON package.

All public exceptions raised by AGON should inherit from `AGONError` so callers
can catch AGON failures with a single except clause.
"""

from __future__ import annotations


class AGONError(ValueError):
    """Base class for all AGON-related errors.

    Inherits from ValueError for compatibility with errors raised by
    the Rust bindings (which raise ValueError via PyO3).
    """
