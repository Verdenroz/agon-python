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
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast, overload

if TYPE_CHECKING:
    from collections.abc import Callable  # pragma: no cover

import orjson

from agon.encoding import DEFAULT_ENCODING, count_tokens
from agon.errors import AGONError
from agon.formats import AGONColumns, AGONFormat, AGONStruct, AGONText

Format = Literal["auto", "json", "text", "columns", "struct"]
ConcreteFormat = Literal["json", "text", "columns", "struct"]


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

    # Format headers (for decoding)
    _headers: ClassVar[dict[ConcreteFormat, str]] = {
        "json": "",
        "text": "@AGON text",
        "columns": "@AGON columns",
        "struct": "@AGON struct",
    }

    # Format registries (encode without headers - headers added separately)
    _encoders: ClassVar[dict[ConcreteFormat, Callable[[Any], str]]] = {
        "json": lambda data: orjson.dumps(data).decode(),
        "text": lambda data: AGONText.encode(data, include_header=False),
        "columns": lambda data: AGONColumns.encode(data, include_header=False),
        "struct": lambda data: AGONStruct.encode(data, include_header=False),
    }

    _decoders: ClassVar[dict[str, Callable[[str], Any]]] = {
        "@AGON text": AGONText.decode,
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
        encoding: str = DEFAULT_ENCODING,
    ) -> AGONEncoding:
        """Encode data to the most token-efficient AGON format.

        Args:
            data: Data to encode. Must be JSON-serializable.
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
            text = AGON._encoders[format](data)
            header = AGON._headers[format]
            return AGONEncoding(format, text, header)

        # format == "auto"
        candidates = [
            AGONEncoding(
                cast("Format", fmt),
                encoder(data),
                AGON._headers.get(fmt, ""),
            )
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
            case "text" | "columns" | "struct":
                header = AGON._headers[cast("ConcreteFormat", format)]
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
    def hint(result_or_format: AGONEncoding | ConcreteFormat) -> str:
        """Get a prescriptive hint instructing LLMs how to generate AGON format.

        NOTE: LLMs have not been trained on AGON, so generation accuracy cannot
        be guaranteed. Use hints when asking LLMs to return AGON-formatted data,
        but validate the output. Prefer sending AGON to LLMs (reliable) over
        asking LLMs to generate AGON (experimental).

        Args:
            result_or_format: AGONEncoding result or format name ("text", "columns",
                "struct", "json"). Returns generation instructions for that format.

        Returns:
            A short prescriptive hint instructing how to generate the format.

        Example:
            >>> result = AGON.encode(data, format="auto")
            >>> AGON.hint(result)  # Generation instruction for selected format
            'Return in AGON text format: Start with @AGON text header, encode arrays as name[N]{fields} with tab-delimited rows'
            >>> AGON.hint("columns")  # Generation instruction for columns format
            'Return in AGON columns format: Start with @AGON columns header, transpose arrays to name[N] with ├/└ field: val1, val2, ...'
        """
        # Extract format if AGONEncoding was passed
        format_name = (
            result_or_format.format
            if isinstance(result_or_format, AGONEncoding)
            else result_or_format
        )

        # Return hint for specific format
        match format_name:
            case "text":
                return AGONText.hint()
            case "columns":
                return AGONColumns.hint()
            case "struct":
                return AGONStruct.hint()
            case "json":
                return "JSON: Standard compact JSON encoding"
            case _:
                msg = f"Unknown format: {format_name}"
                raise AGONError(msg)

    @staticmethod
    def count_tokens(text: str, *, encoding: str = DEFAULT_ENCODING) -> int:
        """Count tokens in text using the specified encoding."""
        return count_tokens(text, encoding=encoding)
