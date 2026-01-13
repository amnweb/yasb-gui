"""
Tests for Schema Fetcher - Widget schema database management.

Tests schema parsing, hierarchy building, database operations.
"""

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from core.schema_fetcher import (
    _build_key_hierarchy,
    _extract_ast_value,
    _parse_validation_schema,
    get_all_widget_types,
    get_widget_key_hierarchy,
    get_widget_schema,
    load_schema_database,
    save_schema_database,
)


@pytest.fixture
def temp_schema_db(tmp_path, monkeypatch):
    """Create temporary schema database path."""
    db_path = tmp_path / "widget_schemas.json"
    monkeypatch.setattr("core.schema_fetcher.SCHEMA_DB_PATH", db_path)
    return db_path


@pytest.fixture
def sample_schema_db(temp_schema_db):
    """Create a sample schema database."""
    data = {
        "_meta": {"version": 1, "source": "test"},
        "widgets": {
            "yasb.clock.ClockWidget": {
                "hierarchy": {
                    "_root": {"type": "dict", "children": ["label", "format", "callbacks"]},
                    "callbacks": {"type": "dict", "children": ["on_left", "on_right"]},
                }
            },
            "yasb.weather.WeatherWidget": {
                "hierarchy": {
                    "_root": {"type": "dict", "children": ["api_key", "location"]},
                }
            },
        },
    }
    with open(temp_schema_db, "w") as f:
        json.dump(data, f)
    return temp_schema_db


# --- Database Operations ---


class TestDatabaseOperations:
    """Tests for schema database load/save."""

    def test_load_empty_database(self, temp_schema_db):
        """Should return empty dict when database doesn't exist."""
        result = load_schema_database()
        assert result == {}

    def test_load_existing_database(self, sample_schema_db):
        """Should load existing database."""
        result = load_schema_database()

        assert "_meta" in result
        assert "widgets" in result
        assert "yasb.clock.ClockWidget" in result["widgets"]

    def test_save_database(self, temp_schema_db):
        """Should save database to file."""
        data = {"_meta": {"version": 1}, "widgets": {"test.Widget": {}}}

        result = save_schema_database(data)

        assert result is True
        assert temp_schema_db.exists()

        with open(temp_schema_db) as f:
            saved = json.load(f)
        assert saved == data

    def test_save_creates_parent_directory(self, tmp_path, monkeypatch):
        """Should create parent directories if needed."""
        nested_path = tmp_path / "nested" / "dir" / "schemas.json"
        monkeypatch.setattr("core.schema_fetcher.SCHEMA_DB_PATH", nested_path)

        result = save_schema_database({"test": "data"})

        assert result is True
        assert nested_path.exists()


# --- Schema Querying ---


class TestSchemaQuerying:
    """Tests for querying schema data."""

    def test_get_widget_schema(self, sample_schema_db):
        """Should return schema for existing widget."""
        schema = get_widget_schema("yasb.clock.ClockWidget")

        assert schema is not None
        assert "hierarchy" in schema

    def test_get_widget_schema_missing(self, sample_schema_db):
        """Should return None for non-existent widget."""
        schema = get_widget_schema("yasb.nonexistent.Widget")
        assert schema is None

    def test_get_widget_key_hierarchy(self, sample_schema_db):
        """Should return hierarchy for existing widget."""
        hierarchy = get_widget_key_hierarchy("yasb.clock.ClockWidget")

        assert "_root" in hierarchy
        assert "label" in hierarchy["_root"]["children"]

    def test_get_widget_key_hierarchy_missing(self, sample_schema_db):
        """Should return empty dict for non-existent widget."""
        hierarchy = get_widget_key_hierarchy("yasb.nonexistent.Widget")
        assert hierarchy == {}

    def test_get_all_widget_types(self, sample_schema_db):
        """Should return list of all widget types."""
        types = get_all_widget_types()

        assert len(types) == 2
        assert "yasb.clock.ClockWidget" in types
        assert "yasb.weather.WeatherWidget" in types


# --- Validation Schema Parsing ---


