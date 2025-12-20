"""Tests for AGON core functionality."""

import json
from typing import Any

import pytest

from agon import AGON, AgonClient, AGONError


class TestTraining:
    """Tests for schema training."""

    def test_train_empty_data(self) -> None:
        """Training with empty data returns empty schema."""
        config = AGON.train([], "empty")
        assert config["cid"] == "empty"
        assert config["schema"]["k"] == []

    def test_train_simple_data(self, simple_data: list[dict[str, Any]]) -> None:
        """Training extracts keys and types correctly."""
        config = AGON.train(simple_data, "simple")
        assert config["cid"] == "simple"
        assert "v" in config  # Version hash
        assert len(config["v"]) == 16
        assert set(config["schema"]["k"]) == {"id", "name", "role"}

    def test_train_dense_first_ordering(self) -> None:
        """Keys are sorted by density (most present first)."""
        data = [
            {"a": 1, "b": 2, "c": 3},
            {"a": 1, "b": 2},  # c is less dense
            {"a": 1},  # b is less dense than a
        ]
        config = AGON.train(data, "dense")
        keys = config["schema"]["k"]
        # 'a' appears in all 3, 'b' in 2, 'c' in 1
        assert keys[0] == "a"
        assert keys[1] == "b"
        assert keys[2] == "c"

    def test_train_dictionary_encoding(self) -> None:
        """Repeated strings get dictionary encoding."""
        data: list[dict[str, Any]] = [{"role": "admin"} for _ in range(10)]
        data.extend([{"role": "user"} for _ in range(10)])
        config = AGON.train(data, "dict_test")
        assert config["schema"]["t"]["role"] == "dict"
        assert "admin" in config["schema"]["d"]["role"]
        assert "user" in config["schema"]["d"]["role"]

    def test_train_nested_objects(self, nested_data: list[dict[str, Any]]) -> None:
        """Nested objects get subschemas."""
        config = AGON.train(nested_data, "nested")
        assert config["schema"]["t"]["user"] == "obj"
        assert "user" in config["schema"]["s"]
        sub = config["schema"]["s"]["user"]
        assert set(sub["k"]) == {"name", "email"}

    def test_train_nested_lists(self, list_data: list[dict[str, Any]]) -> None:
        """Nested lists of objects get subschemas."""
        config = AGON.train(list_data, "list")
        assert config["schema"]["t"]["tags"] == "list"
        assert "tags" in config["schema"]["s"]

    def test_train_mixed_types_become_scalar(self) -> None:
        """Mixed types in a field result in scalar type."""
        data: list[dict[str, Any]] = [
            {"value": "string"},
            {"value": 123},
            {"value": True},
        ]
        config = AGON.train(data, "mixed")
        assert config["schema"]["t"]["value"] == "scalar"

    def test_train_empty_lists_neutral(self) -> None:
        """Empty lists don't affect type inference."""
        data: list[dict[str, Any]] = [
            {"items": []},
            {"items": [{"id": 1}]},
        ]
        config = AGON.train(data, "empty_list")
        assert config["schema"]["t"]["items"] == "list"

    def test_train_non_dict_rows_returns_empty(self) -> None:
        """Non-dict rows return empty schema."""
        # This tests the edge case in _build_node with empty list
        result = AGON._build_node(
            [], {"min_gain": 3.0, "amortize": 50, "max_dict": 100, "enum_only": True, "max_len": 64}
        )
        assert result == {"k": [], "t": {}, "d": {}, "s": {}}

    def test_train_string_not_dict_encoded_without_repetition(self) -> None:
        """Strings without repetition stay as str type."""
        data: list[dict[str, Any]] = [
            {"name": "Alice"},
            {"name": "Bob"},
            {"name": "Charlie"},
        ]
        config = AGON.train(data, "unique_strings")
        # Not enough repetition for dictionary encoding
        assert config["schema"]["t"]["name"] == "str"

    def test_train_unsafe_strings_not_dict_encoded(self) -> None:
        """Strings with newlines/tabs not dictionary encoded."""
        data: list[dict[str, Any]] = [{"text": "line1\nline2"} for _ in range(20)]
        config = AGON.train(data, "unsafe")
        # Should stay as str due to newline
        assert config["schema"]["t"]["text"] == "str"

    def test_train_long_strings_not_dict_encoded(self) -> None:
        """Strings longer than max_enum_len not dictionary encoded."""
        long_string = "x" * 100
        data: list[dict[str, Any]] = [{"text": long_string} for _ in range(20)]
        config = AGON.train(data, "long", max_enum_len=64)
        assert config["schema"]["t"]["text"] == "str"

    def test_train_with_custom_params(self) -> None:
        """Training with custom parameters works."""
        data: list[dict[str, Any]] = [{"role": "admin"} for _ in range(100)]
        config = AGON.train(
            data,
            "custom",
            min_gain=0.1,
            amortize=10,
            max_dict_per_field=5,
            enum_like_only=False,
            max_enum_len=128,
        )
        assert config["cid"] == "custom"


