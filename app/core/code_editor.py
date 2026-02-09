"""
Code editor utilities for YAML and CSS.

Provides Monaco editor integration, YAML validation, formatting, and
intelligent indentation fixing using widget schemas.
"""

import re
from io import StringIO
from pathlib import Path

from core.logger import error
from core.schema_fetcher import get_widget_key_hierarchy
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

SUPPORTED_LANGUAGES = ["yaml", "css", "json", "javascript", "html", "markdown"]


def _get_yaml_instance(preserve_quotes: bool = True) -> YAML:
    """Get a configured YAML parser."""
    y = YAML()
    y.preserve_quotes = preserve_quotes
    y.allow_unicode = False
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 120
    y.default_flow_style = False
    return y


def _get_widget_root_keys(widget_type: str | None) -> set[str]:
    """Get top-level option keys for a widget from schema."""
    if not widget_type:
        return set()

    try:
        hierarchy = get_widget_key_hierarchy(widget_type)
        if hierarchy and "_root" in hierarchy:
            root_info = hierarchy["_root"]
            # New format: {"type": "dict", "children": [...]}
            if isinstance(root_info, dict):
                return set(root_info.get("children", []))
            # Old format fallback: just a list
            return set(root_info)
    except ImportError:
        pass
    except Exception as e:
        error(f"Error getting widget schema: {e}")

    return set()


def _get_widget_key_hierarchy(widget_type: str | None) -> dict[str, dict]:
    """Get the full key hierarchy for a widget type from schema."""
    if not widget_type:
        return {}

    try:
        return get_widget_key_hierarchy(widget_type)
    except ImportError:
        pass
    except Exception as e:
        error(f"Error getting widget hierarchy: {e}")

    return {}


class CodeError:
    """A validation error with line and column info."""

    def __init__(self, line: int, column: int, message: str):
        self.line = line
        self.column = column
        self.message = message

    def __str__(self):
        return f"Line {self.line}, Col {self.column}: {self.message}"


YamlError = CodeError


def validate_yaml(text: str) -> tuple[bool, list[YamlError]]:
    """Check YAML for errors. Returns (is_valid, list_of_errors)."""
    errors = []

    if not text or not text.strip():
        return True, []

    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "\t" in line:
            errors.append(YamlError(i + 1, line.index("\t") + 1, "Tabs are not allowed, use spaces"))

    try:
        y = _get_yaml_instance()
        y.load(StringIO(text))
    except YAMLError as e:
        if hasattr(e, "problem_mark") and e.problem_mark:
            mark = e.problem_mark
            msg = str(e.problem) if hasattr(e, "problem") else str(e)
            errors.append(YamlError(mark.line + 1, mark.column + 1, msg))
        else:
            errors.append(YamlError(1, 1, str(e)))

    return len(errors) == 0, errors


def format_yaml(text: str, indent: int = 2) -> tuple[str, str | None]:
    """Format YAML with proper indentation. Returns (formatted_text, error)."""
    if not text or not text.strip():
        return text, None

    try:
        y = _get_yaml_instance()
        parsed = y.load(StringIO(text))

        if parsed is None:
            return "", None

        stream = StringIO()
        y.dump(parsed, stream)
        formatted = stream.getvalue()

        return formatted.rstrip() + "\n", None

    except YAMLError as e:
        error_msg = str(e)
        if hasattr(e, "problem_mark") and e.problem_mark:
            mark = e.problem_mark
            error_msg = f"Line {mark.line + 1}, Col {mark.column + 1}: {e.problem}"
        return text, error_msg
    except Exception as e:
        return text, str(e)


