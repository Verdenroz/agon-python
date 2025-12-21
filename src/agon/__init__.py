"""AGON - Adaptive Guarded Object Notation.

A self-describing, token-efficient data interchange format optimized for LLMs.
"""

from agon.core import AGON, EncodingResult, Format
from agon.errors import AGONColumnsError, AGONError, AGONTextError

__all__ = [
    "AGON",
    "AGONColumnsError",
    "AGONError",
    "AGONTextError",
    "EncodingResult",
    "Format",
]
__version__ = "0.1.0"
