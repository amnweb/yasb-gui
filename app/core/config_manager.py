"""
Config management - loading, saving, and modifying YASB configs.

Handles reading/writing config.yaml and styles.css, manages bars and widgets,
tracks changes, and provides import/export functionality.
"""

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from core.constants import APP_VERSION, GITHUB_YASB_GUI
from core.logger import error
from ruamel.yaml import YAML


def _normalize(obj):
    """Convert ruamel.yaml types to plain Python for comparison."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    type_name = type(obj).__name__
    if type_name in ("ScalarBoolean", "bool"):
        return bool(obj)
    if type_name in ("ScalarInt", "int"):
        return int(obj)
    if type_name in ("ScalarFloat", "float"):
        return float(obj)
    return str(obj)


def _get_yaml() -> YAML:
    """Get a configured YAML instance."""
    y = YAML()
    y.preserve_quotes = True
    y.allow_unicode = False
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 120
    y.default_flow_style = False
    return y


_ROOT_KEY_ORDER = [
    "watch_stylesheet",
    "watch_config",
    "debug",
    "update_check",
    "komorebi",
    "glazewm",
    "bars",
    "widgets",
]


def _is_empty_value(value: Any) -> bool:
    """Check if a value is empty and should be removed."""
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, dict):
        return all(_is_empty_value(v) for v in value.values())
    return False


def _clean_config(data: dict) -> None:
    """Remove empty values and convert numeric strings to int."""
    if not isinstance(data, dict):
        return

    keys_to_remove = []
    for key, value in list(data.items()):
        if isinstance(value, dict):
            _clean_config(value)
            if _is_empty_value(value):
                keys_to_remove.append(key)
        elif isinstance(value, str):
            if value == "":
                keys_to_remove.append(key)
            elif value.isdigit():
                # Convert pure numeric strings to int (e.g., "500" -> 500)
                data[key] = int(value)
        elif _is_empty_value(value):
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del data[key]


def _sort_root_keys(data: dict) -> dict:
    """Sort root-level keys in preferred order."""
    sorted_data = {}
    # Add keys in preferred order first
    for key in _ROOT_KEY_ORDER:
        if key in data:
            sorted_data[key] = data[key]
    # Add any remaining keys not in the list
    for key in data:
        if key not in sorted_data:
            sorted_data[key] = data[key]
    return sorted_data


class ConfigManager:
    """Manages YASB config files."""

    def __init__(self):
        self._config: dict[str, Any] = {}
        self._original_config: str = "{}"  # JSON snapshot for change detection
        self._original_styles: str = ""  # Snapshot for change detection
        self._config_path: str = ""
        self._styles_path: str = ""
        self._init_paths()

    def _init_paths(self):
        """Set up config file paths."""
        config_home = os.getenv("YASB_CONFIG_HOME", ".config\\yasb")
        self._config_dir = os.path.join(Path.home(), config_home)
        self._config_path = os.path.join(self._config_dir, "config.yaml")
        self._styles_path = os.path.join(self._config_dir, "styles.css")

    def is_config_valid(self) -> tuple[bool, str]:
        """Check if YASB config files exist. Returns (is_valid, what's_missing)."""
        if not os.path.isdir(self._config_dir):
            return False, "config_folder"
        if not os.path.isfile(self._config_path):
            return False, "config_file"
        if not os.path.isfile(self._styles_path):
            return False, "styles_file"
        return True, ""

    @property
    def config_path(self) -> str:
        return self._config_path

    @property
    def styles_path(self) -> str:
        return self._styles_path

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def load_config(self) -> dict[str, Any]:
        """Load config from file (or create default if missing)."""
        if not os.path.isfile(self._config_path):
            self._config = self._get_default_config()
            self.save_config()
            self._original_config = json.dumps(_normalize(self._config), sort_keys=True)
            return self._config

        with open(self._config_path, "r", encoding="utf-8") as f:
            y = _get_yaml()
            self._config = y.load(f) or {}

        self._original_config = json.dumps(_normalize(self._config), sort_keys=True)
        return self._config

    def save_config(self) -> bool:
        """Write config to file."""
        try:
            _clean_config(self._config)
            sorted_config = _sort_root_keys(self._config)

            with open(self._config_path, "w", encoding="utf-8") as f:
                f.write(
                    "# yaml-language-server: $schema=https://raw.githubusercontent.com/amnweb/yasb/main/schema.json\n\n"
                )
                f.write(f"# Generated by YASB GUI v{APP_VERSION}\n")
                f.write(f"# Last edited: {datetime.now().strftime('%b %d, %Y %H:%M')}\n")
                f.write(f"# {GITHUB_YASB_GUI}\n\n")

                y = _get_yaml()
                y.dump(sorted_config, f)

            self._original_config = json.dumps(_normalize(self._config), sort_keys=True)
            return True
        except Exception as e:
            error(f"Error saving config: {e}")
            return False

    def has_config_changed(self) -> bool:
        """Check if config was modified since loading."""
        current = json.dumps(_normalize(self._config), sort_keys=True)
        return current != self._original_config

    def load_styles(self) -> str:
        """Load CSS from styles.css."""
        if not os.path.isfile(self._styles_path):
            self._original_styles = ""
            return ""
        with open(self._styles_path, "r", encoding="utf-8") as f:
            content = f.read()
            self._original_styles = content
            return content

    def save_styles(self, content: str) -> bool:
        """Write CSS to styles.css."""
        try:
            with open(self._styles_path, "w", encoding="utf-8") as f:
                f.write(content)
            self._original_styles = content
            return True
        except Exception as e:
            error(f"Error saving styles: {e}")
            return False

    def has_styles_changed(self, current_styles: str) -> bool:
        """Check if styles were modified since loading."""
        return current_styles != self._original_styles

    def _get_default_config(self) -> dict[str, Any]:
        """Default config when none exists."""
        return {
            "watch_stylesheet": True,
            "watch_config": True,
            "debug": False,
            "update_check": True,
            "bars": {},
            "widgets": {},
        }

    def get_bars(self) -> dict[str, Any]:
        return self._config.get("bars", {})

    def get_bar(self, bar_name: str) -> dict[str, Any] | None:
        return self._config.get("bars", {}).get(bar_name)

    def get_widgets(self) -> dict[str, Any]:
        return self._config.get("widgets", {})

    def get_widget(self, widget_name: str) -> dict[str, Any] | None:
        return self._config.get("widgets", {}).get(widget_name)

    def delete_widget(self, widget_name: str) -> bool:
        if widget_name not in (self._config.get("widgets") or {}):
            return False
        for bar in (self._config.get("bars") or {}).values():
            widgets = bar.get("widgets") or {}
            for position in ["left", "center", "right"]:
                pos_widgets = widgets.get(position) or []
                if widget_name in pos_widgets:
                    pos_widgets.remove(widget_name)
        del self._config["widgets"][widget_name]
        return True

    def rename_widget(self, old_name: str, new_name: str) -> bool:
        """Rename a widget and update all bar references."""
        widgets = self._config.get("widgets") or {}
        if old_name not in widgets or new_name in widgets:
            return False
        widgets[new_name] = widgets.pop(old_name)
        for bar in (self._config.get("bars") or {}).values():
            bar_widgets = bar.get("widgets") or {}
            for position in ["left", "center", "right"]:
                pos_widgets = bar_widgets.get(position) or []
                for i, name in enumerate(pos_widgets):
                    if name == old_name:
                        pos_widgets[i] = new_name
        return True

    def get_global_setting(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set_global_setting(self, key: str, value: Any) -> None:
        self._config[key] = value

    def get_komorebi_settings(self) -> dict[str, str]:
        return self._config.get("komorebi", {})

    def set_komorebi_settings(self, settings: dict[str, str]) -> None:
        self._config["komorebi"] = settings

    def get_glazewm_settings(self) -> dict[str, str]:
        return self._config.get("glazewm", {})

    def set_glazewm_settings(self, settings: dict[str, str]) -> None:
        self._config["glazewm"] = settings

    def remove_setting(self, key: str) -> None:
        """Remove a setting from config."""
        if key in self._config:
            del self._config[key]

    def export_config(self, destination_path: str) -> bool:
        """Export config folder as a zip file."""
        try:
            temp_zip = os.path.join(tempfile.gettempdir(), "yasb_export.zip")
            with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(self._config_dir):
                    for f in files:
                        file_path = os.path.join(root, f)
                        arcname = os.path.relpath(file_path, self._config_dir)
                        zf.write(file_path, arcname)

            shutil.move(temp_zip, destination_path)
            return True
        except Exception as e:
            error(f"Export error: {e}")
            return False
