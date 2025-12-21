"""Pytest configuration and shared fixtures."""

from typing import Any

import pytest


@pytest.fixture
def simple_data() -> list[dict[str, Any]]:
    """Simple test data with basic fields."""
    return [
        {"id": 1, "name": "Alice", "role": "admin"},
        {"id": 2, "name": "Bob", "role": "user"},
        {"id": 3, "name": "Charlie", "role": "user"},
    ]


@pytest.fixture
def nested_data() -> list[dict[str, Any]]:
    """Test data with nested objects."""
    return [
        {"id": 1, "user": {"name": "Alice", "email": "alice@example.com"}},
        {"id": 2, "user": {"name": "Bob", "email": "bob@example.com"}},
    ]


@pytest.fixture
def list_data() -> list[dict[str, Any]]:
    """Test data with nested lists."""
    return [
        {"id": 1, "tags": [{"name": "python"}, {"name": "ai"}]},
        {"id": 2, "tags": [{"name": "rust"}]},
    ]


@pytest.fixture
def data_with_nulls() -> list[dict[str, Any]]:
    """Test data with explicit nulls and missing fields."""
    return [
        {"id": 1, "name": "Alice", "role": None},  # Explicit null
        {"id": 2, "name": "Bob"},  # Missing role
        {"id": 3},  # Missing name and role
    ]
