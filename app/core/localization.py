"""
Localization system - load and manage translations.

Loads translations from JSON files in the locales/ directory.
Falls back to English if a key is missing in the current language.
"""

import json
from pathlib import Path

from core.logger import error
from core.preferences import get_preferences

_localization = None


class Localization:
    """Handles loading and accessing translated strings."""

    def __init__(self):
        self._prefs = get_preferences()
        self._current_language = self._prefs.get("language", "en")
        self._translations = {}
        self._fallback = {}
        self._available_languages = {}
        self._locales_dir = Path(__file__).parent / "locales"

        self._scan_languages()
        self._load_language(self._current_language)

    def _scan_languages(self):
        """Find all available language files in locales/ directory."""
        self._available_languages = {}
        if self._locales_dir.exists():
            for file in self._locales_dir.glob("*.json"):
                try:
                    with open(file, encoding="utf-8") as f:
                        data = json.load(f)
                        lang_code = file.stem
                        lang_name = data.get("_language_name", lang_code.upper())
                        self._available_languages[lang_code] = lang_name
                except Exception as e:
                    error(f"Error scanning language file {file}: {e}")
        if "en" not in self._available_languages:
            self._available_languages["en"] = "English"

    def _load_language(self, lang_code):
        """Load translations for a specific language code."""
        fallback_path = self._locales_dir / "en.json"
        if fallback_path.exists():
            try:
                with open(fallback_path, encoding="utf-8") as f:
                    self._fallback = json.load(f)
            except Exception as e:
                error(f"Error loading fallback language: {e}")
                self._fallback = {}

        if lang_code == "en":
            self._translations = self._fallback
            return

        lang_path = self._locales_dir / f"{lang_code}.json"
        if lang_path.exists():
            try:
                with open(lang_path, encoding="utf-8") as f:
                    self._translations = json.load(f)
                return
            except Exception as e:
                error(f"Error loading language {lang_code}: {e}")
        self._translations = self._fallback

    def get(self, key, **kwargs):
        """Get translated text for a key, with optional formatting."""
        text = self._translations.get(key) or self._fallback.get(key) or key
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    def set_language(self, lang_code):
        """Change the current language (requires app restart)."""
        if lang_code not in self._available_languages:
            return False
        self._prefs.set("language", lang_code)
        return True

    def get_current_language(self):
        return self._current_language

    def get_available_languages(self):
        return self._available_languages.copy()


def initialize():
    """Initialize the localization system."""
    global _localization
    if _localization is None:
        _localization = Localization()
    return _localization


def get_instance():
    """Get the localization instance (creates if needed)."""
    global _localization
    if _localization is None:
        _localization = Localization()
    return _localization


def t(key, **kwargs):
    """Shorthand for getting a translated string."""
    return get_instance().get(key, **kwargs)
