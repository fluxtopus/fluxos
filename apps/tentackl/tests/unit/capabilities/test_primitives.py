"""
Tests for Primitives System

Tests the deterministic, composable operations.
"""

import pytest
from src.primitives import execute_primitive, PrimitiveRegistry
from src.primitives.registry import PrimitiveResult


class TestPrimitiveResult:
    """Tests for PrimitiveResult dataclass."""

    def test_success_status(self):
        result = PrimitiveResult(
            status="success",
            output={"result": "test"},
            execution_time_ms=10,
        )
        assert result.success is True

    def test_error_status(self):
        result = PrimitiveResult(
            status="error",
            output=None,
            execution_time_ms=5,
            error="Something failed",
        )
        assert result.success is False

    def test_to_dict(self):
        result = PrimitiveResult(
            status="success",
            output={"key": "value"},
            execution_time_ms=15,
        )
        d = result.to_dict()

        assert d["status"] == "success"
        assert d["output"] == {"key": "value"}
        assert d["execution_time_ms"] == 15
        assert d["error"] is None


class TestPrimitiveRegistry:
    """Tests for PrimitiveRegistry class."""

    def test_list_all(self):
        """Should list all registered primitives."""
        primitives = PrimitiveRegistry.list_all()

        assert "json.parse" in primitives
        assert "json.stringify" in primitives
        assert "string.template" in primitives
        assert "list.filter" in primitives

    def test_get_handler(self):
        """Should get handler by name."""
        handler = PrimitiveRegistry.get("json.parse")
        assert handler is not None
        assert callable(handler)

    def test_get_nonexistent(self):
        """Should return None for non-existent primitive."""
        handler = PrimitiveRegistry.get("nonexistent.operation")
        assert handler is None


class TestJsonPrimitives:
    """Tests for JSON primitives."""

    @pytest.mark.asyncio
    async def test_json_parse_string(self):
        """Should parse JSON string to object."""
        result = await execute_primitive("json.parse", {
            "data": '{"name": "test", "value": 42}'
        })

        assert result.success is True
        assert result.output["result"]["name"] == "test"
        assert result.output["result"]["value"] == 42

    @pytest.mark.asyncio
    async def test_json_parse_already_parsed(self):
        """Should handle already parsed data."""
        result = await execute_primitive("json.parse", {
            "data": {"name": "test"}
        })

        assert result.success is True
        assert result.output["result"]["name"] == "test"

    @pytest.mark.asyncio
    async def test_json_parse_invalid(self):
        """Should error on invalid JSON."""
        result = await execute_primitive("json.parse", {
            "data": "not valid json"
        })

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_json_stringify(self):
        """Should stringify object to JSON."""
        result = await execute_primitive("json.stringify", {
            "data": {"items": [1, 2, 3]}
        })

        assert result.success is True
        assert '"items"' in result.output["result"]

    @pytest.mark.asyncio
    async def test_json_stringify_with_indent(self):
        """Should stringify with indentation."""
        result = await execute_primitive("json.stringify", {
            "data": {"key": "value"},
            "indent": 2
        })

        assert result.success is True
        assert "\n" in result.output["result"]  # Indented output has newlines


class TestStringPrimitives:
    """Tests for string primitives."""

    @pytest.mark.asyncio
    async def test_string_template(self):
        """Should apply template substitution."""
        result = await execute_primitive("string.template", {
            "template": "Hello {name}, you have {count} messages",
            "variables": {"name": "User", "count": 5}
        })

        assert result.success is True
        assert result.output["result"] == "Hello User, you have 5 messages"

    @pytest.mark.asyncio
    async def test_string_split(self):
        """Should split string into list."""
        result = await execute_primitive("string.split", {
            "text": "a,b,c,d",
            "separator": ","
        })

        assert result.success is True
        assert result.output["result"] == ["a", "b", "c", "d"]
        assert result.output["count"] == 4

    @pytest.mark.asyncio
    async def test_string_replace(self):
        """Should replace text in string."""
        result = await execute_primitive("string.replace", {
            "text": "Hello world, hello universe",
            "pattern": "hello",
            "replacement": "hi",
        })

        assert result.success is True
        assert "hi" in result.output["result"].lower()

    @pytest.mark.asyncio
    async def test_string_match(self):
        """Should match pattern in string."""
        result = await execute_primitive("string.match", {
            "text": "Contact us at support@example.com",
            "pattern": r"\b[\w.-]+@[\w.-]+\.\w+\b"
        })

        assert result.success is True
        assert result.output["matched"] is True
        assert result.output["match"] == "support@example.com"


class TestListPrimitives:
    """Tests for list primitives."""

    @pytest.mark.asyncio
    async def test_list_filter_eq(self):
        """Should filter list by equality."""
        result = await execute_primitive("list.filter", {
            "items": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
                {"name": "Charlie", "age": 30}
            ],
            "field": "age",
            "operator": "eq",
            "value": 30
        })

        assert result.success is True
        assert result.output["count"] == 2
        assert all(item["age"] == 30 for item in result.output["result"])

    @pytest.mark.asyncio
    async def test_list_filter_gt(self):
        """Should filter list by greater than."""
        result = await execute_primitive("list.filter", {
            "items": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
                {"name": "Charlie", "age": 35}
            ],
            "field": "age",
            "operator": "gt",
            "value": 28
        })

        assert result.success is True
        assert result.output["count"] == 2

    @pytest.mark.asyncio
    async def test_list_map_fields(self):
        """Should extract fields from list items."""
        result = await execute_primitive("list.map", {
            "items": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ],
            "fields": ["name"]
        })

        assert result.success is True
        assert result.output["result"][0] == {"name": "Alice"}

    @pytest.mark.asyncio
    async def test_list_map_template(self):
        """Should apply template to list items."""
        result = await execute_primitive("list.map", {
            "items": [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ],
            "template": "{name} is {age} years old"
        })

        assert result.success is True
        assert result.output["result"][0] == "Alice is 30 years old"

    @pytest.mark.asyncio
    async def test_list_reduce_sum(self):
        """Should sum values in list."""
        result = await execute_primitive("list.reduce", {
            "items": [
                {"value": 10},
                {"value": 20},
                {"value": 30}
            ],
            "field": "value",
            "operation": "sum"
        })

        assert result.success is True
        assert result.output["result"] == 60

    @pytest.mark.asyncio
    async def test_list_reduce_join(self):
        """Should join list values."""
        result = await execute_primitive("list.reduce", {
            "items": ["apple", "banana", "cherry"],
            "operation": "join",
            "separator": ", "
        })

        assert result.success is True
        assert result.output["result"] == "apple, banana, cherry"


class TestUnknownPrimitive:
    """Tests for unknown primitive handling."""

    @pytest.mark.asyncio
    async def test_unknown_primitive(self):
        """Should error for unknown primitive."""
        result = await execute_primitive("nonexistent.operation", {})

        assert result.success is False
        assert "Unknown primitive" in result.error
