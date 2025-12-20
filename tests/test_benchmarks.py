"""Benchmark tests for AGON with real-world complex JSON data.

Tests token efficiency, data integrity, and type safety with large datasets.
Results are printed to stdout - use `pytest -s` to see benchmark output.
"""

import json
from pathlib import Path
from typing import Any

import pytest
import tiktoken

from agon import AGON

# Path to test data
DATA_DIR = Path(__file__).parent / "data"

# Tiktoken encoder for token counting
ENCODER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a string using tiktoken."""
    return len(ENCODER.encode(text))


def load_json(filename: str) -> Any:
    """Load JSON file from test data directory."""
    with open(DATA_DIR / filename) as f:
        return json.load(f)


def normalize_floats(obj: Any, precision: int = 10) -> Any:
    """Normalize floats to avoid floating point comparison issues."""
    if isinstance(obj, float):
        return round(obj, precision)
    if isinstance(obj, dict):
        return {k: normalize_floats(v, precision) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_floats(item, precision) for item in obj]
    return obj


class TestChartBenchmark:
    """Benchmarks for chart.json - time series candlestick data."""

    @pytest.fixture
    def chart_data(self) -> dict[str, Any]:
        """Load chart data."""
        return load_json("chart.json")

    @pytest.fixture
    def candles(self, chart_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract candles array from chart data."""
        return chart_data["candles"]

    def test_token_efficiency(self, candles: list[dict[str, Any]]) -> None:
        """AGON should use fewer tokens than raw JSON for repetitive data."""
        # Encode
        raw_json = json.dumps(candles, separators=(",", ":"))
        agon_encoded = AGON.encode(candles, force=True)

        # Count tokens
        raw_tokens = count_tokens(raw_json)
        agon_tokens = count_tokens(agon_encoded)

        # Calculate savings
        savings_percent = (1 - agon_tokens / raw_tokens) * 100

        print(f"\n{'=' * 60}")
        print("CHART CANDLES BENCHMARK")
        print(f"{'=' * 60}")
        print(f"Records: {len(candles)}")
        print(f"Raw JSON tokens: {raw_tokens:,}")
        print(f"AGON tokens: {agon_tokens:,}")
        print(f"Token savings: {savings_percent:.1f}%")
        print(f"{'=' * 60}")

        # AGON should be more efficient for this repetitive data
        assert agon_tokens < raw_tokens, "AGON should use fewer tokens than raw JSON"

    def test_data_integrity(self, candles: list[dict[str, Any]]) -> None:
        """Roundtrip should preserve all data exactly."""
        encoded = AGON.encode(candles, force=True)
        decoded = AGON.decode(encoded)

        # Normalize floats for comparison
        original = normalize_floats(candles)
        result = normalize_floats(decoded)

        assert len(result) == len(original), "Record count mismatch"

        for i, (orig, dec) in enumerate(zip(original, result, strict=True)):
            assert orig == dec, f"Record {i} mismatch: {orig} != {dec}"

    def test_type_preservation(self, candles: list[dict[str, Any]]) -> None:
        """All field types should be preserved after roundtrip."""
        encoded = AGON.encode(candles, force=True)
        decoded = AGON.decode(encoded)

        for i, (orig, dec) in enumerate(zip(candles, decoded, strict=True)):
            for key in orig:
                assert key in dec, f"Missing key '{key}' in record {i}"
                orig_type = type(orig[key])
                dec_type = type(dec[key])
                # Allow int/float flexibility for JSON numbers
                if orig_type in (int, float) and dec_type in (int, float):
                    continue
                assert orig_type == dec_type, (
                    f"Type mismatch for '{key}' in record {i}: "
                    f"{orig_type.__name__} != {dec_type.__name__}"
                )


