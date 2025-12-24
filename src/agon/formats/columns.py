r"""AGONColumns format codec.

AGONColumns is a columnar encoding that transposes data to group by column (type)
instead of row. This provides better token efficiency for wide tables with
many columns of the same type.

Format structure:
    @AGON columns
    @D=<delimiter>  # optional, default: \t
    <data>

Example:
    @AGON columns

    products[3]
    ├ sku: A123, B456, C789
    ├ name: Widget, Gadget, Gizmo
    └ price: 9.99, 19.99, 29.99
"""

from __future__ import annotations

import re
from typing import Any

from agon.errors import AGONColumnsError
from agon.formats.base import AGONFormat

HEADER = "@AGON columns"
DEFAULT_DELIMITER = "\t"
INDENT = "  "

# Tree drawing characters
BRANCH = "├"  # U+251C: has more siblings
LAST_BRANCH = "└"  # U+2514: last sibling
ASCII_BRANCH = "|"
ASCII_LAST = "`"

# Characters that require quoting
SPECIAL_CHARS = frozenset(["@", "#", "-", BRANCH, LAST_BRANCH, ASCII_BRANCH])
BOOL_NULL = frozenset(["true", "false", "null"])

# Regex for numbers
NUMBER_RE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")


class AGONColumns(AGONFormat):
    """AGONColumns format encoder/decoder.

    Encodes JSON data to a columnar format where array fields are transposed
    to show all values of each field together, optimizing for type clustering.
    """

    @staticmethod
    def hint() -> str:
        """Return a short hint instructing LLMs how to generate this format."""
        return "Return in AGON columns format: Start with @AGON columns header, transpose arrays to name[N] with ├/└ field: val1, val2, ..."

    @staticmethod
    def encode(
        data: object,
        *,
        delimiter: str = DEFAULT_DELIMITER,
        include_header: bool = True,
        use_ascii: bool = False,
    ) -> str:
        """Encode data to AGONColumns format.

        Args:
            data: JSON-serializable data to encode.
            delimiter: Value delimiter within columns (default: ", ").
            include_header: Whether to include @AGON columns header.
            use_ascii: Use ASCII tree chars (|, `) instead of Unicode.

        Returns:
            AGONColumns encoded string.
        """
        lines: list[str] = []

        if include_header:
            lines.append(HEADER)
            if delimiter != DEFAULT_DELIMITER:
                lines.append(f"@D={_escape_delimiter(delimiter)}")
            lines.append("")

        _encode_value(data, lines, depth=0, delimiter=delimiter, name=None, use_ascii=use_ascii)

        return "\n".join(lines)

    @staticmethod
    def decode(payload: str, *, lenient: bool = False) -> Any:
        """Decode AGONColumns payload.

        Args:
            payload: AGONColumns encoded string.
            lenient: If True, allow length mismatches and best-effort parsing.

        Returns:
            Decoded Python value.

        Raises:
            AGONColumnsError: If payload is invalid.
        """
        lines = payload.splitlines()
        if not lines:
            raise AGONColumnsError("Empty payload")

        idx = 0
        header_line = lines[idx].strip()
        if not header_line.startswith("@AGON columns"):
            raise AGONColumnsError(f"Invalid header: {header_line}")
        idx += 1

        delimiter = DEFAULT_DELIMITER
        if idx < len(lines) and lines[idx].startswith("@D="):
            delimiter = _parse_delimiter(lines[idx][3:].strip())
            idx += 1

        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        if idx >= len(lines):
            return None

        result, _ = _decode_value(lines, idx, depth=0, delimiter=delimiter, lenient=lenient)
        return result


