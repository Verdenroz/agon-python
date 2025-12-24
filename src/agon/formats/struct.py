"""AGONStruct format codec.

AGONStruct reduces token usage by defining reusable struct templates for repeated
object structures. Instead of repeating field names for every instance, define
the shape once and instantiate with just values.

Format structure:
    @AGON struct

    @StructName: field1, field2, field3?
    @ChildStruct(ParentStruct): extra_field

    <data using StructName(val1, val2, val3) syntax>

Example:
    @AGON struct

    @FR: fmt, raw

    - symbol: AAPL
      regularMarketPrice: FR(150.00, 150.0)
      regularMarketChange: FR(+2.50, 2.5)
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

from agon.errors import AGONStructError
from agon.formats.base import AGONFormat

HEADER = "@AGON struct"
INDENT = "  "

# Regex patterns
NUMBER_RE = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$")

# Struct definition: @StructName: field1, field2, field3?
# Or with inheritance: @ChildStruct(Parent1, Parent2): field1, field2
STRUCT_DEF_RE = re.compile(r"^@(\w+)(?:\(([^)]+)\))?:\s*(.*)$")

# Struct instantiation: StructName(val1, val2, val3)
STRUCT_INST_RE = re.compile(r"^(\w+)\(")

# Key-value pattern
KEY_VALUE_RE = re.compile(r"^([^:]+):\s*(.*)$")

# Array header pattern: name[N] or [N] (may have inline content after colon)
ARRAY_HEADER_RE = re.compile(r"^(\w*)\[(\d+)\]:?")

# Struct definition storage: {name: (fields, optional_fields, parents)}
StructDef = tuple[list[str], set[str], list[str]]
StructRegistry = dict[str, StructDef]


class AGONStruct(AGONFormat):
    """AGONStruct format encoder/decoder.

    Encodes JSON data using struct templates for repeated object structures.
    Significantly reduces tokens for data with consistent nested patterns.
    """

    @staticmethod
    def hint() -> str:
        """Return a short hint instructing LLMs how to generate this format."""
        return "Return in AGON struct format: Start with @AGON struct header, define templates as @Struct: fields, instantiate as Struct(v1, v2)"

    @staticmethod
    def encode(
        data: object,
        *,
        include_header: bool = True,
        min_occurrences: int = 3,
        min_fields: int = 2,
    ) -> str:
        """Encode data to AGONStruct format.

        Args:
            data: JSON-serializable data to encode.
            include_header: Whether to include @AGON struct header.
            min_occurrences: Minimum occurrences to create a struct (default: 3).
            min_fields: Minimum fields for a struct to be worthwhile (default: 2).

        Returns:
            AGONStruct encoded string.
        """
        # Detect repeated object shapes
        shapes = _detect_shapes(data)
        struct_defs = _create_struct_definitions(shapes, min_occurrences, min_fields)

        # Build registry for encoding
        registry: StructRegistry = {}
        for name, fields, optional, parents in struct_defs:
            _register_struct(registry, name, fields, optional, parents)

        lines: list[str] = []

        if include_header:
            lines.append(HEADER)
            lines.append("")

        # Emit struct definitions even when headers are disabled.
        # The header is used for auto-detect decoding, but LLM prompts need
        # the struct templates to interpret instances like FR(v1, v2).
        if struct_defs:
            for name, fields, optional, parents in struct_defs:
                fields_str = ", ".join(f + "?" if f in optional else f for f in fields)
                if parents:
                    parents_str = ", ".join(parents)
                    lines.append(f"@{name}({parents_str}): {fields_str}")
                else:
                    lines.append(f"@{name}: {fields_str}")

            lines.append("")

        _encode_value(data, lines, depth=0, registry=registry)

        return "\n".join(lines)

    @staticmethod
    def decode(payload: str, *, lenient: bool = False) -> Any:
        """Decode AGONStruct payload.

        Args:
            payload: AGONStruct encoded string.
            lenient: If True, allow best-effort parsing.

        Returns:
            Decoded Python value.

        Raises:
            AGONStructError: If payload is invalid.
        """
        lines = payload.splitlines()
        if not lines:
            raise AGONStructError("Empty payload")

        idx = 0
        header_line = lines[idx].strip()
        if not header_line.startswith("@AGON struct"):
            raise AGONStructError(f"Invalid header: {header_line}")
        idx += 1

        # Parse struct definitions
        registry: StructRegistry = {}
        while idx < len(lines):
            line = lines[idx].strip()
            if not line:
                idx += 1
                continue
            if not line.startswith("@"):
                break
            # Parse struct definition
            parsed = _parse_struct_def(line)
            if parsed:
                name, fields, optional, parents = parsed
                _register_struct(registry, name, fields, optional, parents)
            idx += 1

        # Skip blank lines
        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        if idx >= len(lines):
            return None

        result, _ = _decode_value(lines, idx, depth=0, registry=registry, lenient=lenient)
        return result


def _register_struct(
    registry: StructRegistry,
    name: str,
    fields: list[str],
    optional: set[str],
    parents: list[str],
) -> None:
    """Register a struct, resolving parent fields."""
    all_fields: list[str] = []
    all_optional: set[str] = set()

    # Resolve inherited fields from parents
    for parent_name in parents:
        parent = registry.get(parent_name)
        if parent is None:
            raise AGONStructError(f"Unknown parent struct: {parent_name}")
        parent_fields, parent_optional, _ = parent
        for f in parent_fields:
            if f not in all_fields:
                all_fields.append(f)
        all_optional.update(parent_optional)

    # Add own fields
    for f in fields:
        if f not in all_fields:
            all_fields.append(f)
    all_optional.update(optional)

    registry[name] = (all_fields, all_optional, parents)


def _detect_shapes(
    data: object,
    shapes: Counter[tuple[str, ...]] | None = None,
) -> Counter[tuple[str, ...]]:
    """Detect repeated object shapes in data."""
    if shapes is None:
        shapes = Counter()

    if isinstance(data, dict):
        # Only count shapes with primitive values
        primitive_keys: tuple[str, ...] = tuple(
            sorted(k for k, v in data.items() if not isinstance(v, dict | list))
        )
        if len(primitive_keys) >= 2:
            shapes[primitive_keys] += 1

        # Recurse into nested values
        for v in data.values():
            _detect_shapes(v, shapes)

    elif isinstance(data, list):
        for item in data:
            _detect_shapes(item, shapes)

    return shapes


def _create_struct_definitions(
    shapes: Counter[tuple[str, ...]],
    min_occurrences: int,
    min_fields: int,
) -> list[tuple[str, list[str], set[str], list[str]]]:
    """Create struct definitions from detected shapes.

    Returns list of (name, fields, optional_fields, parents).
    """
    struct_defs: list[tuple[str, list[str], set[str], list[str]]] = []
    used_names: set[str] = set()

    # Sort by frequency (most common first) then by field count (larger first)
    sorted_shapes = sorted(
        shapes.items(),
        key=lambda x: (-x[1], -len(x[0])),
    )

    for fields, count in sorted_shapes:
        if count < min_occurrences or len(fields) < min_fields:
            continue

        name = _generate_struct_name(fields, used_names)
        used_names.add(name)
        struct_defs.append((name, list(fields), set(), []))

    return struct_defs


def _generate_struct_name(fields: tuple[str, ...], used_names: set[str]) -> str:
    """Generate a struct name from field names."""
    field_set = set(fields)

    # Common patterns
    if field_set == {"fmt", "raw"}:
        name = "FR"
    elif field_set == {"low", "high"}:
        name = "Range"
    elif field_set == {"x", "y"}:
        name = "Point"
    elif field_set == {"lat", "lng"} or field_set == {"latitude", "longitude"}:
        name = "Coord"
    elif field_set == {"min", "max"}:
        name = "Bounds"
    elif len(fields) <= 3:
        name = "".join(f[0].upper() for f in fields[:3])
    else:
        name = "S"

    # Ensure unique
    base_name = name
    counter = 1
    while name in used_names:
        name = f"{base_name}{counter}"
        counter += 1

    return name


def _parse_struct_def(
    line: str,
) -> tuple[str, list[str], set[str], list[str]] | None:
    """Parse a struct definition line. Returns (name, fields, optional, parents)."""
    m = STRUCT_DEF_RE.match(line)
    if not m:
        return None

    name = m.group(1)
    parents_str = m.group(2)
    fields_str = m.group(3)

    parents: list[str] = []
    if parents_str:
        parents = [p.strip() for p in parents_str.split(",")]

    fields: list[str] = []
    optional: set[str] = set()

    if fields_str:
        for f in fields_str.split(","):
            f = f.strip()
            if f.endswith("?"):
                f = f[:-1]
                optional.add(f)
            if f:
                fields.append(f)

    return name, fields, optional, parents


def _can_use_struct(obj: dict[str, Any], fields: list[str], optional: set[str]) -> bool:
    """Check if an object can be encoded as a struct instance."""
    # Object must have only primitive values
    for v in obj.values():
        if isinstance(v, dict | list):
            return False

    # All required fields must be present
    obj_keys = set(obj.keys())
    required = set(fields) - optional

    if not required.issubset(obj_keys):
        return False

    # Object can only have fields from the struct
    return obj_keys.issubset(set(fields))


def _find_matching_struct(
    obj: dict[str, Any],
    registry: StructRegistry,
) -> tuple[str, list[str], set[str]] | None:
    """Find a struct that matches the object. Returns (name, fields, optional)."""
    for name, (fields, optional, _) in registry.items():
        if _can_use_struct(obj, fields, optional):
            return name, fields, optional
    return None


def _needs_quoting(s: str) -> bool:
    """Check if a string value needs quoting to preserve type."""
    if not s:
        return False
    # Quote if it looks like a number
    if NUMBER_RE.match(s):
        return True
    # Quote if it looks like bool/null
    lower = s.lower()
    if lower in ("true", "false", "null"):
        return True
    # Quote if has leading/trailing whitespace (would be stripped on decode)
    if s != s.strip():
        return True
    # Quote if contains special chars
    # ':' is included to avoid ambiguity with inline key-value parsing in lists.
    return "," in s or ":" in s or "(" in s or ")" in s or "\\" in s or "\n" in s or '"' in s


def _quote_string(s: str) -> str:
    """Quote and escape a string value."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{escaped}"'