class TestEncoding:
    """Tests for AGON encoding."""

    def test_encode_simple(
        self, simple_data: list[dict[str, Any]], simple_config: dict[str, Any]
    ) -> None:
        """Simple data encodes to AGON format when forced."""
        # Use force_agon=True since small data may fall back to raw JSON
        encoded = AGON.encode(simple_data, simple_config, force_agon=True)
        parsed = json.loads(encoded)
        assert parsed.get("_f") == "a"
        assert parsed["c"] == "test"
        assert parsed["v"] == simple_config["v"]

    def test_encode_force_agon(
        self, simple_data: list[dict[str, Any]], simple_config: dict[str, Any]
    ) -> None:
        """force_agon=True always uses AGON format."""
        encoded = AGON.encode(simple_data, simple_config, force_agon=True)
        parsed = json.loads(encoded)
        assert parsed["_f"] == "a"

    def test_encode_schema_drift_fallback(self, simple_config: dict[str, Any]) -> None:
        """Unknown keys trigger fallback to raw JSON."""
        drifted = [{"id": 1, "name": "Alice", "unknown_field": "oops"}]
        encoded = AGON.encode(drifted, simple_config)
        parsed = json.loads(encoded)
        # Should be raw JSON list, not AGON packet
        assert isinstance(parsed, list)
        assert parsed[0]["unknown_field"] == "oops"

    def test_encode_preserves_trailing_nulls(
        self, data_with_nulls: list[dict[str, Any]], nulls_config: dict[str, Any]
    ) -> None:
        """Explicit trailing nulls are preserved, missing fields truncated."""
        encoded = AGON.encode(data_with_nulls, nulls_config, force_agon=True)
        parsed = json.loads(encoded)
        rows = parsed["d"]
        # First row: explicit null at end - should preserve
        # Second row: missing role - should truncate
        # Third row: missing name and role - should truncate
        assert len(rows[0]) > len(rows[2])

    def test_encode_dictionary_pointers(self) -> None:
        """Dictionary values encode as negative integers."""
        # Need enough repetition for dictionary encoding to be worthwhile
        data: list[dict[str, Any]] = [{"role": "admin"} for _ in range(10)]
        data.extend([{"role": "user"} for _ in range(10)])
        config = AGON.train(data, "ptr_test")
        # Verify dictionary encoding was applied
        assert config["schema"]["t"]["role"] == "dict"
        encoded = AGON.encode(data, config, force_agon=True)
        parsed = json.loads(encoded)
        # Check that rows contain negative pointers
        for row in parsed["d"]:
            assert isinstance(row[0], int)
            assert row[0] < 0

    def test_encode_adaptive_chooses_smaller(self) -> None:
        """Adaptive encoding chooses smaller format."""
        # Small data - JSON might be smaller
        data: list[dict[str, Any]] = [{"id": 1}]
        config = AGON.train(data, "small")
        encoded = AGON.encode(data, config)
        # Should be raw JSON for small data
        parsed = json.loads(encoded)
        assert isinstance(parsed, list)

    def test_encode_nested_obj_drift(self) -> None:
        """Nested object with schema drift falls back to JSON."""
        data = [{"user": {"name": "Alice"}}]
        config = AGON.train(data, "nested")
        # Add unknown field in nested object
        drifted = [{"user": {"name": "Alice", "unknown": "field"}}]
        encoded = AGON.encode(drifted, config)
        # Should fall back to JSON
        parsed = json.loads(encoded)
        assert isinstance(parsed, list)

    def test_encode_list_drift(self) -> None:
        """Nested list with schema drift falls back to JSON."""
        data = [{"items": [{"id": 1}]}]
        config = AGON.train(data, "list")
        # Add unknown field in nested list item
        drifted = [{"items": [{"id": 1, "unknown": "field"}]}]
        encoded = AGON.encode(drifted, config)
        # Should fall back to JSON
        parsed = json.loads(encoded)
        assert isinstance(parsed, list)

    def test_encode_non_dict_in_obj_field(self) -> None:
        """Non-dict value in obj field is passed through."""
        data = [{"user": {"name": "Alice"}}]
        config = AGON.train(data, "obj")
        # Replace dict with non-dict
        weird_data: list[dict[str, Any]] = [{"user": "not a dict"}]
        encoded = AGON.encode(weird_data, config, force_agon=True)
        decoded = AGON.decode(encoded, config)
        assert decoded[0]["user"] == "not a dict"

    def test_encode_non_list_in_list_field(self) -> None:
        """Non-list value in list field is passed through."""
        data = [{"items": [{"id": 1}]}]
        config = AGON.train(data, "list")
        weird_data: list[dict[str, Any]] = [{"items": "not a list"}]
        encoded = AGON.encode(weird_data, config, force_agon=True)
        decoded = AGON.decode(encoded, config)
        assert decoded[0]["items"] == "not a list"


