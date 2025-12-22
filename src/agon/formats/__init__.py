"""Codec implementations used by AGON.

This package contains concrete encoders/decoders ("formats"). The public,
user-facing API lives in `agon.core`, which selects among formats.
"""

from __future__ import annotations

from agon.formats.base import AGONFormat
from agon.formats.columns import AGONColumns
from agon.formats.struct import AGONStruct
from agon.formats.text import AGONText

__all__ = ["AGONColumns", "AGONFormat", "AGONStruct", "AGONText"]
