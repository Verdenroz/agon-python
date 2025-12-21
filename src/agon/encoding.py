"""Shared token counting utilities for AGON."""

from __future__ import annotations

from functools import lru_cache

import tiktoken

DEFAULT_ENCODING = "o200k_base"


@lru_cache(maxsize=16)
def get_encoding(name: str = DEFAULT_ENCODING) -> tiktoken.Encoding:
    """Get a tiktoken encoding by name (cached)."""
    return tiktoken.get_encoding(name)


def count_tokens(text: str, *, encoding: str = DEFAULT_ENCODING) -> int:
    """Count tokens in text using the specified encoding."""
    enc = get_encoding(encoding)
    return len(enc.encode(text))
