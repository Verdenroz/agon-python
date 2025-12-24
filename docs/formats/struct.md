# AGONStruct Format

Template-based encoding for repeated nested patterns—eliminates redundant field names.

---

## Overview

AGONStruct is a **template-based encoding format** that defines reusable struct definitions for repeated object structures. Instead of repeating field names in every instance, you define the shape once and instantiate with just values.

**Best for:**

- Repeated nested patterns (e.g., `{fmt, raw}` everywhere)
- Market data with formatted/raw value pairs
- Timestamps with values (`{time, value}`)
- 3+ occurrences of the same 2+ field structure

**Token efficiency:** 30-50% savings vs pretty JSON, 10-30% vs compact JSON (when pattern repeats ≥3 times)

---

## Basic Example

Let's encode market data with a repeated `{fmt, raw}` pattern:

=== "Input (JSON)"

    ```json
    {
      "price": {"fmt": "$100.00", "raw": 100.0},
      "change": {"fmt": "+5.00", "raw": 5.0},
      "volume": {"fmt": "1.2M", "raw": 1200000},
      "high": {"fmt": "$105.00", "raw": 105.0},
      "low": {"fmt": "$98.50", "raw": 98.5}
    }
    ```

=== "Output (AGONStruct)"

    ```
    @FR: fmt, raw

    price: FR($100.00, 100.0)
    change: FR(+5.00, 5.0)
    volume: FR(1.2M, 1200000)
    high: FR($105.00, 105.0)
    low: FR($98.50, 98.5)
    ```

    **Format elements:**

    - `@FR: fmt, raw` - Template definition (defines structure once)
    - `FR($100.00, 100.0)` - Instance (values only, no field names)
    - 5 instances share 1 template definition

=== "Token Breakdown"

    | Format | Tokens | Savings |
    |--------|--------|---------|
    | **Pretty JSON** | **128** | **baseline** |
    | Compact JSON | 75 | +41.4% |
    | AGONText | 90 | +29.7% |
    | **AGONStruct** | **73** | **+43.0%** |

    **Why struct wins:** The repeated `{fmt, raw}` pattern appears 5 times. Traditional formats repeat both field names (`"fmt"` and `"raw"`) in every instance. AGONStruct defines the template once, then each instance only contains values—eliminating 10 redundant field name repetitions.

---

## Format Specification

### Syntax

```
@StructName: field1, field2, field3

key1: StructName(val1, val2, val3)
key2: StructName(val1, val2, val3)
```

**Components:**

1. **Template definition**: `@StructName: field1, field2, ...`
2. **Instance syntax**: `StructName(value1, value2, ...)`
3. **Inline usage**: Can be used as values in key-value pairs or arrays

### Template Definitions

**Basic template:**

```
@FR: fmt, raw
```

Defines a struct named `FR` with two fields: `fmt` and `raw`.

**Optional fields:**

```
@Point: x, y, z?
```

Field `z` is optional (marked with `?`). Instances can omit it.

**Struct inheritance:**

```
@Timestamp: time, value
@AggregatedMetric(Timestamp): count, sum
```

`AggregatedMetric` inherits `time` and `value` from `Timestamp`, then adds `count` and `sum`.

### Instance Syntax

**Basic instance:**

```python
data = {"price": {"fmt": "$100.00", "raw": 100.0}}

# Encodes as:
# @FR: fmt, raw
#
# price: FR($100.00, 100.0)
```

**Inline array of instances:**

```python
data = {
    "points": [
        {"x": 1, "y": 2},
        {"x": 3, "y": 4},
        {"x": 5, "y": 6}
    ]
}

# Encodes as:
# @Point: x, y
#
# points[3]: Point(1, 2), Point(3, 4), Point(5, 6)
```

**Optional field instances:**

```python
data = [
    {"x": 1, "y": 2, "z": 3},  # All fields
    {"x": 4, "y": 5}            # Omit optional z
]

# Encodes as:
# @Point: x, y, z?
#
# [2]: Point(1, 2, 3), Point(4, 5)
```

---

## Encoding Rules

### Automatic Template Detection

AGONStruct automatically detects repeated object patterns with:

- **Minimum occurrences:** 3 (default, configurable)
- **Minimum fields:** 2 (default, configurable)
- **Primitive values only:** Nested objects/arrays don't create structs

```python
from agon.formats import AGONStruct

# Detect patterns with 5+ occurrences (more aggressive)
encoded = AGONStruct.encode(data, min_occurrences=5)

# Only create structs for 3+ field objects
encoded = AGONStruct.encode(data, min_fields=3)
```