def fix_yaml_indentation(text: str, widget_type: str | None = None) -> tuple[str, str | None]:
    """
    Fix indentation from copy-paste using widget schema.

    When users paste widget options from docs, the indentation is often wrong.
    This uses the widget schema to figure out the proper nesting.

    Returns (fixed_text, error_or_none)
    """
    if not text or not text.strip():
        return text, None

    lines = text.split("\n")

    # Check if this is a full widget paste (has type: and options:)
    type_line = options_line = None
    options_indent = 0
    detected_widget_type = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        type_match = re.match(r'^type:\s*["\']?(\w+\.\w+)', stripped)
        if type_match:
            type_line = i
            detected_widget_type = type_match.group(1)
        if re.match(r"^(\s*)options:\s*$", line):
            options_line = i
            options_indent = len(line) - len(line.lstrip())
            break

    if widget_type is None and detected_widget_type:
        widget_type = detected_widget_type

    hierarchy = _get_widget_key_hierarchy(widget_type)
    root_info = hierarchy.get("_root", {})
    root_keys = set(root_info.get("children", [])) if isinstance(root_info, dict) else set()

    # If no schema hierarchy available, just fix tabs and validate
    if not hierarchy or not root_keys:
        fixed_lines = [line.replace("\t", "  ") for line in lines]
        fixed_text = "\n".join(fixed_lines)
        try:
            y = _get_yaml_instance()
            y.load(StringIO(fixed_text))
            return fixed_text, None
        except YAMLError as e:
            error_msg = str(e)
            if hasattr(e, "problem_mark") and e.problem_mark:
                mark = e.problem_mark
                error_msg = f"Line {mark.line + 1}, Col {mark.column + 1}: {e.problem}"
            return fixed_text, f"Remaining error: {error_msg}"

    if type_line is not None and options_line is not None:
        lines = _extract_options_lines(lines, options_line, options_indent)

    # Strip common leading indentation
    non_empty = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    if non_empty:
        min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
        if min_indent > 0:
            lines = [l[min_indent:] if l.strip() else l for l in lines]

    fixed_lines = []

    # Track context: (indent_level, key_name, is_list_parent)
    # is_list_parent means this key contains a list (like menu_list:)
    context_stack = [(0, "_root", False)]

    def get_key_info(key_name: str, parent_key: str = "") -> dict:
        """Get type info for a key. Returns {"type": ..., "children": [...]} or empty dict."""
        # Try composite key first (e.g., "providers.models")
        if parent_key:
            composite = f"{parent_key}.{key_name}"
            if composite in hierarchy:
                return hierarchy[composite]
        # Try direct key
        if key_name in hierarchy:
            return hierarchy[key_name]
        return {}

    def is_list_key(key_name: str, parent_key: str = "") -> bool:
        """Check if a key is a list type."""
        info = get_key_info(key_name, parent_key)
        return info.get("type") == "list"

    def get_children(schema_key: str) -> set[str]:
        """Get valid children for a schema key."""
        if schema_key in hierarchy:
            info = hierarchy[schema_key]
            if isinstance(info, dict):
                return set(info.get("children", []))
        return set()

    def is_valid_child(child_key: str, schema_key: str) -> bool:
        """Check if child_key is valid under schema_key."""
        children = get_children(schema_key)
        if child_key in children:
            return True
        # Also check composite keys
        for key in hierarchy:
            if "." in key and key.endswith(f".{schema_key}"):
                info = hierarchy[key]
                if isinstance(info, dict) and child_key in info.get("children", []):
                    return True
        return False

    def get_schema_for_list_items(parent_key: str) -> str:
        """Get the schema key that defines valid children for list items under parent_key."""
        # Check for composite key first (e.g., "providers.models")
        for key in hierarchy:
            if "." in key and key.endswith(f".{parent_key}"):
                return key
        return parent_key

    for i, line in enumerate(lines):
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            fixed_lines.append(line)
            continue

        line = line.replace("\t", "  ")
        is_list_item = stripped.startswith("-")

        if is_list_item:
            # Check if it's "- key: value" format (mapping in list)
            # But NOT flow style like "- {key: value}" or "- [item]"
            item_content = stripped[1:].strip()
            item_key = None
            is_flow_style = item_content.startswith("{") or item_content.startswith("[")
            if item_content and ":" in item_content and not is_flow_style:
                colon_pos = item_content.find(":")
                before_colon = item_content[:colon_pos]
                # Check colon is outside quotes
                if before_colon.count('"') % 2 == 0 and before_colon.count("'") % 2 == 0:
                    item_key = before_colon.strip()

            # Find the correct list parent context
            # Pop non-list-parent contexts, but also pop list parents if the item key doesn't belong there
            while len(context_stack) > 1:
                _, ctx_key, ctx_is_list = context_stack[-1]
                if not ctx_is_list:
                    context_stack.pop()
                elif item_key and not is_valid_child(item_key, ctx_key):
                    # This list item's key doesn't belong to this list - pop and try parent
                    context_stack.pop()
                else:
                    break

            current_indent, current_key, _ = context_stack[-1]
            # List items go at the list parent's indent level
            dash_indent = current_indent
            fixed_lines.append(" " * dash_indent + stripped)

            if item_key:
                after_colon = item_content[item_content.find(":") + 1 :].strip()
                has_value = bool(after_colon) and not after_colon.startswith("#")

                # Schema for list item children - get the right schema key
                schema_key = get_schema_for_list_items(current_key)

                # Push context for sibling keys in this list item
                # Indent is dash + 2 (aligned after "- ")
                context_stack.append((dash_indent + 2, schema_key, False))

                if not has_value:
                    # Key without value - use schema type info
                    key_is_list = is_list_key(item_key, schema_key)
                    context_stack.append((dash_indent + 4, item_key, key_is_list))
        else:
            # Regular key: value or key:
            is_key = ":" in stripped
            if is_key:
                key_name = stripped.split(":")[0].strip()
                after_colon = stripped[stripped.find(":") + 1 :].strip()
                has_value = bool(after_colon) and not after_colon.startswith("#")

                # Check if key belongs to current context
                current_indent, current_key, current_is_list = context_stack[-1]

                # Check if this key is a valid child of current context
                is_child_of_current = is_valid_child(key_name, current_key)

                if not current_is_list and is_child_of_current:
                    # Key is a sibling in current context (e.g., path after title, or models after provider)
                    fixed_lines.append(" " * current_indent + stripped)
                    if not has_value:
                        # Use schema type info to determine if this key starts a list
                        key_is_list = is_list_key(key_name, current_key)
                        context_stack.append((current_indent + 2, key_name, key_is_list))
                elif key_name in root_keys:
                    # Root level key - pop back to root
                    while len(context_stack) > 1:
                        context_stack.pop()
                    fixed_lines.append(stripped)
                    if not has_value:
                        # Use schema type info to determine if this key starts a list
                        key_is_list = is_list_key(key_name)
                        context_stack.append((2, key_name, key_is_list))
                else:
                    # Try to find proper parent in the context stack
                    found = False
                    for idx in range(len(context_stack) - 1, -1, -1):
                        ctx_indent, ctx_key, ctx_is_list = context_stack[idx]
                        if is_valid_child(key_name, ctx_key):
                            # Pop to this context
                            while len(context_stack) > idx + 1:
                                context_stack.pop()
                            fixed_lines.append(" " * ctx_indent + stripped)
                            if not has_value:
                                key_is_list = is_list_key(key_name, ctx_key)
                                context_stack.append((ctx_indent + 2, key_name, key_is_list))
                            found = True
                            break
                    if not found:
                        # Unknown key - use current indent
                        fixed_lines.append(" " * current_indent + stripped)
                        if not has_value:
                            context_stack.append((current_indent + 2, key_name, False))
            else:
                # Not a key - use current indent
                fixed_lines.append(" " * context_stack[-1][0] + stripped)

    fixed_text = "\n".join(fixed_lines)

    # Validate result
    try:
        y = _get_yaml_instance()
        y.load(StringIO(fixed_text))
        return fixed_text, None
    except YAMLError as e:
        error_msg = str(e)
        if hasattr(e, "problem_mark") and e.problem_mark:
            mark = e.problem_mark
            error_msg = f"Line {mark.line + 1}, Col {mark.column + 1}: {e.problem}"
        return fixed_text, f"Partial fix applied. Remaining error: {error_msg}"


