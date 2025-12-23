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

    def test_encode_falls_back_to_string_for_unknown_types(self) -> None:
        class Custom:
            def __str__(self) -> str:  # pragma: no cover
                return "CUSTOM"

        encoded = AGONColumns.encode({"x": Custom()})
        decoded = AGONColumns.decode(encoded)
        assert decoded == {"x": "CUSTOM"}


class TestAGONColumnsColumnar:
    """Tests for columnar array encoding (uniform objects)."""

    def test_encode_columnar_array(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONColumns.encode(simple_data)
        assert "[3]" in encoded
        assert "├" in encoded or "|" in encoded
        assert "└" in encoded or "`" in encoded

    def test_decode_columnar_array(self) -> None:
        payload = (
            "@AGON columns\n"
            "\n"
            "products[3]\n"
            "├ sku: A123\tB456\tC789\n"
            "├ name: Widget\tGadget\tGizmo\n"
            "└ price: 9.99\t19.99\t29.99\n"
        )
        decoded = AGONColumns.decode(payload)
        assert "products" in decoded
        products = decoded["products"]
        assert len(products) == 3
        assert products[0] == {"sku": "A123", "name": "Widget", "price": 9.99}
        assert products[1] == {"sku": "B456", "name": "Gadget", "price": 19.99}
        assert products[2] == {"sku": "C789", "name": "Gizmo", "price": 29.99}

    def test_decode_columnar_array_unnamed(self) -> None:
        payload = (
            "@AGON columns\n"
            "\n"
            "[3]\n"
            "├ sku: A123\tB456\tC789\n"
            "├ name: Widget\tGadget\tGizmo\n"
            "└ price: 9.99\t19.99\t29.99\n"
        )
        decoded = AGONColumns.decode(payload)
        assert len(decoded) == 3
        assert decoded[0] == {"sku": "A123", "name": "Widget", "price": 9.99}

    def test_roundtrip_columnar_array(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONColumns.encode(simple_data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == simple_data

    def test_columnar_with_missing_values(self) -> None:
        payload = (
            "@AGON columns\n"
            "\n"
            "users[3]\n"
            "├ id: 1\t2\t3\n"
            "├ name: Alice\tBob\tCarol\n"
            "└ email: alice@example.com\t\tcarol@example.com\n"
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
        payload = "@AGON columns\n\nusers[2]\n| id: 1\t2\n` name: Alice\tBob\n"
        decoded = AGONColumns.decode(payload)
        users = decoded["users"]
        assert len(users) == 2
        assert users[0] == {"id": 1, "name": "Alice"}
        assert users[1] == {"id": 2, "name": "Bob"}

    def test_decode_columnar_array_field_shorter_than_count(self) -> None:
        payload = "@AGON columns\n\nusers[2]\n└ id: 1\n"
        decoded = AGONColumns.decode(payload)
        assert decoded == {"users": [{"id": 1}, {}]}

    def test_decode_columnar_array_null_cell_means_present_none(self) -> None:
        payload = "@AGON columns\n\nusers[2]\n└ email: null\t\n"
        decoded = AGONColumns.decode(payload)
        assert decoded == {"users": [{"email": None}, {}]}

    def test_decode_columnar_array_escaped_quote_inside_cell(self) -> None:
        payload = '@AGON columns\n\nitems[2]\n└ s: "a\\"b"\t"c"\n'
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [{"s": 'a"b'}, {"s": "c"}]}


class TestAGONColumnsQuotingRoundtrip:
    """Roundtrip tests for quoting/unquoting strings in columns format."""

    def test_roundtrip_strings_requiring_quotes(self) -> None:
        data = [
            {"s": "123"},
            {"s": "null"},
            {"s": "@hello"},
            {"s": " spaced"},
            {"s": "a\tb"},
            {"s": r"a\\b"},
            {"s": "a\nline"},
            {"s": 'quote: "x"'},
        ]
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data


class TestAGONColumnsDirectives:
    """Tests for @D= delimiter directive parsing."""

    def test_decode_custom_delimiter_declaration(self) -> None:
        payload = '@AGON columns\n@D=\\n\n\nitems[1]\n└ s: "123"\n'
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [{"s": "123"}]}

    def test_decode_tab_delimiter_declaration(self) -> None:
        payload = '@AGON columns\n@D=\\t\n\nitems[2]\n└ s: "a"\t"b"\n'
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [{"s": "a"}, {"s": "b"}]}

    def test_encode_emits_delimiter_declaration_for_non_default(self) -> None:
        data = [{"id": 1}, {"id": 2}]
        encoded = AGONColumns.encode(data, delimiter=",", use_ascii=True)
        assert "@D=," in encoded
        decoded = AGONColumns.decode(encoded)
        assert decoded == data

    def test_decode_custom_comma_delimiter_splits_quoted_values(self) -> None:
        payload = '@AGON columns\n@D=,\n\nitems[2]\n└ s: "a,b","c"\n'
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [{"s": "a,b"}, {"s": "c"}]}