class TestQuoteBenchmark:
    """Benchmarks for quote.json - complex nested stock quote data."""

    @pytest.fixture
    def quote_data(self) -> dict[str, Any]:
        """Load quote data."""
        return load_json("quote.json")

    def test_single_object_handling(self, quote_data: dict[str, Any]) -> None:
        """AGON handles single complex objects wrapped in a list."""
        # Wrap single object in list for AGON
        data = [quote_data]

        raw_json = json.dumps(data, separators=(",", ":"))
        agon_encoded = AGON.encode(data, force=True)

        raw_tokens = count_tokens(raw_json)
        agon_tokens = count_tokens(agon_encoded)

        print(f"\n{'=' * 60}")
        print("QUOTE SINGLE OBJECT BENCHMARK")
        print(f"{'=' * 60}")
        print(f"Raw JSON tokens: {raw_tokens:,}")
        print(f"AGON tokens: {agon_tokens:,}")
        print(f"Difference: {agon_tokens - raw_tokens:+,} tokens")
        print(f"{'=' * 60}")

        # For single objects, AGON might not be smaller due to schema overhead
        # But it should still work correctly

    def test_nested_structure_integrity(self, quote_data: dict[str, Any]) -> None:
        """Nested objects with fmt/raw pairs should be preserved."""
        data = [quote_data]
        encoded = AGON.encode(data, force=True)
        decoded = AGON.decode(encoded)

        assert len(decoded) == 1
        result = decoded[0]

        # Check key nested fields are preserved
        if "regularMarketPrice" in quote_data:
            assert "regularMarketPrice" in result
            orig_price = quote_data["regularMarketPrice"]
            dec_price = result["regularMarketPrice"]
            if isinstance(orig_price, dict):
                assert isinstance(dec_price, dict)
                if "raw" in orig_price:
                    assert normalize_floats(orig_price["raw"]) == normalize_floats(dec_price["raw"])

    def test_null_handling(self, quote_data: dict[str, Any]) -> None:
        """Null values should be preserved correctly."""
        data = [quote_data]
        encoded = AGON.encode(data, force=True)
        decoded = AGON.decode(encoded)

        result = decoded[0]

        # Find and verify null values
        def find_nulls(obj: Any, path: str = "") -> list[str]:
            nulls = []
            if obj is None:
                nulls.append(path)
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    nulls.extend(find_nulls(v, f"{path}.{k}"))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    nulls.extend(find_nulls(v, f"{path}[{i}]"))
            return nulls

        orig_nulls = set(find_nulls(quote_data))
        result_nulls = set(find_nulls(result))

        # All original nulls should be in result
        # (result might have more due to missing->null conversion)
        assert orig_nulls <= result_nulls, f"Missing nulls: {orig_nulls - result_nulls}"


