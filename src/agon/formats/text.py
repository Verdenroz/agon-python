r"""AGONText format codec.

AGONText is a row-based encoding with radical simplicity.
It uses indentation for hierarchy and tabular format for arrays of objects.

Format structure:
    @AGON text
    @D=<delimiter>  # optional, default: \t
    <data>

Example:
    @AGON text

    products[3]{sku	name	price}
    A123	Widget	9.99
    B456	Gadget	19.99
    C789	Gizmo	29.99
"""

from __future__ import annotations

import re
from typing import Any

from agon.errors import AGONTextError
from agon.formats.base import AGONFormat

HEADER = "@AGON text"
DEFAULT_DELIMITER = "\t"
INDENT = "  "  # 2 spaces per level

# Characters that require quoting
SPECIAL_CHARS = frozenset(["@", "#", "-"])
BOOL_NULL = frozenset(["true", "false", "null"])

# Regex for numbers
NUMBER_RE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")


class AGONText(AGONFormat):
    """AGONText format encoder/decoder.

    Encodes JSON data to a row-based text format optimized for
    LLM consumption with significant token savings.
    """

    @staticmethod
    def hint() -> str:
        """Return a short hint instructing LLMs how to generate this format."""
        return "Return in AGON text format: Start with @AGON text header, encode arrays as name[N]{fields} with tab-delimited rows"

    @staticmethod
    def encode(
        data: object,
        *,
        delimiter: str = DEFAULT_DELIMITER,
        include_header: bool = True,
    ) -> str:
        """Encode data to AGONText format.

        Args:
            data: JSON-serializable data to encode.
            delimiter: Field delimiter for tabular data (default: tab).
            include_header: Whether to include @AGON text header.

        Returns:
            AGONText encoded string.
        """
        lines: list[str] = []

        if include_header:
            lines.append(HEADER)
            if delimiter != DEFAULT_DELIMITER:
                lines.append(f"@D={_escape_delimiter(delimiter)}")
            lines.append("")  # blank line after header

        _encode_value(data, lines, depth=0, delimiter=delimiter, name=None)

        return "\n".join(lines)

    @staticmethod
    def decode(payload: str, *, lenient: bool = False) -> Any:
        """Decode AGONText payload.

        Args:
            payload: AGONText encoded string.
            lenient: If True, allow length mismatches and best-effort parsing.

        Returns:
            Decoded Python value.

        Raises:
            AGONTextError: If payload is invalid.
        """
        lines = payload.splitlines()
        if not lines:
            raise AGONTextError("Empty payload")

        # Parse header
        idx = 0
        header_line = lines[idx].strip()
        if not header_line.startswith("@AGON text"):
            raise AGONTextError(f"Invalid header: {header_line}")
        idx += 1

        # Parse delimiter
        delimiter = DEFAULT_DELIMITER
        if idx < len(lines) and lines[idx].startswith("@D="):
            delimiter = _parse_delimiter(lines[idx][3:].strip())
            idx += 1

        # Skip blank lines after header
        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        if idx >= len(lines):
            return None

        result, _ = _decode_value(lines, idx, depth=0, delimiter=delimiter, lenient=lenient)
        return result


def _escape_delimiter(d: str) -> str:
    """Escape delimiter for @D= declaration."""
    # Unreachable via public API: DEFAULT_DELIMITER is "\t" and encode() only calls
    # _escape_delimiter() when delimiter != DEFAULT_DELIMITER.
    if d == "\t":  # pragma: no cover
        return "\\t"
    if d == "\n":
        return "\\n"
    return d


def _parse_delimiter(d: str) -> str:
    """Parse delimiter from @D= declaration."""
    if d == "\\t":
        return "\t"
    if d == "\\n":
        return "\n"
    return d


def _needs_quote(s: str, delimiter: str) -> bool:
    """Check if string needs quoting."""
    if not s:
        return True
    # Leading/trailing whitespace
    if s != s.strip():
        return True
    # Contains delimiter
    if delimiter in s:
        return True
    # Contains newlines or special chars
    if "\n" in s or "\r" in s or "\\" in s or '"' in s:
        return True
    # Starts with special char
    if s[0] in SPECIAL_CHARS:
        return True
    # Looks like number/bool/null
    return bool(s.lower() in BOOL_NULL or NUMBER_RE.match(s))


