# Benchmarks

Real-world performance data demonstrating AGON's adaptive format selection and token savings.

---

## Overview

These benchmarks measure token counts across 7 real-world datasets using tiktoken's `o200k_base` encoding (GPT-4, GPT-4 Turbo, GPT-4o). All results are reproducible—run `make benchmarks` to verify.

---

## Benchmark Datasets

| Dataset | Size | Description | Characteristics |
|---------|------|-------------|-----------------|
| **toon.json** | 0.6 KB | Hiking records with nested context | Uniform array (3 records, 6 fields), mixed nesting |
| **scars.json** | 9.8 KB | Error tracking data | Mixed structure, heterogeneous fields |
| **128KB.json** | 249 KB | Large structured data (788 employee records) | Many nested arrays, wide tables |
| **historical.json** | 127 KB | Historical OHLCV data | Repeated `{time, value}` pattern (struct candidate) |
| **chart.json** | 196 KB | 1,256 candles | Deep nesting, array-heavy, metadata objects |
| **quote.json** | 283 KB | Single quote (nested) | Complex nested structure with 20+ fields |
| **gainers.json** | 257 KB | 100 complex quotes | Complex irregular nested objects (20+ fields each) |

---

## Results Summary

| Dataset | Pretty JSON | Compact JSON | AGONRows | AGONColumns | AGONStruct | **Auto Selected** | **Savings** |
|---------|-------------|--------------|----------|-------------|------------|-------------------|-------------|
| **toon.json** | 229 | 139 | **96** | 108 | 144 | **rows (96)** | **+58.1%** |
| **scars.json** | 2,600 | **2,144** | 2,225 | 2,230 | 2,448 | **json (2,144)** | **+17.5%** |
| **128KB.json** | 77,346 | 62,378 | **54,622** | 54,292 | 59,926 | **rows (54,622)** | **+29.4%** |
| **historical.json** | 84,094 | 55,228 | 70,286 | 70,286 | **48,969** | **struct (48,969)** | **+41.8%** |
| **chart.json** | 101,767 | 71,623 | **51,541** | 51,558 | 65,364 | **rows (51,541)** | **+49.4%** |
| **quote.json** | 128,981 | 85,956 | 67,251 | **65,586** | 69,053 | **columns (65,586)** | **+49.2%** |
| **gainers.json** | 142,791 | 91,634 | 113,132 | 113,132 | **89,012** | **struct (89,012)** | **+37.7%** |

