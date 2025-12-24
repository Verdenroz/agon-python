# API Reference

Complete reference for all AGON methods and classes.

---

## AGON Class

The main entry point for encoding and decoding operations.

### AGON.encode()

Encode data to the optimal token-efficient format.

**Signature:**

```python
AGON.encode(
    data: object,
    format: Format = "auto",
    force: bool = False,
    min_savings: float = 0.10,
    encoding: str = "o200k_base"
) -> AGONEncoding
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `data` | `object` | *required* | JSON-serializable Python data to encode |
| `format` | `Format` | `"auto"` | Format to use: `"auto"`, `"json"`, `"text"`, `"columns"`, `"struct"` |
| `force` | `bool` | `False` | If True with `format="auto"`, never fall back to JSON |
| `min_savings` | `float` | `0.10` | Minimum token savings (0.0-1.0) required to use specialized format vs JSON |
| `encoding` | `str` | `"o200k_base"` | Token encoding to use for counting (tiktoken encoding name) |

**Returns:** `AGONEncoding` - Result object with encoded text and metadata

**Examples:**

=== "Auto Selection (Recommended)"

    ```python
    from agon import AGON

    data = [
        {"id": 1, "name": "Alice", "role": "admin"},
        {"id": 2, "name": "Bob", "role": "user"},
    ]

    # Auto-select best format
    result = AGON.encode(data, format="auto")
    print(f"Selected: {result.format}")  # → "text"
    print(f"Tokens: {AGON.count_tokens(result.text)}")
    print(result)  # Use directly in LLM prompts
    ```

=== "Specific Format"

    ```python
    # Force a specific format
    result_text = AGON.encode(data, format="text")
    result_columns = AGON.encode(data, format="columns")
    result_struct = AGON.encode(data, format="struct")
    result_json = AGON.encode(data, format="json")

    # Each returns AGONEncoding with the specified format
    ```

=== "Custom Threshold"

    ```python
    # Require 20% savings before using specialized format
    result = AGON.encode(data, format="auto", min_savings=0.20)

    # Lower threshold for aggressive optimization
    result = AGON.encode(data, format="auto", min_savings=0.05)
    ```

=== "Force Specialized Format"

    ```python
    # Never fall back to JSON, always use best specialized format
    result = AGON.encode(data, format="auto", force=True)

    # Useful when you know your data is structured
    # and want maximum token savings
    ```

---

### AGON.decode()

Decode AGON-encoded data back to original Python objects.

**Signatures:**

```python
# Overload 1: Decode AGONEncoding result
AGON.decode(payload: AGONEncoding) -> object

# Overload 2: Decode string with auto-detection
AGON.decode(payload: str, format: ConcreteFormat | None = None) -> object
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `payload` | `AGONEncoding \| str` | *required* | Encoded data to decode |
| `format` | `ConcreteFormat \| None` | `None` | Optional format override (`"json"`, `"text"`, `"columns"`, `"struct"`) |

**Returns:** `object` - Decoded Python data (list, dict, etc.)

**Examples:**

=== "Round-Trip Decode"

    ```python
    data = [{"id": 1, "name": "Alice"}]

    # Encode
    result = AGON.encode(data, format="text")

    # Decode - automatically uses result's format
    decoded = AGON.decode(result)
    assert decoded == data  # Lossless
    ```

=== "Auto-Detect from Header"

    ```python
    # AGON-encoded string with header
    agon_string = """@AGON text

    [2]{id	name}
    1	Alice
    2	Bob"""

    # Auto-detects "text" format from @AGON header
    decoded = AGON.decode(agon_string)
    # → [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    ```

=== "Explicit Format"

    ```python
    # Decode without header by specifying format
    agon_text_without_header = """[2]{id	name}
    1	Alice
    2	Bob"""

    decoded = AGON.decode(agon_text_without_header, format="text")
    # → [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    ```

---

### AGON.project_data()

Filter data to keep only specific fields, supporting dotted paths for nested access.

**Signature:**