def _encode_primitive(val: Any, *, for_struct_instance: bool = False) -> str:
    """Encode a primitive value to string.

    Args:
        val: The value to encode.
        for_struct_instance: If True, use empty string for None (struct instances
            can omit trailing None values). If False, use "null" explicitly
            to distinguish from nested objects in key-value pairs.
    """
    if val is None:
        return "" if for_struct_instance else "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int | float):
        if isinstance(val, float):
            if val != val:  # NaN
                return "" if for_struct_instance else "null"
            if val == float("inf") or val == float("-inf"):
                return "" if for_struct_instance else "null"
            if val == 0.0 and str(val) == "-0.0":
                return "0"
        return str(val)
    s = str(val)
    # Empty string must be quoted to distinguish from null
    if s == "":
        return '""'
    if _needs_quoting(s):
        return _quote_string(s)
    return s


def _unescape_value(s: str) -> str:
    """Unescape special characters from struct instance values."""
    if not s:
        return s
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            c = s[i + 1]
            if c == ",":
                result.append(",")
            elif c == "(":
                result.append("(")
            elif c == ")":
                result.append(")")
            elif c == "n":
                result.append("\n")
            elif c == "r":
                result.append("\r")
            elif c == "\\":
                result.append("\\")
            else:
                result.append(s[i + 1])
            i += 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def _encode_struct_instance(
    obj: dict[str, Any],
    name: str,
    fields: list[str],
    optional: set[str],
) -> str:
    """Encode an object as a struct instance."""
    values: list[str] = []

    # Find last non-optional provided value index
    last_idx = -1
    for i, field in enumerate(fields):
        if field not in optional or field in obj:
            last_idx = i

    for i, field in enumerate(fields):
        if i > last_idx:
            break
        val = obj.get(field)
        values.append(_encode_primitive(val, for_struct_instance=True))

    return f"{name}({', '.join(values)})"


