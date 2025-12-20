"""AGON - Adaptive Guarded Object Notation.

A schema-driven, token-efficient data interchange format for Large Language Models.
"""

from agon.core import AGON, AgonClient, AGONError

__all__ = ["AGON", "AGONError", "AgonClient"]
__version__ = "0.1.0"