def _escape_delimiter(d: str) -> str:
    """Escape delimiter for @D= declaration."""
    if d == "\t":
        return "\\t"
    if d == "\n":
        return "\\n"
    # Unreachable via public API: DEFAULT_DELIMITER is ", " and encode() only calls
    # _escape_delimiter() when delimiter != DEFAULT_DELIMITER.
    if d == ", ":  # pragma: no cover
        return ", "
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
    if s != s.strip():
        return True
    if delimiter in s:
        return True
    if "\n" in s or "\r" in s or "\\" in s or '"' in s:
        return True
    if s[0] in SPECIAL_CHARS:
        return True
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
        if isinstance(val, float):
            if val != val:  # NaN
                return ""
            if val == float("inf") or val == float("-inf"):
                return ""
            if val == 0.0 and str(val) == "-0.0":
                return "0"
        return str(val)
    s = str(val)
    if _needs_quote(s, delimiter):
        return _quote_string(s)
    return s


def _parse_primitive(s: str) -> Any:
    """Parse a primitive value from string."""
    s = s.strip()
    if not s:
        return None

    if s.startswith('"') and s.endswith('"'):
        return _unquote_string(s)

    lower = s.lower()
    if lower == "null":
        return None
    if lower == "true":
        return True
    if lower == "false":
        return False

    if NUMBER_RE.match(s):
        if "." in s or "e" in s.lower():
            return float(s)
        return int(s)

    return s


def _is_columnar_array(arr: list[Any]) -> tuple[bool, list[str]]:
    """Check if array can be encoded in columnar format."""
    if not arr:
        return False, []

    if not all(isinstance(x, dict) for x in arr):
        return False, []

    all_keys: set[str] = set()
    for obj in arr:
        all_keys.update(obj.keys())

    if not all_keys:
        return False, []

    for obj in arr:
        for v in obj.values():
            if isinstance(v, dict | list):
                return False, []

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
    use_ascii: bool,
) -> None:
    """Encode a value, appending lines."""
    indent = INDENT * depth

    if val is None or isinstance(val, bool | int | float | str):
        if name:
            lines.append(f"{indent}{name}: {_encode_primitive(val, delimiter)}")
        else:
            lines.append(f"{indent}{_encode_primitive(val, delimiter)}")
        return

    if isinstance(val, list):
        _encode_array(val, lines, depth, delimiter, name, use_ascii)
        return

    if isinstance(val, dict):
        _encode_object(val, lines, depth, delimiter, name, use_ascii)
        return

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
    use_ascii: bool,
) -> None:
    """Encode an array value in columnar format."""
    indent = INDENT * depth
    branch = ASCII_BRANCH if use_ascii else BRANCH
    last = ASCII_LAST if use_ascii else LAST_BRANCH

    if not arr:
        if name:
            lines.append(f"{indent}{name}[0]")
        else:
            lines.append(f"{indent}[0]")
        return

    is_columnar, fields = _is_columnar_array(arr)
    if is_columnar and fields:
        if name:
            lines.append(f"{indent}{name}[{len(arr)}]")
        else:
            lines.append(f"{indent}[{len(arr)}]")

        for i, field in enumerate(fields):
            tree_char = last if i == len(fields) - 1 else branch
            values = [
                (_encode_primitive(obj[field], delimiter) if field in obj else "") for obj in arr
            ]
            lines.append(f"{indent}{tree_char} {field}: {delimiter.join(values)}")
        return

    if _is_primitive_array(arr):
        values = delimiter.join(_encode_primitive(v, delimiter) for v in arr)
        if name:
            lines.append(f"{indent}{name}[{len(arr)}]: {values}")
        else:
            lines.append(f"{indent}[{len(arr)}]: {values}")
        return

    if name:
        lines.append(f"{indent}{name}[{len(arr)}]:")
    else:
        lines.append(f"{indent}[{len(arr)}]:")

    for item in arr:
        if isinstance(item, dict):
            _encode_list_item_object(item, lines, depth + 1, delimiter, use_ascii)
        else:
            lines.append(f"{indent}  - {_encode_primitive(item, delimiter)}")


