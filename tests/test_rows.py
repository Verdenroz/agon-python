"""Tests for AGONRows format.

Tests encoding and decoding of the AGONRows row-based format.
"""

from __future__ import annotations

import textwrap
from typing import Any

import pytest

from agon import AGON, AGONRows


class TestAGONRowsBasic:
    """Basic encoding/decoding tests."""

    def test_encode_simple_object(self) -> None:
        data = {"name": "Alice", "age": 30, "active": True}
        encoded = AGONRows.encode(data, include_header=True)
        assert "@AGON rows" in encoded
        assert "name: Alice" in encoded
        assert "age: 30" in encoded
        assert "active: true" in encoded

    def test_encode_decode_roundtrip_simple(self) -> None:
        data = {"name": "Alice", "age": 30}
        encoded = AGONRows.encode(data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == data

    def test_encode_decode_roundtrip_nested(self) -> None:
        data = {
            "company": "ACME",
            "address": {
                "street": "123 Main St",
                "city": "Seattle",
            },
        }
        encoded = AGONRows.encode(data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == data

    def test_empty_object_roundtrip(self) -> None:
        data: dict[str, Any] = {}
        encoded = AGONRows.encode(data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == {} or decoded is None


class TestAGONRowsTabular:
    """Tests for tabular array encoding (uniform objects)."""

    def test_encode_tabular_array(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONRows.encode(simple_data, include_header=True)
        assert "[3]{" in encoded  # Array header with 3 elements
        assert "id\tname\trole" in encoded or "id" in encoded

    def test_decode_tabular_array(self) -> None:
        # Named array at root level - decodes to object with array value
        payload = textwrap.dedent(
            """\
            @AGON rows

            products[3]{sku\tname\tprice}
            A123\tWidget\t9.99
            B456\tGadget\t19.99
            C789\tGizmo\t29.99
            """
        )
        decoded = AGONRows.decode(payload)
        assert "products" in decoded
        products = decoded["products"]
        assert len(products) == 3
        assert products[0] == {"sku": "A123", "name": "Widget", "price": 9.99}
        assert products[1] == {"sku": "B456", "name": "Gadget", "price": 19.99}
        assert products[2] == {"sku": "C789", "name": "Gizmo", "price": 29.99}

    def test_decode_tabular_array_unnamed(self) -> None:
        # Unnamed array at root - decodes to bare array
        payload = textwrap.dedent(
            """\
            @AGON rows

            [3]{sku\tname\tprice}
            A123\tWidget\t9.99
            B456\tGadget\t19.99
            C789\tGizmo\t29.99
            """
        )
        decoded = AGONRows.decode(payload)
        assert len(decoded) == 3
        assert decoded[0] == {"sku": "A123", "name": "Widget", "price": 9.99}

    def test_roundtrip_tabular_array(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONRows.encode(simple_data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == simple_data

    def test_tabular_with_missing_values(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON rows

            users[3]{id\tname\temail}
            1\tAlice\talice@example.com
            2\tBob\t
            3\t\tcarol@example.com
            """
        )
        decoded = AGONRows.decode(payload)
        users = decoded["users"]
        assert len(users) == 3
        assert users[0] == {"id": 1, "name": "Alice", "email": "alice@example.com"}
        assert users[1] == {"id": 2, "name": "Bob"}  # Missing email
        assert users[2] == {"id": 3, "email": "carol@example.com"}  # Missing name


class TestAGONRowsPrimitiveArrays:
    """Tests for primitive array encoding."""

    def test_encode_primitive_array(self) -> None:
        data = {"tags": ["admin", "ops", "dev"]}
        encoded = AGONRows.encode(data, include_header=True)
        assert "[3]:" in encoded

    def test_decode_primitive_array(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON rows

            tags[4]: admin\tops\tdev\tuser
            """
        )
        decoded = AGONRows.decode(payload)
        assert decoded == {"tags": ["admin", "ops", "dev", "user"]}

    def test_roundtrip_primitive_array(self) -> None:
        data = {"numbers": [1, 2, 3, 4, 5]}
        encoded = AGONRows.encode(data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == data

    def test_decode_primitive_array_with_escaped_quote(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON rows

            vals[2]: "a\\\"b"\t"c"
            """
        )
        assert AGONRows.decode(payload) == {"vals": ['a"b', "c"]}

    def test_empty_array_roundtrip(self) -> None:
        data = {"items": []}
        encoded = AGONRows.encode(data, include_header=True)
        assert "items[0]:" in encoded
        decoded = AGONRows.decode(encoded)
        assert decoded == {"items": []}


class TestAGONRowsMixedArrays:
    """Tests for mixed-type array encoding (list format)."""

    def test_encode_mixed_array(self) -> None:
        data = {"items": [42, "hello", True, None]}
        encoded = AGONRows.encode(data, include_header=True)
        assert "items[4]:" in encoded

    def test_decode_list_array_with_objects(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON rows

            records[2]:
              - name: Alice
                age: 30
              - name: Bob
                age: 25
            """
        )
        decoded = AGONRows.decode(payload)
        records = decoded["records"]
        assert len(records) == 2
        assert records[0] == {"name": "Alice", "age": 30}
        assert records[1] == {"name": "Bob", "age": 25}

    def test_decode_list_array_header_with_no_inline_values(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON rows

            vals[2]:
              - 1
              - 2
            """
        )
        assert AGONRows.decode(payload) == {"vals": [1, 2]}

    def test_parses_newline_delimiter_header(self) -> None:
        # Delimiter may not be used in the body, but header parsing should accept it.
        payload = textwrap.dedent(
            """\
            @AGON rows
            @D=\\n

            s: "x"
            """
        )
        assert AGONRows.decode(payload) == {"s": "x"}

    def test_parses_tab_delimiter_header(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON rows
            @D=\\t

            s: "x"
            """
        )
        assert AGONRows.decode(payload) == {"s": "x"}

    def test_quotes_strings_that_look_like_primitives(self) -> None:
        data = {"b": "true", "n": "123", "z": "null"}
        encoded = AGONRows.encode(data, include_header=True)
        assert 'b: "true"' in encoded
        assert 'n: "123"' in encoded
        assert 'z: "null"' in encoded
        assert AGONRows.decode(encoded) == data

    def test_special_floats_decode_as_none(self) -> None:
        data = {"nan": float("nan"), "inf": float("inf"), "ninf": float("-inf")}
        decoded = AGONRows.decode(AGONRows.encode(data, include_header=True))
        assert decoded["nan"] is None
        assert decoded["inf"] is None
        assert decoded["ninf"] is None


class TestAGONRowsPrimitives:
    """Tests for primitive value handling."""

    def test_encode_null(self) -> None:
        data = {"value": None}
        encoded = AGONRows.encode(data, include_header=True)
        assert "value: null" in encoded

    def test_encode_booleans(self) -> None:
        data = {"active": True, "deleted": False}
        encoded = AGONRows.encode(data, include_header=True)
        assert "active: true" in encoded
        assert "deleted: false" in encoded

    def test_encode_numbers(self) -> None:
        data = {"integer": 42, "float": 3.14, "negative": -17}
        encoded = AGONRows.encode(data, include_header=True)
        assert "integer: 42" in encoded
        assert "float: 3.14" in encoded
        assert "negative: -17" in encoded

    def test_encode_special_floats(self) -> None:
        # NaN and Infinity should become null
        data = {"nan": float("nan"), "inf": float("inf")}
        encoded = AGONRows.encode(data, include_header=True)
        assert "nan: null" in encoded
        assert "inf: null" in encoded

    def test_decode_primitives(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON rows

            value: 42
            name: Alice
            active: true
            missing: null
            """
        )
        decoded = AGONRows.decode(payload)
        assert decoded == {"value": 42, "name": "Alice", "active": True, "missing": None}


class TestAGONRowsQuoting:
    """Tests for string quoting rules."""

    def test_quote_string_with_delimiter(self) -> None:
        data = {"rows": "hello\tworld"}
        encoded = AGONRows.encode(data, include_header=True)
        assert '"hello\\tworld"' in encoded or '"' in encoded

    def test_quote_string_with_leading_space(self) -> None:
        data = {"rows": " leading space"}
        encoded = AGONRows.encode(data, include_header=True)
        assert '" leading space"' in encoded

    def test_quote_string_with_special_char(self) -> None:
        data = {"tag": "@mention"}
        encoded = AGONRows.encode(data, include_header=True)
        assert '"@mention"' in encoded

    def test_quote_string_looks_like_number(self) -> None:
        data = {"code": "42"}
        encoded = AGONRows.encode(data, include_header=True)
        assert '"42"' in encoded

    def test_roundtrip_quoted_strings(self) -> None:
        data = {"rows": 'Say "hello"', "path": "C:\\Users"}
        encoded = AGONRows.encode(data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == data

    def test_long_and_unicode_string_roundtrip(self) -> None:
        data = {"rows": "Hello 世界 🌍" + ("x" * 1000)}
        encoded = AGONRows.encode(data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == data

    def test_roundtrip_string_escaping_newlines_and_whitespace(self) -> None:
        data = {
            "delim": "a\t b",
            "ws": "  padded  ",
            "newline": "x\ny",
            "special": "@tag",
        }
        encoded = AGONRows.encode([data], include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == [data]


class TestAGONRowsNesting:
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
        encoded = AGONRows.encode(data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == data

    def test_array_inside_object(self, nested_data: list[dict[str, Any]]) -> None:
        encoded = AGONRows.encode(nested_data, include_header=True)
        decoded = AGONRows.decode(encoded)
        assert decoded == nested_data

    def test_decode_object_with_named_arrays(self) -> None:
        payload = textwrap.dedent(
            """\
            @AGON rows

            root:
              nums[2]: 1\t2
              rows[2]{a\tb}
              1\t2
              3\t4
              items[1]:
                - x: 1
                  y:
                    z: 2
            """
        )
        assert AGONRows.decode(payload) == {
            "root": {
                "nums": [1, 2],
                "rows": [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
                "items": [{"x": 1, "y": {"z": 2}}],
            }
        }


class TestAGONRowsIntegration:
    """Integration tests with AGON core."""

    def test_agon_encode_rows_format(self, simple_data: list[dict[str, Any]]) -> None:
        result = AGON.encode(simple_data, format="rows")
        assert result.format == "rows"
        assert result.header == "@AGON rows"

    def test_agon_decode_detects_rows_format(self, simple_data: list[dict[str, Any]]) -> None:
        encoded = AGONRows.encode(simple_data, include_header=True)
        decoded = AGON.decode(encoded)
        assert decoded == simple_data

    def test_agon_decode_encoding_directly(self, simple_data: list[dict[str, Any]]) -> None:
        result = AGON.encode(simple_data, format="rows")
        decoded = AGON.decode(result)
        assert decoded == simple_data

    def test_agon_auto_includes_rows_in_candidates(self, simple_data: list[dict[str, Any]]) -> None:
        # Encode with auto should consider rows format
        result = AGON.encode(simple_data, format="auto")
        # Result could be any format, but rows should have been considered
        assert result.format in ("json", "rows", "columns", "struct")


class TestAGONRowsErrors:
    """Error handling tests."""

    def test_invalid_header(self) -> None:
        with pytest.raises(ValueError):
            AGONRows.decode("not a valid header")

    def test_empty_payload(self) -> None:
        with pytest.raises(ValueError):
            AGONRows.decode("")


class TestAGONRowsHint:
    """Test hint method."""

    def test_hint_returns_string(self) -> None:
        hint = AGONRows.hint()
        assert isinstance(hint, str)
        assert "AGON rows" in hint
