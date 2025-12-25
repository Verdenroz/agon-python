"""AGON - Adaptive Guarded Object Notation.

A self-describing, token-efficient data interchange format optimized for LLMs.
"""

# Re-export Rust format classes (inherit from AGONFormat)
from agon.agon_core import (
    AGONColumns,
    AGONFormat,
    AGONRows,
    AGONStruct,
    EncodingResult,
    encode_all_parallel,
    encode_auto_parallel,
)
from agon.core import AGON, AGONEncoding, Format
from agon.errors import AGONError

__all__ = [
    "AGON",
    "AGONColumns",
    "AGONEncoding",
    "AGONError",
    "AGONFormat",
    "AGONRows",
    "AGONStruct",
    "EncodingResult",
    "Format",
    "encode_all_parallel",
    "encode_auto_parallel",
]
__version__ = "0.1.0"