def _extract_options_lines(lines: list, options_line: int, options_indent: int) -> list:
    """Extract and re-indent options content from full widget paste."""
    result = []
    expected_indent = options_indent + 2
    current_mapping_indent = None

    for line in lines[options_line + 1 :]:
        if not line.strip():
            result.append("")
            continue

        current_indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        is_key = ":" in stripped and not stripped.startswith("-")
        key_name = stripped.split(":")[0] if is_key else ""

        # Stop at type/name (past options block)
        if is_key and key_name in ("type", "name") and current_indent <= options_indent:
            break

        has_value = False
        if is_key:
            after_colon = stripped[stripped.find(":") + 1 :].strip()
            has_value = bool(after_colon) and not after_colon.startswith("#")

        # Determine if root-level key
        is_root = is_key and (current_indent == expected_indent or current_indent <= options_indent)
        if current_mapping_indent is not None and current_indent > current_mapping_indent:
            is_root = False

        if is_root:
            result.append(stripped)
            current_mapping_indent = current_indent if (is_key and not has_value) else None
        else:
            result.append("  " + stripped)

    return result


def parse_yaml(text: str) -> tuple[dict | None, str | None]:
    """Parse YAML text to dictionary."""
    if not text or not text.strip():
        return {}, None

    try:
        y = _get_yaml_instance()
        parsed = y.load(StringIO(text))
        if parsed is None:
            return {}, None
        if not isinstance(parsed, dict):
            return None, "YAML must be a mapping/dictionary"
        return dict(parsed), None
    except YAMLError as e:
        error_msg = str(e)
        if hasattr(e, "problem_mark") and e.problem_mark:
            mark = e.problem_mark
            error_msg = f"Line {mark.line + 1}, Col {mark.column + 1}: {e.problem}"
        return None, error_msg


