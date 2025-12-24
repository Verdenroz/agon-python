# AGONColumns Format

Columnar transpose encoding for wide tables—optimized for 10+ fields per record.

---

## Overview

AGONColumns is a **columnar encoding format** that transposes data to group values by field (column) instead of by record (row). This type clustering improves token efficiency for wide tables and numeric-heavy datasets.

**Best for:**

- Wide tables (10+ fields per record)
- Employee records, financial data, analytics tables
- Numeric-heavy or homogeneous types per column
- Sparse data with many missing values

**Token efficiency:** 50-70% savings vs pretty JSON, 20-40% vs compact JSON

---

## Basic Example

Let's encode a simple employee table with 12 fields:

=== "Input (JSON)"

    ```json
    [
      {
        "id": 1, "name": "Alice", "email": "alice@example.com",
        "age": 28, "city": "NYC", "state": "NY", "zip": "10001",
        "phone": "555-0001", "dept": "Eng", "title": "SWE",
        "salary": 120000, "start_date": "2020-01-15"
      },
      {
        "id": 2, "name": "Bob", "email": "bob@example.com",
        "age": 32, "city": "SF", "state": "CA", "zip": "94105",
        "phone": "555-0002", "dept": "Sales", "title": "Manager",
        "salary": 135000, "start_date": "2019-03-20"
      },
      {
        "id": 3, "name": "Charlie", "email": "charlie@example.com",
        "age": 25, "city": "Austin", "state": "TX", "zip": "78701",
        "phone": "555-0003", "dept": "Eng", "title": "SWE",
        "salary": 115000, "start_date": "2021-07-10"
      }
    ]
    ```

=== "Output (AGONColumns)"

    ```
    [3]
    ├ id: 1	2	3
    ├ name: Alice	Bob	Charlie
    ├ email: alice@example.com	bob@example.com	charlie@example.com
    ├ age: 28	32	25
    ├ city: NYC	SF	Austin
    ├ state: NY	CA	TX
    ├ zip: "10001"	"94105"	"78701"
    ├ phone: 555-0001	555-0002	555-0003
    ├ dept: Eng	Sales	Eng
    ├ title: SWE	Manager	SWE
    ├ salary: 120000	135000	115000
    └ start_date: 2020-01-15	2019-03-20	2021-07-10
    ```

    **Format elements:**

    - `[3]` - Array length declaration
    - `├` / `└` - Tree characters (branch / last branch)
    - Field names followed by tab-delimited values
    - Last field uses `└` to indicate end of structure

=== "Token Breakdown"

    | Format | Tokens | Savings |
    |--------|--------|---------|
    | **Pretty JSON** | **309** | **baseline** |
    | Compact JSON | 190 | +38.5% |
    | AGONText | 137 | +55.7% |
    | **AGONColumns** | **158** | **+48.9%** |

    **Why columns helps:** With 12 fields, grouping by type (all IDs together, all names together) provides better compression than row-based format. For even wider tables (20+ fields), the advantage increases.

---

## Format Specification

### Syntax

```
[count]
├ field1: val1	val2	val3
├ field2: val1	val2	val3
└ fieldN: val1	val2	val3
```

**Components:**

1. **Array length**: `[N]` where N is the number of records
2. **Tree structure**: `├` for fields with siblings, `└` for last field
3. **Field lines**: `field: value1<delimiter>value2<delimiter>...`
4. **Delimiters**: Tab character (`\t`) by default

### Tree Characters

**Unicode (default):**

- `├` (U+251C) - Branch: has more siblings below
- `└` (U+2514) - Last branch: final field

**ASCII mode:**

```python
from agon.formats import AGONColumns

# Use ASCII tree characters for compatibility
encoded = AGONColumns.encode(data, use_ascii=True)
# Output:
# [3]
# | id: 1, 2, 3
# | name: Alice, Bob, Charlie
# ` email: ...
```

### Delimiters

**Default:** Tab character (`\t`)

**Custom delimiter:**

```python
from agon.formats import AGONColumns