def _encode_list_item_object(
    obj: dict[str, Any],
    lines: list[str],
    depth: int,
    delimiter: str,
    use_ascii: bool,
) -> None:
    """Encode an object as a list item."""
    indent = INDENT * depth
    first = True

    for k, v in obj.items():
        prefix = f"{indent}- " if first else f"{indent}  "
        first = False

        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            for nk, nv in v.items():
                if isinstance(nv, dict | list):
                    _encode_value(nv, lines, depth + 2, delimiter, nk, use_ascii)
                else:
                    lines.append(f"{indent}    {nk}: {_encode_primitive(nv, delimiter)}")
        elif isinstance(v, list):
            lines.append(f"{prefix}{k}:")
            _encode_value(v, lines, depth + 2, delimiter, None, use_ascii)
        else:
            lines.append(f"{prefix}{k}: {_encode_primitive(v, delimiter)}")


def _encode_object(
    obj: dict[str, Any],
    lines: list[str],
    depth: int,
    delimiter: str,
    name: str | None,
    use_ascii: bool,
) -> None:
    """Encode an object value."""
    indent = INDENT * depth

    if name:
        lines.append(f"{indent}{name}:")
        depth += 1
        indent = INDENT * depth

    for k, v in obj.items():
        if isinstance(v, dict | list):
            _encode_value(v, lines, depth, delimiter, k, use_ascii)
        else:
            lines.append(f"{indent}{k}: {_encode_primitive(v, delimiter)}")


# Decode helpers

ARRAY_HEADER_RE = re.compile(r"^(\w*)\[(\d+)\]$")
PRIMITIVE_ARRAY_RE = re.compile(r"^(\w*)\[(\d+)\]:\s*(.*)$")
LIST_ARRAY_RE = re.compile(r"^(\w*)\[(\d+)\]:$")
KEY_VALUE_RE = re.compile(r"^([^:]+):\s*(.*)$")
COLUMN_LINE_RE = re.compile(r"^[├└|`]\s*([^:]+):\s*(.*)$")

_MISSING_CELL = object()


def _get_indent_depth(line: str) -> int:
    """Get indentation depth (number of 2-space indents)."""
    stripped = line.lstrip(" ")
    spaces = len(line) - len(stripped)
    return spaces // 2


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
    stripped = line.strip()

    if not stripped or stripped.startswith("#"):
        return _decode_value(lines, idx + 1, depth, delimiter, lenient)

    # Check for columnar array: name[N] (no braces, no colon with inline values)
    m = ARRAY_HEADER_RE.match(stripped)
    if m:
        count = int(m.group(2))
        # Empty array case
        if count == 0:
            name = m.group(1)
            if name:
                return _decode_nested_object(
                    lines, idx, _get_indent_depth(line), delimiter, lenient
                )
            return [], idx + 1
        next_idx = idx + 1
        if next_idx < len(lines):
            next_line = lines[next_idx].strip()
            if next_line and (next_line[0] in (BRANCH, LAST_BRANCH, ASCII_BRANCH, ASCII_LAST)):
                if m.group(1):
                    return _decode_nested_object(
                        lines, idx, _get_indent_depth(line), delimiter, lenient
                    )
                return _decode_columnar_array(lines, idx, depth, delimiter, lenient, m)

    # Check for primitive array: name[N]: val1, val2, ...
    m = PRIMITIVE_ARRAY_RE.match(stripped)
    if m:
        values_part = m.group(3).strip()
        if values_part:
            if m.group(1):
                return _decode_nested_object(
                    lines, idx, _get_indent_depth(line), delimiter, lenient
                )
            return _decode_primitive_array(m, delimiter, idx)

    # Check for list array: name[N]:
    m = LIST_ARRAY_RE.match(stripped)
    if m:
        if m.group(1):
            return _decode_nested_object(lines, idx, _get_indent_depth(line), delimiter, lenient)
        return _decode_list_array(lines, idx, depth, delimiter, lenient, m)

    # Check for key:value (object)
    m = KEY_VALUE_RE.match(stripped)
    if m:
        return _decode_nested_object(lines, idx, _get_indent_depth(line), delimiter, lenient)

    raise AGONColumnsError(f"Cannot parse line {idx}: {stripped}")


