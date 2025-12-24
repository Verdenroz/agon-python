"""Benchmark tests for AGON with real-world complex JSON data.

Tests token efficiency, data integrity, and type safety with large datasets.
Results are printed to stdout
"""

from pathlib import Path
import time
from typing import Any

import orjson
import pytest
import tiktoken

from agon import AGON

# Path to test data
DATA_DIR = Path(__file__).parent / "data"

# Tiktoken encoder for token counting
ENCODER = tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a string using tiktoken."""
    return len(ENCODER.encode(text))


def load_json(filename: str) -> Any:
    """Load JSON file from test data directory."""
    with open(DATA_DIR / filename, "rb") as f:
        return orjson.loads(f.read())


def iter_json_fixtures() -> list[Path]:
    """Return all JSON fixtures under tests/data, sorted for stable output."""
    return sorted(DATA_DIR.glob("*.json"), key=lambda p: p.name)


def coerce_records(obj: Any, *, filename: str) -> tuple[Any, str]:
    """Coerce an arbitrary JSON fixture into encodable format for AGON.

    - If fixture is already list[dict], use it.
    - If fixture is a dict and contains a known record-list key (candles/quotes), use that.
    - If fixture is a dict with nested arrays/objects, encode it directly (don't wrap).
    - Otherwise, wrap the dict as a single record.
    """
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
        return obj, f"{filename}"

    if isinstance(obj, dict):
        # Check for known record-list keys
        for key in ("candles", "quotes", "records", "items", "data"):
            val = obj.get(key)
            if isinstance(val, list) and (not val or all(isinstance(x, dict) for x in val)):
                return val, f"{filename}:{key}"

        # If dict contains nested structures (arrays/objects), encode it directly
        # This avoids wrapping well-structured objects like toon.json in a list
        has_nested = any(isinstance(v, dict | list) for v in obj.values())
        if has_nested:
            return obj, f"{filename}"

        # Simple flat dict - wrap as single record
        return [obj], f"{filename}"

    raise TypeError(f"Unsupported fixture shape for {filename}: {type(obj).__name__}")


def time_once_seconds(fn: Any) -> float:
    """Return runtime in seconds for a single call."""
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def normalize_floats(obj: Any, precision: int = 10) -> Any:
    """Normalize floats to avoid floating point comparison issues."""
    if isinstance(obj, float):
        return round(obj, precision)
    if isinstance(obj, dict):
        return {k: normalize_floats(v, precision) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_floats(item, precision) for item in obj]
    return obj


@pytest.mark.parametrize(
    "fixture_path",
    iter_json_fixtures(),
    ids=lambda p: p.name,
)
def test_fixture_benchmark(fixture_path: Path) -> None:
    """One benchmark per JSON fixture."""
    obj = load_json(fixture_path.name)
    records, label = coerce_records(obj, filename=fixture_path.name)

    # Use pretty JSON as baseline (more realistic comparison)
    raw_json = orjson.dumps(records, option=orjson.OPT_INDENT_2).decode()
    raw_tokens = count_tokens(raw_json)

    # Test each format individually
    format_results: dict[
        str, tuple[int, float, float, float]
    ] = {}  # tokens, savings, encode_ms, decode_ms

    for fmt, encoder, decoder in [
        ("text", lambda data: AGON.encode(data, format="text"), AGON.decode),  # type: ignore[misc]
        ("columns", lambda data: AGON.encode(data, format="columns"), AGON.decode),  # type: ignore[misc]
        ("struct", lambda data: AGON.encode(data, format="struct"), AGON.decode),  # type: ignore[misc]
    ]:
        encoded = encoder(records)
        tokens = count_tokens(encoded.text)
        savings = (1 - tokens / max(1, raw_tokens)) * 100

        t0 = time.perf_counter()
        encoder(records)
        encode_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        decoded = decoder(encoded.with_header())
        decode_ms = (time.perf_counter() - t0) * 1000

        # Verify roundtrip
        assert normalize_floats(decoded) == normalize_floats(records), f"{fmt} roundtrip failed"

        format_results[fmt] = (tokens, savings, encode_ms, decode_ms)

    # Test auto selection
    result = AGON.encode(records, format="auto")
    auto_tokens = count_tokens(result.text)
    auto_savings = (1 - auto_tokens / max(1, raw_tokens)) * 100

    # Verify auto decode (decode AGONEncoding directly)
    decoded = AGON.decode(result)
    assert normalize_floats(decoded) == normalize_floats(records), "auto roundtrip failed"

    # Print results
    record_count = len(records) if isinstance(records, list) else 1
    print(f"\n{'=' * 60}")
    print(f"FIXTURE: {label}")
    print(f"Bytes: {fixture_path.stat().st_size:,}  Records: {record_count:,}")
    print(f"JSON baseline (pretty): {raw_tokens:,} tokens")
    print(f"{'-' * 60}")
    print(f"{'Format':<10} {'Tokens':>8} {'Savings':>10} {'Encode':>10} {'Decode':>10}")
    print(f"{'-' * 60}")
    for fmt, (tokens, savings, enc_ms, dec_ms) in format_results.items():
        print(f"{fmt:<10} {tokens:>8,} {savings:>+9.1f}% {enc_ms:>9.2f}ms {dec_ms:>9.2f}ms")
    print(f"{'-' * 60}")
    print(f"{'auto':<10} {auto_tokens:>8,} {auto_savings:>+9.1f}% (selected: {result.format})")
    print(f"{'=' * 60}")
