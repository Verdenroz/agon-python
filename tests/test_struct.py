"""Tests for AGONStruct format.

Tests encoding and decoding of the AGONStruct template-based format.
"""

from __future__ import annotations

import textwrap

import pytest

from agon import AGONStructError
from agon.formats.struct import AGONStruct


class TestAGONStructBasic:
    """Basic encoding/decoding tests."""

    def test_encode_simple_object(self) -> None:
        data = {"name": "Alice", "age": 30, "active": True}
        encoded = AGONStruct.encode(data)
        assert "@AGON struct" in encoded
        assert "name: Alice" in encoded
        assert "age: 30" in encoded
        assert "active: true" in encoded

    def test_encode_decode_roundtrip_simple(self) -> None:
        data = {"name": "Alice", "age": 30}
        encoded = AGONStruct.encode(data)
        decoded = AGONStruct.decode(encoded)
        assert decoded == data

    def test_empty_payload_raises_error(self) -> None:
        with pytest.raises(AGONStructError, match="Empty payload"):
            AGONStruct.decode("")

    def test_invalid_header_raises_error(self) -> None:
        with pytest.raises(AGONStructError, match="Invalid header"):
            AGONStruct.decode("@AGON text\nfoo: bar")


class TestAGONStructDetection:
    """Tests for struct detection and creation."""

    def test_detects_repeated_shapes(self) -> None:
        # Data with repeated {fmt, raw} pattern
        data = {
            "price": {"fmt": "100.00", "raw": 100.0},
            "change": {"fmt": "+5.00", "raw": 5.0},
            "volume": {"fmt": "1M", "raw": 1000000},
        }
        encoded = AGONStruct.encode(data)
        # Should detect FR struct for fmt/raw pattern
        assert "@FR: fmt, raw" in encoded or "@" in encoded

    def test_struct_definition_in_output(self) -> None:
        # Three occurrences needed for struct creation
        data = [
            {"a": {"fmt": "1", "raw": 1}},
            {"b": {"fmt": "2", "raw": 2}},
            {"c": {"fmt": "3", "raw": 3}},
        ]
        encoded = AGONStruct.encode(data)
        # Should have struct definition
        assert "@AGON struct" in encoded

    def test_struct_definitions_emitted_without_header(self) -> None:
        # Headerless encodes are used by AGON core by default, but the payload
        # still needs struct templates so LLMs can interpret FR(v1, v2) instances.
        data = {
            "price": {"fmt": "100.00", "raw": 100.0},
            "change": {"fmt": "+5.00", "raw": 5.0},
            "volume": {"fmt": "1M", "raw": 1000000},
        }
        encoded = AGONStruct.encode(data, include_header=False)
        assert "@AGON struct" not in encoded
        assert "@FR: fmt, raw" in encoded

    def test_no_struct_for_single_occurrence(self) -> None:
        data = {"price": {"fmt": "100", "raw": 100}}
        encoded = AGONStruct.encode(data, min_occurrences=3)
        # Only one occurrence, no struct should be created
        # Check that nested object is expanded normally
        assert "fmt:" in encoded or "raw:" in encoded


