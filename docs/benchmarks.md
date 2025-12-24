# Benchmarks

Real-world performance data demonstrating AGON's adaptive format selection and token savings.

---

## Overview

These benchmarks measure token counts across 6 real-world datasets using tiktoken's `o200k_base` encoding (GPT-4, GPT-4 Turbo, GPT-4o). All results are reproducible—run `uv run pytest tests/test_benchmarks.py -v` to verify.

---

## Benchmark Datasets

| Dataset | Size | Description | Characteristics |
|---------|------|-------------|-----------------|
| **toon.json** | 665 bytes | Hiking records with nested context | Uniform array (3 records, 6 fields), mixed nesting |
| **128KB.json** | 255 KB | Large structured data | Many nested arrays, wide tables |
| **chart.json** | 201 KB | Chart.js configuration | Deep nesting, array-heavy, metadata objects |
| **gainers.json** | 263 KB | Market gainers (100 quotes) | Complex irregular nested objects (20+ fields each) |
| **scars.json** | 10 KB | Error tracking data | Mixed structure, heterogeneous fields |
| **historical.json** | 130 KB | Historical time-series data | Repeated `{time, value}` pattern (struct candidate) |

---

## Results Summary

| Dataset | Pretty JSON | Compact JSON | AGONText | AGONColumns | AGONStruct | **Auto Selected** | **Savings** |
|---------|-------------|--------------|----------|-------------|------------|-------------------|-------------|
| **toon.json** | 229 | 139 | **96** | 108 | 130 | **text (96)** | **+58.1%** |
| **128KB.json** | 77,346 | 63,230 | 54,622 | **54,292** | 56,772 | **columns (54,292)** | **+29.8%** |
| **chart.json** | 101,767 | 71,802 | **51,541** | 51,558 | 61,595 | **text (51,541)** | **+49.4%** |
| **gainers.json** | 142,791 | **91,634** | 113,132 | 113,132 | 89,011 | **json (91,634)** | **+35.8%** |
| **scars.json** | 2,600 | **2,144** | 2,225 | 2,230 | 2,437 | **json (2,144)** | **+17.5%** |
| **historical.json** | 84,094 | 55,228 | 70,286 | 70,286 | **47,713** | **struct (47,713)** | **+43.3%** |

!!! success "Safety Net Demonstrated"

    **gainers.json** and **scars.json** show auto mode's safety guarantee in action:

    - Text/Columns formats made token counts **worse** than compact JSON (113K vs 91K for gainers)
    - Auto mode **correctly fell back to JSON**, avoiding regression
    - Auto selection uses the compact-JSON baseline for `min_savings` gating (see [AGON.encode](api.md#agonencode)), so `gainers.json` chose JSON even though savings against pretty JSON are high.

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

1. **AGONText:** Row-based tabular encoding
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

### [AGONText Format](formats/text.md)

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
      "text": 96,
      "columns": 108,
      "struct": 130,
      "auto_format": "text",
      "auto_tokens": 96
    },
    {
      "name": "128KB.json",
      "description": "Large structured data (128KB)",
      "pretty": 77346,
      "compact": 63230,
      "text": 54622,
      "columns": 54292,
      "struct": 56772,
      "auto_format": "columns",
      "auto_tokens": 54292
    },
    {
      "name": "chart.json",
      "description": "Chart configuration with nested arrays",
      "pretty": 101767,
      "compact": 71802,
      "text": 51541,
      "columns": 51558,
      "struct": 61595,
      "auto_format": "text",
      "auto_tokens": 51541
    },
    {
      "name": "gainers.json",
      "description": "Market gainers with complex nested objects (100 quotes)",
      "pretty": 142791,
      "compact": 91634,
      "text": 113132,
      "columns": 113132,
      "struct": 89011,
      "auto_format": "json",
      "auto_tokens": 91634
    },
    {
      "name": "scars.json",
      "description": "Error tracking data with nested structures",
      "pretty": 2600,
      "compact": 2144,
      "text": 2225,
      "columns": 2230,
      "struct": 2437,
      "auto_format": "json",
      "auto_tokens": 2144
    },
    {
      "name": "historical.json",
      "description": "Historical time-series data",
      "pretty": 84094,
      "compact": 55228,
      "text": 70286,
      "columns": 70286,
      "struct": 47713,
      "auto_format": "struct",
      "auto_tokens": 47713
    }
  ]
};
</script>
