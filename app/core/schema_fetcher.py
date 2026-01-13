"""
Widget schema fetching from YASB repository.

Downloads validation schemas from the YASB repo and builds a local database
of widget options for validation and auto-fixing indentation.
"""

import ast
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from core.constants import SCHEMA_DB_PATH
from core.errors import get_friendly_error_message
from core.logger import error, info

GITHUB_ZIP_URL = "https://github.com/amnweb/yasb/archive/refs/heads/main.zip"
GITHUB_API_URL = "https://api.github.com/repos/amnweb/yasb"
WIDGETS_VALIDATION_PATH = "yasb-main/src/core/validation/widgets"
WIDGETS_DOCS_PATH = "yasb-main/docs/widgets"


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


def _get_repo_size() -> int:
    """Get repo size from GitHub API (helps estimate download size)."""
    try:
        req = urllib.request.Request(GITHUB_API_URL, headers={"User-Agent": "YASB-Config/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.load(response)
            return data.get("size", 0) * 1024
    except Exception:
        return 0


def _download_zip(progress_callback=None) -> bytes | None:
    try:
        info(f"Downloading repository zip from {GITHUB_ZIP_URL}...")
        req = urllib.request.Request(GITHUB_ZIP_URL, headers={"User-Agent": "YASB-Config/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get("Content-Length", 0))

            # If no Content-Length (common with GitHub archives), try API
            if total_size == 0:
                total_size = _get_repo_size()

            downloaded = 0
            chunks = []

            info(f"Starting download. Total size: {total_size} bytes")

            while chunk := response.read(65536):
                chunks.append(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    if total_size > 0:
                        progress = int((downloaded / total_size) * 100)
                        progress_callback(progress, 100, f"Downloading... {downloaded // 1024} KB")
                    else:
                        # Unknown size - send 0 as total
                        progress_callback(downloaded, 0, f"Downloading... {downloaded // 1024} KB")

            info("Download complete.")
            return b"".join(chunks)
    except urllib.error.URLError as e:
        error(f"Network error during download: {e.reason if hasattr(e, 'reason') else e}")
    except Exception as e:
        error(f"Failed to download repository: {e}")
    return None


def _extract_from_zip(zip_data: bytes) -> tuple[dict[str, str], dict[str, str]]:
    """Extract validation schemas and widget types from the downloaded zip."""
    validation_files = {}
    widget_types = {}

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            file_list = zf.namelist()

            for name in file_list:
                if name.startswith(WIDGETS_VALIDATION_PATH) and name.endswith(".py"):
                    relative = name[len(WIDGETS_VALIDATION_PATH) + 1 :]
                    if "/" in relative:
                        content = zf.read(name).decode("utf-8")
                        validation_files[relative] = content

                elif name.startswith(WIDGETS_DOCS_PATH) and name.endswith(".md"):
                    content = zf.read(name).decode("utf-8")
                    match = re.search(r"type:\s*['\"]?([\w]+\.[\w.]+)['\"]?", content)
                    if match:
                        full_type = match.group(1)
                        short_path = full_type.rsplit(".", 1)[0]
                        widget_types[short_path] = full_type

    except Exception as e:
        error(f"Failed to extract files: {e}")

    return validation_files, widget_types


def _extract_ast_value(node: ast.AST) -> Any:
    """Convert AST node to Python value."""
    if isinstance(node, ast.Dict):
        return {_extract_ast_value(k): _extract_ast_value(v) for k, v in zip(node.keys, node.values) if k is not None}
    elif isinstance(node, ast.List):
        return [_extract_ast_value(el) for el in node.elts]
    elif isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Name):
        return f"${{{node.id}}}"
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = _extract_ast_value(node.operand)
        return -val if isinstance(val, (int, float)) else None
    return None


def _parse_validation_schema(content: str) -> dict | None:
    """Parse VALIDATION_SCHEMA from Python file content."""
    try:
        for node in ast.walk(ast.parse(content)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "VALIDATION_SCHEMA":
                        return _extract_ast_value(node.value)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "VALIDATION_SCHEMA":
                    return _extract_ast_value(node.value) if node.value else None
    except Exception as e:
        error(f"Error parsing validation file: {e}")
    return None


def _build_key_hierarchy(schema: dict, parent_key: str = "") -> dict[str, dict]:
    """Build parent -> {type, children} mapping from schema.

    Returns a dict where each key maps to:
    - {"type": "dict"|"list"|"scalar", "children": [...]} for keys with nested structure
    - Just the key name in _root's children list for simple tracking
    """
    result = {}
    children = []

    for key, value in schema.items():
        children.append(key)
        if not isinstance(value, dict):
            continue

        full_key = f"{parent_key}.{key}" if parent_key else key
        inner_schema = value.get("schema")

        value_type = value.get("type")
        is_dict = value_type == "dict" or (isinstance(value_type, list) and "dict" in value_type)
        is_list = value_type == "list" or (isinstance(value_type, list) and "list" in value_type)

        if is_dict and inner_schema and isinstance(inner_schema, dict):
            # Dict type - children are direct properties
            nested = _build_key_hierarchy(inner_schema, full_key)
            result.update(nested)
            result[full_key] = {"type": "dict", "children": list(inner_schema.keys())}
        elif is_list:
            if inner_schema and inner_schema.get("type") == "dict" and "schema" in inner_schema:
                # List of dicts - children are properties of each list item
                item_schema = inner_schema["schema"]
                nested = _build_key_hierarchy(item_schema, full_key)
                result.update(nested)
                result[full_key] = {"type": "list", "children": list(item_schema.keys())}
            else:
                # Simple list (list of scalars)
                result[full_key] = {"type": "list", "children": []}

    result[parent_key or "_root"] = {"type": "dict", "children": children}
    return result


def fetch_all_schemas(progress_callback=None) -> dict[str, Any]:
    """Fetch all widget schemas from GitHub."""
    schemas = {"_meta": {"version": 1, "source": "github.com/amnweb/yasb"}, "widgets": {}}

    zip_data = _download_zip(progress_callback)
    if not zip_data:
        return schemas

    if progress_callback:
        progress_callback(100, 100, "Extracting files...")

    validation_files, widget_types = _extract_from_zip(zip_data)

    for path, content in validation_files.items():
        parts = path.replace(".py", "").split("/")
        if len(parts) != 2:
            continue

        short_path = f"{parts[0]}.{parts[1]}"
        full_type = widget_types.get(short_path)
        if not full_type:
            continue

        if progress_callback:
            progress_callback(100, 100, f"Processing {full_type}...")

        validation_schema = _parse_validation_schema(content)
        if validation_schema:
            hierarchy = _build_key_hierarchy(validation_schema)
            schemas["widgets"][full_type] = {"hierarchy": hierarchy}

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