# Use comma-space delimiter
encoded = AGONColumns.encode(data, delimiter=", ")

# Output:
# [3]
# ├ id: 1, 2, 3
# ├ name: Alice, Bob, Charlie
# └ email: alice@example.com, bob@example.com, charlie@example.com
```

---

## Encoding Rules

### Primitives

AGONColumns infers types from content—no type markers needed:

| Type | Example Input | Encoded Output |
|------|--------------|----------------|
| String | `"Alice"` | `Alice` |
| Integer | `42` | `42` |
| Float | `3.14` | `3.14` |
| Boolean | `true` | `true` |
| Null | `null` | `null` |

### Missing Values

**Missing/null values in columns** → Empty cell (consecutive delimiters):

```
[3]
├ id: 1	2	3
├ name: Alice	Bob	Charlie
└ email: alice@example.com		charlie@example.com
```

Row 2 (Bob) has missing `email` field—shown by consecutive tabs.

**Important distinction:**

- **Empty cell** (``): field is absent from object
- **Literal `null`**: field is present with value `None`

```python
data = [
    {"id": 1, "name": "Alice"},           # no email field
    {"id": 2, "name": "Bob", "email": None}  # email field = null
]

# Encodes as:
# [2]
# ├ id: 1	2
# ├ name: Alice	Bob
# └ email: 	null
```

### Quoting

**Simple values** (no special characters) → Unquoted:

```
├ name: Alice	Bob	Charlie
```

**Values with spaces, delimiters, or special chars** → Quoted:

```
├ address: "123 Main St"	"456 Oak Ave"	"789 Pine Rd"
├ zip: "10001"	"94105"	"78701"
```

**Quotes in values** → Escaped with backslash:

```
├ bio: "Alice \"The Great\""	"Bob \"Builder\""
```

### Type Clustering Advantage

Columnar format groups same-type values together, improving LLM tokenization:

**Example: Numeric clustering**

```
├ id: 1	2	3	4	5	6	7	8	9	10
├ age: 28	32	25	45	38	29	41	33	27	36
├ salary: 120000	135000	115000	150000	128000	122000	145000	132000	118000	140000
```

All numeric values are adjacent, creating better token compression than alternating between numbers and strings in row-based format.

### Nested Objects

**Nested objects** → Indented key-value pairs:

```
company:
  name: Acme Corp
  founded: 2010
  headquarters:
    city: San Francisco
    state: CA
