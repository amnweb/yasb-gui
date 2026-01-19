"""Application constants and configuration."""

import os
import sys
from pathlib import Path

# Application metadata
APP_VERSION = "0.0.2"
DEFAULT_SETTINGS = {"language": "en", "theme": "default", "backdrop": "mica"}

# External URLs
YASB_SITE = "https://yasb.dev"
GITHUB_YASB = "https://github.com/amnweb/yasb"
GITHUB_YASB_GUI = "https://github.com/amnweb/yasb-gui"
GITHUB_REGISTRY = "https://raw.githubusercontent.com/amnweb/yasb-gui-registry/main/registry.json"
GITHUB_RELEASES_API = "https://api.github.com/repos/amnweb/yasb-gui/releases"

# Update settings
UPDATE_CHECK_INTERVAL_MINUTES = 60

# App ID package identity (Package Family Name + App ID)
APP_ID = "YASB.GUI_wbnnev551gwxy!App"

# Application paths
IS_EXECUTABLE = bool(getattr(sys, "frozen", False))
APP_BASE_PATH = Path(sys.executable).resolve().parent if IS_EXECUTABLE else Path(__file__).resolve().parents[2]
APP_ICON = APP_BASE_PATH / "assets" / "app.ico"

# User data directories
APP_DATA = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
APP_DATA_DIR = os.path.join(APP_DATA, "YASB-GUI")
os.makedirs(APP_DATA_DIR, exist_ok=True)

WEBVIEW_CACHE_DIR = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", ".")), f"yasb_gui_{APP_VERSION}")
os.makedirs(WEBVIEW_CACHE_DIR, exist_ok=True)

# Application data files
SETTINGS_PATH = Path(APP_DATA_DIR) / "settings.json"
LOG_PATH = os.path.join(APP_DATA_DIR, "app.log")
REGISTRY_FILE = Path(APP_DATA_DIR) / "widget_registry.json"
UPDATE_METADATA_FILE = Path(APP_DATA_DIR) / "update_metadata.json"
SCHEMA_DB_PATH = Path(APP_DATA_DIR) / "widget_schemas.json"
