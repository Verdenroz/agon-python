"""AGON Protocol.

AGON (Adaptive Guarded Object Notation) is a self-describing, token-efficient
encoding for lists of JSON objects, optimized for LLM consumption.

Core features:
    - Key elimination: objects become positional rows with inline schema.
    - Recursive encoding: nested arrays of objects are also encoded.
    - Adaptive: automatically selects the best format for token efficiency.
    - Self-describing: no training or config required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Callable  # pragma: no cover

import orjson

from agon.encoding import DEFAULT_ENCODING, count_tokens
from agon.errors import AGONError
from agon.formats import AGONColumns, AGONFormat, AGONStruct, AGONText

Format = Literal["auto", "json", "text", "columns", "struct"]


@dataclass(frozen=True)
class EncodingResult:
    """Result of AGON encoding with format metadata."""

    format: Format
    text: str


class AGON:
    """Self-describing encoder/decoder for AGON formats.

    AGON orchestrates multiple encoding formats and selects the most
    token-efficient representation:

    Formats:
        - "json": Raw JSON (baseline)
        - "text": AGONText row-based format
        - "columns": AGONColumns columnar format for wide tables
        - "struct": AGONStruct template format for repeated object shapes

    Core ideas:
        - Key elimination: objects become positional rows with inline schema.
        - Recursive encoding: nested arrays of objects are also encoded.
        - Adaptive: automatically selects the best format for token efficiency.
        - Self-describing: no training or config required.
    """

    # Format registries
    _encoders: ClassVar[dict[str, Callable[[Any], str]]] = {
        "json": lambda data: orjson.dumps(data).decode(),
        "text": AGONText.encode,
        "columns": AGONColumns.encode,
        "struct": AGONStruct.encode,
    }

    _decoders: ClassVar[dict[str, Callable[[str], Any]]] = {
        "@AGON text": AGONText.decode,
        "@AGON columns": AGONColumns.decode,
        "@AGON struct": AGONStruct.decode,
    }

    @staticmethod
    def encode(
        data: Any,
        *,
        format: Format = "auto",
        force: bool = False,
        min_savings: float = 0.10,
        encoding: str = DEFAULT_ENCODING,
    ) -> str:
        """Encode data to the most token-efficient AGON format.

        Args:
            data: Data to encode. Any JSON-serializable value.
            format: Format to use:
                - "auto": Select best format based on token count (default)
                - "json": Raw JSON
                - "text": AGONText row-based format
                - "columns": AGONColumns columnar format for wide tables
                - "struct": AGONStruct template format for repeated shapes
            force: If True with format="auto", always use a non-JSON format.
            min_savings: Minimum token savings ratio vs JSON to use non-JSON format.
            encoding: Tiktoken encoding for token counting (default: o200k_base).

        Returns:
            Encoded string in the selected format.

        Example:
            >>> data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
            >>> AGON.encode(data, format="text")
        """
        # Direct format dispatch
        if encoder := AGON._encoders.get(format):
            return encoder(data)

        # format == "auto": select best
        candidates = [
            (fmt, encoder(data))
            for fmt, encoder in AGON._encoders.items()
            if force is False or fmt != "json"
        ]

        # Select smallest token count
        token_counts = [count_tokens(text, encoding=encoding) for _, text in candidates]
        best_idx = min(range(len(candidates)), key=lambda i: token_counts[i])
        best_format, best_text = candidates[best_idx]

        # Apply min_savings threshold
        if not force and best_format != "json":
            json_idx = next(i for i, (fmt, _) in enumerate(candidates) if fmt == "json")
            json_tokens = token_counts[json_idx]
            savings = 1.0 - (token_counts[best_idx] / max(1, json_tokens))
            if savings < min_savings:
                return candidates[json_idx][1]

        return best_text

    @staticmethod
    def encode_with_format(
        data: Any,
        *,
        format: Format = "auto",
        force: bool = False,
        min_savings: float = 0.10,
        encoding: str = DEFAULT_ENCODING,
    ) -> EncodingResult:
        """Encode data and return result with format metadata.

        Same as encode() but returns an EncodingResult with format info.
        """
        # Direct format dispatch
        if encoder := AGON._encoders.get(format):
            return EncodingResult(format, encoder(data))

        # format == "auto"
        candidates = [
            EncodingResult(cast("Format", fmt), encoder(data))
            for fmt, encoder in AGON._encoders.items()
            if force is False or fmt != "json"
        ]

        token_counts = [count_tokens(c.text, encoding=encoding) for c in candidates]
        best_idx = min(range(len(candidates)), key=lambda i: token_counts[i])
        best = candidates[best_idx]

        if not force and best.format != "json":
            json_result = next(c for c in candidates if c.format == "json")
            json_idx = candidates.index(json_result)
            json_tokens = token_counts[json_idx]
            savings = 1.0 - (token_counts[best_idx] / max(1, json_tokens))
            if savings < min_savings:
                return json_result

        return best

    @staticmethod
    def decode(payload: str) -> Any:
        """Decode an AGON-encoded payload.

        Automatically detects the format by prefix matching.

        Args:
            payload: Encoded string in any AGON format.

        Returns:
            Decoded Python value.

        Raises:
            AGONError: If the payload is invalid.
        """
        payload = payload.strip()

        # Prefix-based decoder dispatch
        for prefix, decoder in AGON._decoders.items():
            if payload.startswith(prefix):
                return decoder(payload)

        # Fallback: raw JSON
        try:
            return orjson.loads(payload)
        except orjson.JSONDecodeError as e:
            raise AGONError(f"Invalid JSON: {e}") from e

    @staticmethod
    def project_data(data: list[dict[str, Any]], keep_paths: list[str]) -> list[dict[str, Any]]:
        """Project data to only keep specified fields.

        Useful for reducing data before encoding when you only need
        specific fields for an LLM query.

        Args:
            data: List of objects to project.
            keep_paths: List of field paths to keep. Supports dotted paths
                like "user.name" or "quotes.symbol".

        Returns:
            Projected data with only the specified fields.

        Example:
            >>> data = [{"id": 1, "name": "Alice", "role": "admin"}]
            >>> AGON.project_data(data, ["id", "name"])
            [{"id": 1, "name": "Alice"}]
        """
        return AGONFormat.project_data(data, keep_paths)

    @staticmethod
    def hint() -> str:
        """Optional short hint for LLMs about AGON format.

        Most LLMs can understand AGON without any hint since it's self-describing.
        This hint is ~24 tokens vs ~100+ tokens for traditional schema prompts.

        Returns:
            A short hint string.
        """
        return AGONText.hint()

    @staticmethod
    def count_tokens(text: str, *, encoding: str = DEFAULT_ENCODING) -> int:
        """Count tokens in text using the specified encoding."""
        return count_tokens(text, encoding=encoding)