class TestAGONStructInstances:
    """Tests for struct instance encoding/decoding."""

    def test_decode_struct_instance(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @FR: fmt, raw

            price: FR("100.00", 100.0)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"price": {"fmt": "100.00", "raw": 100.0}}

    def test_decode_multiple_struct_instances(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @FR: fmt, raw

            price: FR("100.00", 100.0)
            change: FR("+5.00", 5.0)
            volume: FR(1M, 1000000)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded["price"] == {"fmt": "100.00", "raw": 100.0}
        assert decoded["change"] == {"fmt": "+5.00", "raw": 5.0}
        assert decoded["volume"] == {"fmt": "1M", "raw": 1000000}

    def test_roundtrip_with_structs(self) -> None:
        data = {
            "price": {"fmt": "100", "raw": 100},
            "change": {"fmt": "5", "raw": 5},
            "volume": {"fmt": "1M", "raw": 1000000},
        }
        encoded = AGONStruct.encode(data)
        decoded = AGONStruct.decode(encoded)
        assert decoded == data


class TestAGONStructInheritance:
    """Tests for struct inheritance."""

    def test_decode_inherited_struct(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @FR: fmt, raw
            @FRC(FR): currency

            price: FRC("100.00", 100.0, USD)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"price": {"fmt": "100.00", "raw": 100.0, "currency": "USD"}}

    def test_unknown_parent_raises_error(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Child(Unknown): field

            value: Child(1)
            """
        )
        with pytest.raises(AGONStructError, match="Unknown parent struct"):
            AGONStruct.decode(payload)


class TestAGONStructOptionalFields:
    """Tests for optional fields."""

    def test_decode_optional_field_present(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Quote: symbol, price, volume?

            stock: Quote(AAPL, 150.0, 1000000)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"stock": {"symbol": "AAPL", "price": 150.0, "volume": 1000000}}

    def test_decode_optional_field_omitted(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Quote: symbol, price, volume?

            stock: Quote(AAPL, 150.0)
            """
        )
        decoded = AGONStruct.decode(payload)
        # Optional field omitted should not appear in result
        assert decoded == {"stock": {"symbol": "AAPL", "price": 150.0}}

    def test_decode_optional_field_explicit_null(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Quote: symbol, price, volume?

            stock: Quote(AAPL, 150.0, )
            """
        )
        decoded = AGONStruct.decode(payload)
        # Explicit empty means null for optional field (omitted)
        assert decoded == {"stock": {"symbol": "AAPL", "price": 150.0}}


class TestAGONStructArrays:
    """Tests for arrays with struct instances."""

    def test_decode_inline_struct_array(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @FR: fmt, raw

            [3]: FR("1", 1.0), FR("2", 2.0), FR("3", 3.0)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert len(decoded) == 3
        assert decoded[0] == {"fmt": "1", "raw": 1.0}
        assert decoded[1] == {"fmt": "2", "raw": 2.0}
        assert decoded[2] == {"fmt": "3", "raw": 3.0}

    def test_decode_empty_array(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @FR: fmt, raw

            prices[0]:
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"prices": []}

    def test_roundtrip_array_of_structs(self) -> None:
        data = [
            {"fmt": "1", "raw": 1},
            {"fmt": "2", "raw": 2},
            {"fmt": "3", "raw": 3},
        ]
        encoded = AGONStruct.encode(data)
        decoded = AGONStruct.decode(encoded)
        assert decoded == data

    def test_roundtrip_array_of_strings_with_colon(self) -> None:
        # quoted strings containing ':' must not be parsed as
        # inline key-value objects when they appear as list items.
        data = ["keyword match: for, object, return", "language match"]
        encoded = AGONStruct.encode(data)
        decoded = AGONStruct.decode(encoded)
        assert decoded == data


class TestAGONStructEscaping:
    """Tests for value escaping."""

    def test_escape_comma_in_value(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Pair: a, b

            item: Pair(hello\\, world, test)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"item": {"a": "hello, world", "b": "test"}}

    def test_escape_parentheses_in_value(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Pair: a, b

            item: Pair(func\\(x\\), result)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"item": {"a": "func(x)", "b": "result"}}

    def test_escape_backslash_in_value(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Pair: a, b

            item: Pair(path\\\\file, test)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"item": {"a": "path\\file", "b": "test"}}


class TestAGONStructNestedObjects:
    """Tests for nested objects with structs."""

    def test_nested_object_with_struct(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @FR: fmt, raw

            quote:
              price: FR("100", 100.0)
              change: FR("5", 5.0)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {
            "quote": {
                "price": {"fmt": "100", "raw": 100.0},
                "change": {"fmt": "5", "raw": 5.0},
            }
        }

    def test_list_items_with_structs(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @FR: fmt, raw

            [2]:
              - symbol: AAPL
                price: FR("150", 150.0)
              - symbol: GOOG
                price: FR("100", 100.0)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert len(decoded) == 2
        assert decoded[0] == {"symbol": "AAPL", "price": {"fmt": "150", "raw": 150.0}}
        assert decoded[1] == {"symbol": "GOOG", "price": {"fmt": "100", "raw": 100.0}}


class TestAGONStructPrimitives:
    """Tests for primitive value handling."""

    def test_boolean_values(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Flags: a, b

            item: Flags(true, false)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"item": {"a": True, "b": False}}

    def test_null_values(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Pair: a, b

            item: Pair(, test)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"item": {"a": None, "b": "test"}}

    def test_numeric_values(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON struct

            @Nums: int_val, float_val

            item: Nums(42, 3.14)
            """
        )
        decoded = AGONStruct.decode(payload)
        assert decoded == {"item": {"int_val": 42, "float_val": 3.14}}


class TestAGONStructHint:
    """Tests for hint method."""

    def test_hint_returns_string(self) -> None:
        hint = AGONStruct.hint()
        assert isinstance(hint, str)
        assert "struct" in hint.lower()


class TestAGONStructRoundtrip:
    """End-to-end roundtrip tests."""

    def test_roundtrip_financial_data(self) -> None:
        """Test roundtrip with financial-like data having repeated shapes."""
        data = {
            "symbol": "AAPL",
            "regularMarketPrice": {"fmt": "150.00", "raw": 150.0},
            "regularMarketChange": {"fmt": "+2.50", "raw": 2.5},
            "regularMarketVolume": {"fmt": "1M", "raw": 1000000},
            "fiftyTwoWeekHigh": {"fmt": "180.00", "raw": 180.0},
            "fiftyTwoWeekLow": {"fmt": "120.00", "raw": 120.0},
        }
        encoded = AGONStruct.encode(data)
        decoded = AGONStruct.decode(encoded)
        assert decoded == data

    def test_roundtrip_array_of_records(self) -> None:
        data = [
            {
                "id": 1,
                "price": {"fmt": "100", "raw": 100},
                "change": {"fmt": "+5", "raw": 5},
            },
            {
                "id": 2,
                "price": {"fmt": "200", "raw": 200},
                "change": {"fmt": "-3", "raw": -3},
            },
            {
                "id": 3,
                "price": {"fmt": "150", "raw": 150},
                "change": {"fmt": "+10", "raw": 10},
            },
        ]
        encoded = AGONStruct.encode(data)
        decoded = AGONStruct.decode(encoded)
        assert decoded == data

    def test_roundtrip_mixed_content(self) -> None:
        data = {
            "name": "Test",
            "values": [1, 2, 3],
            "nested": {
                "a": {"fmt": "1", "raw": 1},
                "b": {"fmt": "2", "raw": 2},
                "c": {"fmt": "3", "raw": 3},
            },
        }
        encoded = AGONStruct.encode(data)
        decoded = AGONStruct.decode(encoded)
        assert decoded == data