def _decode_columnar_array(
    lines: list[str],
    idx: int,
    depth: int,
    delimiter: str,
    lenient: bool,
    match: re.Match[str],
) -> tuple[Any, int]:
    """Decode columnar array: name[N] followed by ├/└ field: values."""
    name = match.group(1)
    count = int(match.group(2))
    idx += 1

    columns: dict[str, list[Any]] = {}
    field_order: list[str] = []

    def _parse_columnar_cell(cell: str) -> Any:
        # In columnar arrays, an empty cell means “key absent”, while the
        # literal token "null" means the key is present with value None.
        if not cell.strip():
            return _MISSING_CELL
        return _parse_primitive(cell)

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if not stripped:
            idx += 1
            continue

        if stripped.startswith("#"):
            idx += 1
            continue

        m = COLUMN_LINE_RE.match(stripped)
        if not m:
            break

        field = m.group(1).strip()
        # Don't strip trailing whitespace - it's part of the delimiter for empty values
        values_str = m.group(2).lstrip()

        values = _split_column_values(values_str, delimiter)
        columns[field] = [_parse_columnar_cell(v) for v in values]
        field_order.append(field)
        idx += 1

    result: list[dict[str, Any]] = []
    for row_idx in range(count):
        obj: dict[str, Any] = {}
        for field in field_order:
            vals = columns.get(field, [])
            val = vals[row_idx] if row_idx < len(vals) else _MISSING_CELL
            if val is not _MISSING_CELL:
                obj[field] = val
        result.append(obj)

    if name:
        return {name: result}, idx
    return result, idx


def _split_column_values(values_str: str, delimiter: str) -> list[str]:
    """Split column values, respecting quotes."""
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


def _decode_primitive_array(
    match: re.Match[str],
    delimiter: str,
    idx: int,
) -> tuple[Any, int]:
    """Decode primitive array: name[N]: val1, val2, ..."""
    name = match.group(1)
    values_str = match.group(3)

    if not values_str.strip():
        arr: list[Any] = []
    else:
        values = _split_column_values(values_str, delimiter)
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
            item_str = stripped[2:].strip()
            kv_match = KEY_VALUE_RE.match(item_str)
            if kv_match:
                obj, idx = _decode_list_item_object(lines, idx, base_depth, delimiter, lenient)
                result.append(obj)
            else:
                result.append(_parse_primitive(item_str))
                idx += 1
        else:
            break

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
    item_depth = base_depth

    first_line = lines[idx].strip()
    first_content = first_line[2:].strip()
    m = KEY_VALUE_RE.match(first_content)
    if m:
        key = m.group(1).strip()
        val_str = m.group(2).strip()
        if val_str:
            obj[key] = _parse_primitive(val_str)
        else:
            idx += 1
            while idx < len(lines) and (
                not lines[idx].strip() or lines[idx].strip().startswith("#")
            ):
                idx += 1
            if idx < len(lines):
                next_line = lines[idx]
                next_depth = _get_indent_depth(next_line)
                if next_depth >= item_depth + 2:
                    val, idx = _decode_value(lines, idx, next_depth, delimiter, lenient)
                    obj[key] = val
                else:
                    obj[key] = {}
            else:
                obj[key] = {}
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
                if (
                    ARRAY_HEADER_RE.match(stripped)
                    or PRIMITIVE_ARRAY_RE.match(stripped)
                    or LIST_ARRAY_RE.match(stripped)
                ):
                    nested, idx = _decode_value(lines, idx, line_depth, delimiter, lenient)
                    if isinstance(nested, dict):
                        obj.update(nested)
                    continue

                kv = KEY_VALUE_RE.match(stripped)
                if kv:
                    k = kv.group(1).strip()
                    v_str = kv.group(2).strip()
                    if v_str:
                        obj[k] = _parse_primitive(v_str)
                    else:
                        idx += 1
                        while idx < len(lines) and (
                            not lines[idx].strip() or lines[idx].strip().startswith("#")
                        ):
                            idx += 1
                        if idx < len(lines):
                            next_line = lines[idx]
                            next_depth = _get_indent_depth(next_line)
                            if next_depth > line_depth:
                                val, idx = _decode_value(lines, idx, next_depth, delimiter, lenient)
                                obj[k] = val
                            else:
                                obj[k] = {}
                        else:
                            obj[k] = {}
                        continue
                idx += 1
            return obj, idx
    idx += 1

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
        m = ARRAY_HEADER_RE.match(stripped)
        if m:
            count = int(m.group(2))
            if count == 0:
                name = m.group(1)
                if name:
                    obj[name] = []
                idx += 1
                continue
            next_idx = idx + 1
            if next_idx < len(lines):
                next_line = lines[next_idx].strip()
                if next_line and (next_line[0] in (BRANCH, LAST_BRANCH, ASCII_BRANCH, ASCII_LAST)):
                    nested, idx = _decode_columnar_array(
                        lines, idx, line_depth, delimiter, lenient, m
                    )
                    if isinstance(nested, dict):
                        obj.update(nested)
                    continue

        m = LIST_ARRAY_RE.match(stripped)
        if m:
            nested, idx = _decode_list_array(lines, idx, line_depth, delimiter, lenient, m)
            if isinstance(nested, dict):
                obj.update(nested)
            continue

        m = PRIMITIVE_ARRAY_RE.match(stripped)
        if m:
            nested, idx = _decode_primitive_array(m, delimiter, idx)
            if isinstance(nested, dict):
                obj.update(nested)
            continue

        kv = KEY_VALUE_RE.match(stripped)
        if kv:
            key = kv.group(1).strip()
            val_str = kv.group(2).strip()
            if val_str:
                obj[key] = _parse_primitive(val_str)
                idx += 1
            else:
                idx += 1
                while idx < len(lines) and (
                    not lines[idx].strip() or lines[idx].strip().startswith("#")
                ):
                    idx += 1
                if idx < len(lines):
                    next_line = lines[idx]
                    next_depth = _get_indent_depth(next_line)
                    if next_depth > line_depth:
                        val, idx = _decode_value(lines, idx, next_depth, delimiter, lenient)
                        obj[key] = val
                    else:
                        obj[key] = {}
                else:
                    obj[key] = {}
        else:
            idx += 1

    return obj, idx


