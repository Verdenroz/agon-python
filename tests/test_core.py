"""Tests for the AGON core API.

These tests target `agon.core` behavior (format selection, dispatch, and helpers).
Format-specific behavior lives in `tests/test_rows.py`.
"""

from __future__ import annotations

from typing import Any

import orjson
import pytest

from agon import AGON, AGONError, AGONRows


def test_encode_json_format_returns_json() -> None:
    data: dict[str, Any] = {"a": 1, "b": [1, 2, 3]}
    result = AGON.encode(data, format="json")
    assert orjson.loads(result.text) == data


def test_encode_rows_format_uses_header() -> None:
    data: dict[str, Any] = {"a": 1, "b": "x"}
    result = AGON.encode(data, format="rows")
    assert result.format == "rows"
    assert result.header == "@AGON rows"


def test_encode_routes_to_specific_formats(simple_data: list[dict[str, Any]]) -> None:
    res_json = AGON.encode(simple_data, format="json")
    assert res_json.format == "json"
    assert isinstance(orjson.loads(res_json.text), list)

    res_rows = AGON.encode(simple_data, format="rows")
    assert res_rows.format == "rows"
    assert res_rows.header == "@AGON rows"


def test_encode_struct_includes_definitions_without_header() -> None:
    data = {
        "price": {"fmt": "100.00", "raw": 100.0},
        "change": {"fmt": "+5.00", "raw": 5.0},
        "volume": {"fmt": "1M", "raw": 1000000},
    }
    result = AGON.encode(data, format="struct")
    assert result.format == "struct"
    assert result.header == "@AGON struct"
    assert "@AGON struct" not in result.text
    assert "@FR: fmt, raw" in result.text


def test_decode_detects_rows_payload() -> None:
    payload = AGONRows.encode({"x": 1}, include_header=True)
    assert AGON.decode(payload) == {"x": 1}


def test_decode_raw_json_list_roundtrip() -> None:
    raw = '[{"id": 1, "name": "Test"}]'
    assert AGON.decode(raw) == [{"id": 1, "name": "Test"}]


def test_decode_invalid_json_raises() -> None:
    with pytest.raises(AGONError, match="Invalid JSON"):
        AGON.decode("{invalid json")


def test_decode_invalid_non_json_string_raises() -> None:
    with pytest.raises(AGONError, match="Invalid JSON"):
        AGON.decode("this is not json and not AGON")


def test_decode_agon_encoding_directly() -> None:
    """Test decoding AGONEncoding directly."""
    data = [{"id": 1, "name": "Alice"}]
    result = AGON.encode(data, format="rows")
    # Decode AGONEncoding directly
    decoded = AGON.decode(result)
    assert decoded == data


def test_decode_with_format_parameter() -> None:
    """Test decoding with explicit format (no header needed)."""
    data = [{"id": 1, "name": "Alice"}]
    result = AGON.encode(data, format="rows")
    # Decode using format parameter
    decoded = AGON.decode(result.text, format=result.format)
    assert decoded == data


def test_project_data_delegates() -> None:
    data: list[dict[str, Any]] = [{"id": 1, "name": "Ada", "extra": "x"}]
    assert AGON.project_data(data, ["id"]) == [{"id": 1}]


def test_hint_with_agon_encoding_result() -> None:
    """AGONEncoding.hint() should return prescriptive generation instructions."""
    data = [{"id": 1, "name": "Alice"}]
    result = AGON.encode(data, format="rows")
    hint = result.hint()
    assert isinstance(hint, str)
    assert "Return in AGON rows format" in hint
    assert "@AGON rows header" in hint


def test_hint_rows_format() -> None:
    """hint() should return rows format instructions."""
    result = AGON.encode({"a": 1}, format="rows")
    hint = result.hint()
    assert isinstance(hint, str)
    assert "Return in AGON rows format" in hint
    assert "@AGON rows header" in hint
    assert "name[N]{fields}" in hint


def test_hint_columns_format() -> None:
    """hint() should return columns format instructions."""
    result = AGON.encode([{"id": 1}], format="columns")
    hint = result.hint()
    assert isinstance(hint, str)
    assert "Return in AGON columns format" in hint
    assert "@AGON columns header" in hint
    assert "├/└" in hint


