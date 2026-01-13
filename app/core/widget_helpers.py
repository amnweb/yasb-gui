"""
Utilities for working with widget configs.

Helps parse and extract widget options from YAML, handling different
formats users might paste (plain options, full widget config, etc.).
"""

import copy
from io import StringIO

from core.logger import error
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError


def _get_yaml() -> YAML:
    """Get configured YAML instance."""
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 120
    y.default_flow_style = False
    return y


def parse_yaml(text: str) -> tuple[dict | None, str | None]:
    """Parse YAML text into a dict. Returns (dict, None) or (None, error)."""
    if not text or not text.strip():
        return {}, None

    try:
        y = _get_yaml()
        parsed = y.load(StringIO(text))
        if parsed is None:
            return {}, None
        if not isinstance(parsed, dict):
            return None, "YAML must be a dictionary"
        return dict(parsed), None
    except YAMLError as e:
        if hasattr(e, "problem_mark") and e.problem_mark:
            mark = e.problem_mark
            return None, f"Line {mark.line + 1}, Column {mark.column + 1}: {getattr(e, 'problem', str(e))}"
        return None, str(e)


def extract_widget_options(data: dict, expected_type: str | None = None) -> tuple[dict, str | None]:
    """
    Extract just the options part from a widget config.

    Users sometimes paste the full widget definition when they should only paste
    the options. This handles different formats and extracts the options dict.

    Returns (options_dict, error_msg or None)
    """
    if not data:
        return data, None

    pasted_type = None

    # Check if it has type + options keys (widget definition pattern)
    if "type" in data and "options" in data:
        pasted_type = data.get("type")
        # If there are OTHER keys besides type/options, it's likely malformed paste
        extra_keys = set(data.keys()) - {"type", "options"}
        if extra_keys:
            return (
                None,
                f'Invalid widget structure. Found extra keys at root level: {", ".join(sorted(extra_keys))}. Check your YAML indentation or try to fix from the context menu "Fix Indentation" option.',
            )

        # Validate type matches if expected_type provided
        if expected_type and pasted_type and pasted_type != expected_type:
            pasted_short = pasted_type.split(".")[-1] if "." in pasted_type else pasted_type
            expected_short = expected_type.split(".")[-1] if "." in expected_type else expected_type
            return None, f"Widget type mismatch. You pasted config for '{pasted_short}' but editing '{expected_short}'."

        return dict(data.get("options") or {}), None

    # Check if wrapped in widget name: {name: {type: ..., options: ...}}
    if len(data) == 1:
        key = list(data.keys())[0]
        value = list(data.values())[0]
        if isinstance(value, dict) and "type" in value and "options" in value:
            pasted_type = value.get("type")
            # Check for extra keys in the nested dict too
            extra_keys = set(value.keys()) - {"type", "options"}
            if extra_keys:
                return (
                    None,
                    f"Invalid widget structure under '{key}'. Found extra keys: {', '.join(sorted(extra_keys))}. Check your YAML indentation.",
                )

            # Validate type matches if expected_type provided
            if expected_type and pasted_type and pasted_type != expected_type:
                pasted_short = pasted_type.split(".")[-1] if "." in pasted_type else pasted_type
                expected_short = expected_type.split(".")[-1] if "." in expected_type else expected_type
                return (
                    None,
                    f"Widget type mismatch. You pasted config for '{pasted_short}' but editing '{expected_short}'.",
                )

            return dict(value.get("options") or {}), None
        # Single key but NOT a valid widget definition - likely malformed paste
        if isinstance(value, dict) and ("type" in value or "options" in value):
            return None, f"Invalid widget structure under '{key}'. Expected both 'type' and 'options' keys."

    # Check for suspicious patterns that indicate malformed widget paste
    # If any value contains 'type' key, user likely pasted incorrectly
    for key, value in data.items():
        if isinstance(value, dict) and "type" in value:
            return (
                None,
                f"Invalid structure: '{key}' contains a 'type' field. Did you paste a full widget definition incorrectly?",
            )

    # Plain options dict - use as-is
    return data, None


def move_widget_order(config_manager, bar_name, widget_name, position, direction):
    """Move widget up or down in the list."""
    try:
        bar = config_manager.get_bar(bar_name)
        if not bar:
            return False

        widgets = bar.get("widgets", {})
        if position not in widgets:
            return False

        widget_list = widgets[position]
        if widget_name not in widget_list:
            return False

        idx = widget_list.index(widget_name)
        new_idx = idx + direction

        if 0 <= new_idx < len(widget_list):
            widget_list[idx], widget_list[new_idx] = widget_list[new_idx], widget_list[idx]
            return True
        return False
    except Exception as e:
        error(f"Move widget order error: {e}", exc_info=True)
        return False