```python
AGON.project_data(
    data: list[dict],
    keep_paths: list[str]
) -> list[dict]
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `data` | `list[dict]` | List of dictionaries to filter |
| `keep_paths` | `list[str]` | List of field paths to keep (supports dot notation) |

**Returns:** `list[dict]` - Filtered data with only specified fields

**Examples:**

=== "Simple Fields"

    ```python
    data = [
        {"id": 1, "name": "Alice", "email": "alice@example.com", "age": 28},
        {"id": 2, "name": "Bob", "email": "bob@example.com", "age": 32},
    ]

    # Keep only id and name
    projected = AGON.project_data(data, ["id", "name"])
    # → [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    ```

=== "Nested Paths"

    ```python
    data = [
        {
            "user": {
                "profile": {"name": "Alice", "age": 28},
                "settings": {"theme": "dark"}
            },
            "status": "active"
        }
    ]

    # Extract nested fields with dot notation
    projected = AGON.project_data(data, ["user.profile.name", "status"])
    # → [{"user": {"profile": {"name": "Alice"}}, "status": "active"}]
    ```

=== "Array Fields"

    ```python
    data = [
        {
            "type": "DAY_GAINERS",
            "quotes": [
                {"symbol": "AAPL", "price": 150.0, "volume": 1000000},
                {"symbol": "GOOGL", "price": 2800.0, "volume": 500000}
            ]
        }
    ]

    # Project fields from nested arrays
    projected = AGON.project_data(data, ["quotes.symbol", "quotes.price"])
    # → [{"quotes": [{"symbol": "AAPL", "price": 150.0},
    #                {"symbol": "GOOGL", "price": 2800.0}]}]
    ```

!!! tip "Use Before Encoding"

    Project data before encoding to reduce token count further:

    ```python
    # Filter to essential fields, then encode
    projected = AGON.project_data(full_data, ["id", "name", "score"])
    result = AGON.encode(projected, format="auto")
    ```

---

### AGON.hint()

Get prescriptive generation instructions for LLMs (experimental feature for asking LLMs to return AGON-formatted data).

**Signature:**

```python
AGON.hint(
    result_or_format: AGONEncoding | ConcreteFormat
) -> str
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `result_or_format` | `AGONEncoding \| ConcreteFormat` | Encoding result or format name (`"text"`, `"columns"`, `"struct"`, `"json"`) |

**Returns:** `str` - Prescriptive hint instructing how to generate the format

**Examples:**

=== "From Encoding Result"

    ```python
    data = [{"id": 1, "name": "Alice"}]
    result = AGON.encode(data, format="auto")

    # Get hint for the selected format
    hint = AGON.hint(result)
    print(hint)
    # → "Return in AGON text format: Start with @AGON text header,
    #    encode arrays as name[N]{fields} with tab-delimited rows"
    ```

=== "From Format Name"

    ```python
    # Get hint for specific format
    hint_text = AGON.hint("text")
    hint_columns = AGON.hint("columns")
    hint_struct = AGON.hint("struct")
    ```

=== "Use in LLM Prompts"

    ```python
    data = [{"id": 1, "name": "Alice", "role": "admin"}]
    result = AGON.encode(data, format="auto")

    # Ask LLM to respond in AGON format
    prompt = f"""Analyze this data and return enriched results in AGON format.

    Instructions: {AGON.hint(result)}

    Example output:
    {result.with_header()}

    Task: Add a "seniority" field (junior/mid/senior) based on role.
    """
    ```

!!! warning "Experimental Feature"

    LLMs have **not** been trained on AGON format, so generation accuracy cannot be guaranteed. This is experimental—always validate LLM-generated AGON data.

    **Prefer:** Sending AGON to LLMs (reliable)
    **Over:** Asking LLMs to generate AGON (experimental)

---

### AGON.count_tokens()

Count tokens in text using the specified encoding.

**Signature:**

```python
AGON.count_tokens(
    text: str,
    encoding: str = "o200k_base"
) -> int
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | *required* | Text to count tokens for |
| `encoding` | `str` | `"o200k_base"` | Tiktoken encoding name |

**Returns:** `int` - Number of tokens

**Example:**

```python
text = "Hello, world!"
tokens = AGON.count_tokens(text)
print(f"Tokens: {tokens}")  # → 4

# Use different encoding
tokens_gpt4 = AGON.count_tokens(text, encoding="cl100k_base")
```

---

## AGONEncoding Class