class TestGainersBenchmark:
    """Benchmarks for gainers.json - array of stock quotes."""

    @pytest.fixture
    def gainers_data(self) -> dict[str, Any]:
        """Load gainers data."""
        return load_json("gainers.json")

    @pytest.fixture
    def quotes(self, gainers_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract quotes array from gainers data."""
        return gainers_data["quotes"]

    def test_token_efficiency(self, quotes: list[dict[str, Any]]) -> None:
        """AGON should use fewer tokens for array of similar objects."""
        raw_json = json.dumps(quotes, separators=(",", ":"))
        agon_encoded = AGON.encode(quotes, force=True)

        raw_tokens = count_tokens(raw_json)
        agon_tokens = count_tokens(agon_encoded)
        savings_percent = (1 - agon_tokens / raw_tokens) * 100

        print(f"\n{'=' * 60}")
        print("GAINERS QUOTES BENCHMARK")
        print(f"{'=' * 60}")
        print(f"Records: {len(quotes)}")
        print(f"Raw JSON tokens: {raw_tokens:,}")
        print(f"AGON tokens: {agon_tokens:,}")
        print(f"Token savings: {savings_percent:.1f}%")
        print(f"{'=' * 60}")

        # Should have savings for multiple similar records
        assert agon_tokens < raw_tokens, "AGON should use fewer tokens"

    def test_data_integrity(self, quotes: list[dict[str, Any]]) -> None:
        """All quote records should roundtrip correctly."""
        encoded = AGON.encode(quotes, force=True)
        decoded = AGON.decode(encoded)

        assert len(decoded) == len(quotes), "Record count mismatch"

        original = normalize_floats(quotes)
        result = normalize_floats(decoded)

        for i, (orig, dec) in enumerate(zip(original, result, strict=True)):
            # Check all original keys are present
            for key in orig:
                assert key in dec, f"Missing key '{key}' in record {i}"

            # Compare values
            assert orig == dec, f"Record {i} mismatch"

    def test_schema_coverage(self, quotes: list[dict[str, Any]]) -> None:
        """All keys should be preserved in roundtrip."""
        encoded = AGON.encode(quotes, force=True)
        decoded = AGON.decode(encoded)

        # Collect all unique keys from original data
        all_keys: set[str] = set()
        for quote in quotes:
            all_keys.update(quote.keys())

        # Collect all keys from decoded data
        decoded_keys: set[str] = set()
        for quote in decoded:
            decoded_keys.update(quote.keys())

        # All original keys should be in decoded
        missing = all_keys - decoded_keys
        assert not missing, f"Missing keys in decoded: {missing}"


class TestCombinedBenchmarks:
    """Combined benchmarks across all test data."""

    def test_summary_report(self) -> None:
        """Generate a summary report of token savings across all datasets."""
        results = []

        # Chart candles
        chart = load_json("chart.json")
        candles = chart["candles"]
        raw = json.dumps(candles, separators=(",", ":"))
        agon = AGON.encode(candles, force=True)
        results.append(
            {
                "dataset": "chart (candles)",
                "records": len(candles),
                "raw_tokens": count_tokens(raw),
                "agon_tokens": count_tokens(agon),
            }
        )

        # Gainers quotes
        gainers = load_json("gainers.json")
        quotes = gainers["quotes"]
        raw = json.dumps(quotes, separators=(",", ":"))
        agon = AGON.encode(quotes, force=True)
        results.append(
            {
                "dataset": "gainers (quotes)",
                "records": len(quotes),
                "raw_tokens": count_tokens(raw),
                "agon_tokens": count_tokens(agon),
            }
        )

        # Quote (single object)
        quote = load_json("quote.json")
        data = [quote]
        raw = json.dumps(data, separators=(",", ":"))
        agon = AGON.encode(data, force=True)
        results.append(
            {
                "dataset": "quote (single)",
                "records": 1,
                "raw_tokens": count_tokens(raw),
                "agon_tokens": count_tokens(agon),
            }
        )

        # Print summary
        print(f"\n{'=' * 80}")
        print(f"{'AGON TOKEN EFFICIENCY SUMMARY':^80}")
        print(f"{'=' * 80}")
        print(f"{'Dataset':<25} {'Records':>10} {'Raw':>12} {'AGON':>12} {'Savings':>12}")
        print(f"{'-' * 80}")

        total_raw = 0
        total_agon = 0

        for r in results:
            savings = (1 - r["agon_tokens"] / r["raw_tokens"]) * 100
            print(
                f"{r['dataset']:<25} {r['records']:>10,} {r['raw_tokens']:>12,} "
                f"{r['agon_tokens']:>12,} {savings:>11.1f}%"
            )
            total_raw += r["raw_tokens"]
            total_agon += r["agon_tokens"]

        print(f"{'-' * 80}")
        total_savings = (1 - total_agon / total_raw) * 100
        print(f"{'TOTAL':<25} {'':<10} {total_raw:>12,} {total_agon:>12,} {total_savings:>11.1f}%")
        print(f"{'=' * 80}")

    def test_all_roundtrips_pass(self) -> None:
        """Verify all datasets roundtrip without data loss."""
        datasets = [
            ("chart.json", "candles"),
            ("gainers.json", "quotes"),
        ]

        for filename, key in datasets:
            data = load_json(filename)
            records = data[key]

            encoded = AGON.encode(records, force=True)
            decoded = AGON.decode(encoded)

            original = normalize_floats(records)
            result = normalize_floats(decoded)

            assert original == result, f"Roundtrip failed for {filename}"

        # Single object dataset
        quote = load_json("quote.json")
        data = [quote]
        encoded = AGON.encode(data, force=True)
        decoded = AGON.decode(encoded)

        assert normalize_floats(data) == normalize_floats(decoded), "Roundtrip failed for quote"