def _encode_value(
    val: Any,
    lines: list[str],
    depth: int,
    registry: StructRegistry,
) -> None:
    """Encode a value, appending lines."""
    indent = INDENT * depth

    if val is None or isinstance(val, bool | int | float | str):
        lines.append(f"{indent}{_encode_primitive(val)}")
        return

    if isinstance(val, list):
        _encode_array(val, lines, depth, registry)
        return

    if isinstance(val, dict):
        _encode_object(val, lines, depth, registry, name=None)
        return

    lines.append(f"{indent}{_encode_primitive(str(val))}")


def _encode_array(
    arr: list[Any],
    lines: list[str],
    depth: int,
    registry: StructRegistry,
) -> None:
    """Encode an array value."""
    indent = INDENT * depth

    # Empty array - scar lesson: check count=0
    if not arr:
        lines.append(f"{indent}[0]:")
        return

    # Check if all items can be same struct instances
    all_same_struct = True
    struct_info: tuple[str, list[str], set[str]] | None = None
    for item in arr:
        if isinstance(item, dict):
            item_struct = _find_matching_struct(item, registry)
            if item_struct is None:
                all_same_struct = False
                break
            if struct_info is None:
                struct_info = item_struct
            elif struct_info[0] != item_struct[0]:
                all_same_struct = False
                break
        else:
            all_same_struct = False
            break

    # Inline struct instance array
    if all_same_struct and struct_info is not None:
        name, fields, optional = struct_info
        instances = [_encode_struct_instance(item, name, fields, optional) for item in arr]
        lines.append(f"{indent}[{len(arr)}]: {', '.join(instances)}")
        return

    # List format
    lines.append(f"{indent}[{len(arr)}]:")
    for item in arr:
        if isinstance(item, dict):
            _encode_list_item_object(item, lines, depth + 1, registry)
        elif isinstance(item, list):
            lines.append(f"{indent}  -")
            _encode_array(item, lines, depth + 2, registry)
        else:
            lines.append(f"{indent}  - {_encode_primitive(item)}")