def move_widget(config_manager, bar_name, widget_name, old_position, new_position):
    """Move widget to a different position."""
    try:
        bar = config_manager.get_bar(bar_name)
        if not bar:
            return False

        widgets = bar.get("widgets", {})

        if old_position in widgets and widget_name in widgets[old_position]:
            widgets[old_position].remove(widget_name)

        if new_position not in widgets:
            widgets[new_position] = []
        widgets[new_position].append(widget_name)

        return True
    except Exception as e:
        error(f"Move widget error: {e}", exc_info=True)
        return False


def duplicate_widget(config_manager, bar_name, widget_name, position):
    """Duplicate a widget."""
    try:
        original_name = widget_name[1:] if widget_name.startswith("#") else widget_name
        widget = config_manager.get_widget(original_name)
        if not widget:
            return None

        # Create unique name
        existing = config_manager.get_widgets()
        counter = 1
        new_name = f"{original_name}_{counter}"
        while new_name in existing:
            counter += 1
            new_name = f"{original_name}_{counter}"

        config_manager.config["widgets"][new_name] = copy.deepcopy(widget)

        # Add to bar after original
        bar = config_manager.get_bar(bar_name)
        if bar:
            widgets = bar.get("widgets", {})
            if position not in widgets:
                widgets[position] = []
            idx = (
                widgets[position].index(widget_name) + 1 if widget_name in widgets[position] else len(widgets[position])
            )
            widgets[position].insert(idx, new_name)

        return new_name
    except Exception as e:
        error(f"Duplicate widget error: {e}", exc_info=True)
        return None


def disable_widget(config_manager, bar_name, widget_name, position):
    """Disable a widget by removing it from the bar (keeps config)."""
    try:
        bar = config_manager.get_bar(bar_name)
        if not bar:
            return False

        widgets = bar.get("widgets", {})
        if position in widgets and widget_name in widgets[position]:
            widgets[position].remove(widget_name)
            return True
        return False
    except Exception as e:
        error(f"Disable widget error: {e}", exc_info=True)
        return False


def delete_widget(config_manager, bar_name, widget_name, position):
    """Delete a widget from bar and config."""
    try:
        if not bar_name:
            return False

        bar = config_manager.get_bar(bar_name)
        if bar:
            widgets = bar.get("widgets", {})
            if position in widgets and widget_name in widgets[position]:
                widgets[position].remove(widget_name)

        config_manager.delete_widget(widget_name)
        return True
    except Exception as e:
        error(f"Delete widget error: {e}", exc_info=True)
        return False


def enable_widget(config_manager, bar_name, widget_name, position):
    """Enable a widget by adding it to a bar position."""
    try:
        bar = config_manager.get_bar(bar_name)
        if not bar:
            return False

        widgets = bar.get("widgets", {})
        if position not in widgets:
            widgets[position] = []

        widgets[position].append(widget_name)
        return True
    except Exception as e:
        error(f"Enable widget error: {e}", exc_info=True)
        return False


def delete_disabled_widget(config_manager, widget_name):
    """Delete a disabled widget from config entirely."""
    try:
        config_manager.delete_widget(widget_name)
        return True
    except Exception as e:
        error(f"Delete disabled widget error: {e}", exc_info=True)
        return False


def save_widget_options(config_manager, widget_name, options_text):
    """Save widget options from YAML text.

    Returns:
        tuple: (success: bool, error_message: str | None)
    """
    try:
        widget = config_manager.get_widget(widget_name)
        if not widget:
            return False, "Widget not found"

        # Get the widget's expected type for validation
        expected_type = widget.get("type")

        parsed, err = parse_yaml(options_text)
        if err:
            return False, err

        # Extract options if user pasted full widget definition, validate type matches
        options, extract_err = extract_widget_options(parsed, expected_type)
        if extract_err:
            return False, extract_err

        widget["options"] = options
        return True, None
    except Exception as e:
        error(f"Save widget options error: {e}", exc_info=True)
        return False, str(e)


def add_widget_to_bar(config_manager, bar_name, widget_info, position):
    """Add a widget to the selected bar."""
    try:
        if not bar_name:
            return None

        bar = config_manager.get_bar(bar_name)
        if not bar:
            return None

        # Create unique name
        base_name = widget_info["id"]
        existing = config_manager.get_widgets()
        name = base_name
        counter = 1
        while name in existing:
            name = f"{base_name}_{counter}"
            counter += 1

        if "widgets" not in config_manager.config:
            config_manager.config["widgets"] = {}

        config_manager.config["widgets"][name] = {
            "type": widget_info["type_path"],
            "options": widget_info["defaults"].copy() if widget_info["defaults"] else {},
        }

        if "widgets" not in bar:
            bar["widgets"] = {"left": [], "center": [], "right": []}
        if position not in bar["widgets"]:
            bar["widgets"][position] = []

        bar["widgets"][position].append(name)
        return name
    except Exception as e:
        error(f"Add widget error: {e}", exc_info=True)
        return None