### Template Naming

Templates are named automatically based on field patterns:

| Fields | Generated Name | Example |
|--------|----------------|---------|
| `{fmt, raw}` | `FR` | `FR($100, 100.0)` |
| `{x, y}` | `Point` | `Point(1, 2)` |
| `{lat, lng}` | `Coord` | `Coord(37.7, -122.4)` |
| `{min, max}` | `Bounds` | `Bounds(0, 100)` |
| `{low, high}` | `Range` | `Range(50, 150)` |
| `{a, b, c}` | `ABC` | `ABC(1, 2, 3)` |
| Other | `S`, `S1`, `S2` | `S(v1, v2)` |

### Primitives in Instances

Values in struct instances follow the same rules as other AGON formats:

| Type | Example | Encoded in Instance |
|------|---------|---------------------|
| String | `"Alice"` | `FR(Alice, 100)` |
| Number | `42` | `FR(test, 42)` |
| Boolean | `true` | `FR(flag, true)` |
| Null | `null` | `FR(, 5)` (empty) |
| With special chars | `"$100"` | `FR($100, 100)` |

**Quoting rules:**

- Strings with commas, parens, or colons → Quoted
- Empty strings → `""`
- Most simple values → Unquoted

```python
data = [
    {"name": "Alice, Bob", "count": 5},  # Comma requires quoting
    {"name": "Charlie", "count": 3}
]

# Encodes as:
# @NC: name, count
#
# [2]: NC("Alice, Bob", 5), NC(Charlie, 3)
```

### Missing Values

**Optional fields** can be omitted from instances:

```python
data = [
    {"x": 1, "y": 2, "label": "A"},
    {"x": 3, "y": 4},  # No label
    {"x": 5, "y": 6, "label": "C"}
]

# Encodes as:
# @Point: x, y, label?
#
# [3]: Point(1, 2, A), Point(3, 4), Point(5, 6, C)
```

**Null values** are represented as empty cells:

```python
data = [
    {"a": 1, "b": 2},
    {"a": 3, "b": None}  # Explicit null
]

# Encodes as:
# @AB: a, b
#
# [2]: AB(1, 2), AB(3, )
```

---

## Complete Example

Real-world financial quote data:

=== "Input (JSON)"

    ```json
    {
      "symbol": "AAPL",
      "companyName": "Apple Inc.",
      "regularMarketPrice": {"fmt": "150.00", "raw": 150.0},
      "regularMarketChange": {"fmt": "+2.50", "raw": 2.5},
      "regularMarketChangePercent": {"fmt": "+1.69%", "raw": 0.0169},
      "regularMarketVolume": {"fmt": "52.3M", "raw": 52300000},
      "marketCap": {"fmt": "2.45T", "raw": 2450000000000},
      "fiftyTwoWeekHigh": {"fmt": "198.23", "raw": 198.23},
      "fiftyTwoWeekLow": {"fmt": "124.17", "raw": 124.17}
    }
    ```

=== "Output (AGONStruct)"

    ```
    @FR: fmt, raw

    symbol: AAPL
    companyName: Apple Inc.
    regularMarketPrice: FR(150.00, 150.0)
    regularMarketChange: FR(+2.50, 2.5)
    regularMarketChangePercent: FR(+1.69%, 0.0169)
    regularMarketVolume: FR(52.3M, 52300000)
    marketCap: FR(2.45T, 2450000000000)
    fiftyTwoWeekHigh: FR(198.23, 198.23)
    fiftyTwoWeekLow: FR(124.17, 124.17)
    ```

=== "Token Comparison"

    | Format | Tokens | Savings |
    |--------|--------|---------|
    | Pretty JSON | 285 | baseline |
    | Compact JSON | 167 | +41.4% |
    | AGONText | 197 | +30.9% |
    | **AGONStruct** | **153** | **+46.3%** |

    **Why struct wins:** The `{fmt, raw}` pattern appears 7 times. Template definition costs ~10 tokens, but saves ~6 tokens per instance. At 7 instances, savings are `7 × 6 - 10 = 32 tokens`.

---

## When AGONStruct Wins

