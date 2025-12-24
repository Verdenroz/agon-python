# AGON

[![PyPI version](https://img.shields.io/pypi/v/agon-python.svg)](https://pypi.org/project/agon-python/)
[![Python versions](https://img.shields.io/pypi/pyversions/agon-python.svg)](https://pypi.org/project/agon-python/)
[![License](https://img.shields.io/pypi/l/agon-python.svg)](https://github.com/Verdenroz/agon-python/blob/master/LICENSE)
[![CI](https://github.com/Verdenroz/agon-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Verdenroz/agon-python/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Verdenroz/agon-python/branch/master/graph/badge.svg)](https://codecov.io/gh/Verdenroz/agon-python)

**Adaptive Guarded Object Notation** - a self-describing, multi-format JSON encoding optimized for LLM prompts with one guarantee: **never worse than JSON**.

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
# Auto tries: text, columns, struct
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

# Encode with auto-selection (tries text/columns/struct, picks best or falls back to JSON)
result = AGON.encode(data, format="auto")
print(f"Selected format: {result.format}")  # → "text"
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
# 1. Generation instructions via AGON.hint(result)
# 2. An example with header via result.with_header()
prompt = f"""Analyze this user data and return enriched data in AGON format.

Instructions: {AGON.hint(result)}

Example output:
{result.with_header()}

Task: Add an is_admin boolean field and return in the same format."""

# Example LLM response (hypothetical - accuracy not guaranteed)
llm_response = """@AGON text

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

AGON provides three specialized **repetition-aware** encoding formats that are friendly to LLMs:

### The Three Formats

1. **AGONText**: Row-based tabular encoding for arrays of uniform objects
   - Similar to TOON's approach
   - Best for: Uniform arrays with consistent fields
   - Example: User lists, transaction logs, simple metrics

2. **AGONColumns**: Columnar encoding with type clustering
   - Transposes data: groups same-type values together
   - Best for: Wide tables (many columns), numeric-heavy data
   - Example: Financial data with 20+ fields per record

3. **AGONStruct**: Template-based encoding for repeated nested patterns
   - Declares struct templates (e.g., `S(...)`) once, reuses with values
   - Best for: Complex nested objects with repeated shapes
   - Example: Market data with nested `{fmt, raw}` or `{value, timestamp}` patterns

### Adaptive Auto Mode

```python
result = AGON.encode(data, format="auto")
```

**How `auto` works:**

1. **Try all formats**: Encodes data with text, columns, struct
2. **Count tokens**: Measures each encoding's token count
3. **Compare to JSON**: Calculates savings vs compact JSON baseline
4. **Apply threshold**: Requires minimum savings (default 5%) to use specialized format
5. **Select winner**: Returns format with best savings, or JSON if none meet threshold

**The guarantee:** Auto mode *never* returns a format with more tokens than compact JSON. If all specialized formats are worse or marginally better, it returns JSON.

**Example decision tree:**
```
Data shape analysis:
  → Text:    96 tokens (30.9% better than JSON)   ✅ Winner
  → Columns: 108 tokens (22.3% better than JSON)  ❌ Not optimal
  → Struct:  130 tokens (6.5% better than JSON)   ❌ Not optimal
  → JSON:    139 tokens (baseline)                ❌ Fallback

Decision: Use text (best savings, exceeds 10% threshold)
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
| **AGON text** | 96 | **+58.1%** ✅ | **+30.9%** ✅ | Tied with TOON |
| **AGON columns** | 108 | **+52.8%** ✅ | **+22.3%** ✅ | |
| **AGON struct** | 130 | **+43.2%** ✅ | **+6.5%** ✅ | |
| **AGON auto** | **96** | **+58.1%** ✅ | **+30.9%** ✅ | **Winner** (selected `text`) |

### Format Encodings with Explanations

**TOON (96 tokens, +58.1% savings):**
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

**How it works:** TOON uses YAML-like indentation for nested objects and CSV-style tab-delimited rows for arrays. The `[3]` declares array length and `{fields}` lists column headers—giving LLMs explicit structure to validate against.

---

**AGON text (96 tokens, +58.1% savings - identical to TOON!):**
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

**Why auto selected this:** AGON's text format produces identical output to TOON for uniform arrays. Auto mode tried all three formats and chose text because it had the lowest token count (96 vs 108 for columns vs 130 for struct).

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

**How it works:** Columnar format transposes the data, grouping same-type values together. This can be more token-efficient for wide tables (20+ columns) or numeric-heavy data where type clustering improves compression. Not selected here because text format is better for this data shape.

---

**AGON struct (130 tokens, +43.2% savings):**
```
@S: companion, distanceKm, elevationGain, id, name, wasSunny

context:
  task: Our favorite hikes together
  location: Boulder
  season: spring_2025
friends:
  [3]:
    - ana
    - luis
    - sam
hikes:
  [3]: S(ana, 7.5, 320, 1, Blue Lake Trail, true), S(luis, 9.2, 540, 2, Ridge Overlook, false), S(sam, 5.1, 180, 3, Wildflower Loop, true)
```

**How it works:** Struct format declares reusable templates (`S`) once at the top, then references them with just values. Excels at deeply nested data with repeated patterns. Not optimal here because the hikes array is already flat—text format is more efficient.

### When AGON Falls Back to JSON

But what about data where specialized formats don't provide enough benefit? Let's look at [`gainers.json`](tests/data/gainers.json) (100 complex quote objects with deeply nested structures):

| Format | Tokens | Savings vs Pretty JSON | Decision |
|--------|--------|------------------------|----------|
| **JSON (pretty)** | 142,791 | — (baseline) | |
| **JSON (compact)** | 91,634 | **+35.8%** ✅ | |
| **AGON text** | 113,132 | **+20.8%** ✅ | |
| **AGON columns** | 113,132 | **+20.8%** ✅ | |
| **AGON struct** | 89,011 | **+37.7%** ✅ (best format!) | |
| **AGON auto** | **91,634** | **+35.8%** (returned compact JSON) | ✅ **Safe choice** |

**AGON's safety net in action:** Even though `struct` format achieved the best savings (37.7%), when compared against *compact* JSON (the real alternative), struct only saved 2.9%—below the minimum threshold (default 10%). Rather than risk the encoding overhead for marginal gains, `auto` returned compact JSON, guaranteeing excellent performance with zero complexity.

**Key insight:** Text/columns formats actually *hurt* compared to compact JSON (113K vs 91K tokens), but `auto` intelligently avoided them. And while struct was marginally better, the gains weren't worth the format overhead.

**With AGON:** You get compact JSON back (35.8% better than pretty), paying zero format complexity, with zero risk.

## Use Cases

AGON excels in scenarios where data structure varies and intelligent format selection provides value:

- **Variable data pipelines**: Data that changes shape (sometimes uniform arrays, sometimes nested objects) where auto-mode selects the optimal format
- **Data projection workflows**: Use cases where filtering fields before encoding is important (`AGON.project_data`)
- **Cost-sensitive applications**: Where honest fallback to compact JSON prevents paying encoding overhead when specialized formats don't provide enough benefit

**When AGON helps most:**
- Repeated nested patterns (AGONStruct: up to 49% savings vs pretty JSON)
- Uniform arrays (AGONText: up to 58% savings vs pretty JSON)
- Mixed data types where adaptive selection matters

**When AGON helps least:**
- Tiny JSON payloads (encoding overhead > savings)
- Highly irregular objects with no repetition (auto-mode falls back to JSON)

## API Reference

### Encoding

```python
# Auto (recommended)
result = AGON.encode(data)

# Choose a specific format
result = AGON.encode(data, format="text")
result = AGON.encode(data, format="columns")
result = AGON.encode(data, format="struct")
result = AGON.encode(data, format="json")

# Auto-mode controls
result = AGON.encode(data, format="auto", force=True)        # never pick JSON
result = AGON.encode(data, format="auto", min_savings=0.10)  # require 10% savings vs JSON
```

### Decoding

```python
# Auto-detect by header
decoded = AGON.decode(payload_with_header)

# Or decode with an explicit format (header not required)
decoded = AGON.decode(payload_without_header, format="text")
```

### Helpers

```python
# Keep only specific fields (supports dotted paths like "user.profile.name" or "quotes.symbol")
projected = AGON.project_data(data, ["id", "name"])

# Get prescriptive generation instructions for LLMs (when asking LLMs to return AGON format)
result = AGON.encode(data, format="auto")
hint = AGON.hint(result)  # Instructions for the selected format
# or
hint = AGON.hint("text")  # Instructions for a specific format

# Token counting helper
tokens = AGON.count_tokens("hello world")
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

This repo includes an MkDocs site under `docs/`.

```bash
# Serve locally
make docs
```

## Benchmarks

AGON's adaptive approach yields variable results depending on data structure, demonstrating its intelligent format selection:

### Real-World Results

Benchmarks on actual test fixtures from [`tests/data/`](tests/data/), showing token counts for all formats:

| Dataset | Type | JSON Pretty | JSON Compact | Text | Columns | Struct | **Auto** | **Selected** |
|---------|------|-------------|--------------|------|---------|--------|----------|--------------|
| [`toon.json`](tests/data/toon.json) | Hiking records (nested) | 229 | 139 (+39.3%) | 96 (+58.1%) | 108 (+52.8%) | 130 (+43.2%) | **96** | **text** |
| [`chart.json`](tests/data/chart.json) | 1,256 candles | 101,767 | 71,623 (+29.6%) | 51,541 (+49.4%) | 51,558 (+49.3%) | 61,595 (+39.5%) | **51,541** | **text** |
| [`quote.json`](tests/data/quote.json) | Single quote (nested) | 128,981 | 85,956 (+33.4%) | 67,251 (+47.9%) | 65,586 (+49.2%) | 65,698 (+49.1%) | **65,586** | **columns** |
| [`128KB.json`](tests/data/128KB.json) | 788 employee records | 77,346 | 62,378 (+19.4%) | 54,622 (+29.4%) | 54,292 (+29.8%) | 56,772 (+26.6%) | **54,292** | **columns** |
| [`historical.json`](tests/data/historical.json) | Historical OHLCV data | 84,094 | 55,228 (+34.3%) | 70,286 (+16.4%) | 70,286 (+16.4%) | 47,713 (+43.3%) | **47,713** | **struct** |
| [`gainers.json`](tests/data/gainers.json) | 100 complex quotes | 142,791 | 91,634 (+35.8%) | 113,132 (+20.8%) | 113,132 (+20.8%) | 89,011 (+37.7%) | **91,634** | **json** ⚠️ |
| [`scars.json`](tests/data/scars.json) | Error records | 2,600 | 2,144 (+17.5%) | 2,225 (+14.4%) | 2,230 (+14.2%) | 2,437 (+6.3%) | **2,144** | **json** ⚠️ |

**Key insights from the data:**
- **text** format excels at uniform arrays (toon, chart)
- **columns** format wins for wide tables with many fields (quote, 128KB)
- **struct** format dominates deeply nested repeated patterns
- **json** fallback returns compact JSON when specialized formats don't meet `min_savings` threshold


### Running Benchmarks

```bash
# Print detailed token counts and savings for all test fixtures
uv run pytest tests/test_benchmarks.py -s --cov-fail-under=0
```

The documentation site also includes a Benchmarks page with recent results and methodology.

## Related Projects and Resources

### TOON Format
- **Website**: [https://toonformat.dev](https://toonformat.dev/)
- **Github**: [https://github.com/toon-format/toon](https://github.com/toon-format/toon)

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
