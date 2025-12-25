"""AGON Protocol.

AGON (Adaptive Guarded Object Notation) is a self-describing, token-efficient
encoding for lists of JSON objects, optimized for LLM consumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast, overload

if TYPE_CHECKING:
    from collections.abc import Callable  # pragma: no cover

import orjson

# Rust py03 bindings
from agon.agon_core import AGONColumns, AGONFormat, AGONRows, AGONStruct
from agon.agon_core import count_tokens as _rs_count_tokens
from agon.agon_core import encode_auto_parallel as _rs_encode_auto_parallel
from agon.errors import AGONError

# Type aliases
Format = Literal["auto", "json", "rows", "columns", "struct"]
ConcreteFormat = Literal["json", "rows", "columns", "struct"]

# Tiktoken encodings supported by tiktoken_rs
Encoding = Literal[
    "o200k_base",  # GPT-4o, o1, o3
    "o200k_harmony",  # GPT-OSS
    "cl100k_base",  # GPT-4, GPT-3.5-turbo
    "p50k_base",  # Codex, text-davinci-003
    "p50k_edit",  # text-davinci-edit-001
    "r50k_base",  # GPT-3 (davinci, curie, babbage, ada)
]


@dataclass(frozen=True)
class AGONEncoding:
    r"""Result of AGON encoding with format metadata.

    Use directly in LLM prompts - str() returns the encoded text.

    Example:
        >>> result = AGON.encode(data)
        >>> prompt = f"Analyze this data:\\n{result}"  # uses __str__
        >>> len(result)  # character count
        >>> AGON.decode(response, format=result.format)
    """

    format: Format
    text: str
    header: str = ""

    def __str__(self) -> str:
        """Return encoded text for use in prompts."""
        return self.text

    def __len__(self) -> int:
        """Return character count of encoded text."""
        return len(self.text)

    def __repr__(self) -> str:
        """Return debug representation."""
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"AGONEncoding(format={self.format!r}, len={len(self.text)}, text={preview!r})"

    def with_header(self) -> str:
        """Return encoded text with header prepended (for auto-detect decoding)."""
        if not self.header:
            return self.text
        return f"{self.header}\n\n{self.text}"

    def hint(self) -> str:
        """Get a prescriptive hint instructing LLMs how to generate this format.

        NOTE: LLMs have not been trained on AGON, so generation accuracy cannot
        be guaranteed. Use hints when asking LLMs to return AGON-formatted data,
        but validate the output. Prefer sending AGON to LLMs (reliable) over
        asking LLMs to generate AGON (experimental).

        Returns:
            A short prescriptive hint instructing how to generate the format.

        Example:
            >>> result = AGON.encode(data, format="auto")
            >>> result.hint()
            'Return in AGON rows format: Start with @AGON rows header...'
        """
        match self.format:
            case "rows":
                return AGONRows.hint()
            case "columns":
                return AGONColumns.hint()
            case "struct":
                return AGONStruct.hint()
            case "json":
                return "JSON: Standard compact JSON encoding"
            case _:
                msg = f"Unknown format: {self.format}"
                raise AGONError(msg)


class AGON:
    """Self-describing encoder/decoder for AGON formats.

    AGON orchestrates multiple encoding formats and selects the most
    token-efficient representation:

    Formats:
        - "json": Raw JSON (baseline)
        - "rows": AGONRows row-based format
        - "columns": AGONColumns columnar format for wide tables
        - "struct": AGONStruct template format for repeated object shapes

    Core ideas:
        - Key elimination: objects become positional rows with inline schema.
        - Recursive encoding: nested arrays of objects are also encoded.
        - Adaptive: automatically selects the best format for token efficiency.
        - Self-describing: no training or config required.
    """

    # Format headers (for decoding)
    _headers: ClassVar[dict[ConcreteFormat, str]] = {
        "json": "",
        "rows": "@AGON rows",
        "columns": "@AGON columns",
        "struct": "@AGON struct",
    }

    # Encoders - Rust for AGON formats, orjson for JSON
    _encoders: ClassVar[dict[ConcreteFormat, Callable[[Any], str]]] = {
        "json": lambda data: orjson.dumps(data).decode(),
        "rows": lambda data: str(AGONRows.encode(data, include_header=False)),
        "columns": lambda data: str(AGONColumns.encode(data, include_header=False)),
        "struct": lambda data: str(AGONStruct.encode(data, include_header=False)),
    }

    # Decoders - Rust for AGON formats
    _decoders: ClassVar[dict[str, Callable[[str], Any]]] = {
        "@AGON rows": AGONRows.decode,
        "@AGON columns": AGONColumns.decode,
        "@AGON struct": AGONStruct.decode,
    }

    @staticmethod
    def encode(
        data: object,
        *,
        format: Format = "auto",
        force: bool = False,
        min_savings: float = 0.10,
        encoding: Encoding | None = None,
    ) -> AGONEncoding:
        """Encode data to the most token-efficient AGON format.

        Args:
            data: Data to encode. Must be JSON-serializable.
            format: Format to use:
                - "auto": Select best format based on token count (default)
                - "json": Raw JSON
                - "rows": AGONRows row-based format
                - "columns": AGONColumns columnar format for wide tables
                - "struct": AGONStruct template format for repeated shapes
            force: If True with format="auto", always use a non-JSON format.
            min_savings: Minimum token savings ratio vs JSON to use non-JSON format.
            encoding: Tiktoken encoding for token counting. If None (default),
                uses fast byte-length estimation. Set to "o200k_base" for accurate
                token counts (slower). See `Encoding` type for options.

        Returns:
            EncodingResult containing:
            - format: The format used
            - text: Encoded data (send this to LLMs)
            - header: Format header (for decoding with auto-detect)

        Example:
            >>> data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
            >>> result = AGON.encode(data)
            >>> response = send_to_llm(f"Analyze: {result}")  # uses __str__
            >>> AGON.decode(response, result)  # decode using same format
        """
        # Direct format dispatch
        if format != "auto":
            encoder = AGON._encoders[format]
            text = encoder(data)
            header = AGON._headers[format]
            return AGONEncoding(format, text, header)

        # format == "auto": use Rust for fast parallel encoding and format selection
        # encoding=None means use fast byte-length estimate, otherwise use specified tiktoken encoding
        result = _rs_encode_auto_parallel(data, force, min_savings, encoding)
        selected_format = cast("ConcreteFormat", result.format)
        header = AGON._headers[selected_format]
        return AGONEncoding(selected_format, result.text, header)

    @overload
    @staticmethod
    def decode(payload: AGONEncoding) -> Any: ...

    @overload
    @staticmethod
    def decode(payload: str, format: Format | None = None) -> Any: ...

    @staticmethod
    def decode(
        payload: str | AGONEncoding,
        format: Format | None = None,
    ) -> Any:
        """Decode an AGON-encoded payload.

        Args:
            payload: What to decode. Can be:
                - AGONEncoding: Decode using its text and format
                - str: Encoded string (use format param or auto-detect)
            format: Format to use (only for str payload). If None, auto-detects.

        Returns:
            Decoded Python value.

        Raises:
            AGONError: If the payload is invalid.

        Example:
            >>> result = AGON.encode(data)
            >>> AGON.decode(result)  # decode AGONEncoding directly
        """
        if isinstance(payload, AGONEncoding):
            format, payload = payload.format, payload.text

        text = payload.strip()

        # Auto-detect from header prefix
        if format is None or format == "auto":
            for prefix, decoder in AGON._decoders.items():
                if text.startswith(prefix):
                    return decoder(text)
            return AGON._decode_json(text)

        # Dispatch by format
        match format:
            case "json":
                return AGON._decode_json(text)
            case "rows" | "columns" | "struct":
                header = AGON._headers[format]
                if not text.startswith(header):
                    text = f"{header}\n\n{text}"
                return AGON._decoders[header](text)

    @staticmethod
    def _decode_json(text: str) -> object:
        """Decode JSON text."""
        try:
            return orjson.loads(text)
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
    def count_tokens(text: str, *, encoding: Encoding = "o200k_base") -> int:
        """Count tokens in text using the specified tiktoken encoding.

        Uses the Rust tiktoken implementation for performance.

        Args:
            text: Text to count tokens in.
            encoding: Tiktoken encoding name. See `Encoding` type for options.
                Default is "o200k_base" (GPT-4o). Use "cl100k_base" for GPT-4/GPT-3.5-turbo.

        Returns:
            Number of tokens in the text.

        Raises:
            ValueError: If the encoding is not supported.
        """
        return _rs_count_tokens(text, encoding)