class TestDecoding:
    """Tests for AGON decoding."""

    def test_decode_roundtrip(
        self, simple_data: list[dict[str, Any]], simple_config: dict[str, Any]
    ) -> None:
        """Encode then decode returns original data."""
        encoded = AGON.encode(simple_data, simple_config, force_agon=True)
        decoded = AGON.decode(encoded, simple_config)
        assert decoded == simple_data

    def test_decode_raw_json(self, simple_config: dict[str, Any]) -> None:
        """Decoding raw JSON list returns it unchanged."""
        raw = '[{"id": 1, "name": "Test"}]'
        decoded = AGON.decode(raw, simple_config)
        assert decoded == [{"id": 1, "name": "Test"}]

    def test_decode_cid_mismatch_strict(self, simple_config: dict[str, Any]) -> None:
        """CID mismatch raises error in strict mode."""
        packet = json.dumps({"_f": "a", "c": "wrong", "v": simple_config["v"], "d": []})
        with pytest.raises(AGONError, match="CID Mismatch"):
            AGON.decode(packet, simple_config, strict=True)

    def test_decode_version_mismatch_strict(self, simple_config: dict[str, Any]) -> None:
        """Version mismatch raises error in strict mode."""
        packet = json.dumps({"_f": "a", "c": simple_config["cid"], "v": "wrongversion00", "d": []})
        with pytest.raises(AGONError, match="Version Mismatch"):
            AGON.decode(packet, simple_config, strict=True)

    def test_decode_invalid_json_strict(self, simple_config: dict[str, Any]) -> None:
        """Invalid JSON raises error in strict mode."""
        with pytest.raises(AGONError, match="Invalid JSON"):
            AGON.decode("{invalid json", simple_config, strict=True)

    def test_decode_invalid_json_nonstrict(self, simple_config: dict[str, Any]) -> None:
        """Invalid JSON returns empty list in non-strict mode."""
        result = AGON.decode("{invalid json", simple_config, strict=False)
        assert result == []

    def test_decode_nested_roundtrip(
        self, nested_data: list[dict[str, Any]], nested_config: dict[str, Any]
    ) -> None:
        """Nested objects roundtrip correctly."""
        encoded = AGON.encode(nested_data, nested_config, force_agon=True)
        decoded = AGON.decode(encoded, nested_config)
        assert decoded == nested_data

    def test_decode_list_roundtrip(
        self, list_data: list[dict[str, Any]], list_config: dict[str, Any]
    ) -> None:
        """Nested lists roundtrip correctly."""
        encoded = AGON.encode(list_data, list_config, force_agon=True)
        decoded = AGON.decode(encoded, list_config)
        assert decoded == list_data

    def test_decode_unknown_format_strict(self, simple_config: dict[str, Any]) -> None:
        """Unknown format raises error in strict mode."""
        packet = json.dumps({"unknown": "format"})
        with pytest.raises(AGONError, match="Unknown format"):
            AGON.decode(packet, simple_config, strict=True)

    def test_decode_unknown_format_nonstrict(self, simple_config: dict[str, Any]) -> None:
        """Unknown format returns empty list in non-strict mode."""
        packet = json.dumps({"unknown": "format"})
        result = AGON.decode(packet, simple_config, strict=False)
        assert result == []

    def test_decode_invalid_d_field_strict(self, simple_config: dict[str, Any]) -> None:
        """Invalid 'd' field raises error in strict mode."""
        packet = json.dumps(
            {"_f": "a", "c": simple_config["cid"], "v": simple_config["v"], "d": "not a list"}
        )
        with pytest.raises(AGONError, match="'d' must be a list"):
            AGON.decode(packet, simple_config, strict=True)

    def test_decode_invalid_d_field_nonstrict(self, simple_config: dict[str, Any]) -> None:
        """Invalid 'd' field returns empty list in non-strict mode."""
        packet = json.dumps(
            {"_f": "a", "c": simple_config["cid"], "v": simple_config["v"], "d": "not a list"}
        )
        result = AGON.decode(packet, simple_config, strict=False)
        assert result == []

    def test_decode_invalid_row_strict(self, simple_config: dict[str, Any]) -> None:
        """Invalid row raises error in strict mode."""
        packet = json.dumps(
            {"_f": "a", "c": simple_config["cid"], "v": simple_config["v"], "d": ["not a list"]}
        )
        with pytest.raises(AGONError, match="Row must be a list"):
            AGON.decode(packet, simple_config, strict=True)

    def test_decode_invalid_row_nonstrict(self, simple_config: dict[str, Any]) -> None:
        """Invalid row is skipped in non-strict mode."""
        packet = json.dumps(
            {
                "_f": "a",
                "c": simple_config["cid"],
                "v": simple_config["v"],
                "d": ["not a list", [1, "Alice", "admin"]],
            }
        )
        result = AGON.decode(packet, simple_config, strict=False)
        # First row skipped, second decoded
        assert len(result) == 1

    def test_decode_invalid_dict_pointer_strict(self) -> None:
        """Invalid dictionary pointer raises error in strict mode."""
        data: list[dict[str, Any]] = [{"role": "admin"} for _ in range(20)]
        config = AGON.train(data, "dict")
        # Manually create packet with invalid pointer
        packet = json.dumps({"_f": "a", "c": config["cid"], "v": config["v"], "d": [[-999]]})
        with pytest.raises(AGONError, match="Invalid dict ref"):
            AGON.decode(packet, config, strict=True)

    def test_decode_invalid_dict_pointer_nonstrict(self) -> None:
        """Invalid dictionary pointer preserved in non-strict mode."""
        data: list[dict[str, Any]] = [{"role": "admin"} for _ in range(20)]
        config = AGON.train(data, "dict")
        packet = json.dumps({"_f": "a", "c": config["cid"], "v": config["v"], "d": [[-999]]})
        result = AGON.decode(packet, config, strict=False)
        assert result[0]["role"] == -999

    def test_decode_cid_mismatch_nonstrict(self, simple_config: dict[str, Any]) -> None:
        """CID mismatch ignored in non-strict mode."""
        packet = json.dumps(
            {"_f": "a", "c": "wrong", "v": simple_config["v"], "d": [[1, "Test", "admin"]]}
        )
        result = AGON.decode(packet, simple_config, strict=False)
        assert len(result) == 1

    def test_decode_drift_guard_nested_obj(self) -> None:
        """Drift guard handles malformed nested object."""
        data = [{"user": {"name": "Alice"}}]
        config = AGON.train(data, "obj")
        # Create packet with dict instead of packed row for nested obj
        packet = json.dumps(
            {"_f": "a", "c": config["cid"], "v": config["v"], "d": [[{"name": "Alice"}]]}
        )
        result = AGON.decode(packet, config)
        # Dict passed through as-is (drift guard)
        assert result[0]["user"] == {"name": "Alice"}

    def test_decode_drift_guard_nested_list(self) -> None:
        """Drift guard handles malformed nested list."""
        data = [{"items": [{"id": 1}]}]
        config = AGON.train(data, "list")
        # Create packet with non-list-of-lists for nested list
        packet = json.dumps({"_f": "a", "c": config["cid"], "v": config["v"], "d": [[[1, 2, 3]]]})
        result = AGON.decode(packet, config)
        # Malformed data passed through
        assert len(result) == 1