def _decode_nested_object(
    lines: list[str],
    idx: int,
    expected_depth: int,
    delimiter: str,
    lenient: bool,
) -> tuple[dict[str, Any], int]:
    """Decode a nested object at a specific indent level."""
    obj: dict[str, Any] = {}

    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue

        line_depth = _get_indent_depth(line)
        if line_depth < expected_depth:
            break

        stripped = line.strip()

        # Check for array patterns first
        m = ARRAY_HEADER_RE.match(stripped)
        if m:
            nested, idx = _decode_columnar_array(lines, idx, line_depth, delimiter, lenient, m)
            if isinstance(nested, dict):
                obj.update(nested)
            continue

        m = LIST_ARRAY_RE.match(stripped)
        if m:
            nested, idx = _decode_list_array(lines, idx, line_depth, delimiter, lenient, m)
            if isinstance(nested, dict):
                obj.update(nested)
            continue

        m = PRIMITIVE_ARRAY_RE.match(stripped)
        if m:
            nested, idx = _decode_primitive_array(m, delimiter, idx)
            if isinstance(nested, dict):
                obj.update(nested)
            continue

        kv = KEY_VALUE_RE.match(stripped)
        if kv:
            key = kv.group(1).strip()
            val_str = kv.group(2).strip()
            if val_str:
                obj[key] = _parse_primitive(val_str)
                idx += 1
            else:
                idx += 1
                while idx < len(lines) and (
                    not lines[idx].strip() or lines[idx].strip().startswith("#")
                ):
                    idx += 1
                if idx < len(lines):
                    next_line = lines[idx]
                    next_depth = _get_indent_depth(next_line)
                    if next_depth > line_depth:
                        val, idx = _decode_value(lines, idx, next_depth, delimiter, lenient)
                        obj[key] = val
                    else:
                        obj[key] = {}
                else:
                    obj[key] = {}
        else:
            break

    return obj, idx