employees[3]
├ id: 1	2	3
├ name: Alice	Bob	Charlie
└ dept: Eng	Sales	Eng
```

### Arrays

**Primitive arrays** → Inline with delimiter:

```
tags[5]: python	javascript	rust	go	typescript
scores[4]: 95	87	92	88
```

**Object arrays** → Columnar format (primary use case):

```
products[3]
├ sku: A123	B456	C789
├ name: Widget	Gadget	Gizmo
└ price: 9.99	19.99	29.99
```

---

## Complete Example

Real-world employee data:

=== "Input (JSON)"

    ```json
    {
      "department": "Engineering",
      "headcount": 3,
      "employees": [
        {
          "id": 1, "name": "Alice", "email": "alice@example.com",
          "age": 28, "city": "NYC", "state": "NY", "zip": "10001",
          "phone": "555-0001", "dept": "Eng", "title": "SWE",
          "salary": 120000, "start_date": "2020-01-15"
        },
        {
          "id": 2, "name": "Bob", "email": "bob@example.com",
          "age": 32, "city": "SF", "state": "CA", "zip": "94105",
          "phone": "555-0002", "dept": "Sales", "title": "Manager",
          "salary": 135000, "start_date": "2019-03-20"
        },
        {
          "id": 3, "name": "Charlie", "email": "charlie@example.com",
          "age": 25, "city": "Austin", "state": "TX", "zip": "78701",
          "phone": "555-0003", "dept": "Eng", "title": "SWE",
          "salary": 115000, "start_date": "2021-07-10"
        }
      ]
    }
    ```

=== "Output (AGONColumns)"

    ```
    department: Engineering
    headcount: 3
    employees[3]
    ├ id: 1	2	3
    ├ name: Alice	Bob	Charlie
    ├ email: alice@example.com	bob@example.com	charlie@example.com
    ├ age: 28	32	25
    ├ city: NYC	SF	Austin
    ├ state: NY	CA	TX
    ├ zip: "10001"	"94105"	"78701"
    ├ phone: 555-0001	555-0002	555-0003
    ├ dept: Eng	Sales	Eng
    ├ title: SWE	Manager	SWE
    ├ salary: 120000	135000	115000
    └ start_date: 2020-01-15	2019-03-20	2021-07-10
    ```

=== "Token Comparison"

    | Format | Tokens | Savings |
    |--------|--------|---------| | Pretty JSON | 381 | baseline |
    | Compact JSON | 231 | +39.4% |
    | AGONText | 171 | +55.1% |
    | **AGONColumns** | **186** | **+51.2%** |

    **Trade-off:** AGONText wins for this example (fewer fields), but as field count grows beyond 10, AGONColumns pulls ahead due to type clustering.

---

## When AGONColumns Wins

- **Wide tables** with 10+ fields per record (sweet spot: 15-50 fields)
- **Financial data** (many numeric columns: price, volume, market_cap, P/E, etc.)
- **Analytics tables** (metrics, dimensions, timestamps, aggregations)
- **Employee databases** (ID, name, email, age, city, state, zip, phone, dept, title, salary, etc.)
- **Sparse data** with many missing values (columnar handles better than row-based)
- **Homogeneous column types** (all numbers, all strings, etc.)
- **Scientific datasets** with measurement arrays (time, temp, pressure, velocity, etc.)

---

## When AGONColumns Loses

- **Few fields** (2-5 fields) → AGONText wins with simpler row-based format
- **Highly irregular structure** (fields vary between records) → JSON fallback
- **Deeply nested objects** with no arrays → AGONStruct or JSON
- **Heterogeneous data** per column (mixed types) → Row-based better
- **Very small arrays** (<3 records) → Overhead not worth it

**Example where Text wins:**

```python
# Only 3 fields - too narrow for columnar advantage
user_data = [
    {"id": 1, "name": "Alice", "role": "admin"},
    {"id": 2, "name": "Bob", "role": "user"},
    {"id": 3, "name": "Charlie", "role": "user"}
]

result = AGON.encode(user_data, format="auto")
# → Selects "text" (simpler for narrow tables)
```

---

## Direct Usage

For advanced use cases, use AGONColumns encoder directly:

```python
from agon.formats import AGONColumns

# Encode with default options
encoded = AGONColumns.encode(data)

# Custom delimiter (comma-space)
encoded = AGONColumns.encode(data, delimiter=", ")

# ASCII tree characters (for compatibility)
encoded = AGONColumns.encode(data, use_ascii=True)
# Output uses | and ` instead of ├ and └

# Without header (for LLM prompts)
encoded = AGONColumns.encode(data, include_header=False)

# With header (for decoding)
encoded_with_header = AGONColumns.encode(data, include_header=True)
# → @AGON columns\n\n[3]...