class TestNullSemantics:
    """Tests for null/missing field handling."""

    def test_trailing_missing_truncated(self) -> None:
        """Trailing missing fields are truncated."""
        data: list[dict[str, Any]] = [{"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 2}, {"a": 1}]
        config = AGON.train(data, "truncate")
        encoded = AGON.encode(data, config, force_agon=True)
        parsed = json.loads(encoded)
        rows = parsed["d"]
        assert len(rows[0]) == 3
        assert len(rows[1]) == 2
        assert len(rows[2]) == 1

    def test_explicit_null_preserved(self) -> None:
        """Explicit trailing null is preserved."""
        data: list[dict[str, Any]] = [{"a": 1, "b": None}]  # Explicit null
        config = AGON.train(data, "null_test")
        encoded = AGON.encode(data, config, force_agon=True)
        decoded = AGON.decode(encoded, config)
        assert decoded[0]["b"] is None

    def test_internal_null_handling(self) -> None:
        """Internal nulls are preserved, trailing missing are truncated."""
        # Dense-first ordering puts less-frequent keys at end
        # 'a' and 'c' appear in both rows (100% dense)
        # 'b' only appears in first row (50% dense) -> goes last
        data: list[dict[str, Any]] = [
            {"a": 1, "b": None, "c": 3},  # b is explicit null (trailing)
            {"a": 1, "c": 3},  # b is missing (trailing)
        ]
        config = AGON.train(data, "internal")
        encoded = AGON.encode(data, config, force_agon=True)
        decoded = AGON.decode(encoded, config)
        # Explicit trailing null is preserved
        assert decoded[0]["b"] is None
        # Missing trailing field is truncated (not restored)
        assert "b" not in decoded[1]


class TestJSONSchema:
    """Tests for JSON Schema generation."""

    def test_json_schema_structure(self, simple_config: dict[str, Any]) -> None:
        """Generated schema has correct structure."""
        schema = AGON.get_json_schema(simple_config)
        assert schema["type"] == "object"
        assert "_f" in schema["properties"]
        assert "c" in schema["properties"]
        assert "v" in schema["properties"]
        assert "d" in schema["properties"]
        assert schema["additionalProperties"] is False

    def test_json_schema_constants(self, simple_config: dict[str, Any]) -> None:
        """Schema enforces correct constants."""
        schema = AGON.get_json_schema(simple_config)
        assert schema["properties"]["_f"]["const"] == "a"
        assert schema["properties"]["c"]["const"] == simple_config["cid"]
        assert schema["properties"]["v"]["const"] == simple_config["v"]

    def test_json_schema_nested_obj(self, nested_config: dict[str, Any]) -> None:
        """JSON schema handles nested objects."""
        schema = AGON.get_json_schema(nested_config)
        assert "d" in schema["properties"]

    def test_json_schema_nested_list(self, list_config: dict[str, Any]) -> None:
        """JSON schema handles nested lists."""
        schema = AGON.get_json_schema(list_config)
        assert "d" in schema["properties"]

    def test_json_schema_dict_type(self) -> None:
        """JSON schema handles dictionary-encoded fields."""
        data: list[dict[str, Any]] = [{"role": "admin"} for _ in range(20)]
        config = AGON.train(data, "dict")
        schema = AGON.get_json_schema(config)
        # Should have integer constraint for negative pointers
        d_schema = schema["properties"]["d"]
        assert d_schema["type"] == "array"


class TestSystemPrompt:
    """Tests for system prompt generation."""

    def test_system_prompt_contains_config(self, simple_config: dict[str, Any]) -> None:
        """System prompt contains config identifiers."""
        prompt = AGON.system_prompt(simple_config)
        assert simple_config["cid"] in prompt
        assert simple_config["v"] in prompt

    def test_system_prompt_contains_schema_info(self, simple_config: dict[str, Any]) -> None:
        """System prompt contains schema information."""
        prompt = AGON.system_prompt(simple_config)
        assert "keys" in prompt
        assert "AGON" in prompt


class TestAgonClient:
    """Tests for high-level AgonClient class."""

    def test_register_and_encode(self) -> None:
        """AgonClient can register endpoints and encode data."""
        client = AgonClient()
        sample: list[dict[str, Any]] = [{"id": 1, "name": "Test"}]
        client.register("test", sample)
        encoded = client.encode("test", sample)
        assert encoded  # Non-empty string

    def test_encode_unregistered(self) -> None:
        """Unregistered endpoint returns raw JSON."""
        client = AgonClient()
        data: list[dict[str, Any]] = [{"id": 1}]
        encoded = client.encode("unknown", data)
        assert encoded == '[{"id":1}]'

    def test_roundtrip(self) -> None:
        """AgonClient roundtrip works correctly."""
        client = AgonClient()
        sample: list[dict[str, Any]] = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        client.register("users", sample)
        encoded = client.encode("users", sample)
        decoded = client.decode("users", encoded)
        assert decoded == sample

    def test_get_prompt(self) -> None:
        """AgonClient returns system prompt for endpoint."""
        client = AgonClient()
        client.register("test", [{"id": 1}])
        prompt = client.get_prompt("test")
        assert "AGON" in prompt

    def test_get_tool_schema(self) -> None:
        """AgonClient returns tool schema for endpoint."""
        client = AgonClient()
        client.register("test", [{"id": 1}])
        schema = client.get_tool_schema("test")
        assert schema["type"] == "json_schema"
        assert "agon_test" in schema["json_schema"]["name"]

    def test_decode_unregistered_raw_json(self) -> None:
        """Unregistered endpoint decodes raw JSON."""
        client = AgonClient()
        payload = '[{"id": 1}]'
        decoded = client.decode("unknown", payload)
        assert decoded == [{"id": 1}]

    def test_decode_unregistered_invalid_json(self) -> None:
        """Unregistered endpoint returns empty on invalid JSON."""
        client = AgonClient()
        decoded = client.decode("unknown", "{invalid")
        assert decoded == []

    def test_decode_unregistered_j_format(self) -> None:
        """Unregistered endpoint handles 'j' format."""
        client = AgonClient()
        payload = json.dumps({"_f": "j", "d": [{"id": 1}]})
        decoded = client.decode("unknown", payload)
        assert decoded == [{"id": 1}]

    def test_decode_unregistered_unknown_format(self) -> None:
        """Unregistered endpoint returns empty on unknown format."""
        client = AgonClient()
        payload = json.dumps({"unknown": "format"})
        decoded = client.decode("unknown", payload)
        assert decoded == []


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_list_encoding(self) -> None:
        """Empty list encodes correctly."""
        config = AGON.train([{"id": 1}], "empty_test")
        encoded = AGON.encode([], config)
        assert encoded == "[]"

    def test_deeply_nested_structure(self) -> None:
        """Deeply nested structures work correctly."""
        data: list[dict[str, Any]] = [
            {
                "level1": {
                    "level2": {"level3": {"value": 1}},
                },
            }
        ]
        config = AGON.train(data, "deep")
        encoded = AGON.encode(data, config, force_agon=True)
        decoded = AGON.decode(encoded, config)
        assert decoded[0]["level1"]["level2"]["level3"]["value"] == 1

    def test_special_characters_in_strings(self) -> None:
        """Strings with special characters handled correctly."""
        data: list[dict[str, Any]] = [
            {"text": "Hello, World!"},
            {"text": 'Quotes: "test"'},
            {"text": "Unicode: \u00e9\u00e8\u00ea"},
        ]
        config = AGON.train(data, "special")
        encoded = AGON.encode(data, config)
        decoded = AGON.decode(encoded, config)
        assert decoded == data

    def test_numeric_edge_cases(self) -> None:
        """Numeric edge cases handled correctly."""
        data: list[dict[str, Any]] = [
            {"num": 0},
            {"num": -1},
            {"num": 1.5},
            {"num": 1e10},
        ]
        config = AGON.train(data, "numeric")
        encoded = AGON.encode(data, config)
        decoded = AGON.decode(encoded, config)
        assert decoded == data

    def test_boolean_values(self) -> None:
        """Boolean values handled correctly."""
        data: list[dict[str, Any]] = [{"flag": True}, {"flag": False}]
        config = AGON.train(data, "bool")
        encoded = AGON.encode(data, config)
        decoded = AGON.decode(encoded, config)
        assert decoded == data

    def test_validate_packed_row_too_long(self) -> None:
        """Packed row longer than schema is invalid."""
        data = [{"a": 1}]
        config = AGON.train(data, "short")
        # Row with more elements than keys
        result = AGON._validate_packed_row_structure([1, 2, 3], config["schema"])
        assert result is False

    def test_validate_packed_row_with_dict(self) -> None:
        """Packed row with raw dict is invalid."""
        data = [{"a": 1}]
        config = AGON.train(data, "no_dict")
        result = AGON._validate_packed_row_structure([{"raw": "dict"}], config["schema"])
        assert result is False

    def test_validate_packed_row_obj_type_not_list(self) -> None:
        """Obj field value that's not a list is invalid."""
        data = [{"user": {"name": "Alice"}}]
        config = AGON.train(data, "obj")
        result = AGON._validate_packed_row_structure(["not a list"], config["schema"])
        assert result is False

    def test_validate_packed_row_list_type_not_list_of_lists(self) -> None:
        """List field value that's not list-of-lists is invalid."""
        data = [{"items": [{"id": 1}]}]
        config = AGON.train(data, "list")
        result = AGON._validate_packed_row_structure([[1, 2, 3]], config["schema"])
        assert result is False

    def test_token_counting(self) -> None:
        """Token counting functions work correctly."""
        # Test _tk_text
        count1 = AGON._tk_text("hello world")
        assert count1 > 0

        # Test _tk_frag (cached)
        count2 = AGON._tk_frag('"test"')
        assert count2 > 0

        # Test _tk_val
        count3 = AGON._tk_val({"key": "value"})
        assert count3 > 0