def dict_to_yaml(data: dict, indent: int = 2) -> str:
    """Convert dictionary to YAML string."""
    if not data:
        return ""

    try:
        y = _get_yaml_instance()
        stream = StringIO()
        y.dump(data, stream)
        return stream.getvalue().rstrip()
    except Exception as e:
        error(f"Error converting dict to YAML: {e}")
        return str(data)


def get_code_editor_html_path() -> str:
    """Get the path to the code editor HTML file."""
    editor_dir = Path(__file__).parent / "editor"
    html_path = editor_dir / "code_editor.html"
    return str(html_path.resolve())


def get_code_editor_html_uri() -> str:
    """Get the file URI for the code editor HTML file."""
    path = get_code_editor_html_path()
    return Path(path).as_uri()


def extract_widget_options(parsed: dict, expected_type: str | None = None) -> tuple[dict | None, str | None]:
    """Extract widget options from parsed YAML dict.

    Args:
        parsed: Parsed YAML dictionary
        expected_type: Expected widget type for validation (e.g., "yasb.clock.ClockWidget")

    Returns:
        tuple: (options dict, error message or None)
    """
    if parsed is None:
        return {}, None

    # Case 1: Full widget definition with type and options at root
    if "type" in parsed and "options" in parsed:
        if expected_type and parsed["type"] != expected_type:
            return None, f"Widget type mismatch: expected '{expected_type}', got '{parsed['type']}'"
        return parsed.get("options", {}), None

    # Case 2: Named widget definition like "clock_1: {type: ..., options: ...}"
    if len(parsed) == 1:
        key = list(parsed.keys())[0]
        value = parsed[key]
        if isinstance(value, dict) and "type" in value and "options" in value:
            if expected_type and value["type"] != expected_type:
                return None, f"Widget type mismatch: expected '{expected_type}', got '{value['type']}'"
            return value.get("options", {}), None

    # Case 3: Just options (no type/options wrapper)
    return parsed, None