def _encode_list_item_object(
    obj: dict[str, Any],
    lines: list[str],
    depth: int,
    registry: StructRegistry,
) -> None:
    """Encode an object as a list item."""
    indent = INDENT * depth
    first = True

    for k, v in obj.items():
        prefix = f"{indent}- " if first else f"{indent}  "
        first = False

        if isinstance(v, dict):
            struct_info = _find_matching_struct(v, registry)
            if struct_info:
                name, fields, optional = struct_info
                lines.append(f"{prefix}{k}: {_encode_struct_instance(v, name, fields, optional)}")
            else:
                lines.append(f"{prefix}{k}:")
                _encode_nested_object(v, lines, depth + 2, registry)
        elif isinstance(v, list):
            lines.append(f"{prefix}{k}:")
            _encode_array(v, lines, depth + 2, registry)
        else:
            lines.append(f"{prefix}{k}: {_encode_primitive(v)}")


def _encode_object(
    obj: dict[str, Any],
    lines: list[str],
    depth: int,
    registry: StructRegistry,
    name: str | None,
) -> None:
    """Encode an object value."""
    indent = INDENT * depth

    # Check if whole object can be a struct instance
    struct_info = _find_matching_struct(obj, registry)
    if struct_info and name:
        sname, fields, optional = struct_info
        lines.append(f"{indent}{name}: {_encode_struct_instance(obj, sname, fields, optional)}")
        return

    if name:
        lines.append(f"{indent}{name}:")
        depth += 1
        indent = INDENT * depth

    for k, v in obj.items():
        if isinstance(v, dict):
            nested_struct = _find_matching_struct(v, registry)
            if nested_struct:
                sname, fields, optional = nested_struct
                lines.append(f"{indent}{k}: {_encode_struct_instance(v, sname, fields, optional)}")
            else:
                lines.append(f"{indent}{k}:")
                _encode_nested_object(v, lines, depth + 1, registry)
        elif isinstance(v, list):
            lines.append(f"{indent}{k}:")
            _encode_array(v, lines, depth + 1, registry)
        else:
            lines.append(f"{indent}{k}: {_encode_primitive(v)}")


