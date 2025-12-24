# JSON Fallback

Understanding when and why AGON returns compact JSON.

---

## What is JSON Fallback?

JSON fallback is AGON's safety mechanism—when specialized formats (Text, Columns, Struct) don't provide sufficient token savings, auto mode returns **compact JSON** instead.

This is **a feature, not a failure**. It's the guarantee that makes `format="auto"` safe to use everywhere.

### When JSON Fallback Occurs

Auto mode returns JSON when **any** of these conditions are met:

1. **Insufficient savings**: Best specialized format saves less than `min_savings` threshold vs compact JSON
2. **Specialized formats worse**: All specialized formats produce more tokens than compact JSON
3. **Explicit selection**: User chooses `format="json"`

```python
# Auto mode with 10% minimum savings threshold
result = AGON.encode(data, format="auto", min_savings=0.10)
# Returns JSON if best format saves <10% vs compact JSON
```

---

## Why JSON Fallback Matters

Fixed-format encoders can make token counts **worse** than JSON on irregular data. AGON's fallback prevents this problem.

### The Fixed-Format Problem

=== "Without Fallback"

    ```python
    # Fixed format encoder - always applies format
    irregular_data = {
        "users": [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob", "email": "bob@example.com", "extra_field": True}
        ],
        "nested": {"deeply": {"nested": {"irregular": "structure"}}}
    }

    # Fixed format struggles with irregular structure
    fixed_result = FixedEncoder.encode(irregular_data)
    # Might be worse than JSON! No safety net.
    ```

=== "With AGON Fallback"

    ```python
    # AGON with safety guarantee
    result = AGON.encode(irregular_data, format="auto")

    # Auto mode tries specialized formats, finds they don't help
    # Returns compact JSON instead - guaranteed excellent savings
    print(result.format)  # → "json"
    # Still gets ~35% savings vs pretty JSON!
    ```

---

## When JSON Wins: Examples

### 1. Highly Irregular Objects

**Data with inconsistent structure:**

```python
data = [
    {"type": "user", "id": 1, "name": "Alice"},
    {"type": "product", "sku": "ABC123", "price": 29.99, "inventory": 50},
    {"type": "order", "order_id": 1001, "items": [1, 2, 3], "total": 89.97}
]

result = AGON.encode(data, format="auto")
# → "json" (no consistent structure to compress)
```

**Why JSON wins:** Specialized formats rely on repetition—irregular data has no patterns to exploit.

### 2. Deeply Nested Heterogeneous Data

**Complex nested structure with varied types:**

```python
data = {
    "config": {
        "database": {"host": "localhost", "port": 5432, "ssl": True},
        "cache": {"ttl": 3600, "max_size": "100MB"},
        "features": ["auth", "logging", "metrics"]
    },
    "metadata": {
        "version": "1.0.0",
        "timestamp": "2025-01-15T10:30:00Z"
    }
}

result = AGON.encode(data, format="auto")
# → "json" (nested objects vary in structure)
```

**Why JSON wins:** No repeated patterns, nesting doesn't follow consistent shape.

### 3. Small Payloads

**Tiny data where format overhead exceeds savings:**

```python
data = {"status": "ok", "count": 42}

result = AGON.encode(data, format="auto")
# → "json" (payload too small for format overhead to pay off)
```

**Why JSON wins:** Compact JSON = 18 tokens, specialized format overhead ≈ 10 tokens—not worth it.

## Decision Matrix

When should you expect JSON vs specialized formats?

| Data Characteristic | Expected Format |
|---------------------|-----------------|
| Uniform array, 3-10 fields | **Text** |
| Uniform array, 10+ fields | **Columns** |
| Repeated nested `{a, b}` pattern (3+ times) | **Struct** |
| Mixed types, inconsistent structure | **JSON** |
| Deeply nested, heterogeneous | **JSON** |
| <50 tokens total | **JSON** |
| Sparse data, many nulls | **Columns** or **JSON** |

## FAQ

??? question "Is JSON fallback a failure?"

    **No!** JSON fallback is a **success**—it's the safety mechanism that guarantees you'll never do worse than compact JSON.

    When auto mode returns JSON, it means:

    - Specialized formats didn't provide enough benefit
    - You still get 30-40% savings vs pretty JSON
    - You avoided complexity without sufficient reward

??? question "How do I force a specialized format?"

    Use `force=True` to disable JSON fallback:

    ```python
    result = AGON.encode(data, format="auto", force=True)
    # Always uses best specialized format, never JSON
    ```

    **Warning:** Only use when you've validated that specialized formats work well on your data.

??? question "Can I use a specific format directly?"

    Yes! Bypass auto mode entirely:

    ```python
    # Guarantee Text format
    result = AGON.encode(data, format="text")

    # Guarantee Columns format
    result = AGON.encode(data, format="columns")

    # Guarantee Struct format
    result = AGON.encode(data, format="struct")
    ```

??? question "Why does my data always return JSON?"

    Common reasons:

    1. **Irregular structure** - Specialized formats need consistent patterns
    2. **Threshold too high** - Try lowering `min_savings`:
       ```python
       result = AGON.encode(data, format="auto", min_savings=0.05)
       ```
    3. **Data preparation** - Ensure fields are consistent across records
    4. **Genuinely unsuitable** - Some data just doesn't compress well

---

## Next Steps

### [AGONText Format](text.md)

Learn about the most common specialized format

### [Core Concepts](../concepts.md)

Design principles and adaptive approach

### [API Reference](../api.md)

Complete API documentation
