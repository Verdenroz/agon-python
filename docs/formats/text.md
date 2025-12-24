# AGONText Format

Row-based tabular encoding for uniform arrays—AGON's most commonly selected format.

---

## Overview

AGONText is a **row-based encoding format** optimized for uniform arrays of objects with consistent field structure. It's similar to TOON's approach and produces identical output for uniform arrays.

**Best for:**

- User lists, transaction logs, simple metrics
- Consistent field structure across records (2-10 fields)
- Flat or shallow nesting
- Homogeneous data types per field

---

## Basic Example

Let's encode a simple user list:

=== "Input (JSON)"

    ```json
    [
      {"id": 1, "name": "Alice", "role": "admin"},
      {"id": 2, "name": "Bob", "role": "user"},
      {"id": 3, "name": "Charlie", "role": "user"}
    ]
    ```

=== "Output (AGONText)"

    ```
    [3]{id	name	role}
    1	Alice	admin
    2	Bob	user
    3	Charlie	user
    ```

    **Format elements:**

    - `[3]` - Array length declaration
    - `{id name role}` - Field headers (tab-separated)
    - Rows - Tab-delimited values

=== "Token Breakdown"

    | Element | Tokens | Purpose |
    |---------|--------|---------|
    | `[3]` | 2 | Array length (enables validation) |
    | `{id name role}` | 5 | Field headers (schema) |
    | Row 1 | 5 | `1 Alice admin` |
    | Row 2 | 4 | `2 Bob user` |
    | Row 3 | 5 | `3 Charlie user` |
    | **Total** | **26** | **58% savings** vs pretty JSON (62 tokens) |

    **Why it works:** Eliminates repeated field names (`"id":`, `"name":`, `"role":`) and JSON syntax overhead (`{`, `}`, `"`).

---

## Format Specification

### Syntax

```
[count]{field1	field2	field3}
value1	value2	value3
value1	value2	value3
```

**Components:**

1. **Array length**: `[N]` where N is the number of records
2. **Field headers**: `{field1 field2 ...}` tab-separated field names
3. **Rows**: Tab-delimited values, one row per record

### Delimiters

**Default:** Tab character (`\t`)

**Custom delimiter:**

```python
from agon.formats import AGONText

# Use pipe delimiter instead of tab
encoded = AGONText.encode(data, delimiter="|")
```

---

## Encoding Rules

### Primitives

AGONText infers types from content—no type markers needed:

| Type | Example Input | Encoded Output |
|------|--------------|----------------|
| String | `"Alice"` | `Alice` |
| Integer | `42` | `42` |
| Float | `3.14` | `3.14` |
| Boolean | `true` | `true` |
| Null | `null` | `` (empty cell) |

### Missing Values

**Missing/null values** → Empty cell (consecutive delimiters):

```
[2]{id	name	email}
1	Alice	alice@example.com
2	Bob
```

Row 2 has empty `email` field (two consecutive tabs).

### Quoting

**Simple values** (no special characters) → Unquoted:

```
Alice	Bob	Charlie
```

**Values with spaces, tabs, or newlines** → Quoted:

```
"Alice Smith"	"Bob\tJones"	Charlie
```

**Quotes in values** → Escaped with backslash:

```
"Alice \"The Great\""
```

### Nested Objects

**Nested objects** → Indented key-value pairs:

```
context:
  task: Our favorite hikes
  location: Boulder
  season: spring_2025
friends[3]: ana	luis	sam
```

**Indentation:** 2 spaces per level

### Arrays

**Primitive arrays** → Inline with delimiter:

```
friends[3]: ana	luis	sam
scores[4]: 95	87	92	88
```

**Object arrays** → Tabular format (primary use case):

```
hikes[3]{id	name	distanceKm}
1	Blue Lake Trail	7.5
2	Ridge Overlook	9.2
3	Wildflower Loop	5.1
```

---

## Complete Example

Real-world data from `toon.json`:

=== "Input (JSON)"

    ```json
    {
      "context": {
        "task": "Our favorite hikes together",
        "location": "Boulder",
        "season": "spring_2025"
      },
      "friends": ["ana", "luis", "sam"],
      "hikes": [
        {
          "id": 1,
          "name": "Blue Lake Trail",
          "distanceKm": 7.5,
          "elevationGain": 320,
          "companion": "ana",
          "wasSunny": true
        },
        {
          "id": 2,
          "name": "Ridge Overlook",
          "distanceKm": 9.2,
          "elevationGain": 540,
          "companion": "luis",
          "wasSunny": false
        },
        {
          "id": 3,
          "name": "Wildflower Loop",
          "distanceKm": 5.1,
          "elevationGain": 180,
          "companion": "sam",
          "wasSunny": true
        }
      ]
    }
    ```

=== "Output (AGONText)"

    ```
    context:
      task: Our favorite hikes together
      location: Boulder
      season: spring_2025
    friends[3]: ana	luis	sam
    hikes[3]{id	name	distanceKm	elevationGain	companion	wasSunny}
    1	Blue Lake Trail	7.5	320	ana	true
    2	Ridge Overlook	9.2	540	luis	false
    3	Wildflower Loop	5.1	180	sam	true
    ```