class TestAGONColumnsPrimitiveArrays:
    """Tests for primitive array encoding."""

    def test_encode_primitive_array(self) -> None:
        data = {"tags": ["admin", "ops", "dev"]}
        encoded = AGONColumns.encode(data)
        assert "[3]:" in encoded

    def test_decode_primitive_array(self) -> None:
        payload = "@AGON columns\n\ntags[4]: admin\tops\tdev\tuser\n"
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

    def test_decode_list_array_with_primitives(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            items[3]:
              - 1
              - null
              - \"x\"
            """
        )
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [1, None, "x"]}

    def test_decode_list_array_skips_blank_and_comment_lines(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON columns

            items[2]:
              # comment line
              - 1

              - 2
            """
        )
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [1, 2]}

    def test_roundtrip_list_item_object_with_nested_object(self) -> None:
        data = {"items": [{"id": 1, "meta": {"tags": ["a", "b"], "flag": True}}]}
        encoded = AGONColumns.encode(data)
        decoded = AGONColumns.decode(encoded)
        assert decoded == data


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
        # Tab is the delimiter, so strings containing tabs need quoting
        data = {"text": "hello\tworld"}
        encoded = AGONColumns.encode(data)
        assert '"hello\\tworld"' in encoded

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

    def test_decode_quoted_string_with_unknown_escape(self) -> None:
        payload = '@AGON columns\n\nv: "a\\q"\n'
        decoded = AGONColumns.decode(payload)
        assert decoded == {"v": "aq"}

    def test_unquote_string_is_noop_for_unquoted_input(self) -> None:
        from agon.formats.columns import _unquote_string

        assert _unquote_string("abc") == "abc"


class TestAGONColumnsDelimiters:
    """Tests for custom delimiters."""

    def test_encode_with_comma_delimiter(self) -> None:
        # Tab is now the default, so test with comma to verify @D= is emitted
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        encoded = AGONColumns.encode(data, delimiter=",")
        assert "@D=," in encoded

    def test_decode_with_tab_delimiter(self) -> None:
        # Tab is now the default, so no @D= needed
        payload = "@AGON columns\n\nusers[2]\n├ id: 1\t2\n└ name: Alice\tBob\n"
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


class TestAGONColumnsEmptyAndStrings:
    """Tests for empty values and string handling."""

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


class TestAGONColumnsArrays:
    """Tests for array variants beyond pure columnar tables."""

    def test_decode_primitive_array_empty_values(self) -> None:
        payload = "@AGON columns\n\nnums[0]: \n"
        decoded = AGONColumns.decode(payload)
        assert decoded == {"nums": []}

    def test_decode_list_array_item_with_nested_primitive_array(self) -> None:
        payload = "@AGON columns\n\nitems[1]:\n  - id: 1\n    tags[2]: a\tb\n"
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [{"id": 1, "tags": ["a", "b"]}]}

    def test_decode_list_array_item_object_with_nested_object_value(self) -> None:
        payload = "@AGON columns\n\nitems[1]:\n  - meta:\n      a: 1\n"
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [{"meta": {"a": 1}}]}

    def test_decode_list_array_item_object_missing_nested_value_becomes_empty_object(self) -> None:
        payload = "@AGON columns\n\nitems[1]:\n  - meta:\n"
        decoded = AGONColumns.decode(payload)
        assert decoded == {"items": [{"meta": {}}]}


class TestAGONColumnsIntegration:
    """Integration tests with AGON core."""

    def test_agon_encode_columns_format(self, simple_data: list[dict[str, Any]]) -> None:
        result = AGON.encode(simple_data, format="columns")
        assert result.format == "columns"
        assert result.header == "@AGON columns"

    def test_agon_decode_detects_columns_format(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONColumns.encode(simple_data)
        decoded = AGON.decode(encoded)
        assert decoded == simple_data

    def test_agon_decode_encoding_directly(self, simple_data: list[dict[str, Any]]) -> None:
        result = AGON.encode(simple_data, format="columns")
        decoded = AGON.decode(result)
        assert decoded == simple_data

    def test_agon_auto_includes_columns_in_candidates(
        self, simple_data: list[dict[str, Any]]
    ) -> None:
        result = AGON.encode(simple_data, format="auto")
        assert result.format in ("json", "text", "columns", "struct")


class TestAGONColumnsErrors:
    """Error handling tests."""

    def test_invalid_header(self) -> None:
        with pytest.raises(AGONColumnsError, match="Invalid header"):
            AGONColumns.decode("not a valid header")

    def test_empty_payload(self) -> None:
        with pytest.raises(AGONColumnsError, match="Empty payload"):
            AGONColumns.decode("")

    def test_cannot_parse_line_raises(self) -> None:
        payload = "@AGON columns\n\n???\n"
        with pytest.raises(AGONColumnsError, match=r"Cannot parse line"):
            AGONColumns.decode(payload)

    def test_array_header_without_tree_lines_raises(self) -> None:
        payload = "@AGON columns\n\n[2]\nnot-a-tree\n"
        with pytest.raises(AGONColumnsError, match=r"Cannot parse line"):
            AGONColumns.decode(payload)


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
        # Values should be grouped by column (tab-separated)
        assert "status: active\tactive\tactive" in encoded
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
        # Values should be tab-separated
        assert "price: 9.99\t19.99\t29.99" in encoded
        assert "qty: 10\t20\t30" in encoded
        decoded = AGONColumns.decode(encoded)
        assert decoded == data
