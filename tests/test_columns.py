"""Tests for AGONColumns format.

Tests encoding and decoding of the columnar format optimized for wide tables.
"""

from __future__ import annotations

import textwrap
from typing import Any

import pytest

from agon import AGON, AGONColumnsError
from agon.formats.columns import AGONColumns


class TestAGONColumnsBasic:
    """Basic encoding/decoding tests."""

    def test_encode_simple_object(self) -> None:
        data = {"name": "Alice", "age": 30, "active": True}
        encoded = AGONColumns.encode(data)
        assert "@AGON columns" in encoded
        assert "name: Alice" in encoded
        assert "age: 30" in encoded
        assert "active: true" in encoded

    def test_encode_decode_roundtrip_simple(self) -> None:
        data = {"name": "Alice", "age": 30}
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data

    def test_encode_decode_roundtrip_nested(self) -> None:
        data = {
            "company": "ACME",
            "address": {
                "street": "123 Main St",
                "city": "Seattle",
            },
        }
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data


class TestAGONColumnsColumnar:
    """Tests for columnar array encoding (uniform objects)."""

    def test_encode_columnar_array(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONColumns.encode(simple_data)
        assert "[3]" in encoded
        assert "├" in encoded or "|" in encoded
        assert "└" in encoded or "`" in encoded

    def test_decode_columnar_array(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            products[3]
            ├ sku: A123, B456, C789
            ├ name: Widget, Gadget, Gizmo
            └ price: 9.99, 19.99, 29.99
            """
        )
        decoded = AGONColumns.decode(payload)
        assert "products" in decoded
        products = decoded["products"]
        assert len(products) == 3
        assert products[0] == {"sku": "A123", "name": "Widget", "price": 9.99}
        assert products[1] == {"sku": "B456", "name": "Gadget", "price": 19.99}
        assert products[2] == {"sku": "C789", "name": "Gizmo", "price": 29.99}

    def test_decode_columnar_array_unnamed(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            [3]
            ├ sku: A123, B456, C789
            ├ name: Widget, Gadget, Gizmo
            └ price: 9.99, 19.99, 29.99
            """
        )
        decoded = AGONColumns.decode(payload)
        assert len(decoded) == 3
        assert decoded[0] == {"sku": "A123", "name": "Widget", "price": 9.99}

    def test_roundtrip_columnar_array(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONColumns.encode(simple_data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == simple_data

    def test_columnar_with_missing_values(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            users[3]
            ├ id: 1, 2, 3
            ├ name: Alice, Bob, Carol
            └ email: alice@example.com, , carol@example.com
            """
        )
        decoded = AGONColumns.decode(payload)
        users = decoded["users"]
        assert len(users) == 3
        assert users[0] == {"id": 1, "name": "Alice", "email": "alice@example.com"}
        assert users[1] == {"id": 2, "name": "Bob"}
        assert users[2] == {"id": 3, "name": "Carol", "email": "carol@example.com"}

    def test_ascii_tree_chars(self) -> None:
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        encoded = AGONColumns.encode(data, use_ascii=True)
        assert "|" in encoded
        assert "`" in encoded
        assert "├" not in encoded
        assert "└" not in encoded

    def test_decode_ascii_tree_chars(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            users[2]
            | id: 1, 2
            ` name: Alice, Bob
            """
        )
        decoded = AGONColumns.decode(payload)
        users = decoded["users"]
        assert len(users) == 2
        assert users[0] == {"id": 1, "name": "Alice"}
        assert users[1] == {"id": 2, "name": "Bob"}


class TestAGONColumnsPrimitiveArrays:
    """Tests for primitive array encoding."""

    def test_encode_primitive_array(self) -> None:
        data = {"tags": ["admin", "ops", "dev"]}
        encoded = AGONColumns.encode(data)
        assert "[3]:" in encoded

    def test_decode_primitive_array(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            tags[4]: admin, ops, dev, user
            """
        )
        decoded = AGONColumns.decode(payload)
        assert decoded == {"tags": ["admin", "ops", "dev", "user"]}

    def test_roundtrip_primitive_array(self) -> None:
        data = {"numbers": [1, 2, 3, 4, 5]}
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data


class TestAGONColumnsMixedArrays:
    """Tests for mixed-type array encoding (list format)."""

    def test_encode_mixed_array(self) -> None:
        data = {"items": [42, "hello", True, None]}
        encoded = AGONColumns.encode(data)
        assert "items[4]:" in encoded

    def test_decode_list_array_with_objects(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            records[2]:
              - name: Alice
                age: 30
              - name: Bob
                age: 25
            """
        )
        decoded = AGONColumns.decode(payload)
        records = decoded["records"]
        assert len(records) == 2
        assert records[0] == {"name": "Alice", "age": 30}
        assert records[1] == {"name": "Bob", "age": 25}


class TestAGONColumnsPrimitives:
    """Tests for primitive value handling."""

    def test_encode_null(self) -> None:
        data = {"value": None}
        encoded = AGONColumns.encode(data)
        assert "value:" in encoded

    def test_encode_booleans(self) -> None:
        data = {"active": True, "deleted": False}
        encoded = AGONColumns.encode(data)
        assert "active: true" in encoded
        assert "deleted: false" in encoded

    def test_encode_numbers(self) -> None:
        data = {"integer": 42, "float": 3.14, "negative": -17}
        encoded = AGONColumns.encode(data)
        assert "integer: 42" in encoded
        assert "float: 3.14" in encoded
        assert "negative: -17" in encoded

    def test_encode_special_floats(self) -> None:
        data = {"nan": float("nan"), "inf": float("inf")}
        encoded = AGONColumns.encode(data)
        assert "nan:" in encoded
        assert "inf:" in encoded

    def test_decode_primitives(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            value: 42
            name: Alice
            active: true
            missing: null
            """
        )
        decoded = AGONColumns.decode(payload)
        assert decoded == {"value": 42, "name": "Alice", "active": True, "missing": None}


class TestAGONColumnsQuoting:
    """Tests for string quoting rules."""

    def test_quote_string_with_delimiter(self) -> None:
        data = {"text": "hello, world"}
        encoded = AGONColumns.encode(data)
        assert '"hello, world"' in encoded

    def test_quote_string_with_leading_space(self) -> None:
        data = {"text": " leading space"}
        encoded = AGONColumns.encode(data)
        assert '" leading space"' in encoded

    def test_quote_string_with_special_char(self) -> None:
        data = {"tag": "@mention"}
        encoded = AGONColumns.encode(data)
        assert '"@mention"' in encoded

    def test_quote_string_looks_like_number(self) -> None:
        data = {"code": "42"}
        encoded = AGONColumns.encode(data)
        assert '"42"' in encoded

    def test_roundtrip_quoted_strings(self) -> None:
        data = {"text": 'Say "hello"', "path": "C:\\Users"}
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data


class TestAGONColumnsDelimiters:
    """Tests for custom delimiters."""

    def test_encode_with_tab_delimiter(self) -> None:
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        encoded = AGONColumns.encode(data, delimiter="\t")
        assert "@D=\\t" in encoded

    def test_decode_with_tab_delimiter(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns
            @D=\\t

            users[2]
            ├ id: 1\t2
            └ name: Alice\tBob
            """
        )
        decoded = AGONColumns.decode(payload)
        users = decoded["users"]
        assert len(users) == 2
        assert users[0] == {"id": 1, "name": "Alice"}
        assert users[1] == {"id": 2, "name": "Bob"}


class TestAGONColumnsNesting:
    """Tests for nested structures."""

    def test_nested_object(self) -> None:
        data = {
            "company": {
                "name": "ACME",
                "address": {
                    "street": "123 Main St",
                    "city": "Seattle",
                },
            },
        }
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data

    def test_array_inside_object(self, nested_data: list[dict[str, Any]]) -> None:
        encoded = AGONColumns.encode(nested_data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == nested_data


class TestAGONColumnsEdgeCases:
    """Edge case tests."""

    def test_empty_array(self) -> None:
        data = {"items": []}
        encoded = AGONColumns.encode(data)
        assert "items[0]" in encoded
        decoded = AGONColumns.decode(encoded)
        assert decoded == {"items": []}

    def test_empty_object(self) -> None:
        data: dict[str, Any] = {}
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == {} or decoded is None

    def test_single_element_array(self) -> None:
        data = [{"id": 1, "name": "Only"}]
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data

    def test_long_string(self) -> None:
        data = {"text": "x" * 1000}
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data

    def test_unicode_string(self) -> None:
        data = {"text": "Hello 世界 🌍"}
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data

    def test_wide_table(self) -> None:
        """Test with many columns (columnar format's strength)."""
        data = [
            {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8},
            {"a": 10, "b": 20, "c": 30, "d": 40, "e": 50, "f": 60, "g": 70, "h": 80},
        ]
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data


class TestAGONColumnsIntegration:
    """Integration tests with AGON core."""

    def test_agon_encode_columns_format(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGON.encode(simple_data, format="columns")
        assert "@AGON columns" in encoded

    def test_agon_encode_with_format_columns(self, simple_data: list[dict[str, Any]]) -> None:
        result = AGON.encode_with_format(simple_data, format="columns")
        assert result.format == "columns"
        assert "@AGON columns" in result.text

    def test_agon_decode_detects_columns_format(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONColumns.encode(simple_data)
        decoded = AGON.decode(encoded)
        assert decoded == simple_data

    def test_agon_auto_includes_columns_in_candidates(
        self, simple_data: list[dict[str, Any]]
    ) -> None:
        result = AGON.encode_with_format(simple_data, format="auto")
        assert result.format in ("json", "text", "columns")


class TestAGONColumnsErrors:
    """Error handling tests."""

    def test_invalid_header(self) -> None:
        with pytest.raises(AGONColumnsError, match="Invalid header"):
            AGONColumns.decode("not a valid header")

    def test_empty_payload(self) -> None:
        with pytest.raises(AGONColumnsError, match="Empty payload"):
            AGONColumns.decode("")


class TestAGONColumnsHint:
    """Test hint method."""

    def test_hint_returns_string(self) -> None:
        hint = AGONColumns.hint()
        assert isinstance(hint, str)
        assert "AGON columns" in hint


class TestAGONColumnsTokenEfficiency:
    """Tests demonstrating columnar format's token efficiency advantages."""

    def test_repeated_values_in_column(self) -> None:
        """Columnar format groups same values together for better compression."""
        data = [
            {"status": "active", "type": "user"},
            {"status": "active", "type": "user"},
            {"status": "active", "type": "admin"},
        ]
        encoded = AGONColumns.encode(data)
        # Values should be grouped by column
        assert "status: active, active, active" in encoded
        decoded = AGONColumns.decode(encoded)
        assert decoded == data

    def test_numeric_sequences(self) -> None:
        """Numeric values in columns should tokenize efficiently."""
        data = [
            {"price": 9.99, "qty": 10},
            {"price": 19.99, "qty": 20},
            {"price": 29.99, "qty": 30},
        ]
        encoded = AGONColumns.encode(data)
        assert "price: 9.99, 19.99, 29.99" in encoded
        assert "qty: 10, 20, 30" in encoded
        decoded = AGONColumns.decode(encoded)
        assert decoded == data