- **Repeated nested patterns** appearing 3+ times with same structure
- **Market data** with formatted/raw value pairs (`{fmt, raw}`)
- **Time-series data** with timestamp/value pairs (`{time, value}`)
- **Coordinate data** with x/y or lat/lng pairs (`{x, y}`, `{lat, lng}`)
- **Range data** with min/max or low/high pairs (`{min, max}`, `{low, high}`)
- **API responses** with consistent nested object shapes
- **Scientific data** with measurement/uncertainty pairs (`{value, error}`)
- **Localization** with locale/text pairs (`{lang, text}`)

---

## When AGONStruct Loses

- **Few occurrences** (<3 instances) → Template overhead not worth it
- **Few fields** (1 field objects) → No savings from template
- **Irregular nested structures** → Can't identify consistent pattern
- **Deeply nested objects** → Struct only works for shallow primitives
- **Array-heavy data** → AGONText or AGONColumns better

**Example where template overhead hurts:**

```python
# Only 2 instances - template not worth it
data = {
    "start": {"x": 0, "y": 0},
    "end": {"x": 100, "y": 50}
}

result = AGON.encode(data, format="auto")
# → Selects "json" (template overhead exceeds savings)

# Template would cost:
# @Point: x, y  (~6 tokens)
# But only saves ~4 tokens per instance
# 2 instances × 4 - 6 = 2 net tokens saved (below 10% threshold)
```

---

## Direct Usage

For advanced use cases, use AGONStruct encoder directly:

```python
from agon.formats import AGONStruct

# Encode with default options (min_occurrences=3, min_fields=2)
encoded = AGONStruct.encode(data)

# More aggressive: detect patterns with 5+ occurrences
encoded = AGONStruct.encode(data, min_occurrences=5)

# Only create structs for objects with 3+ fields
encoded = AGONStruct.encode(data, min_fields=3)

# Without header (for LLM prompts)
# NOTE: Struct definitions are ALWAYS included even without header
# (LLMs need templates to interpret instances)
encoded = AGONStruct.encode(data, include_header=False)

# With header (for decoding)
encoded_with_header = AGONStruct.encode(data, include_header=True)
# → @AGON struct\n\n@FR: fmt, raw\n\n...

# Decode
decoded = AGONStruct.decode(encoded)
assert decoded == data  # Lossless
```

---

## Edge Cases

