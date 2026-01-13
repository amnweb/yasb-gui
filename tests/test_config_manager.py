"""
Tests for config loading, saving, and managing bars/widgets/settings.

Makes sure we can read/write config files, modify widgets and bars,
and track changes properly.
"""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from core.config_manager import ConfigManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    """Set up a temporary config directory for testing."""
    config_dir = tmp_path / "yasb_config"
    config_dir.mkdir()
    monkeypatch.setenv("YASB_CONFIG_HOME", str(config_dir))
    return config_dir


@pytest.fixture
def manager(temp_config_dir):
    """Fresh ConfigManager with empty temp directory."""
    return ConfigManager()


@pytest.fixture
def manager_with_config(temp_config_dir):
    """ConfigManager with sample config already loaded."""
    shutil.copy(FIXTURES_DIR / "sample_config.yaml", temp_config_dir / "config.yaml")
    return ConfigManager()


@pytest.fixture
def manager_with_minimal_config(temp_config_dir):
    """ConfigManager with a nearly empty config."""
    shutil.copy(FIXTURES_DIR / "minimal_config.yaml", temp_config_dir / "config.yaml")
    return ConfigManager()


class TestConfigLoading:
    """Loading config files."""

    def test_creates_default_config_when_missing(self, manager):
        """If no config exists, create a default one."""
        config = manager.load_config()

        assert config is not None
        assert "watch_stylesheet" in config
        assert "watch_config" in config

    def test_reads_existing_config(self, manager_with_config):
        """Load an existing config file properly."""
        config = manager_with_config.load_config()

        assert config["watch_stylesheet"] is True
        assert config["debug"] is False
        assert "primary-bar" in config["bars"]
        assert "clock" in config["widgets"]

    def test_parses_bar_configuration(self, manager_with_config):
        """Parse bar settings from config."""
        manager_with_config.load_config()
        bars = manager_with_config.get_bars()

        assert "primary-bar" in bars
        assert bars["primary-bar"]["enabled"] is True
        assert bars["primary-bar"]["class_name"] == "yasb-bar"

    def test_parses_widget_configuration(self, manager_with_config):
        """Parse widget settings from config."""
        manager_with_config.load_config()
        widgets = manager_with_config.get_widgets()

        assert "clock" in widgets
        assert widgets["clock"]["type"] == "yasb.clock.ClockWidget"
        assert "options" in widgets["clock"]


class TestConfigSaving:
    """Saving config changes."""

    def test_writes_config_to_file(self, manager, temp_config_dir):
        """Write changes back to the config file."""
        manager.load_config()
        manager._config["debug"] = True
        manager.save_config()

        content = (temp_config_dir / "config.yaml").read_text()
        assert "debug: true" in content


class TestStyles:
    """CSS styles management."""

    def test_returns_empty_when_missing(self, manager):
        """No styles file means empty string."""
        assert manager.load_styles() == ""

    def test_reads_existing_styles(self, manager, temp_config_dir):
        """Load existing styles.css file."""
        (temp_config_dir / "styles.css").write_text(".bar { background: #000; }")
        assert ".bar { background: #000; }" in manager.load_styles()

    def test_saves_styles_to_file(self, manager, temp_config_dir):
        """Write CSS back to styles.css."""
        css = ".widget { color: #fff; }"
        assert manager.save_styles(css) is True
        assert (temp_config_dir / "styles.css").read_text() == css


class TestWidgetOperations:
    """Creating, reading, updating, and deleting widgets."""

    def test_get_widget(self, manager_with_config):
        """Get a widget by name."""
        manager_with_config.load_config()
        widget = manager_with_config.get_widget("clock")

        assert widget["type"] == "yasb.clock.ClockWidget"

    def test_get_widget_returns_none_for_missing(self, manager_with_config):
        """Return None if widget doesn't exist."""
        manager_with_config.load_config()
        assert manager_with_config.get_widget("nonexistent") is None

    def test_delete_widget(self, manager_with_config):
        """Delete a widget from the config."""
        manager_with_config.load_config()

        assert manager_with_config.delete_widget("volume") is True
        assert "volume" not in manager_with_config.get_widgets()

    def test_delete_widget_removes_from_bars(self, manager_with_config):
        """Deleting a widget should also remove it from all bars."""
        manager_with_config.load_config()
        manager_with_config.delete_widget("volume")

        bar = manager_with_config.get_bar("primary-bar")
        assert "volume" not in bar["widgets"]["right"]

    def test_delete_nonexistent_widget(self, manager_with_config):
        """Can't delete what doesn't exist."""
        manager_with_config.load_config()
        assert manager_with_config.delete_widget("nonexistent") is False

    def test_rename_widget(self, manager_with_config):
        """Rename a widget."""
        manager_with_config.load_config()

        assert manager_with_config.rename_widget("clock", "my_clock") is True
        assert "my_clock" in manager_with_config.get_widgets()
        assert "clock" not in manager_with_config.get_widgets()

    def test_rename_widget_updates_bar_references(self, manager_with_config):
        """Renaming should update all references in bars."""
        manager_with_config.load_config()
        manager_with_config.rename_widget("clock", "my_clock")

        bar = manager_with_config.get_bar("primary-bar")
        assert "my_clock" in bar["widgets"]["center"]
        assert "clock" not in bar["widgets"]["center"]

    def test_rename_fails_if_source_missing(self, manager_with_config):
        """Can't rename a widget that doesn't exist."""
        manager_with_config.load_config()
        assert manager_with_config.rename_widget("nonexistent", "new") is False

    def test_rename_fails_if_target_exists(self, manager_with_config):
        """Can't rename to a name that's already taken."""
        manager_with_config.load_config()
        assert manager_with_config.rename_widget("clock", "volume") is False


