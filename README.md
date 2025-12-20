# AGON

[![PyPI version](https://img.shields.io/pypi/v/agon-python.svg)](https://pypi.org/project/agon-python/)
[![Python versions](https://img.shields.io/pypi/pyversions/agon-python.svg)](https://pypi.org/project/agon-python/)
[![License](https://img.shields.io/pypi/l/agon-python.svg)](https://github.com/Verdenroz/agon/blob/main/LICENSE)
[![CI](https://github.com/Verdenroz/agon/actions/workflows/ci.yml/badge.svg)](https://github.com/Verdenroz/agon/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Verdenroz/agon/branch/main/graph/badge.svg)](https://codecov.io/gh/Verdenroz/agon)

**Adaptive Guarded Object Notation** - A schema-driven, token-efficient data interchange format for Large Language Models.

## Features

- **Token Efficiency**: Minimize tokens for LLM input/output using positional arrays and dictionary encoding
- **Adaptive Safety**: Never worse than raw JSON; automatic fallback when unsafe or inefficient
- **Schema Anchoring**: Cryptographic hash prevents decoding with wrong schema version
- **Drift Protection**: Detect unknown keys and malformed shapes at runtime
- **Type Safety**: Generate strict JSON Schema for constrained decoding (OpenAI, XGrammar)

## Installation

```bash
pip install agon-python
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add agon-python
```

## Quick Start

```python
from agon import AGON

# Sample data - list of objects with repeated structure
data = [
    {"id": 1, "name": "Alice", "role": "admin"},
    {"id": 2, "name": "Bob", "role": "user"},
    {"id": 3, "name": "Charlie", "role": "user"},
]

# Train a schema from sample data
config = AGON.train(data, context_id="users")

# Encode - automatically uses AGON if smaller, otherwise raw JSON
encoded = AGON.encode(data, config)
print(encoded)
# {"_f":"a","c":"users","v":"abc123...","d":[[1,"Alice",-1],[2,"Bob",-2],[3,"Charlie",-2]]}

# Decode back to original format
decoded = AGON.decode(encoded, config)
assert decoded == data
```

## How It Works

AGON encodes lists of JSON objects as **positional arrays**:

```json
// Original (67 tokens)
[
  {"id": 1, "name": "Alice", "role": "admin"},
  {"id": 2, "name": "Bob", "role": "user"}
]

// AGON encoded (23 tokens)
{"_f":"a","c":"users","v":"...","d":[[1,"Alice",-1],[2,"Bob",-2]]}
```

Key optimizations:
- **Positional encoding**: Keys are defined once in the schema, values are stored by position
- **Dictionary encoding**: Repeated strings like `"admin"`, `"user"` become negative integer pointers (`-1`, `-2`)
- **Trailing truncation**: Missing fields at the end of rows are omitted
- **Adaptive fallback**: Automatically falls back to raw JSON if AGON wouldn't save tokens

## API Reference

### Training

```python
config = AGON.train(
    data,                      # List of sample objects
    context_id="endpoint",     # Identifier for this schema
    min_gain=3.0,              # Minimum token savings required
    amortize=50,               # Expected uses to amortize prompt cost
    max_dict_per_field=100,    # Max dictionary entries per field
    enum_like_only=True,       # Only encode safe strings (no \n\r\t)
    max_enum_len=64,           # Max string length for dictionary
)
```

### Encoding

```python
# Adaptive encoding (recommended)
encoded = AGON.encode(data, config)

# Force AGON format even if larger
encoded = AGON.encode(data, config, force_agon=True)
```

### Decoding

```python
# Strict mode (raises errors on validation failures)
decoded = AGON.decode(payload, config, strict=True)

# Non-strict mode (returns empty list on failures)
decoded = AGON.decode(payload, config, strict=False)
```

### LLM Integration

```python
# Generate system prompt for LLM
prompt = AGON.system_prompt(config)

# Generate JSON Schema for constrained decoding
schema = AGON.get_json_schema(config)
```

### High-Level Client

```python
from agon import AgonClient

client = AgonClient()

# Register endpoints with sample data
client.register("users", sample_users)
client.register("products", sample_products)

# Encode/decode by endpoint
encoded = client.encode("users", data)
decoded = client.decode("users", payload)

# Get LLM integration helpers
prompt = client.get_prompt("users")
tool_schema = client.get_tool_schema("users")
```

## Development

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Clone the repository
git clone https://github.com/Verdenroz/agon.git
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

## License

MIT License - see [LICENSE](LICENSE) for details.