def test_hint_struct_format() -> None:
    """hint() should return struct format instructions."""
    result = AGON.encode({"a": {"fmt": "1", "raw": 1}}, format="struct")
    hint = result.hint()
    assert isinstance(hint, str)
    assert "Return in AGON struct format" in hint
    assert "@AGON struct header" in hint
    assert "@Struct" in hint or "Struct(" in hint


def test_hint_json_format() -> None:
    """hint() should return JSON format hint."""
    result = AGON.encode({"a": 1}, format="json")
    hint = result.hint()
    assert isinstance(hint, str)
    assert "JSON" in hint


def test_hint_matches_across_formats() -> None:
    """hint() should return consistent hints for each format."""
    data = [{"id": 1, "name": "Alice"}]

    for fmt in ["rows", "columns", "struct", "json"]:
        result = AGON.encode(data, format=fmt)  # type: ignore[arg-type]
        hint = result.hint()
        assert isinstance(hint, str)
        assert len(hint) > 0


def test_count_tokens_positive() -> None:
    assert AGON.count_tokens("hello world") > 0


def test_project_top_level_key() -> None:
    data: list[dict[str, Any]] = [{"type": "DAY_GAINERS", "description": "x", "value": 100}]
    assert AGON.project_data(data, ["type"]) == [{"type": "DAY_GAINERS"}]


def test_project_multiple_keys() -> None:
    data: list[dict[str, Any]] = [{"id": 1, "name": "Alice", "role": "admin", "extra": "ignored"}]
    assert AGON.project_data(data, ["id", "name"]) == [{"id": 1, "name": "Alice"}]


def test_project_nested_path() -> None:
    data: list[dict[str, Any]] = [
        {"user": {"profile": {"name": "Ada", "age": 37}, "id": 123}, "type": "x"}
    ]
    assert AGON.project_data(data, ["user.profile.name"]) == [
        {"user": {"profile": {"name": "Ada"}}}
    ]


def test_project_nested_list_key() -> None:
    data: list[dict[str, Any]] = [
        {
            "type": "DAY_GAINERS",
            "quotes": [
                {"symbol": "DJTWW", "exchange": "NYQ", "price": 10.37},
                {"symbol": "AAPL", "exchange": "NMS", "price": 199.0},
            ],
        }
    ]
    assert AGON.project_data(data, ["quotes.symbol"]) == [
        {"quotes": [{"symbol": "DJTWW"}, {"symbol": "AAPL"}]}
    ]


def test_project_preserves_null() -> None:
    data: list[dict[str, Any]] = [{"id": 1, "name": None}]
    assert AGON.project_data(data, ["id", "name"]) == [{"id": 1, "name": None}]


def test_project_missing_key_ignored() -> None:
    data: list[dict[str, Any]] = [{"id": 1}]
    assert AGON.project_data(data, ["id", "nonexistent"]) == [{"id": 1}]


def test_auto_format_selects_best() -> None:
    """Auto format should choose most token-efficient option."""
    data: list[dict[str, Any]] = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    result = AGON.encode(data, format="auto")
    assert result.format in ("json", "rows", "columns", "struct")


def test_force_skips_json() -> None:
    """With force=True, auto should not select JSON."""
    data: dict[str, Any] = {"a": 1}
    result = AGON.encode(data, format="auto", force=True)
    assert result.format == "rows"


def test_auto_min_savings_can_fall_back_to_json() -> None:
    # Make it very likely that a non-JSON format wins token-counting,
    # then force an impossible savings threshold so it must fall back.
    records = [{"id": i, "name": "Alice"} for i in range(60)]

    result = AGON.encode(records, format="auto", min_savings=1.0)
    assert result.format == "json"
    assert result.text.startswith("[")


def test_auto_min_savings_allows_best_format_when_threshold_met() -> None:
    # Ensure we cover the non-fallback path of min_savings logic.
    records = [{"id": i, "name": "Alice"} for i in range(60)]

    result = AGON.encode(records, format="auto", min_savings=0.0)
    assert result.format != "json"


def test_auto_force_excludes_json_candidate() -> None:
    records = [{"id": i, "name": "Alice"} for i in range(5)]

    result = AGON.encode(records, format="auto", force=True)
    assert result.format != "json"


def test_encode_reports_json_fallback() -> None:
    records = [{"id": i, "name": "Alice"} for i in range(60)]

    res = AGON.encode(records, format="auto", min_savings=1.0)
    assert res.format == "json"
    assert res.text.startswith("[")