class TestBarOperations:
    """Managing bars."""

    def test_get_bar(self, manager_with_config):
        """Get a bar by name."""
        manager_with_config.load_config()
        bar = manager_with_config.get_bar("primary-bar")

        assert bar["enabled"] is True
        assert bar["class_name"] == "yasb-bar"

    def test_get_bar_returns_none_for_missing(self, manager_with_config):
        """Return None if bar doesn't exist."""
        manager_with_config.load_config()
        assert manager_with_config.get_bar("nonexistent") is None


class TestGlobalSettings:
    """Global settings (not widget or bar specific)."""

    def test_get_setting(self, manager_with_config):
        """Read a global setting value."""
        manager_with_config.load_config()

        assert manager_with_config.get_global_setting("debug") is False
        assert manager_with_config.get_global_setting("watch_stylesheet") is True

    def test_get_setting_with_default(self, manager_with_config):
        """Return default if setting doesn't exist."""
        manager_with_config.load_config()
        assert manager_with_config.get_global_setting("nonexistent", "default") == "default"

    def test_set_setting(self, manager_with_config):
        """Update a setting value."""
        manager_with_config.load_config()
        manager_with_config.set_global_setting("debug", True)

        assert manager_with_config.get_global_setting("debug") is True

    def test_remove_setting(self, manager_with_config):
        """Remove a setting completely."""
        manager_with_config.load_config()
        manager_with_config.set_komorebi_settings({"start_command": "test"})
        manager_with_config.remove_setting("komorebi")

        assert "komorebi" not in manager_with_config._config


class TestWindowManagerSettings:
    """Komorebi and GlazeWM integration settings."""

    def test_komorebi_settings(self, manager_with_config):
        """Get and set Komorebi settings."""
        manager_with_config.load_config()

        settings = {"start_command": "start", "stop_command": "stop"}
        manager_with_config.set_komorebi_settings(settings)

        assert manager_with_config.get_komorebi_settings() == settings

    def test_glazewm_settings(self, manager_with_config):
        """Get and set GlazeWM settings."""
        manager_with_config.load_config()

        settings = {"start_command": "start", "stop_command": "stop"}
        manager_with_config.set_glazewm_settings(settings)

        assert manager_with_config.get_glazewm_settings() == settings


class TestChangeTracking:
    """Detecting when config or styles have unsaved changes."""

    def test_no_changes_after_load(self, manager_with_config):
        """Right after loading, there should be no changes."""
        manager_with_config.load_config()
        assert manager_with_config.has_config_changed() is False

    def test_detects_modification(self, manager_with_config):
        """Should detect when we modify the config."""
        manager_with_config.load_config()
        manager_with_config.set_global_setting("debug", True)

        assert manager_with_config.has_config_changed() is True

    def test_detects_revert(self, manager_with_config):
        """If we change something then change it back, no changes."""
        manager_with_config.load_config()
        original = manager_with_config.get_global_setting("debug")

        manager_with_config.set_global_setting("debug", not original)
        manager_with_config.set_global_setting("debug", original)

        assert manager_with_config.has_config_changed() is False

    def test_resets_after_save(self, manager_with_config):
        """After saving, change flag should reset."""
        manager_with_config.load_config()
        manager_with_config.set_global_setting("debug", True)
        manager_with_config.save_config()

        assert manager_with_config.has_config_changed() is False

    def test_styles_change_detection(self, manager, temp_config_dir):
        """Detect when CSS styles have changed."""
        (temp_config_dir / "styles.css").write_text(".bar { color: red; }")
        original = manager.load_styles()

        assert manager.has_styles_changed(original) is False
        assert manager.has_styles_changed(".bar { color: blue; }") is True


class TestEdgeCases:
    """Empty configs and edge cases."""

    def test_empty_bars(self, manager_with_minimal_config):
        """Handle config with no bars defined."""
        manager_with_minimal_config.load_config()

        assert manager_with_minimal_config.get_bars() == {}
        assert manager_with_minimal_config.get_bar("any") is None

    def test_empty_widgets(self, manager_with_minimal_config):
        """Handle config with no widgets defined."""
        manager_with_minimal_config.load_config()

        assert manager_with_minimal_config.get_widgets() == {}
        assert manager_with_minimal_config.get_widget("any") is None

    def test_operations_on_empty_config(self, manager_with_minimal_config):
        """Operations on empty config should fail gracefully."""
        manager_with_minimal_config.load_config()

        assert manager_with_minimal_config.delete_widget("any") is False
        assert manager_with_minimal_config.rename_widget("old", "new") is False