!!! success "Safety Net Demonstrated"

    **scars.json** shows auto mode's safety guarantee in action:

    - All AGON formats produce worse or marginal results compared to compact JSON
    - Auto mode **correctly fell back to JSON**, avoiding regression
    - Auto selection uses the compact-JSON baseline for `min_savings` gating (see [AGON.encode](api.md#agonencode))

    **gainers.json** demonstrates adaptive format selection:

    - Rows/Columns formats made token counts **worse** than compact JSON (113K vs 91K)
    - Auto mode selected Struct format (89,012 tokens), achieving 37.7% savings vs pretty JSON

---

## Performance

AGON's core encoding engine is built in **Rust** and exposed to Python via **PyO3**, delivering exceptional performance even on large datasets.

### Encode Times

Time to encode data to each format (in milliseconds):

| Dataset | Size | Records | JSON | Rows | Columns | Struct | Auto (selected) |
|---------|------|---------|------|------|---------|--------|-----------------|
| [toon.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/toon.json) | 0.6 KB | 1 | 0.00 ms | 0.10 ms | 0.09 ms | 0.14 ms | **0.40 ms** (rows) |
| [scars.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/scars.json) | 9.8 KB | 1 | 0.01 ms | 0.56 ms | 0.51 ms | 0.64 ms | **1.65 ms** (json) |
| [128KB.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/128KB.json) | 249 KB | 788 | 0.16 ms | 16.82 ms | 14.10 ms | 19.49 ms | **27.94 ms** (rows) |
| [historical.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/historical.json) | 127 KB | 1 | 1.05 ms | 20.72 ms | 21.09 ms | 31.90 ms | **36.22 ms** (struct) |
| [chart.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/chart.json) | 196 KB | 1,256 | 0.50 ms | 26.46 ms | 25.27 ms | 35.97 ms | **36.55 ms** (rows) |
| [quote.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/quote.json) | 283 KB | 1 | 0.62 ms | 47.15 ms | 42.86 ms | 67.44 ms | **63.21 ms** (columns) |
| [gainers.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/gainers.json) | 257 KB | 100 | 0.72 ms | 47.46 ms | 42.46 ms | 62.38 ms | **71.10 ms** (struct) |

### Decode Times

Time to decode data from each format back to Python objects (in milliseconds):

| Dataset | Size | Records | JSON | Rows | Columns | Struct | Auto (selected) |
|---------|------|---------|------|------|---------|--------|-----------------|
| [toon.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/toon.json) | 0.6 KB | 1 | 0.01 ms | 0.30 ms | 0.12 ms | 0.29 ms | **0.48 ms** (rows) |
| [scars.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/scars.json) | 9.8 KB | 1 | 0.05 ms | 3.26 ms | 0.76 ms | 3.20 ms | **0.11 ms** (json) |
| [128KB.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/128KB.json) | 249 KB | 788 | 0.91 ms | 22.68 ms | 17.28 ms | 60.26 ms | **19.91 ms** (rows) |
| [historical.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/historical.json) | 127 KB | 1 | 2.50 ms | 131.49 ms | 30.78 ms | 68.84 ms | **68.35 ms** (struct) |
| [chart.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/chart.json) | 196 KB | 1,256 | 1.30 ms | 33.20 ms | 31.50 ms | 57.79 ms | **33.39 ms** (rows) |
| [quote.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/quote.json) | 283 KB | 1 | 1.91 ms | 92.92 ms | 52.45 ms | 102.22 ms | **45.21 ms** (columns) |
| [gainers.json](https://github.com/Verdenroz/agon-python/blob/master/tests/data/gainers.json) | 257 KB | 100 | 2.06 ms | 241.39 ms | 68.67 ms | 139.56 ms | **141.88 ms** (struct) |

### Rust + PyO3 Architecture

AGON's performance comes from its **Rust core** with **zero-copy PyO3 bindings**:

- **Parallel encoding**: Uses `rayon` for concurrent format evaluation in auto mode
- **Fast tokenization**: Rust implementation of `tiktoken` for accurate token counting
- **Memory efficient**: Minimal allocations, string operations optimized
- **Native speed**: Compiled Rust code with Python convenience

```python
# Behind the scenes, this Rust code runs:
# - Parallel format encoding with rayon
# - Fast JSON parsing with serde_json
# - Efficient string building with zero allocations
result = AGON.encode(large_dataset, format="auto")
```

---

## Savings

<div style="position: relative; height: 400px; margin: 2rem 0;">
  <canvas id="savingsChart"></canvas>
</div>

---

## Running Benchmarks

Reproduce these results locally:

```bash
# Run all benchmarks with verbose output
uv run pytest tests/test_benchmarks.py -v

# Run benchmarks for specific dataset
uv run pytest tests/test_benchmarks.py::test_benchmark_toon -v
```

---

## Methodology

### Token Counting

All token counts use `tiktoken` library with `o200k_base` encoding:

```python
import tiktoken

encoding = tiktoken.get_encoding("o200k_base")
tokens = len(encoding.encode(text))
```

This encoding is used by:

- GPT-4 (all variants)
- GPT-4 Turbo
- GPT-4o

### Baseline Comparison

**Pretty JSON:** `json.dumps(data, indent=2)`

- Standard 2-space indentation
- Newlines after each field
- Human-readable, not optimized

**Compact JSON:** `json.dumps(data, separators=(',', ':'))`

- No whitespace
- Minimal formatting
- **Primary baseline** for AGON `min_savings` comparison

### Format Testing

Each dataset tested with all formats:

1. **AGONRows:** Row-based tabular encoding
2. **AGONColumns:** Columnar transpose encoding
3. **AGONStruct:** Template-based encoding
4. **Auto mode:** Selects best of above or falls back to JSON

### Savings Calculation

```python
savings_percent = ((baseline - agon) / baseline) * 100
```

- **Positive %:** AGON saved tokens (better)
- **Negative %:** AGON used more tokens (worse—triggers JSON fallback)

---

## Next Steps

### [JSON Fallback](formats/json.md)

View how JSON is used as a safety net

### [AGONRows Format](formats/rows.md)

Learn about the most common format

### [API Reference](api.md)

Complete API documentation

### [Core Concepts](concepts.md)

Design principles and adaptive approach

<script>
// Benchmark data embedded for Chart.js
window.benchmarkData = {
  "datasets": [
    {
      "name": "toon.json",
      "description": "Hiking records with nested context (3 records, 6 fields)",
      "pretty": 229,
      "compact": 139,
      "rows": 96,
      "columns": 108,
      "struct": 144,
      "auto_format": "rows",
      "auto_tokens": 96
    },
    {
      "name": "scars.json",
      "description": "Error tracking data with nested structures",
      "pretty": 2600,
      "compact": 2144,
      "rows": 2225,
      "columns": 2230,
      "struct": 2448,
      "auto_format": "json",
      "auto_tokens": 2144
    },
    {
      "name": "128KB.json",
      "description": "Large structured data (788 employee records)",
      "pretty": 77346,
      "compact": 62378,
      "rows": 54622,
      "columns": 54292,
      "struct": 59926,
      "auto_format": "rows",
      "auto_tokens": 54622
    },
    {
      "name": "historical.json",
      "description": "Historical OHLCV time-series data",
      "pretty": 84094,
      "compact": 55228,
      "rows": 70286,
      "columns": 70286,
      "struct": 48969,
      "auto_format": "struct",
      "auto_tokens": 48969
    },
    {
      "name": "chart.json",
      "description": "Chart configuration with 1,256 candles",
      "pretty": 101767,
      "compact": 71623,
      "rows": 51541,
      "columns": 51558,
      "struct": 65364,
      "auto_format": "rows",
      "auto_tokens": 51541
    },
    {
      "name": "quote.json",
      "description": "Single quote with complex nested structure",
      "pretty": 128981,
      "compact": 85956,
      "rows": 67251,
      "columns": 65586,
      "struct": 69053,
      "auto_format": "columns",
      "auto_tokens": 65586
    },
    {
      "name": "gainers.json",
      "description": "Market gainers with complex nested objects (100 quotes)",
      "pretty": 142791,
      "compact": 91634,
      "rows": 113132,
      "columns": 113132,
      "struct": 89012,
      "auto_format": "struct",
      "auto_tokens": 89012
    }
  ]
};
</script>