def _quote_string(s: str) -> str:
    """Quote and escape a string value."""
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _unquote_string(s: str) -> str:
    """Unquote and unescape a string value."""
    if not (s.startswith('"') and s.endswith('"')):
        return s
    inner = s[1:-1]
    result = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner):
            c = inner[i + 1]
            if c == "n":
                result.append("\n")
            elif c == "r":
                result.append("\r")
            elif c == "t":
                result.append("\t")
            elif c == "\\":
                result.append("\\")
            elif c == '"':
                result.append('"')
            else:
                result.append(inner[i + 1])
            i += 2
        else:
            result.append(inner[i])
            i += 1
    return "".join(result)


def _encode_primitive(val: Any, delimiter: str) -> str:
    """Encode a primitive value to string."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int | float):
        # Handle special float values
        if isinstance(val, float):
            if val != val:  # NaN
                return "null"
            if val == float("inf") or val == float("-inf"):
                return "null"
            if val == 0.0 and str(val) == "-0.0":
                return "0"
        return str(val)
    # String
    s = str(val)
    if _needs_quote(s, delimiter):
        return _quote_string(s)
    return s


def _parse_primitive(s: str) -> Any:
    """Parse a primitive value from string."""
    s = s.strip()
    if not s:
        return None

    # Quoted string
    if s.startswith('"') and s.endswith('"'):
        return _unquote_string(s)

    # Boolean/null
    lower = s.lower()
    if lower == "null":
        return None
    if lower == "true":
        return True
    if lower == "false":
        return False

    # Number
    if NUMBER_RE.match(s):
        if "." in s or "e" in s.lower():
            return float(s)
        return int(s)

    # Plain string
    return s


def _is_uniform_array(arr: list[Any]) -> tuple[bool, list[str]]:
    """Check if array is uniform objects, return (is_uniform, fields)."""
    if not arr:
        return False, []

    if not all(isinstance(x, dict) for x in arr):
        return False, []

    # Get all keys in order
    all_keys: set[str] = set()
    for obj in arr:
        all_keys.update(obj.keys())

    if not all_keys:
        return False, []

    # Check all objects have only primitive values
    for obj in arr:
        for v in obj.values():
            if isinstance(v, dict | list):
                return False, []

    # Return keys in consistent order (first seen order from union)
    key_order: list[str] = []
    for obj in arr:
        for k in obj:
            if k not in key_order:
                key_order.append(k)

    return True, key_order


def _is_primitive_array(arr: list[Any]) -> bool:
    """Check if array contains only primitives."""
    return all(not isinstance(x, dict | list) for x in arr)


def _encode_value(
    val: Any,
    lines: list[str],
    depth: int,
    delimiter: str,
    name: str | None,
) -> None:
    """Encode a value, appending lines."""
    indent = INDENT * depth

    if val is None or isinstance(val, bool | int | float | str):
        # Primitive value
        if name:
            lines.append(f"{indent}{name}: {_encode_primitive(val, delimiter)}")
        else:
            lines.append(f"{indent}{_encode_primitive(val, delimiter)}")
        return

    if isinstance(val, list):
        _encode_array(val, lines, depth, delimiter, name)
        return

    if isinstance(val, dict):
        _encode_object(val, lines, depth, delimiter, name)
        return

    # Fallback: treat as string
    if name:
        lines.append(f"{indent}{name}: {_encode_primitive(str(val), delimiter)}")
    else:
        lines.append(f"{indent}{_encode_primitive(str(val), delimiter)}")


def _encode_array(
    arr: list[Any],
    lines: list[str],
    depth: int,
    delimiter: str,
    name: str | None,
) -> None:
    """Encode an array value."""
    indent = INDENT * depth

    if not arr:
        # Empty array
        if name:
            lines.append(f"{indent}{name}[0]:")
        else:
            lines.append(f"{indent}[0]:")
        return

    # Check for uniform objects (tabular format)
    is_uniform, fields = _is_uniform_array(arr)
    if is_uniform and fields:
        header = delimiter.join(fields)
        if name:
            lines.append(f"{indent}{name}[{len(arr)}]{{{header}}}")
        else:
            lines.append(f"{indent}[{len(arr)}]{{{header}}}")

        for obj in arr:
            row_values = []
            for f in fields:
                if f in obj:
                    row_values.append(_encode_primitive(obj[f], delimiter))
                else:
                    row_values.append("")
            lines.append(f"{indent}{delimiter.join(row_values)}")
        return

    # Check for primitive array (inline format)
    if _is_primitive_array(arr):
        values = delimiter.join(_encode_primitive(v, delimiter) for v in arr)
        if name:
            lines.append(f"{indent}{name}[{len(arr)}]: {values}")
        else:
            lines.append(f"{indent}[{len(arr)}]: {values}")
        return

    # Mixed/nested array (list format)
    if name:
        lines.append(f"{indent}{name}[{len(arr)}]:")
    else:
        lines.append(f"{indent}[{len(arr)}]:")

    for item in arr:
        if isinstance(item, dict):
            # Nested object in list - encode with - prefix
            _encode_list_item_object(item, lines, depth + 1, delimiter)
        else:
            lines.append(f"{indent}  - {_encode_primitive(item, delimiter)}")


def _encode_list_item_object(
    obj: dict[str, Any],
    lines: list[str],
    depth: int,
    delimiter: str,
) -> None:
    """Encode an object as a list item (with - prefix for first line)."""
    indent = INDENT * depth
    first = True

    for k, v in obj.items():
        prefix = f"{indent}- " if first else f"{indent}  "
        first = False

        if isinstance(v, dict):
            # Nested object
            lines.append(f"{prefix}{k}:")
            for nk, nv in v.items():
                if isinstance(nv, dict | list):
                    _encode_value(nv, lines, depth + 2, delimiter, nk)
                else:
                    lines.append(f"{indent}    {nk}: {_encode_primitive(nv, delimiter)}")
        elif isinstance(v, list):
            lines.append(f"{prefix}{k}:")
            _encode_value(v, lines, depth + 2, delimiter, None)
        else:
            lines.append(f"{prefix}{k}: {_encode_primitive(v, delimiter)}")


def _encode_object(
    obj: dict[str, Any],
    lines: list[str],
    depth: int,
    delimiter: str,
    name: str | None,
) -> None:
    """Encode an object value."""
    indent = INDENT * depth

    if name:
        lines.append(f"{indent}{name}:")
        depth += 1
        indent = INDENT * depth

    for k, v in obj.items():
        if isinstance(v, dict):
            _encode_value(v, lines, depth, delimiter, k)
        elif isinstance(v, list):
            # Always encode lists (even empty ones) with array format
            _encode_value(v, lines, depth, delimiter, k)
        else:
            lines.append(f"{indent}{k}: {_encode_primitive(v, delimiter)}")


# Decode helpers

TABULAR_HEADER_RE = re.compile(r"^(\w*)\[(\d+)\]\{(.+)\}$")
PRIMITIVE_ARRAY_RE = re.compile(r"^(\w*)\[(\d+)\]:\s*(.*)$")
LIST_ARRAY_RE = re.compile(r"^(\w*)\[(\d+)\]:$")
KEY_VALUE_RE = re.compile(r"^([^:]+):\s*(.*)$")


def _get_indent_depth(line: str) -> int:
    """Get indentation depth (number of 2-space indents)."""
    stripped = line.lstrip(" ")
    spaces = len(line) - len(stripped)
    return spaces // 2


def _decode_array_field(
    lines: list[str],
    idx: int,
    depth: int,
    delimiter: str,
    lenient: bool,
) -> tuple[Any, int]:
    """Try to decode a line as an array field."""
    if idx >= len(lines):
        return None, idx

    line = lines[idx]
    stripped = line.strip()

    m = TABULAR_HEADER_RE.match(stripped)
    if m:
        return _decode_tabular_array(lines, idx, depth, delimiter, lenient, m)

    m = PRIMITIVE_ARRAY_RE.match(stripped)
    if m:
        values_part = m.group(3).strip()
        if values_part:
            return _decode_primitive_array(m, delimiter, idx)
        # Fall through to list array check if no inline values

    m = LIST_ARRAY_RE.match(stripped)
    if m:
        return _decode_list_array(lines, idx, depth, delimiter, lenient, m)

    return None, idx


def _decode_value(
    lines: list[str],
    idx: int,
    depth: int,
    delimiter: str,
    lenient: bool,
) -> tuple[Any, int]:
    """Decode a value from lines starting at idx."""
    if idx >= len(lines):
        return None, idx

    line = lines[idx]

    # Check indentation matches expected depth
    if _get_indent_depth(line) < depth:
        return None, idx

    stripped = line.strip()

    if not stripped or stripped.startswith("#"):
        return _decode_value(lines, idx + 1, depth, delimiter, lenient)

    # Check for array patterns
    # If it's a named array, treat as object start
    m = TABULAR_HEADER_RE.match(stripped)
    if m:
        if m.group(1):
            return _decode_object(lines, idx, depth, delimiter, lenient)
        return _decode_tabular_array(lines, idx, depth, delimiter, lenient, m)

    m = PRIMITIVE_ARRAY_RE.match(stripped)
    if m:
        values_part = m.group(3).strip()
        if values_part:
            if m.group(1):
                return _decode_object(lines, idx, depth, delimiter, lenient)
            return _decode_primitive_array(m, delimiter, idx)
        # Fall through to list array check

    m = LIST_ARRAY_RE.match(stripped)
    if m:
        if m.group(1):
            return _decode_object(lines, idx, depth, delimiter, lenient)
        return _decode_list_array(lines, idx, depth, delimiter, lenient, m)

    # Check for key:value (object)
    m = KEY_VALUE_RE.match(stripped)
    if m:
        return _decode_object(lines, idx, depth, delimiter, lenient)

    raise AGONTextError(f"Cannot parse line {idx}: {stripped}")


def _decode_tabular_array(
    lines: list[str],
    idx: int,
    depth: int,
    delimiter: str,
    lenient: bool,
    match: re.Match[str],
) -> tuple[Any, int]:
    """Decode tabular array: name[N]{fields}."""
    name = match.group(1)
    count = int(match.group(2))
    fields_str = match.group(3)
    fields = [f.strip() for f in fields_str.split(delimiter)]

    idx += 1
    result: list[dict[str, Any]] = []

    while idx < len(lines) and len(result) < count:
        row_line = lines[idx].strip()
        if not row_line or row_line.startswith("#"):
            idx += 1
            continue

        values = _split_row(row_line, delimiter)

        obj: dict[str, Any] = {}
        for i, field in enumerate(fields):
            if i < len(values):
                raw = values[i]
                val = _parse_primitive(raw)
                if val is not None or raw.strip():
                    obj[field] = val
        result.append(obj)
        idx += 1

    if len(result) < count and not lenient:
        raise AGONTextError(f"Expected {count} rows, got {len(result)}")

    if name:
        return {name: result}, idx
    return result, idx


def _split_row(values_str: str, delimiter: str) -> list[str]:
    """Split delimiter-separated values, respecting quotes."""
    result: list[str] = []
    current: list[str] = []
    in_quote = False
    i = 0

    while i < len(values_str):
        if values_str[i : i + len(delimiter)] == delimiter and not in_quote:
            result.append("".join(current))
            current = []
            i += len(delimiter)
            continue

        c = values_str[i]
        if c == '"' and not in_quote:
            in_quote = True
            current.append(c)
        elif c == '"' and in_quote:
            if i > 0 and values_str[i - 1] == "\\":
                current.append(c)
            else:
                in_quote = False
                current.append(c)
        else:
            current.append(c)
        i += 1

    result.append("".join(current))
    return result


def _decode_primitive_array(match: re.Match[str], delimiter: str, idx: int) -> tuple[Any, int]:
    """Decode primitive array: name[N]: v1<delim>v2..."""
    name = match.group(1)
    values_str = match.group(3)

    if not values_str.strip():
        arr: list[Any] = []
    else:
        values = _split_row(values_str, delimiter)
        arr = [_parse_primitive(v) for v in values]

    if name:
        return {name: arr}, idx + 1
    return arr, idx + 1


def _decode_list_array(
    lines: list[str],
    idx: int,
    depth: int,
    delimiter: str,
    lenient: bool,
    match: re.Match[str],
) -> tuple[Any, int]:
    """Decode list array: name[N]: followed by - items."""
    name = match.group(1)
    count = int(match.group(2))
    idx += 1
    result: list[Any] = []
    base_depth = depth + 1

    while idx < len(lines) and len(result) < count:
        line = lines[idx]
        if not line.strip() or line.strip().startswith("#"):
            idx += 1
            continue

        line_depth = _get_indent_depth(line)
        if line_depth < base_depth:
            break

        stripped = line.strip()
        if stripped.startswith("- "):
            # List item
            item_str = stripped[2:].strip()

            # Check if it's a key:value (nested object)
            kv_match = KEY_VALUE_RE.match(item_str)
            if kv_match:
                # Nested object starting with first key
                obj, idx = _decode_list_item_object(lines, idx, base_depth, delimiter, lenient)
                result.append(obj)
            else:
                result.append(_parse_primitive(item_str))
                idx += 1
        else:
            break

    # If array has a name, wrap in object
    if name:
        return {name: result}, idx
    return result, idx


def _decode_list_item_object(
    lines: list[str],
    idx: int,
    base_depth: int,
    delimiter: str,
    lenient: bool,
) -> tuple[dict[str, Any], int]:
    """Decode an object that starts with '- key: value'."""
    obj: dict[str, Any] = {}
    item_depth = base_depth  # The '- ' line depth

    # Parse first line (starts with -)
    first_line = lines[idx].strip()
    first_content = first_line[2:].strip()  # Remove '- '
    m = KEY_VALUE_RE.match(first_content)
    if m:
        key = m.group(1).strip()
        val_str = m.group(2).strip()
        if val_str:
            obj[key] = _parse_primitive(val_str)
        else:
            # Value is on subsequent lines - could be object, array, etc.
            idx += 1
            nested_val, idx = _decode_value(lines, idx, item_depth + 2, delimiter, lenient)
            obj[key] = nested_val if nested_val is not None else {}
            # Continue to parse more keys at item_depth + 1
            while idx < len(lines):
                line = lines[idx]
                if not line.strip():
                    idx += 1
                    continue
                line_depth = _get_indent_depth(line)
                if line_depth <= item_depth:
                    break
                stripped = line.strip()

                # Check for array patterns first
                nested, new_idx = _decode_array_field(lines, idx, line_depth, delimiter, lenient)
                if nested is not None:
                    if isinstance(nested, dict):
                        obj.update(nested)
                    idx = new_idx
                    continue

                kv = KEY_VALUE_RE.match(stripped)
                if kv:
                    k = kv.group(1).strip()
                    v_str = kv.group(2).strip()
                    if v_str:
                        obj[k] = _parse_primitive(v_str)
                    else:
                        idx += 1
                        nested, idx = _decode_value(lines, idx, line_depth + 1, delimiter, lenient)
                        obj[k] = nested if nested is not None else {}
                        continue
                idx += 1
            return obj, idx
    idx += 1

    # Parse continuation lines at deeper indent
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue
        line_depth = _get_indent_depth(line)
        if line_depth <= item_depth:
            break

        stripped = line.strip()
        # Check for array patterns first
        nested, new_idx = _decode_array_field(lines, idx, line_depth, delimiter, lenient)
        if nested is not None:
            if isinstance(nested, dict):
                obj.update(nested)
            idx = new_idx
            continue
        kv = KEY_VALUE_RE.match(stripped)
        if kv:
            key = kv.group(1).strip()
            val_str = kv.group(2).strip()
            if val_str:
                obj[key] = _parse_primitive(val_str)
                idx += 1
            else:
                # Nested value (could be object or array)
                idx += 1
                nested, idx = _decode_value(lines, idx, line_depth + 1, delimiter, lenient)
                obj[key] = nested if nested is not None else {}
        else:
            idx += 1

    return obj, idx


def _decode_object(
    lines: list[str],
    idx: int,
    depth: int,
    delimiter: str,
    lenient: bool,
) -> tuple[dict[str, Any], int]:
    """Decode an object from key:value pairs."""
    result: dict[str, Any] = {}
    if idx >= len(lines):
        return result, idx

    base_depth = _get_indent_depth(lines[idx])

    while idx < len(lines):
        line = lines[idx]
        if not line.strip() or line.strip().startswith("#"):
            idx += 1
            continue

        line_depth = _get_indent_depth(line)
        if line_depth < base_depth:
            break

        stripped = line.strip()

        # Check for array patterns first (they can match KEY_VALUE_RE falsely)
        # e.g., "filings[1]:" would match as key="filings[1]", value=""
        nested, new_idx = _decode_array_field(lines, idx, line_depth, delimiter, lenient)
        if nested is not None:
            # If it's a named array like {name: [...]} merge it
            if isinstance(nested, dict):
                result.update(nested)
            else:
                # Shouldn't happen for named arrays, but handle gracefully
                break
            idx = new_idx
            continue

        m = KEY_VALUE_RE.match(stripped)
        if not m:
            break

        key = m.group(1).strip()
        val_str = m.group(2).strip()

        if val_str:
            result[key] = _parse_primitive(val_str)
            idx += 1
        else:
            # No inline value - check for nested structure
            idx += 1
            if idx < len(lines):
                next_line = lines[idx]
                next_depth = _get_indent_depth(next_line)
                if next_depth > line_depth:
                    nested, idx = _decode_value(lines, idx, next_depth, delimiter, lenient)
                    result[key] = nested
                else:
                    result[key] = {}
            else:
                result[key] = {}

    return result, idx