# Decode
decoded = AGONColumns.decode(encoded)
assert decoded == data  # Lossless
```

---

## Edge Cases

??? question "Empty array"

    ```python
    data = []

    result = AGON.encode(data, format="columns")
    # → [0]
    ```

??? question "Single item array"

    ```python
    data = [{"id": 1, "name": "Alice", "email": "alice@example.com"}]

    result = AGON.encode(data, format="columns")
    # → [1]
    #   ├ id: 1
    #   ├ name: Alice
    #   └ email: alice@example.com
    ```

??? question "All null values"

    ```python
    data = [{"a": None, "b": None}, {"a": None, "b": None}]

    result = AGON.encode(data, format="columns")
    # → [2]
    #   ├ a: null	null
    #   └ b: null	null
    ```

??? question "Missing fields (sparse data)"

    ```python
    data = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob"},  # no email
        {"id": 3, "name": "Charlie", "email": "charlie@example.com"}
    ]

    result = AGON.encode(data, format="columns")
    # → [3]
    #   ├ id: 1	2	3
    #   ├ name: Alice	Bob	Charlie
    #   └ email: alice@example.com		charlie@example.com
    ```

    (Empty cell for Bob's missing email—two consecutive tabs)

??? question "Special characters in column values"

    ```python
    data = [
        {"name": "Alice\tSmith", "bio": "She said \"hi\""},
        {"name": "Bob", "bio": "Normal text"}
    ]

    result = AGON.encode(data, format="columns")
    # → [2]
    #   ├ name: "Alice\tSmith"	Bob
    #   └ bio: "She said \"hi\""	"Normal text"
    ```

    (Automatic quoting and escaping)

---

## Comparison: Columns vs Text

For the same employee dataset with 12 fields:

=== "AGONText (Row-Based)"

    ```
    [3]{id	name	email	age	city	state	zip	phone	dept	title	salary	start_date}
    1	Alice	alice@example.com	28	NYC	NY	"10001"	555-0001	Eng	SWE	120000	2020-01-15
    2	Bob	bob@example.com	32	SF	CA	"94105"	555-0002	Sales	Manager	135000	2019-03-20
    3	Charlie	charlie@example.com	25	Austin	TX	"78701"	555-0003	Eng	SWE	115000	2021-07-10
    ```

    **Tokens:** 137 (better for this case—12 fields is borderline)

=== "AGONColumns (Columnar)"

    ```
    [3]
    ├ id: 1	2	3
    ├ name: Alice	Bob	Charlie
    ├ email: alice@example.com	bob@example.com	charlie@example.com
    ├ age: 28	32	25
    ├ city: NYC	SF	Austin
    ├ state: NY	CA	TX
    ├ zip: "10001"	"94105"	"78701"
    ├ phone: 555-0001	555-0002	555-0003
    ├ dept: Eng	Sales	Eng
    ├ title: SWE	Manager	SWE
    ├ salary: 120000	135000	115000
    └ start_date: 2020-01-15	2019-03-20	2021-07-10
    ```

    **Tokens:** 158 (slightly worse due to tree overhead, but scales better with more fields)

**Decision factors:**

- **2-10 fields:** Use AGONText (simpler, less overhead)
- **10-15 fields:** Borderline—auto mode chooses based on data
- **15+ fields:** Use AGONColumns (type clustering advantage wins)

---

## FAQ

??? question "When should I use Columns vs Text?"

    **Use Columns when:**

    - 10+ fields per record (sweet spot: 15-50 fields)
    - Numeric-heavy data (financial, scientific)
    - Sparse data with many nulls

    **Use Text when:**

    - 2-10 fields (simpler row-based format)
    - Mixed data types per field
    - Narrow tables

??? question "Can I customize tree characters?"

    Yes! Use ASCII mode for compatibility:

    ```python
    from agon.formats import AGONColumns
    encoded = AGONColumns.encode(data, use_ascii=True)
    # Uses | and ` instead of ├ and └
    ```

??? question "How does AGONColumns handle missing fields?"

    Empty cells (consecutive delimiters) indicate missing fields:

    ```python
    data = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob"},  # no email
    ]

    # Encodes as:
    # [2]
    # ├ id: 1	2
    # ├ name: Alice	Bob
    # └ email: alice@example.com
    ```

??? question "Why doesn't auto mode always choose Columns for wide tables?"

    Auto mode considers multiple factors:

    - **Token count:** Columns must save ≥ 10% vs compact JSON
    - **Field count:** 10+ fields favors Columns
    - **Type homogeneity:** Mixed types reduce clustering benefit
    - **Data regularity:** Irregular structure may favor JSON

    Use `force=True` to guarantee specialized format selection.

---

## Next Steps

### [AGONText Format](text.md)

Learn about row-based encoding for narrow tables

### [AGONStruct Format](struct.md)

Learn about template-based encoding

### [Benchmarks](../benchmarks.md)

See AGONColumns performance on real datasets

### [API Reference](..//api.md)

Complete API documentation