=== "Token Comparison"

    | Format | Tokens | Savings |
    |--------|--------|---------|
    | Pretty JSON | 229 | baseline |
    | Compact JSON | 139 | +39.3% |
    | **AGONText** | **96** | **+58.1%** |

    **30.9% savings** vs compact JSON!

---

## When AGONText Wins

- **Uniform arrays** with 3+ records having identical field structure
- **Consistent field types** (all records have same fields with same types)
- **2-10 fields per record** (sweet spot for row-based format)
- **Simple data types** (strings, numbers, booleans—not deeply nested objects)
- **Transaction logs** (timestamp, user, action, status)
- **User lists** (id, name, email, role)
- **Metrics/analytics** (date, metric_name, value, unit)
- **Flat CSV-like data** being sent to LLMs

---

## When AGONText Loses

- **Wide tables** (10+ fields) → AGONColumns wins (type clustering)
- **Irregular structure** (fields vary between records) → JSON fallback
- **Deeply nested objects** with no arrays → JSON or Struct
- **Sparse data** (many nulls) → AGONColumns handles better
- **Repeated nested patterns** (e.g., `{fmt, raw}` everywhere) → Struct wins

**Example where Columns wins:**

```python
# 12 fields - wide table
employee_data = [
    {
        "id": 1, "name": "Alice", "email": "alice@example.com",
        "age": 28, "city": "NYC", "state": "NY", "zip": "10001",
        "phone": "555-0001", "dept": "Eng", "title": "SWE",
        "salary": 120000, "start_date": "2020-01-15"
    },
    # ... more records
]

result = AGON.encode(employee_data, format="auto")
# → Selects "columns" (better type clustering for 12 fields)
```

---

## Direct Usage

For advanced use cases, use AGONText encoder directly:

```python
from agon.formats import AGONText

# Encode with default options
encoded = AGONText.encode(data)

# Custom delimiter
encoded = AGONText.encode(data, delimiter="|")

# Without header (for LLM prompts)
encoded = AGONText.encode(data, include_header=False)

# With header (for decoding)
encoded_with_header = AGONText.encode(data, include_header=True)
# → @AGON text\n\n[3]{id...}

# Decode
decoded = AGONText.decode(encoded)
assert decoded == data  # Lossless
```

---

## Edge Cases

??? question "Empty array"

    ```python
    data = []

    result = AGON.encode(data, format="text")
    # → [0]{}
    ```

??? question "Single item array"

    ```python
    data = [{"id": 1, "name": "Alice"}]

    result = AGON.encode(data, format="text")
    # → [1]{id	name}
    #   1	Alice
    ```

??? question "All null values"

    ```python
    data = [{"a": None, "b": None}]

    result = AGON.encode(data, format="text")
    # → [1]{a	b}
    #
    ```

    (Two consecutive tabs for empty cells)

??? question "Special characters in values"

    ```python
    data = [{"name": "Alice\tBob", "quote": "He said \"hi\""}]

    result = AGON.encode(data, format="text")
    # → [1]{name	quote}
    #   "Alice\tBob"	"He said \"hi\""
    ```

    (Automatic quoting and escaping)

---

## Comparison with TOON

For uniform arrays, AGONText and TOON produce **near identical output**:

=== "JSON"

    ```json
    [
      {"id": 1, "name": "Alice", "role": "admin"},
      {"id": 2, "name": "Bob", "role": "user"},
      {"id": 3, "name": "Charlie", "role": "user"}
    ]
    ```

=== "TOON"

    ```toon
    [3]{id,name,role}:
    1,Alice,admin
    2,Bob,user
    3,Charlie,user
    ```

=== "AGONText"

    ```agon
    [3]{id	name	role}
    1	Alice	admin
    2	Bob	user
    3	Charlie	user
    ```


Both achieve the same token savings vs JSON.

**TOON and AGONText are near identical! The only difference is AGONText uses the `\t` delimiter.**

---

## FAQ

??? question "When should I use Text vs Columns?"

    **Use Text when:**

    - 2-10 fields per record
    - Consistent structure
    - Mixed data types

    **Use Columns when:**

    - 10+ fields (wide tables)
    - Numeric-heavy data
    - Sparse data (many nulls)

??? question "Can I customize the delimiter?"

    Yes! Use AGONText encoder directly:

    ```python
    from agon.formats import AGONText
    encoded = AGONText.encode(data, delimiter="|")
    ```

??? question "Does AGONText handle nested objects?"

    Yes, with indentation:

    ```python
    data = {"user": {"name": "Alice", "age": 28}}

    # Encodes as:
    # user:
    #   name: Alice
    #   age: 28
    ```

??? question "Is AGONText the same as TOON?"

    **For uniform arrays:** Yes, near identical output.

    **Overall:** AGON includes safety features (auto mode, JSON fallback) that TOON doesn't have.

---

## Next Steps

### [AGONColumns Format](columns.md)

Learn about columnar encoding for wide tables

### [AGONStruct Format](struct.md)

Learn about template-based encoding

### [Benchmarks](../benchmarks.md)

See AGONText performance on real datasets

### [API Reference](../api.md)

Complete API documentation
