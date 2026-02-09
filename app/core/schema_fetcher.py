"""
Widget schema fetching from YASB JSON schema.

Downloads the JSON schema from the YASB repo and builds a local database
of widget options for validation and auto-fixing indentation.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from core.constants import SCHEMA_DB_PATH
from core.errors import get_friendly_error_message
from core.logger import error, info

SCHEMA_JSON_URL = "https://raw.githubusercontent.com/amnweb/yasb/refs/heads/main/schema.json"


def get_schema_db_path() -> Path:
    return SCHEMA_DB_PATH


def is_database_valid() -> bool:
    db = load_schema_database()
    return bool(db.get("widgets"))


def load_schema_database() -> dict[str, Any]:
    try:
        if SCHEMA_DB_PATH.exists():
            with open(SCHEMA_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        error(f"Failed to load schema database: {e}")
    return {}


def save_schema_database(schemas: dict[str, Any]) -> bool:
    try:
        SCHEMA_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEMA_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(schemas, f, indent=2)
        return True
    except Exception as e:
        error(f"Failed to save schema database: {e}")
        return False


def _download_schema_json(progress_callback=None) -> dict[str, Any] | None:
    try:
        info(f"Downloading JSON schema from {SCHEMA_JSON_URL}...")
        req = urllib.request.Request(SCHEMA_JSON_URL, headers={"User-Agent": "YASB-Config/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunks = []

            while chunk := response.read(65536):
                chunks.append(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    if total_size > 0:
                        progress = int((downloaded / total_size) * 100)
                        progress_callback(progress, 100, f"Downloading... {downloaded // 1024} KB")
                    else:
                        progress_callback(downloaded, 0, f"Downloading... {downloaded // 1024} KB")

            info("Schema download complete.")
            return json.loads(b"".join(chunks))
    except urllib.error.URLError as e:
        error(f"Network error during download: {e.reason if hasattr(e, 'reason') else e}")
    except Exception as e:
        error(f"Failed to download schema: {e}")
    return None


def _resolve_ref(ref: str, defs: dict[str, Any]) -> dict[str, Any] | None:
    if not ref.startswith("#/$defs/"):
        return None
    name = ref.split("/", 2)[2]
    return defs.get(name)


def _schema_is_object(schema: dict[str, Any]) -> bool:
    schema_type = schema.get("type")
    return schema_type == "object" or "properties" in schema


def _schema_is_array(schema: dict[str, Any]) -> bool:
    schema_type = schema.get("type")
    return schema_type == "array" or "items" in schema


def _schema_is_null(schema: dict[str, Any]) -> bool:
    schema_type = schema.get("type")
    if schema_type == "null":
        return True
    enum_values = schema.get("enum")
    return isinstance(enum_values, list) and len(enum_values) == 1 and enum_values[0] is None


def _merge_schema_nodes(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    properties = dict(base.get("properties", {}))
    properties.update(extra.get("properties", {}))
    if properties:
        merged["properties"] = properties
    for key, value in extra.items():
        if key == "properties":
            continue
        merged[key] = value
    return merged


def _resolve_schema_node(schema: dict[str, Any], defs: dict[str, Any], seen: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}

    seen = seen or set()
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            return {}
        seen.add(ref)
        resolved = _resolve_ref(ref, defs)
        return _resolve_schema_node(resolved or {}, defs, seen)

    if "allOf" in schema:
        merged = {}
        for part in schema.get("allOf", []):
            merged = _merge_schema_nodes(merged, _resolve_schema_node(part, defs, seen))
        remainder = {k: v for k, v in schema.items() if k != "allOf"}
        return _merge_schema_nodes(merged, remainder)

    if "anyOf" in schema or "oneOf" in schema:
        options = schema.get("anyOf") or schema.get("oneOf") or []
        best = _choose_schema_variant(options, defs, seen)
        remainder = {k: v for k, v in schema.items() if k not in ("anyOf", "oneOf")}
        return _merge_schema_nodes(best, remainder)

    return schema


def _choose_schema_variant(options: list[dict[str, Any]], defs: dict[str, Any], seen: set[str]) -> dict[str, Any]:
    for option in options:
        resolved = _resolve_schema_node(option, defs, seen.copy())
        if _schema_is_object(resolved) or _schema_is_array(resolved):
            return resolved
    for option in options:
        resolved = _resolve_schema_node(option, defs, seen.copy())
        if not _schema_is_null(resolved):
            return resolved
    if options:
        return _resolve_schema_node(options[0], defs, seen.copy())
    return {}


def _build_key_hierarchy(schema: dict, defs: dict[str, Any] | None = None, parent_key: str = "") -> dict[str, dict]:
    """Build parent -> {type, children} mapping from JSON schema objects."""
    defs = defs or {}
    resolved = _resolve_schema_node(schema, defs)
    properties = resolved.get("properties", {}) if isinstance(resolved, dict) else {}

    result: dict[str, dict] = {}
    children: list[str] = []

    for key, value in properties.items():
        children.append(key)
        if not isinstance(value, dict):
            continue

        full_key = f"{parent_key}.{key}" if parent_key else key
        nested_schema = _resolve_schema_node(value, defs)

        if _schema_is_object(nested_schema):
            nested_props = nested_schema.get("properties", {})
            nested = _build_key_hierarchy(nested_schema, defs, full_key)
            result.update(nested)
            result[full_key] = {"type": "dict", "children": list(nested_props.keys())}
            continue

        if _schema_is_array(nested_schema):
            item_schema = _resolve_schema_node(nested_schema.get("items", {}), defs)
            if _schema_is_object(item_schema):
                item_props = item_schema.get("properties", {})
                nested = _build_key_hierarchy(item_schema, defs, full_key)
                result.update(nested)
                result[full_key] = {"type": "list", "children": list(item_props.keys())}
            else:
                result[full_key] = {"type": "list", "children": []}

    result[parent_key or "_root"] = {"type": "dict", "children": children}
    return result


def _extract_widget_option_schemas(schema_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defs = schema_json.get("$defs", {})
    widgets_schema = schema_json.get("properties", {}).get("widgets", {})
    additional_props = widgets_schema.get("additionalProperties", {})
    entries = additional_props.get("anyOf", [])

    widget_schemas: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_schema = _resolve_schema_node(entry, defs)
        props = entry_schema.get("properties", {}) if isinstance(entry_schema, dict) else {}

        type_schema = _resolve_schema_node(props.get("type", {}), defs)
        widget_type = type_schema.get("const")
        if not widget_type:
            enum_values = type_schema.get("enum", [])
            if isinstance(enum_values, list) and len(enum_values) == 1:
                widget_type = enum_values[0]

        options_schema = _resolve_schema_node(props.get("options", {}), defs)
        if widget_type and options_schema:
            widget_schemas[widget_type] = options_schema

    return widget_schemas


def fetch_all_schemas(progress_callback=None) -> dict[str, Any]:
    """Fetch all widget schemas from GitHub."""
    schemas = {"_meta": {"version": 1, "source": SCHEMA_JSON_URL}, "widgets": {}}

    schema_json = _download_schema_json(progress_callback)
    if not schema_json:
        return schemas

    defs = schema_json.get("$defs", {})
    widget_options = _extract_widget_option_schemas(schema_json)
    total = len(widget_options)

    for index, (widget_type, options_schema) in enumerate(widget_options.items(), start=1):
        if progress_callback:
            progress_callback(index, total, f"Processing {widget_type}...")

        hierarchy = _build_key_hierarchy(options_schema, defs)
        schemas["widgets"][widget_type] = {"hierarchy": hierarchy}

    if progress_callback:
        progress_callback(100, 100, "Complete!")

    return schemas


def update_schema_database(progress_callback=None) -> tuple[bool, str]:
    """Update the local schema database from GitHub."""
    try:
        info("Starting schema database update...")
        schemas = fetch_all_schemas(progress_callback)

        widget_count = len(schemas.get("widgets", {}))
        if widget_count == 0:
            error("Schema update finished but 0 widgets were found/parsed. Check logs for regex/extraction failures.")
            return False, "No schemas found. Check your internet connection."

        schemas["_meta"]["updated"] = datetime.now().isoformat()

        if save_schema_database(schemas):
            info(f"Schema database updated with {widget_count} widgets")
            return True, f"Successfully updated {widget_count} widget schemas"
        return False, "Failed to save schema database"
    except Exception as e:
        error(f"Schema update failed: {e}")
        return False, get_friendly_error_message(e)


def get_widget_schema(widget_type: str) -> dict | None:
    """Get schema for a widget type."""
    return load_schema_database().get("widgets", {}).get(widget_type)


def get_widget_key_hierarchy(widget_type: str) -> dict[str, dict]:
    """Get key hierarchy for a widget type.

    Returns dict where each key maps to {"type": "dict"|"list", "children": [...]}.
    """
    schema = get_widget_schema(widget_type)
    return schema.get("hierarchy", {}) if schema else {}


def get_all_widget_types() -> list[str]:
    """Get list of all known widget types."""
    return list(load_schema_database().get("widgets", {}).keys())