def _encode_nested_object(
    obj: dict[str, Any],
    lines: list[str],
    depth: int,
    registry: StructRegistry,
) -> None:
    """Encode a nested object without prefix."""
    indent = INDENT * depth

    for k, v in obj.items():
        if isinstance(v, dict):
            struct_info = _find_matching_struct(v, registry)
            if struct_info:
                sname, fields, optional = struct_info
                lines.append(f"{indent}{k}: {_encode_struct_instance(v, sname, fields, optional)}")
            else:
                lines.append(f"{indent}{k}:")
                _encode_nested_object(v, lines, depth + 1, registry)
        elif isinstance(v, list):
            lines.append(f"{indent}{k}:")
            _encode_array(v, lines, depth + 1, registry)
        else:
            lines.append(f"{indent}{k}: {_encode_primitive(v)}")


# Decode helpers


def _get_indent_depth(line: str) -> int:
    """Get indentation depth (number of 2-space indents)."""
    stripped = line.lstrip(" ")
    spaces = len(line) - len(stripped)
    return spaces // 2


def _unquote_string(s: str) -> str:
    """Unquote and unescape a quoted string value."""
    if not (s.startswith('"') and s.endswith('"')):
        return s
    inner = s[1:-1]
    result: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner):
            c = inner[i + 1]
            if c == "n":
                result.append("\n")
            elif c == "r":
                result.append("\r")
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


def _parse_primitive(s: str) -> Any:
    """Parse a primitive value from string."""
    s = s.strip()
    if not s:
        return None

    # Quoted string - preserve as string
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


def _parse_struct_instance(s: str, registry: StructRegistry) -> dict[str, Any] | None:
    """Parse a struct instance like StructName(val1, val2)."""
    m = STRUCT_INST_RE.match(s)
    if not m:
        return None

    struct_name = m.group(1)
    struct_def = registry.get(struct_name)
    if not struct_def:
        return None

    fields, optional, _ = struct_def

    # Find matching closing paren
    start = len(struct_name) + 1  # After "StructName("
    values = _parse_instance_values(s[start:])

    # Build object from values
    obj: dict[str, Any] = {}
    for i, field in enumerate(fields):
        if i < len(values):
            val_str = values[i].strip()
            if val_str:
                val_str = _unescape_value(val_str)
                obj[field] = _parse_primitive(val_str)
            elif field not in optional:
                obj[field] = None
        elif field not in optional:
            obj[field] = None

    return obj


def _parse_instance_values(s: str) -> list[str]:
    """Parse comma-separated values from inside parentheses."""
    values: list[str] = []
    current: list[str] = []
    depth = 0
    in_quotes = False
    i = 0

    while i < len(s):
        c = s[i]

        if c == "\\" and i + 1 < len(s):
            current.append(c)
            current.append(s[i + 1])
            i += 2
            continue

        if c == '"':
            in_quotes = not in_quotes
            current.append(c)
        elif c == "(" and not in_quotes:
            depth += 1
            current.append(c)
        elif c == ")" and not in_quotes:
            if depth == 0:
                values.append("".join(current))
                break
            depth -= 1
            current.append(c)
        elif c == "," and depth == 0 and not in_quotes:
            values.append("".join(current))
            current = []
        else:
            current.append(c)
        i += 1

    return values