def test_encode_with_encoding_none_uses_fast_estimate() -> None:
    """encoding=None (default) uses fast byte-length estimate."""
    data = [{"id": i, "name": f"User{i}"} for i in range(10)]
    result = AGON.encode(data, format="auto", encoding=None)
    assert result.format in ("json", "rows", "columns", "struct")
    assert len(result.text) > 0


def test_encode_with_encoding_specified_uses_tiktoken() -> None:
    """encoding='o200k_base' uses tiktoken for accurate token counting."""
    data = [{"id": i, "name": f"User{i}"} for i in range(10)]
    result = AGON.encode(data, format="auto", encoding="o200k_base")
    assert result.format in ("json", "rows", "columns", "struct")
    assert len(result.text) > 0


def test_encode_both_encoding_modes_produce_valid_results() -> None:
    """Both encoding modes should produce decodable results."""
    data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    # Fast estimate (default)
    result_fast = AGON.encode(data, format="auto", encoding=None)
    decoded_fast = AGON.decode(result_fast)
    assert decoded_fast == data

    # Tiktoken
    result_tiktoken = AGON.encode(data, format="auto", encoding="o200k_base")
    decoded_tiktoken = AGON.decode(result_tiktoken)
    assert decoded_tiktoken == data


def test_count_tokens_with_default_encoding() -> None:
    """count_tokens uses o200k_base by default."""
    tokens = AGON.count_tokens("hello world")
    assert tokens > 0
    assert isinstance(tokens, int)


def test_count_tokens_with_different_encodings() -> None:
    """count_tokens supports multiple tiktoken encodings."""
    text = "The quick brown fox jumps over the lazy dog."

    # Different encodings may produce different token counts
    o200k = AGON.count_tokens(text, encoding="o200k_base")
    cl100k = AGON.count_tokens(text, encoding="cl100k_base")

    assert o200k > 0
    assert cl100k > 0
    # Token counts may differ between encodings
    assert isinstance(o200k, int)
    assert isinstance(cl100k, int)


def test_agon_encoding_str_returns_text() -> None:
    """AGONEncoding str() returns the encoded text."""
    data = [{"id": 1}]
    result = AGON.encode(data, format="json")
    assert str(result) == result.text


def test_agon_encoding_len_returns_text_length() -> None:
    """AGONEncoding len() returns character count."""
    data = [{"id": 1}]
    result = AGON.encode(data, format="json")
    assert len(result) == len(result.text)


def test_agon_encoding_repr() -> None:
    """AGONEncoding has useful repr."""
    data = [{"id": 1}]
    result = AGON.encode(data, format="json")
    r = repr(result)
    assert "AGONEncoding" in r
    assert "json" in r


def test_agon_encoding_with_header() -> None:
    """with_header() prepends header for auto-detect decoding."""
    data = [{"id": 1, "name": "Alice"}]
    result = AGON.encode(data, format="rows")
    with_header = result.with_header()
    assert with_header.startswith("@AGON rows")
    # Can decode with auto-detect
    assert AGON.decode(with_header) == data


def test_project_data_handles_nested_paths_and_ignores_empty() -> None:
    data = [
        {
            "id": 1,
            "user": {"name": "Alice", "age": 30},
            "users": [{"name": "Bob", "age": 20}],
            "extra": "x",
        }
    ]

    projected = AGON.project_data(
        data,
        keep_paths=[
            "",  # ignored
            ".",  # ignored
            "user.name",
            "users.name",
            "user..age",  # exercises empty segment filtering
        ],
    )

    assert projected == [{"user": {"name": "Alice", "age": 30}, "users": [{"name": "Bob"}]}]


def test_project_data_path_collision_prefers_deeper_tree() -> None:
    # Exercises keep-tree path collision where a prefix path is later treated as an object.
    data: list[dict[str, Any]] = [{"a": {"b": 1, "c": 2}, "x": 9}]
    assert AGON.project_data(data, ["a", "a.b"]) == [{"a": {"b": 1}}]


def test_project_data_handles_empty_and_mixed_lists() -> None:
    data = [
        {
            "users": [],
            "mixed": [{"name": "Alice"}, "oops"],
            "user": "not-an-object",
        }
    ]

    projected = AGON.project_data(data, ["users.name", "mixed.name", "user.name"])
    assert projected == [
        {"users": [], "mixed": [{"name": "Alice"}, "oops"], "user": "not-an-object"}
    ]
