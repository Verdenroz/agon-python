"""Shared error types for the AGON package.

All public exceptions raised by AGON should inherit from `AGONError` so callers
can catch AGON failures with a single except clause.
"""

from __future__ import annotations


class AGONError(ValueError):
    """Base class for all AGON-related errors."""


class AGONTextError(AGONError):
    """Raised when AGONText decoding fails."""


class AGONColumnsError(AGONError):
    """Raised when AGONColumns encoding/decoding fails."""


class AGONStructError(AGONError):
    """Raised when AGONStruct encoding/decoding fails."""
