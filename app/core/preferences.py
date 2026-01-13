"""
App preferences - storing UI settings like language, theme, etc.

Stored in JSON in the app data directory, separate from YASB config.
"""

import json
import os

from core.constants import APP_DATA_DIR, DEFAULT_SETTINGS, SETTINGS_PATH
from core.logger import error

_preferences = None


class Preferences:
    """Simple key-value storage for app settings (not YASB config)."""

    def __init__(self):
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        self._settings_path = SETTINGS_PATH
        self._settings = DEFAULT_SETTINGS.copy()
        self._load()

    def _load(self) -> None:
        try:
            if self._settings_path.exists():
                with open(self._settings_path, encoding="utf-8") as f:
                    saved = json.load(f)
                    self._settings = {**DEFAULT_SETTINGS, **(saved or {})}
        except Exception as e:
            error(f"Error loading app settings: {e}")
            self._settings = DEFAULT_SETTINGS.copy()

    def _save(self) -> None:
        try:
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            error(f"Error saving app settings: {e}")

    def get(self, key: str, default=None):
        return self._settings.get(key, default)

    def set(self, key: str, value) -> None:
        self._settings[key] = value
        self._save()


def get_preferences() -> Preferences:
    """Get the preferences instance (creates if needed)."""
    global _preferences
    if _preferences is None:
        _preferences = Preferences()
    return _preferences