class TestValidationParsing:
    """Tests for parsing VALIDATION_SCHEMA from Python code."""

    def test_parse_simple_schema(self):
        """Should parse simple validation schema."""
        code = """
VALIDATION_SCHEMA = {
    "label": {"type": "string", "default": "Clock"},
    "format": {"type": "string", "default": "%H:%M"},
}
"""
        result = _parse_validation_schema(code)

        assert result is not None
        assert "label" in result
        assert result["label"]["type"] == "string"

    def test_parse_nested_schema(self):
        """Should parse schema with nested dict."""
        code = """
VALIDATION_SCHEMA = {
    "callbacks": {
        "type": "dict",
        "schema": {
            "on_left": {"type": "string"},
            "on_right": {"type": "string"},
        }
    }
}
"""
        result = _parse_validation_schema(code)

        assert result is not None
        assert "callbacks" in result
        assert result["callbacks"]["type"] == "dict"
        assert "on_left" in result["callbacks"]["schema"]

    def test_parse_list_schema(self):
        """Should parse schema with list type."""
        code = """
VALIDATION_SCHEMA = {
    "items": {
        "type": "list",
        "schema": {"type": "dict", "schema": {"name": {"type": "string"}}}
    }
}
"""
        result = _parse_validation_schema(code)

        assert result is not None
        assert result["items"]["type"] == "list"

    def test_parse_annotated_assignment(self):
        """Should parse annotated assignment (VALIDATION_SCHEMA: dict = {...})."""
        code = """
VALIDATION_SCHEMA: dict = {
    "label": {"type": "string"},
}
"""
        result = _parse_validation_schema(code)

        assert result is not None
        assert "label" in result

    def test_parse_invalid_code(self):
        """Should return None for invalid Python code."""
        result = _parse_validation_schema("not valid python {{{{")
        assert result is None

    def test_parse_no_schema(self):
        """Should return None when VALIDATION_SCHEMA not found."""
        code = """
OTHER_VAR = {"key": "value"}
"""
        result = _parse_validation_schema(code)
        assert result is None


# --- Hierarchy Building ---


class TestHierarchyBuilding:
    """Tests for building key hierarchy from schema."""

    def test_simple_hierarchy(self):
        """Should build hierarchy for flat schema."""
        schema = {
            "label": {"type": "string"},
            "enabled": {"type": "boolean"},
        }
        result = _build_key_hierarchy(schema)

        assert "_root" in result
        assert "label" in result["_root"]["children"]
        assert "enabled" in result["_root"]["children"]

    def test_nested_dict_hierarchy(self):
        """Should build hierarchy for nested dicts."""
        schema = {
            "callbacks": {
                "type": "dict",
                "schema": {
                    "on_left": {"type": "string"},
                    "on_right": {"type": "string"},
                },
            }
        }
        result = _build_key_hierarchy(schema)

        assert "callbacks" in result
        assert result["callbacks"]["type"] == "dict"
        assert "on_left" in result["callbacks"]["children"]

    def test_list_of_dicts_hierarchy(self):
        """Should build hierarchy for list of dicts."""
        schema = {
            "menu_list": {
                "type": "list",
                "schema": {
                    "type": "dict",
                    "schema": {
                        "title": {"type": "string"},
                        "path": {"type": "string"},
                    },
                },
            }
        }
        result = _build_key_hierarchy(schema)

        assert "menu_list" in result
        assert result["menu_list"]["type"] == "list"
        assert "title" in result["menu_list"]["children"]

    def test_simple_list_hierarchy(self):
        """Should handle simple list (list of scalars)."""
        schema = {
            "margin": {
                "type": "list",
                "schema": {"type": "integer"},
            }
        }
        result = _build_key_hierarchy(schema)

        assert "margin" in result
        assert result["margin"]["type"] == "list"
        assert result["margin"]["children"] == []


# --- AST Value Extraction ---


class TestAstExtraction:
    """Tests for AST value extraction."""

    def test_extract_string(self):
        """Should extract string constants."""
        node = ast.Constant(value="test")
        assert _extract_ast_value(node) == "test"

    def test_extract_number(self):
        """Should extract numeric constants."""
        node = ast.Constant(value=42)
        assert _extract_ast_value(node) == 42

    def test_extract_boolean(self):
        """Should extract boolean constants."""
        node = ast.Constant(value=True)
        assert _extract_ast_value(node) is True

    def test_extract_list(self):
        """Should extract list values."""
        node = ast.List(elts=[ast.Constant(value=1), ast.Constant(value=2)])
        assert _extract_ast_value(node) == [1, 2]

    def test_extract_dict(self):
        """Should extract dict values."""
        node = ast.Dict(keys=[ast.Constant(value="key")], values=[ast.Constant(value="value")])
        assert _extract_ast_value(node) == {"key": "value"}

    def test_extract_negative_number(self):
        """Should extract negative numbers."""
        node = ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=5))
        assert _extract_ast_value(node) == -5