Result object returned by `AGON.encode()`.

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `format` | `ConcreteFormat` | Format used: `"json"`, `"text"`, `"columns"`, `"struct"` |
| `text` | `str` | Encoded output (ready for LLM prompts) |
| `header` | `str` | Format header (e.g., `"@AGON text"`) |

**Methods:**

### \_\_str\_\_()

Returns the encoded text (without header) for direct use in prompts.

```python
result = AGON.encode(data, format="text")
prompt = f"Analyze this data:\n\n{result}"  # Converts to string via __str__()
```

### \_\_len\_\_()

Returns character count of the encoded text.

```python
result = AGON.encode(data, format="text")
char_count = len(result)  # Character count
```

### \_\_repr\_\_()

Returns debug representation.

```python
result = AGON.encode(data, format="text")
print(repr(result))
# → AGONEncoding(format='text', length=45)
```

### with_header()

Returns encoded text with header prepended (for auto-detect decoding).

```python
result = AGON.encode(data, format="text")

# Without header (for sending to LLM)
print(result.text)
# → [2]{id	name}
#   1	Alice
#   2	Bob

# With header (for decoding)
print(result.with_header())
# → @AGON text
#
#   [2]{id	name}
#   1	Alice
#   2	Bob
```

**Use cases:**

- **Without header** (`result.text` or `str(result)`): Send to LLM prompts
- **With header** (`result.with_header()`): Store for later decoding, or ask LLM to return in same format

---

## Format-Specific Encoders

For advanced use cases, you can access format-specific encoders directly.

### AGONText

```python
from agon.formats import AGONText

# Direct encoding with custom options
encoded = AGONText.encode(
    data,
    delimiter="\t",  # Default: tab
    include_header=False  # Default: False
)

# Direct decoding
decoded = AGONText.decode(encoded)
```

### AGONColumns

```python
from agon.formats import AGONColumns

# Direct encoding
encoded = AGONColumns.encode(
    data,
    delimiter="\t",  # Default: tab
    include_header=False
)

decoded = AGONColumns.decode(encoded)
```

### AGONStruct

```python
from agon.formats import AGONStruct

# Direct encoding
encoded = AGONStruct.encode(
    data,
    include_header=False
)

decoded = AGONStruct.decode(encoded)
```

!!! info "When to Use Direct Encoders"

    Use direct format encoders when:

    - You want guaranteed format selection (bypass auto mode)
    - You need format-specific options (custom delimiters)
    - You're benchmarking or comparing formats

    For most use cases, `AGON.encode(data, format="text")` is preferred.

---

## Error Handling

AGON defines a hierarchy of exceptions for error handling.

### AGONError

Base exception for all AGON errors.

```python
from agon import AGONError

try:
    result = AGON.encode(data, format="auto")
except AGONError as e:
    print(f"AGON error: {e}")
```

### Format-Specific Exceptions

- `AGONTextError` - Errors specific to AGONText format
- `AGONColumnsError` - Errors specific to AGONColumns format
- `AGONStructError` - Errors specific to AGONStruct format

```python
from agon import AGONTextError, AGONColumnsError, AGONStructError

try:
    result = AGON.decode(malformed_agon_text, format="text")
except AGONTextError as e:
    print(f"Text format error: {e}")
```

---

## Constants & Defaults

| Constant | Value | Description |
|----------|-------|-------------|
| `DEFAULT_ENCODING` | `"o200k_base"` | Default token encoding (GPT-4, GPT-4 Turbo) |
| `DEFAULT_DELIMITER` | `"\t"` | Default field delimiter (tab character) |
| `DEFAULT_MIN_SAVINGS` | `0.10` | Default minimum token savings threshold (10%) |

---

## Type Aliases

```python
from agon import Format, ConcreteFormat

# Format includes "auto"
Format = Literal["auto", "json", "text", "columns", "struct"]

# ConcreteFormat excludes "auto" (actual encoding formats)
ConcreteFormat = Literal["json", "text", "columns", "struct"]
```

---

## Next Steps

### [JSON Fallback](formats/json.md)

View how JSON is used as a safety net

### [AGONText Format](formats/text.md)

Complete guide to row-based encoding

### [Core Concepts](concepts.md)

Understand AGON's adaptive approach and design principles

### [Benchmarks](benchmarks.md)

See real-world performance across multiple datasets