??? question "Empty objects"

    ```python
    data = [
        {"a": 1, "b": 2},
        {},  # Empty object
        {"a": 3, "b": 4}
    ]

    result = AGON.encode(data, format="struct")
    # → [3]:
    #   - a: 1
    #     b: 2
    #   -
    #   - a: 3
    #     b: 4
    ```

    (Empty object doesn't match any struct pattern)

??? question "Pattern appears only twice"

    ```python
    data = {
        "price": {"fmt": "$100", "raw": 100.0},
        "change": {"fmt": "+5", "raw": 5.0}
    }

    result = AGON.encode(data, format="struct")
    # No template created (default min_occurrences=3)
    # Falls back to inline objects:
    # price:
    #   fmt: $100
    #   raw: 100.0
    # change:
    #   fmt: +5
    #   raw: 5.0

    # OR force lower threshold:
    result = AGON.encode(data, format="struct", min_occurrences=2)
    # → @FR: fmt, raw
    #
    #   price: FR($100, 100.0)
    #   change: FR(+5, 5.0)
    ```

??? question "Nested objects within structs"

    ```python
    data = [
        {"name": "Alice", "score": 95, "metadata": {"tag": "premium"}},
        {"name": "Bob", "score": 87, "metadata": {"tag": "standard"}}
    ]

    result = AGON.encode(data, format="struct")
    # Struct only created for primitive fields (name, score)
    # Nested 'metadata' doesn't become part of struct
    ```

??? question "Optional fields with mix of presence"

    ```python
    data = [
        {"x": 1, "y": 2, "z": 3},
        {"x": 4, "y": 5},
        {"x": 6, "y": 7, "z": 9},
        {"x": 8, "y": 10}
    ]

    result = AGON.encode(data, format="struct")
    # → @Point: x, y, z?
    #
    #   [4]: Point(1, 2, 3), Point(4, 5), Point(6, 7, 9), Point(8, 10)
    ```

    (Field `z` detected as optional—present in some instances, absent in others)

??? question "Special characters in struct instance values"

    ```python
    data = [
        {"label": "Alice, Bob", "count": 5},
        {"label": "Charlie (admin)", "count": 3}
    ]

    result = AGON.encode(data, format="struct")
    # → @LC: label, count
    #
    #   [2]: LC("Alice, Bob", 5), LC("Charlie (admin)", 3)
    ```

    (Automatic quoting for special chars: commas, parens, colons)

---

### Token Efficiency by Field Count

**Scenario:** 5 instances of same pattern

| Fields | Pattern | Template Cost | Per-Instance Savings | Net Savings (5×) |
|--------|---------|---------------|---------------------|------------------|
| 2 | `{a, b}` | ~6 tokens | ~4 tokens | ~14 tokens |
| 3 | `{a, b, c}` | ~10 tokens | ~8 tokens | ~30 tokens |
| 4 | `{a, b, c, d}` | ~14 tokens | ~12 tokens | ~46 tokens |
| 5 | `{a, b, c, d, e}` | ~18 tokens | ~16 tokens | ~62 tokens |

**Observation:** More fields = greater per-instance savings. However, AGONStruct is optimized for **small repeated patterns** (2-4 fields). For 10+ field objects repeated many times, AGONColumns often wins.

## Comparison: Struct vs Text

For the same market data with 5 `{fmt, raw}` instances:

=== "AGONText (No Template)"

    ```
    price:
      fmt: $100.00
      raw: 100.0
    change:
      fmt: +5.00
      raw: 5.0
    volume:
      fmt: 1.2M
      raw: 1200000
    high:
      fmt: $105.00
      raw: 105.0
    low:
      fmt: $98.50
      raw: 98.5
    ```

    **Tokens:** 90 (each `fmt` and `raw` field name repeated 5 times)

=== "AGONStruct (Template)"

    ```
    @FR: fmt, raw

    price: FR($100.00, 100.0)
    change: FR(+5.00, 5.0)
    volume: FR(1.2M, 1200000)
    high: FR($105.00, 105.0)
    low: FR($98.50, 98.5)
    ```

    **Tokens:** 73 (`fmt` and `raw` defined once in template, eliminated from instances)

**Key difference:** AGONText repeats field names in every nested object. AGONStruct defines template once, then instances reference it by name with positional values.

---

## FAQ

??? question "When should I use Struct vs Text/Columns?"

    **Use Struct when:**

    - Same nested object pattern repeats 3+ times
    - Objects have 2-4 primitive fields
    - Examples: `{fmt, raw}`, `{x, y}`, `{time, value}`

    **Use Text when:**

    - Flat uniform arrays (no nested patterns)
    - 2-10 fields per record

    **Use Columns when:**

    - Wide tables (10+ fields)
    - Numeric-heavy data

??? question "Can I customize minimum occurrences threshold?"

    Yes! Use the encoder directly:

    ```python
    from agon.formats import AGONStruct

    # Lower threshold (detect patterns with 2+ occurrences)
    encoded = AGONStruct.encode(data, min_occurrences=2)

    # Higher threshold (only create templates for very common patterns)
    encoded = AGONStruct.encode(data, min_occurrences=10)
    ```

??? question "How does AGONStruct handle deeply nested objects?"

    AGONStruct only creates templates for **shallow objects with primitive values**. Nested objects and arrays within structs are encoded recursively but don't become part of the struct template:

    ```python
    data = [
        {
            "name": "Alice",
            "score": 95,
            "metadata": {"tag": "premium", "region": "US"}
        },
        {"name": "Bob", "score": 87, "metadata": {"tag": "standard"}}
    ]

    # Template only created for name/score (primitives)
    # 'metadata' remains nested, not part of struct
    ```

??? question "Can struct templates inherit from other templates?"

    Yes, using inheritance syntax:

    ```
    @Base: field1, field2
    @Extended(Base): field3, field4
    ```

    `Extended` inherits `field1` and `field2` from `Base`, then adds its own fields. However, this feature is rarely needed—auto-detection typically creates independent templates.

??? question "Why doesn't auto mode always choose Struct for nested data?"

    Auto mode considers multiple factors:

    - **Occurrence count:** Pattern must repeat ≥ 3 times (default)
    - **Field count:** Objects must have ≥ 2 fields
    - **Token savings:** Must save ≥ 10% vs compact JSON
    - **Pattern regularity:** All instances must have same fields (with optional variations)

    If no repeated pattern meets these criteria, auto mode falls back to JSON or uses Text/Columns for arrays.

---

## Next Steps

### [AGONText Format](text.md)

Learn about row-based encoding for flat arrays

### [AGONColumns Format](columns.md)

Learn about columnar encoding for wide tables

### [Benchmarks](../benchmarks.md)

See AGONStruct performance on real datasets

### [API Reference](../api.md)

Complete API documentation