def _decode_value(
    lines: list[str],
    idx: int,
    depth: int,
    registry: StructRegistry,
    lenient: bool,
) -> tuple[Any, int]:
    """Decode a value from lines starting at idx."""
    if idx >= len(lines):
        return None, idx

    line = lines[idx]
    stripped = line.strip()

    if not stripped:
        return _decode_value(lines, idx + 1, depth, registry, lenient)

    # Check for array header
    m = ARRAY_HEADER_RE.match(stripped)
    if m:
        return _decode_array(lines, idx, depth, registry, lenient, m)

    # Check for bullet list item
    if stripped.startswith("- "):
        return _decode_list_item_object(lines, idx, depth, registry, lenient)

    # Check for key: value
    m = KEY_VALUE_RE.match(stripped)
    if m:
        return _decode_object(lines, idx, depth, registry, lenient)

    # Try as struct instance
    inst = _parse_struct_instance(stripped, registry)
    if inst is not None:
        return inst, idx + 1

    return _parse_primitive(stripped), idx + 1


def _decode_array(
    lines: list[str],
    idx: int,
    depth: int,
    registry: StructRegistry,
    lenient: bool,
    match: re.Match[str],
) -> tuple[Any, int]:
    """Decode an array from [N]: header."""
    name = match.group(1)
    count = int(match.group(2))

    # Empty array - scar lesson
    if count == 0:
        if name:
            return {name: []}, idx + 1
        return [], idx + 1

    # Check for inline struct instances on same line
    line = lines[idx].strip()
    colon_idx = line.find(":")
    if colon_idx >= 0:
        after_colon = line[colon_idx + 1 :].strip()
        if after_colon and STRUCT_INST_RE.match(after_colon):
            instances = _split_struct_instances(after_colon)
            result: list[Any] = []
            for inst_str in instances:
                inst = _parse_struct_instance(inst_str.strip(), registry)
                if inst:
                    result.append(inst)
                else:
                    result.append(_parse_primitive(inst_str.strip()))
            if name:
                return {name: result}, idx + 1
            return result, idx + 1

    idx += 1
    result = []
    base_depth = depth + 1

    while idx < len(lines) and len(result) < count:
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue

        line_depth = _get_indent_depth(line)
        if line_depth < base_depth:
            break

        stripped = line.strip()

        if stripped.startswith("- "):
            content = stripped[2:].strip()
            inst = _parse_struct_instance(content, registry)
            if inst is not None:
                result.append(inst)
                idx += 1
                continue

            # If this is a quoted string list item, treat it as a primitive.
            # This avoids ambiguity with inline object syntax when the string
            # contains ':' (e.g. "keyword match: foo").
            if content.startswith('"') and content.endswith('"'):
                result.append(_parse_primitive(content))
                idx += 1
                continue

            kv = KEY_VALUE_RE.match(content)
            if kv:
                obj, idx = _decode_list_item_object(lines, idx, base_depth, registry, lenient)
                result.append(obj)
            else:
                result.append(_parse_primitive(content))
                idx += 1
        else:
            inst = _parse_struct_instance(stripped, registry)
            if inst is not None:
                result.append(inst)
            else:
                result.append(_parse_primitive(stripped))
            idx += 1

    if name:
        return {name: result}, idx
    return result, idx


