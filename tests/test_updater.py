"""
Tests for Updater - Asset update management.

Tests update metadata, registry validation, and update flow.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from core.updater import AssetUpdater


@pytest.fixture
def temp_updater(tmp_path, monkeypatch):
    """Create updater with temporary paths."""
    registry_path = tmp_path / "widget_registry.json"
    metadata_path = tmp_path / "update_metadata.json"

    updater = AssetUpdater()
    updater._registry_path = registry_path
    updater._metadata_path = metadata_path

    return updater


@pytest.fixture
def updater_with_metadata(temp_updater):
    """Create updater with existing metadata."""
    data = {"last_database_updated": datetime.now().isoformat()}
    with open(temp_updater._metadata_path, "w") as f:
        json.dump(data, f)
    return temp_updater


@pytest.fixture
def updater_with_old_metadata(temp_updater):
    """Create updater with old (10 days) metadata."""
    old_date = datetime.now() - timedelta(days=10)
    data = {"last_database_updated": old_date.isoformat()}
    with open(temp_updater._metadata_path, "w") as f:
        json.dump(data, f)
    return temp_updater


@pytest.fixture
def updater_with_registry(temp_updater):
    """Create updater with valid registry file."""
    data = {"widgets": {"clock": {"name": "Clock Widget"}}}
    with open(temp_updater._registry_path, "w") as f:
        json.dump(data, f)
    return temp_updater


# --- Update Metadata ---


class TestUpdateMetadata:
    """Tests for update metadata handling."""

    def test_no_metadata_returns_none(self, temp_updater):
        """Should return None and 999 days when no metadata exists."""
        last_update, age = temp_updater.get_last_update_info()

        assert last_update is None
        assert age == 999

    def test_get_last_update_info(self, updater_with_metadata):
        """Should return datetime and age for existing metadata."""
        last_update, age = updater_with_metadata.get_last_update_info()

        assert last_update is not None
        assert isinstance(last_update, datetime)
        assert age == 0  # Updated today

    def test_get_old_update_age(self, updater_with_old_metadata):
        """Should correctly calculate age in days."""
        last_update, age = updater_with_old_metadata.get_last_update_info()

        assert last_update is not None
        assert age == 10

    def test_save_update_metadata(self, temp_updater):
        """Should save current timestamp."""
        temp_updater._save_update_metadata()

        assert temp_updater._metadata_path.exists()

        with open(temp_updater._metadata_path) as f:
            data = json.load(f)

        assert "last_database_updated" in data

    def test_save_preserves_other_keys(self, temp_updater):
        """Should preserve other keys in metadata file."""
        # Create metadata with extra key
        with open(temp_updater._metadata_path, "w") as f:
            json.dump({"custom_key": "value"}, f)

        temp_updater._save_update_metadata()

        with open(temp_updater._metadata_path) as f:
            data = json.load(f)

        assert "custom_key" in data
        assert "last_database_updated" in data

    def test_removes_old_keys(self, temp_updater):
        """Should remove deprecated keys."""
        # Create metadata with old keys
        with open(temp_updater._metadata_path, "w") as f:
            json.dump({"last_updated": "old", "version": "1.0"}, f)

        temp_updater._save_update_metadata()

        with open(temp_updater._metadata_path) as f:
            data = json.load(f)

        assert "last_updated" not in data
        assert "version" not in data


# --- Registry Validation ---


class TestRegistryValidation:
    """Tests for registry file validation."""

    def test_no_registry_returns_false(self, temp_updater):
        """Should return False when registry doesn't exist."""
        assert temp_updater.is_registry_present() is False

    def test_valid_registry_returns_true(self, updater_with_registry):
        """Should return True for valid registry."""
        assert updater_with_registry.is_registry_present() is True

    def test_invalid_registry_returns_false(self, temp_updater):
        """Should return False for registry without widgets key."""
        with open(temp_updater._registry_path, "w") as f:
            json.dump({"other_key": "value"}, f)

        assert temp_updater.is_registry_present() is False

    def test_corrupted_registry_returns_false(self, temp_updater):
        """Should return False for corrupted JSON."""
        with open(temp_updater._registry_path, "w") as f:
            f.write("not valid json {{{")

        assert temp_updater.is_registry_present() is False


# --- Update Flow ---


class TestUpdateFlow:
    """Tests for update flow control."""

    def test_prevents_concurrent_updates(self, temp_updater):
        """Should prevent concurrent update calls."""
        temp_updater._is_updating = True

        success, message = temp_updater.update_sync()

        assert success is False
        assert "already in progress" in message.lower()

    def test_update_resets_flag_on_completion(self, temp_updater, monkeypatch):
        """Should reset updating flag after completion."""
        # Mock the actual update to avoid network calls
        monkeypatch.setattr(temp_updater, "_update_registry", lambda: None)
        monkeypatch.setattr("core.updater.update_schema_database", lambda cb=None: (True, "Success"))

        temp_updater.update_sync()

        assert temp_updater._is_updating is False

    def test_update_resets_flag_on_error(self, temp_updater, monkeypatch):
        """Should reset updating flag even on error."""

        def raise_error():
            raise Exception("Test error")

        monkeypatch.setattr(temp_updater, "_update_registry", raise_error)

        temp_updater.update_sync()

        assert temp_updater._is_updating is False


# --- Progress Callback ---


class TestProgressCallback:
    """Tests for progress callback handling."""

    def test_progress_callback_called(self, temp_updater, monkeypatch):
        """Should call progress callback during update."""
        progress_calls = []

        def track_progress(current, total, message):
            progress_calls.append((current, total, message))

        monkeypatch.setattr(temp_updater, "_update_registry", lambda: None)
        monkeypatch.setattr("core.updater.update_schema_database", lambda cb=None: (True, "Success"))

        temp_updater.update_sync(progress_callback=track_progress)

        assert len(progress_calls) > 0
        # Should end at 100%
        assert progress_calls[-1][0] == 100
