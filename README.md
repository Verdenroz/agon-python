# AGON

[![PyPI version](https://img.shields.io/pypi/v/agon-python.svg)](https://pypi.org/project/agon-python/)
[![Python versions](https://img.shields.io/pypi/pyversions/agon-python.svg)](https://pypi.org/project/agon-python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/Verdenroz/agon-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Verdenroz/agon-python/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Verdenroz/agon-python/branch/master/graph/badge.svg)](https://codecov.io/gh/Verdenroz/agon-python)
[![Rust](https://img.shields.io/badge/rust-%23000000.svg?style=flat&logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![PyO3](https://img.shields.io/badge/PyO3-v0.27-blue)](https://pyo3.rs/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://Verdenroz.github.io/agon-python/)

**Adaptive Guarded Object Notation** - a self-describing, multi-format JSON encoding optimized for LLM prompts with one guarantee: **never worse than JSON**.

📚 **[Full Documentation](https://Verdenroz.github.io/agon-python/)** | 🚀 **[Quick Start](#quick-start)** | ⚡ **[Benchmarks](#benchmarks)**

## Table of Contents

- [Why AGON?](#why-agon)
- [Quick Comparison: AGON vs TOON](#quick-comparison-agon-vs-toon)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Concrete Example: TOON vs AGON](#concrete-example-toon-vs-agon)
- [Use Cases](#use-cases)
- [API Reference](#api-reference)
- [Benchmarks](#benchmarks)
- [Development](#development)
- [Related Projects and Resources](#related-projects-and-resources)
- [Contributing](#contributing)
- [License](#license)

## Why AGON?

**The Problem:** Fixed-format encoders can actually make token counts worse. When your data doesn't match the encoder's assumptions (e.g., deeply nested objects, sparse arrays, irregular structures), you pay the overhead of the format *without* the benefits.

**AGON's Solution:** Adaptive encoding with multiple guard rails.

```python
result = AGON.encode(data, format="auto")
# Auto tries: rows, columns, struct
# Returns: whichever saves the most tokens
# Falls back: to compact JSON if none are better
```

## Quick Comparison: AGON vs TOON

| Aspect | TOON | AGON |
|--------|------|------|
| **Approach** | Single unified format | Multiple adaptive formats + JSON fallback |
| **Risk** | Can be worse than JSON on irregular data | **Never worse than JSON** (guaranteed) |
| **Format Selection** | Always applies TOON encoding | Auto-selects best format or falls back to JSON |
| **Best For** | Uniform arrays, consistent pipelines | Variable data shapes, risk-averse optimization |
| **Philosophy** | "One format for all JSON" | "Best format for each data shape, or JSON" |


## Installation

```bash
pip install agon-python
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add agon-python
```

## Quick Start

### Basic Usage: Encode and Use in LLM Prompts

```python
from agon import AGON

# Sample data - list of objects with repeated structure
data = [
    {"id": 1, "name": "Alice", "role": "admin"},
    {"id": 2, "name": "Bob", "role": "user"},
    {"id": 3, "name": "Charlie", "role": "user"},
]

# Encode with auto-selection (tries rows/columns/struct, picks best or falls back to JSON)
result = AGON.encode(data, format="auto")
print(f"Selected format: {result.format}")  # → "rows"
print(f"Encoded output:\n{result}")
# Outputs clean format WITHOUT @AGON header:
# [3]{id	name	role}
# 1	Alice	admin
# 2	Bob	user
# 3	Charlie	user

# Verify lossless round-trip
decoded = AGON.decode(result)
assert decoded == data  # ✅ Perfect reconstruction

# Use directly in LLM prompts - no header needed for sending data to LLMs
prompt = f"""Analyze this user data:

{result}

What percentage are admins?"""

# LLM can easily parse the structured format and respond with: "33.3% (1 out of 3 users)"
```

### Experimental: Asking LLMs to Generate AGON Format

**⚠️ Note:** LLMs have NOT been trained on AGON format, so accuracy cannot be guaranteed. This is an experimental feature. For production use, prefer **sending AGON to LLMs** (reliable) over **asking LLMs to generate AGON** (experimental, requires validation).

```python
from agon import AGON

# Same data as before
data = [
    {"id": 1, "name": "Alice", "role": "admin"},
    {"id": 2, "name": "Bob", "role": "user"},
    {"id": 3, "name": "Charlie", "role": "user"},
]

result = AGON.encode(data, format="auto")

# To ask an LLM to respond in AGON format, provide both:
# 1. Generation instructions via result.hint()
# 2. An example with header via result.with_header()
prompt = f"""Analyze this user data and return enriched data in AGON format.

Instructions: {result.hint()}

Example output:
{result.with_header()}

Task: Add an is_admin boolean field and return in the same format."""

# Example LLM response (hypothetical - accuracy not guaranteed)
llm_response = """@AGON rows

[3]{name	role	is_admin}
Alice	admin	true
Bob	user	false
Charlie	user	false"""

# Decode LLM response using header to auto-detect format
parsed = AGON.decode(llm_response)
# → [{"name": "Alice", "role": "admin", "is_admin": True},
#    {"name": "Bob", "role": "user", "is_admin": False},
#    {"name": "Charlie", "role": "user", "is_admin": False}]

admin_count = sum(1 for user in parsed if user.get("is_admin"))
print(f"Admin percentage: {admin_count / len(parsed) * 100:.1f}%")  # → 33.3%
```

## How It Works

AGON provides three specialized **repetition-aware** encoding formats that are friendly to LLMs, powered by a **high-performance Rust core** for minimal latency:

### The Three Formats

1. **AGONRows**: Row-based tabular encoding for arrays of uniform objects
   - Similar to [TOON format](https://github.com/toon-format/toon)
   - Best for: Uniform arrays with consistent fields
   - Example: User lists, transaction logs, simple metrics

2. **AGONColumns**: Columnar encoding with type clustering
   - Transposes data: groups same-type values together
   - Best for: Wide tables (many columns), numeric-heavy data
   - Example: Financial data with 20+ fields per record

3. **AGONStruct**: Template-based encoding for repeated nested patterns
   - Similar to [TRON format](https://github.com/tron-format/tron-javascript) but with abbreviated struct names
   - Best for: Complex nested objects with repeated shapes
   - Example: Market data with nested `{fmt, raw}` or `{value, timestamp}` patterns

### Rust-Powered Performance

AGON's core encoding/decoding is implemented in **Rust** with **PyO3** bindings, delivering:

- **Parallel format selection**: Auto mode uses [Rayon](https://github.com/rayon-rs/rayon) to encode all formats concurrently
- **Native Python integration**: Format classes (`AGONRows`, `AGONColumns`, `AGONStruct`) exposed as Python objects via PyO3

### Adaptive Auto Mode

```python
result = AGON.encode(data, format="auto")
```

**How `auto` works:**

1. **Try all formats in parallel**: Rust encodes rows, columns, struct concurrently
2. **Count tokens**: Measures each encoding's token count
3. **Compare to JSON**: Calculates savings vs compact JSON baseline
4. **Apply threshold**: Requires minimum savings (default 10%) to use specialized format
5. **Select winner**: Returns format with best savings, or JSON if none meet threshold

**The guarantee:** Auto mode *never* returns a format with more tokens than compact JSON. If all specialized formats are worse or marginally better, it returns JSON.

**Example decision tree:**
```
Data shape analysis:
  → Rows:    96 tokens (30.9% better than JSON)   ✅ Winner
  → Columns: 108 tokens (22.3% better than JSON)  ❌ Not optimal
  → Struct:  130 tokens (6.5% better than JSON)   ❌ Not optimal
  → JSON:    139 tokens (baseline)                ❌ Fallback

Decision: Use rows (best savings, exceeds 10% threshold)
```

All non-JSON encodings start with an `@AGON ...` header so they can be decoded later.

## Concrete Example: TOON vs AGON

Let's compare formats on the same data with real token counts (using `o200k_base` tokenizer).

### Source Data: [toon.json](tests/data/toon.json)

This example demonstrates encoding a list of hiking records with nested context and uniform arrays—a common LLM use case.

**JSON (pretty, 229 tokens - baseline):**
```json
{
  "context": {"task": "Our favorite hikes together", "location": "Boulder", "season": "spring_2025"},
  "friends": ["ana", "luis", "sam"],
  "hikes": [
    {"id": 1, "name": "Blue Lake Trail", "distanceKm": 7.5, "elevationGain": 320, "companion": "ana", "wasSunny": true},
    {"id": 2, "name": "Ridge Overlook", "distanceKm": 9.2, "elevationGain": 540, "companion": "luis", "wasSunny": false},
    {"id": 3, "name": "Wildflower Loop", "distanceKm": 5.1, "elevationGain": 180, "companion": "sam", "wasSunny": true}
  ]
}
```

**JSON (compact, 139 tokens):**
```json
{"context":{"task":"Our favorite hikes together","location":"Boulder","season":"spring_2025"},"friends":["ana","luis","sam"],"hikes":[{"id":1,"name":"Blue Lake Trail","distanceKm":7.5,"elevationGain":320,"companion":"ana","wasSunny":true},{"id":2,"name":"Ridge Overlook","distanceKm":9.2,"elevationGain":540,"companion":"luis","wasSunny":false},{"id":3,"name":"Wildflower Loop","distanceKm":5.1,"elevationGain":180,"companion":"sam","wasSunny":true}]}
```

### Token Comparison

| Format | Tokens | Savings vs Pretty | Savings vs Compact | Winner |
|--------|--------|-------------------|--------------------|--------|
| **JSON (pretty)** | 229 | — (baseline) | -64.7% 📉 | |
| **JSON (compact)** | 139 | +39.3% ✅ | — (baseline) | |
| **TOON** | 96 | **+58.1%** ✅ | **+30.9%** ✅ | |
| **AGON rows** | 96 | **+58.1%** ✅ | **+30.9%** ✅ | Tied with TOON |
| **AGON columns** | 108 | **+52.8%** ✅ | **+22.3%** ✅ | |
| **AGON struct** | 130 | **+43.2%** ✅ | **+6.5%** ✅ | |
| **AGON auto** | **96** | **+58.1%** ✅ | **+30.9%** ✅ | **Winner** (selected `rows`) |

### Format Encodings with Explanations

**TOON (96 tokens, +58.1% savings):**
```
context:
  task: Our favorite hikes together
  location: Boulder
  season: spring_2025
friends[3]: ana,luis,sam
hikes[3]{id,name,distanceKm,elevationGain,companion,wasSunny}:
  1,Blue Lake Trail,7.5,320,ana,true
  2,Ridge Overlook,9.2,540,luis,false
  3,Wildflower Loop,5.1,180,sam,true
```

**How it works:** TOON uses YAML-like indentation for nested objects and **comma-delimited** rows for arrays. The `[3]` declares array length and `{fields}` lists column headers—giving LLMs explicit structure to validate against.

---

**AGON rows (96 tokens, +58.1% savings - nearly identical to TOON!):**
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

**How it works:** AGON rows uses the same structure as TOON but with **tab-delimited** rows instead of commas. Both achieve identical token counts (96 tokens) because the delimiter choice doesn't significantly affect tokenization. Auto mode chose rows because it had the lowest token count (96 vs 108 for columns vs 130 for struct).

---

**AGON columns (108 tokens, +52.8% savings):**
```
context:
  task: Our favorite hikes together
  location: Boulder
  season: spring_2025
friends[3]: ana	luis	sam
hikes[3]
├ id: 1	2	3
├ name: Blue Lake Trail	Ridge Overlook	Wildflower Loop
├ distanceKm: 7.5	9.2	5.1
├ elevationGain: 320	540	180
├ companion: ana	luis	sam
└ wasSunny: true	false	true
```

**How it works:** Columnar format transposes the data, grouping same-type values together. This can be more token-efficient for wide tables (20+ columns) or numeric-heavy data where type clustering improves compression. Not selected here because rows format is better for this data shape.

---

**AGON struct (144 tokens, +37.1% savings):**
```
@CDEI: companion, distanceKm, elevationGain, id, name, wasSunny

context:
  task: Our favorite hikes together
  location: Boulder
  season: spring_2025
friends
  [3]:
    - ana
    - luis
    - sam
hikes
  [3]:
    - CDEI(ana, 7.5, 320, 1, Blue Lake Trail, true)
    - CDEI(luis, 9.2, 540, 2, Ridge Overlook, false)
    - CDEI(sam, 5.1, 180, 3, Wildflower Loop, true)
```

**How it works:** Struct format declares reusable templates (`@CDEI: fields`) once at the top, then instantiates them with just values `CDEI(...)`. The struct name is generated from the first letter of each field (Companion, DistanceKm, ElevationGain, Id → CDEI).

### When AGON Falls Back to JSON

But what about data where specialized formats don't provide enough benefit? Let's look at [`gainers.json`](tests/data/gainers.json) (100 complex quote objects with deeply nested structures):

| Format | Tokens | Savings vs Pretty JSON | Decision |
|--------|--------|------------------------|----------|
| **JSON (pretty)** | 142,791 | — (baseline) | |
| **JSON (compact)** | 91,634 | **+35.8%** ✅ | |
| **AGON rows** | 113,132 | **+20.8%** ✅ | |
| **AGON columns** | 113,132 | **+20.8%** ✅ | |
| **AGON struct** | 89,011 | **+37.7%** ✅ (best format!) | |
| **AGON auto** | **91,634** | **+35.8%** (returned compact JSON) | ✅ **Safe choice** |

**AGON's safety net in action:** Even though `struct` format achieved the best savings (37.7%), when compared against *compact* JSON (the real alternative), struct only saved 2.9%—below the minimum threshold (default 10%). Rather than risk the encoding overhead for marginal gains, `auto` returned compact JSON, guaranteeing excellent performance with zero complexity.

**Key insight:** Rows/columns formats actually *hurt* compared to compact JSON (113K vs 91K tokens), but `auto` intelligently avoided them. And while struct was marginally better, the gains weren't worth the format overhead.

**With AGON:** You get compact JSON back (35.8% better than pretty), paying zero format complexity, with zero risk.

## Use Cases

AGON excels in scenarios where data structure varies and intelligent format selection provides value:

- **Variable data pipelines**: Data that changes shape (sometimes uniform arrays, sometimes nested objects) where auto-mode selects the optimal format
- **Data projection workflows**: Use cases where filtering fields before encoding is important (`AGON.project_data`)
- **Cost-sensitive applications**: Where honest fallback to compact JSON prevents paying encoding overhead when specialized formats don't provide enough benefit

**When AGON helps most:**
- Repeated nested patterns (AGONStruct: up to 49% savings vs pretty JSON)
- Uniform arrays (AGONRows: up to 58% savings vs pretty JSON)
- Mixed data types where adaptive selection matters

**When AGON helps least:**
- Tiny JSON payloads (encoding overhead > savings)
- Highly irregular objects with no repetition (auto-mode falls back to JSON)

## API Reference

### Encoding

```python
from agon import AGON, Encoding

# Auto (recommended) - uses fast byte-length estimation
result = AGON.encode(data)

# Auto with accurate token counting (slower but precise)
result = AGON.encode(data, encoding="o200k_base")  # or "cl100k_base", "p50k_base", etc.

# Choose a specific format
result = AGON.encode(data, format="rows")
result = AGON.encode(data, format="columns")
result = AGON.encode(data, format="struct")
result = AGON.encode(data, format="json")

# Auto-mode controls
result = AGON.encode(data, format="auto", force=True)        # never pick JSON
result = AGON.encode(data, format="auto", min_savings=0.10)  # require 10% savings vs JSON
```

### Decoding

```python
# Decode AGONEncoding directly
result = AGON.encode(data, format="rows")
decoded = AGON.decode(result)

# Decode string with auto-detection by header
decoded = AGON.decode(payload_with_header)

# Decode string with explicit format (header not required)
decoded = AGON.decode(payload_without_header, format="rows")
```

### AGONEncoding Methods

```python
result = AGON.encode(data, format="auto")

# Get the encoded text (for use in LLM prompts)
text = str(result)  # or just use result directly in f-strings
text = result.text  # explicit access

# Get character count
length = len(result)

# Get format that was selected
format_used = result.format  # "rows", "columns", "struct", or "json"

# Get format header
header = result.header  # "@AGON rows", "@AGON columns", etc.

# Get text with header prepended (for auto-detect decoding)
with_header = result.with_header()

# Get generation instructions for LLMs
hint = result.hint()
```

### Helpers

```python
# Keep only specific fields (supports dotted paths like "user.profile.name" or "quotes.symbol")
projected = AGON.project_data(data, ["id", "name"])

# Token counting helper (uses Rust tiktoken implementation)
tokens = AGON.count_tokens("hello world")  # default: o200k_base
tokens = AGON.count_tokens("hello world", encoding="cl100k_base")  # GPT-4/3.5-turbo
```

## Development

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Clone the repository
git clone https://github.com/Verdenroz/agon-python.git
cd agon

# Install dependencies (including dev)
uv sync --dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=agon --cov-report=html

# Run linting
uv run ruff check src tests
uv run ruff format src tests

# Run type checking
uv run basedpyright src

# Install pre-commit hooks
uv run pre-commit install
```

## Documentation

Full documentation is available at [https://Verdenroz.github.io/agon-python/](https://Verdenroz.github.io/agon-python/)

This repo includes an MkDocs site under `docs/`.

```bash
# Serve locally
make docs
```

## Benchmarks

AGON's adaptive approach yields variable results depending on data structure and format used. Benchmarks on actual test fixtures from [`tests/data/`](tests/data/).

### Performance

Encoding and decoding times for all formats across all datasets:

| Dataset | Size | Records | JSON | Rows | Columns | Struct | Auto (selected) |
|---------|------|---------|------|------|---------|--------|-----------------|
| [toon.json](tests/data/toon.json) | 0.6 KB | 1 | 0.00 / 0.01 ms | 0.10 / 0.30 ms | 0.09 / 0.12 ms | 0.14 / 0.29 ms | **0.40 / 0.48 ms** (rows) |
| [scars.json](tests/data/scars.json) | 9.8 KB | 1 | 0.01 / 0.05 ms | 0.56 / 3.26 ms | 0.51 / 0.76 ms | 0.64 / 3.20 ms | **1.65 / 0.11 ms** (json) |
| [128KB.json](tests/data/128KB.json) | 249 KB | 788 | 0.16 / 0.91 ms | 16.82 / 22.68 ms | 14.10 / 17.28 ms | 19.49 / 60.26 ms | **27.94 / 19.91 ms** (rows) |
| [historical.json](tests/data/historical.json) | 127 KB | 1 | 1.05 / 2.50 ms | 20.72 / 131.49 ms | 21.09 / 30.78 ms | 31.90 / 68.84 ms | **36.22 / 68.35 ms** (struct) |
| [chart.json](tests/data/chart.json) | 196 KB | 1,256 | 0.50 / 1.30 ms | 26.46 / 33.20 ms | 25.27 / 31.50 ms | 35.97 / 57.79 ms | **36.55 / 33.39 ms** (rows) |
| [quote.json](tests/data/quote.json) | 283 KB | 1 | 0.62 / 1.91 ms | 47.15 / 92.92 ms | 42.86 / 52.45 ms | 67.44 / 102.22 ms | **63.21 / 45.21 ms** (columns) |
| [gainers.json](tests/data/gainers.json) | 257 KB | 100 | 0.72 / 2.06 ms | 47.46 / 241.39 ms | 42.46 / 68.67 ms | 62.38 / 139.56 ms | **71.10 / 141.88 ms** (struct) |

### Token Efficiency

| Dataset | Type | JSON Pretty | JSON Compact | Rows | Columns | Struct | **Auto** | **Selected** |
|---------|------|-------------|--------------|------|---------|--------|----------|--------------|
| [toon.json](tests/data/toon.json) | Hiking records (nested) | 229 | 139 (+39.3%) | 96 (+58.1%) | 108 (+52.8%) | 144 (+37.1%) | **96** | **rows** |
| [scars.json](tests/data/scars.json) | Error records | 2,600 | 2,144 (+17.5%) | 2,225 (+14.4%) | 2,230 (+14.2%) | 2,448 (+5.8%) | **2,144** | **json** ⚠️ |
| [128KB.json](tests/data/128KB.json) | 788 employee records | 77,346 | 62,378 (+19.4%) | 54,622 (+29.4%) | 54,292 (+29.8%) | 59,926 (+22.5%) | **54,622** | **rows** |
| [historical.json](tests/data/historical.json) | Historical OHLCV data | 84,094 | 55,228 (+34.3%) | 70,286 (+16.4%) | 70,286 (+16.4%) | 48,969 (+41.8%) | **48,969** | **struct** |
| [chart.json](tests/data/chart.json) | 1,256 candles | 101,767 | 71,623 (+29.6%) | 51,541 (+49.4%) | 51,558 (+49.3%) | 65,364 (+35.8%) | **51,541** | **rows** |
| [quote.json](tests/data/quote.json) | Single quote (nested) | 128,981 | 85,956 (+33.4%) | 67,251 (+47.9%) | 65,586 (+49.2%) | 69,053 (+46.5%) | **65,586** | **columns** |
| [gainers.json](tests/data/gainers.json) | 100 complex quotes | 142,791 | 91,634 (+35.8%) | 113,132 (+20.8%) | 113,132 (+20.8%) | 89,012 (+37.7%) | **89,012** | **struct** |

**Key insights:**
- **rows** format excels at uniform arrays (toon, chart, 128KB)
- **columns** format wins for wide tables with many fields (quote)
- **struct** format dominates deeply nested repeated patterns (historical, gainers)
- **json** fallback returns compact JSON when specialized formats don't meet `min_savings` threshold using compact JSON as its baseline.

### Running Benchmarks

```bash
# Run performance benchmarks (token counts + encode/decode times)
make benchmarks

# Or directly with pytest
uv run pytest tests/test_benchmarks.py -s --no-cov -o addopts=""
```

The documentation site also includes a Benchmarks page with recent results and methodology.

## Related Projects and Resources

### TOON Format
- **Website**: [https://toonformat.dev](https://toonformat.dev/)
- **Github**: [https://github.com/toon-format/toon](https://github.com/toon-format/toon)

### TRON Format
- **Website** : [https://tron-format.github.io/](https://tron-format.github.io/)
- **GitHub**: [https://github.com/tron-format/tron-javascript](https://github.com/tron-format/tron-javascript)

### LLM Token Optimization
- [Anthropic's Prompt Engineering Guide](https://docs.anthropic.com/claude/docs/prompt-engineering)
- [OpenAI's Tokenizer](https://platform.openai.com/tokenizer)

## Contributing

Contributions welcome! AGON is in active development. Areas of interest:

- Additional format implementations (e.g., AGONTable for markdown tables)
- Performance optimizations for large datasets
- LLM parsing reliability tests
- Cross-language implementations (Go, Rust, TypeScript ports welcome)
- Editor support (VS Code extension, syntax highlighting)

Please open issues or PRs on [GitHub](https://github.com/Verdenroz/agon-python).

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**AGON** - Adaptive Guarded Object Notation
