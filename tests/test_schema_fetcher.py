"""
Tests for Schema Fetcher - Widget schema database management.

Tests schema parsing, hierarchy building, database operations.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from core.schema_fetcher import (
    _build_key_hierarchy,
    _extract_widget_option_schemas,
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


# --- JSON Schema Extraction ---


class TestJsonSchemaExtraction:
    """Tests for extracting widget schemas from JSON schema."""

    def test_extract_widget_options_from_schema(self):
        """Should extract widget option schemas from widgets anyOf."""
        schema = {
            "$defs": {
                "SampleConfig": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}},
                },
                "SampleEntry": {
                    "type": "object",
                    "properties": {
                        "type": {"const": "yasb.sample.SampleWidget"},
                        "options": {"$ref": "#/$defs/SampleConfig"},
                    },
                },
            },
            "properties": {"widgets": {"additionalProperties": {"anyOf": [{"$ref": "#/$defs/SampleEntry"}]}}},
        }

        result = _extract_widget_option_schemas(schema)

        assert "yasb.sample.SampleWidget" in result
        assert result["yasb.sample.SampleWidget"]["type"] == "object"


# --- Hierarchy Building ---


class TestHierarchyBuilding:
    """Tests for building key hierarchy from schema."""

    def test_simple_hierarchy(self):
        """Should build hierarchy for flat schema."""
        schema = {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "enabled": {"type": "boolean"},
            },
        }
        result = _build_key_hierarchy(schema)

        assert "_root" in result
        assert "label" in result["_root"]["children"]
        assert "enabled" in result["_root"]["children"]

    def test_nested_dict_hierarchy(self):
        """Should build hierarchy for nested dicts."""
        schema = {
            "type": "object",
            "properties": {
                "callbacks": {
                    "type": "object",
                    "properties": {
                        "on_left": {"type": "string"},
                        "on_right": {"type": "string"},
                    },
                }
            },
        }
        result = _build_key_hierarchy(schema)

        assert "callbacks" in result
        assert result["callbacks"]["type"] == "dict"
        assert "on_left" in result["callbacks"]["children"]

    def test_list_of_dicts_hierarchy(self):
        """Should build hierarchy for list of dicts."""
        schema = {
            "type": "object",
            "properties": {
                "menu_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "path": {"type": "string"},
                        },
                    },
                }
            },
        }
        result = _build_key_hierarchy(schema)

        assert "menu_list" in result
        assert result["menu_list"]["type"] == "list"
        assert "title" in result["menu_list"]["children"]

    def test_simple_list_hierarchy(self):
        """Should handle simple list (list of scalars)."""
        schema = {
            "type": "object",
            "properties": {
                "margin": {
                    "type": "array",
                    "items": {"type": "integer"},
                }
            },
        }
        result = _build_key_hierarchy(schema)

        assert "margin" in result
        assert result["margin"]["type"] == "list"
        assert result["margin"]["children"] == []


# --- JSON Schema Variants ---


class TestJsonSchemaVariants:
    """Tests for anyOf handling in JSON schema."""

    def test_anyof_nullable_object(self):
        """Should use the object branch when nullable is present."""
        schema = {
            "type": "object",
            "properties": {
                "label": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "null"},
                    ]
                },
                "callbacks": {
                    "anyOf": [
                        {"type": "null"},
                        {"type": "object", "properties": {"on_left": {"type": "string"}}},
                    ]
                },
            },
        }
        result = _build_key_hierarchy(schema)

        assert "callbacks" in result
        assert result["callbacks"]["type"] == "dict"
