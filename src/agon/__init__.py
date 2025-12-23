"""AGON - Adaptive Guarded Object Notation.

A self-describing, token-efficient data interchange format optimized for LLMs.
"""

from agon.core import AGON, AGONEncoding, Format
from agon.errors import (
    AGONColumnsError,
    AGONError,
    AGONStructError,
    AGONTextError,
)

__all__ = [
    "AGON",
    "AGONColumnsError",
    "AGONEncoding",
    "AGONError",
    "AGONStructError",
    "AGONTextError",
    "Format",
]
__version__ = "0.1.0"