def _split_struct_instances(s: str) -> list[str]:
    """Split a string of struct instances like 'FR(a, b), FR(c, d)'."""
    results: list[str] = []
    current: list[str] = []
    depth = 0
    in_quotes = False
    i = 0

    while i < len(s):
        c = s[i]

        # Handle escape sequences inside quotes
        if c == "\\" and i + 1 < len(s) and in_quotes:
            current.append(c)
            current.append(s[i + 1])
            i += 2
            continue

        if c == '"':
            in_quotes = not in_quotes
            current.append(c)
        elif c == "(" and not in_quotes:
            depth += 1
            current.append(c)
        elif c == ")" and not in_quotes:
            depth -= 1
            current.append(c)
            if depth == 0:
                results.append("".join(current).strip())
                current = []
        elif c == "," and depth == 0 and not in_quotes:
            if current:
                results.append("".join(current).strip())
                current = []
        else:
            current.append(c)
        i += 1

    if current:
        text = "".join(current).strip()
        if text:
            results.append(text)

    return results


def _decode_list_item_object(
    lines: list[str],
    idx: int,
    _base_depth: int,
    registry: StructRegistry,
    lenient: bool,
) -> tuple[dict[str, Any], int]:
    """Decode an object starting with '- key: value'."""
    obj: dict[str, Any] = {}
    line_depth = _get_indent_depth(lines[idx])

    first_line = lines[idx].strip()
    content = first_line[2:].strip() if first_line.startswith("- ") else first_line

    m = KEY_VALUE_RE.match(content)
    if m:
        key = m.group(1).strip()
        val_str = m.group(2).strip()

        if val_str:
            inst = _parse_struct_instance(val_str, registry)
            if inst is not None:
                obj[key] = inst
            else:
                obj[key] = _parse_primitive(val_str)
            idx += 1
        else:
            idx += 1
            if idx < len(lines) and _get_indent_depth(lines[idx]) > line_depth:
                nested, idx = _decode_value(lines, idx, line_depth + 1, registry, lenient)
                obj[key] = nested if nested is not None else {}
            else:
                obj[key] = {}
    else:
        idx += 1

    # Parse continuation lines
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue

        cont_depth = _get_indent_depth(line)
        if cont_depth <= line_depth:
            break

        stripped = line.strip()
        m = KEY_VALUE_RE.match(stripped)
        if not m:
            break

        key = m.group(1).strip()
        val_str = m.group(2).strip()

        if val_str:
            inst = _parse_struct_instance(val_str, registry)
            if inst is not None:
                obj[key] = inst
            else:
                obj[key] = _parse_primitive(val_str)
            idx += 1
        else:
            idx += 1
            if idx < len(lines) and _get_indent_depth(lines[idx]) > cont_depth:
                nested, idx = _decode_value(lines, idx, cont_depth + 1, registry, lenient)
                obj[key] = nested if nested is not None else {}
            else:
                obj[key] = {}

    return obj, idx


def _decode_object(
    lines: list[str],
    idx: int,
    _depth: int,
    registry: StructRegistry,
    lenient: bool,
) -> tuple[dict[str, Any], int]:
    """Decode an object from key: value pairs."""
    result: dict[str, Any] = {}
    if idx >= len(lines):
        return result, idx

    base_depth = _get_indent_depth(lines[idx])

    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue

        line_depth = _get_indent_depth(line)
        if line_depth < base_depth:
            break

        stripped = line.strip()

        # Check for array header
        m = ARRAY_HEADER_RE.match(stripped)
        if m:
            name = m.group(1)
            if name:
                nested, idx = _decode_array(lines, idx, line_depth, registry, lenient, m)
                if isinstance(nested, dict):
                    result.update(nested)
                continue

        m = KEY_VALUE_RE.match(stripped)
        if not m:
            break

        key = m.group(1).strip()
        val_str = m.group(2).strip()

        if val_str:
            inst = _parse_struct_instance(val_str, registry)
            if inst is not None:
                result[key] = inst
            else:
                result[key] = _parse_primitive(val_str)
            idx += 1
        else:
            idx += 1
            if idx < len(lines):
                next_depth = _get_indent_depth(lines[idx])
                if next_depth > line_depth:
                    nested, idx = _decode_value(lines, idx, next_depth, registry, lenient)
                    result[key] = nested
                else:
                    result[key] = {}
            else:
                result[key] = {}

    return result, idx
