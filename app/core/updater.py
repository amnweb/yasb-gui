"""
Asset updater - keeps widget registry and schemas up to date.

Downloads the widget registry from yasb-gui-registry and widget schemas
from the main YASB repo. Tracks update timestamps.
"""

import datetime
import json
import platform
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from core.constants import (
    APP_ID,
    APP_VERSION,
    GITHUB_REGISTRY,
    GITHUB_RELEASES_API,
    REGISTRY_FILE,
    UPDATE_CHECK_INTERVAL_MINUTES,
    UPDATE_METADATA_FILE,
)
from core.errors import get_friendly_error_message
from core.logger import error, info
from core.schema_fetcher import update_schema_database


class AssetUpdater:
    def __init__(self):
        self._registry_path = REGISTRY_FILE
        self._metadata_path = UPDATE_METADATA_FILE
        self._is_updating = False

    def get_last_update_info(self):
        """Get when the database was last updated and how old it is."""
        if not self._metadata_path.exists():
            return None, 999

        try:
            with open(self._metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                last_updated = data.get("last_database_updated")

                if not last_updated:
                    return None, 999

                dt = datetime.datetime.fromisoformat(last_updated)
                age = (datetime.datetime.now() - dt).days
                return dt, age
        except Exception:
            return None, 999

    def _save_update_metadata(self):
        """Save current timestamp and app version as last update info."""
        try:
            if self._metadata_path.exists():
                try:
                    with open(self._metadata_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except:
                    data = {}
            else:
                data = {}

            data["last_database_updated"] = datetime.datetime.now().isoformat()
            data["last_database_app_version"] = APP_VERSION

            data.pop("last_updated", None)
            data.pop("version", None)

            with open(self._metadata_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            error(f"Failed to save metadata: {e}")

    def has_version_changed(self) -> bool:
        """Check if the app version changed since last schema update."""
        if not self._metadata_path.exists():
            return False
        try:
            with open(self._metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                last_version = data.get("last_database_app_version")
                if last_version and last_version != APP_VERSION:
                    return True
        except Exception:
            pass
        return False

    def is_registry_present(self) -> bool:
        """Check if registry file exists and looks valid."""
        if not self._registry_path.exists():
            return False
        try:
            with open(self._registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return "widgets" in data
        except:
            return False

    def update_sync(self, progress_callback=None) -> tuple[bool, str]:
        """Update registry and schemas. Returns (success, message)."""
        if self._is_updating:
            return False, "Update already in progress"

        self._is_updating = True
        try:
            if progress_callback:
                progress_callback(10, 100, "Updating Widget Registry...")
            self._update_registry()

            if progress_callback:
                progress_callback(50, 100, "Updating Validation Schemas...")

            def schema_callback_wrapper(cur, tot, msg):
                if progress_callback:
                    if tot > 0:
                        pct = cur / tot
                        if pct > 1.0:
                            pct = 1.0
                        overall_pct = 50 + (pct * 45)
                        progress_callback(overall_pct, 100, msg)
                    else:
                        progress_callback(50, 100, msg)

            success, msg = update_schema_database(schema_callback_wrapper)

            if not success:
                return False, msg

            self._save_update_metadata()

            if progress_callback:
                progress_callback(100, 100, "Update Complete")

            info("All assets updated successfully")
            return True, "All assets updated successfully"

        except Exception as e:
            error(f"Asset update failed: {e}")
            return False, get_friendly_error_message(e)
        finally:
            self._is_updating = False

    def _update_registry(self):
        """Download the latest registry.json."""
        try:
            info("Downloading registry from: " + GITHUB_REGISTRY)
            req = urllib.request.Request(GITHUB_REGISTRY, headers={"User-Agent": "YASB-Config-Updater"})

            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    data = response.read()
                    # Verify it's valid JSON before saving
                    json.loads(data)

                    with open(self._registry_path, "wb") as f:
                        f.write(data)
                    info("Registry file saved.")
                else:
                    error(f"Failed to download registry. Status: {response.status}")
        except Exception as e:
            error(f"Registry download error: {e}")
            raise


class AppUpdater:
    """Handles application updates from GitHub releases."""

    def __init__(self):
        self._metadata_path = UPDATE_METADATA_FILE

    def _get_system_arch(self) -> str:
        """Detect system architecture (x64 or aarch64)."""
        machine = platform.machine().lower()
        if machine in ["arm64", "aarch64"]:
            return "aarch64"
        elif machine in ["amd64", "x86_64", "x64"]:
            return "x64"
        elif platform.architecture()[0] == "64bit":
            return "x64"
        return "x64"  # Default to x64

    def _compare_versions(self, current: str, latest: str) -> bool:
        """
        Compare version strings. Returns True if latest > current.
        Handles versions like: 0.0.1, 1.0.0, 0.1.0-beta, etc.
        """
        try:
            # Strip 'v' prefix if present
            current = current.lstrip("v")
            latest = latest.lstrip("v")

            # Split by '-' to separate version from pre-release tag
            current_ver = current.split("-")[0]
            latest_ver = latest.split("-")[0]

            # Split into parts and compare
            current_parts = [int(x) for x in current_ver.split(".")]
            latest_parts = [int(x) for x in latest_ver.split(".")]

            # Pad to same length
            max_len = max(len(current_parts), len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))

            # Compare each part
            for c, l in zip(current_parts, latest_parts):
                if l > c:
                    return True
                elif l < c:
                    return False

            return False  # Versions are equal
        except Exception as e:
            error(f"Version comparison error: {e}")
            return False

    def _save_metadata(self, check_time: bool = False, version: Optional[str] = None, url: Optional[str] = None):
        """Save app update check metadata."""
        try:
            if self._metadata_path.exists():
                try:
                    with open(self._metadata_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except:
                    data = {}
            else:
                data = {}

            if check_time:
                data["last_app_update_check"] = datetime.datetime.now().isoformat()

            if version:
                data["available_update_version"] = version
                if url:
                    data["available_update_url"] = url
            else:
                # Clear update info if no version provided
                data.pop("available_update_version", None)
                data.pop("available_update_url", None)

            with open(self._metadata_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            error(f"Failed to save app update metadata: {e}")

    def can_check_update(self) -> Tuple[bool, str]:
        """Check if enough time has passed since last app update check."""
        if not self._metadata_path.exists():
            return True, ""

        try:
            with open(self._metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                last_check = data.get("last_app_update_check")

                if not last_check:
                    return True, ""

                dt = datetime.datetime.fromisoformat(last_check)
                age_minutes = (datetime.datetime.now() - dt).total_seconds() / 60

                if age_minutes < UPDATE_CHECK_INTERVAL_MINUTES:
                    remaining = int(UPDATE_CHECK_INTERVAL_MINUTES - age_minutes)
                    return False, f"Please wait {remaining} minute(s)"

                return True, ""
        except Exception:
            return True, ""

    def get_available_update(self) -> Optional[Tuple[str, str]]:
        """
        Get available update info from metadata.
        Returns (version, download_url) tuple or None.
        """
        if not self._metadata_path.exists():
            return None

        try:
            with open(self._metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                version = data.get("available_update_version")
                url = data.get("available_update_url")

                if version and url:
                    return (version, url)
        except Exception:
            pass

        return None

    def start_background_check(self, on_update_found_callback):
        """
        Start background update check in a separate thread.
        Calls the callback function if an update is found.

        Args:
            on_update_found_callback: Function to call if update is available
        """

        def _check():
            try:
                if self.check_for_update_background():
                    on_update_found_callback()
            except Exception as e:
                error(f"Background update check failed: {e}")

        threading.Thread(target=_check, daemon=True).start()

    def check_for_update_background(self) -> Optional[Tuple[str, str]]:
        """
        Background check for updates (called on app startup).
        Respects rate limiting and returns cached update if available.
        Returns (version, url) tuple if update is available, None otherwise.
        """
        try:
            # Check rate limit
            can_check, _ = self.can_check_update()
            if not can_check:
                # Too soon, return cached update info if available
                return self.get_available_update()

            # Check for updates (respects rate limiting)
            success, message, version, url = self.check_for_update(skip_rate_limit=False)
            if success and version:
                return (version, url)
        except Exception as e:
            error(f"Background update check failed: {e}")

        return None

    def check_for_update(self, skip_rate_limit: bool = False) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Check for app updates from GitHub releases.
        Args:
            skip_rate_limit: If True, bypasses the 30-minute rate limit (for manual checks)
        Returns (success, message, version, download_url).
        """
        # Check rate limit unless explicitly skipped
        if not skip_rate_limit:
            can_check, msg = self.can_check_update()
            if not can_check:
                return False, msg, None, None
        try:
            info("Checking for app updates...")

            # Fetch releases from GitHub API
            req = urllib.request.Request(GITHUB_RELEASES_API, headers={"User-Agent": "YASB-GUI-Updater"})

            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status != 200:
                    error(f"Failed to fetch releases. Status: {response.status}")
                    return False, "Failed to check for updates", None, None

                releases = json.loads(response.read())

            if not releases:
                info("No releases found")
                self._save_metadata(check_time=True)
                return True, "No updates available", None, None

            # Get the latest release (first in list)
            latest_release = releases[0]
            latest_version = latest_release.get("tag_name", "").lstrip("v")

            info(f"Latest release: {latest_version}, Current: {APP_VERSION}")

            # Compare versions
            if not self._compare_versions(APP_VERSION, latest_version):
                info("Already on latest version")
                self._save_metadata(check_time=True)
                return True, "You are on the latest version", None, None

            # Find msixbundle asset (extract publisher ID from APP_ID)
            publisher_id = APP_ID.split("_")[1]
            bundle_name = f"YASB.GUI_{latest_version}_{publisher_id}.msixbundle"

            download_url = None
            for asset in latest_release.get("assets", []):
                if asset.get("name") == bundle_name:
                    download_url = asset.get("browser_download_url")
                    break

            if not download_url:
                error(f"Could not find {bundle_name}")
                return False, "No installer found", None, None

            # Save update info
            self._save_metadata(check_time=True, version=latest_version, url=download_url)

            info(f"Update available: {latest_version}")
            return True, f"Update {latest_version} available", latest_version, download_url

        except Exception as e:
            error(f"App update check failed: {e}")
            self._save_metadata(check_time=True)
            return False, get_friendly_error_message(e), None, None

    def download_update(self, download_url: str, progress_callback=None) -> Tuple[bool, str, Optional[str]]:
        """
        Download app update installer.
        Returns (success, message, file_path).
        """
        try:
            info(f"Downloading update from: {download_url}")

            # Download to temp directory
            temp_dir = tempfile.gettempdir()
            filename = download_url.split("/")[-1]
            download_path = Path(temp_dir) / filename

            req = urllib.request.Request(download_url, headers={"User-Agent": "YASB-GUI-Updater"})

            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status != 200:
                    error(f"Download failed. Status: {response.status}")
                    return False, "Download failed", None

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 8192

                with open(download_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback and total_size > 0:
                            progress_callback(downloaded, total_size, "Downloading...")

            info(f"Download complete: {download_path}")
            return True, "Download complete", str(download_path)

        except Exception as e:
            error(f"Download error: {e}")
            return False, get_friendly_error_message(e), None

    def install_update(self, installer_path: str) -> Tuple[bool, str]:
        """
        Install app update using MSIX package.
        Returns (success, message).
        """
        try:
            info(f"Installing update from {installer_path}")
            self._save_metadata(check_time=False)
            ps_script = f"""
$ErrorActionPreference = 'Stop'
try {{
    Add-AppxPackage -Path '{installer_path}' -ForceApplicationShutdown
    Start-Sleep -Seconds 2
    Start-Process 'shell:AppsFolder\{APP_ID}!App'
}} catch {{
    Write-Error $_.Exception.Message
    exit 1
}}
"""

            subprocess.Popen(
                ["powershell.exe", "-WindowStyle", "Hidden", "-Command", ps_script],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            info("Update initiated - app will restart after installation")
            return True, "Installation started"

        except Exception as e:
            error(f"Installation error: {e}")
            return False, get_friendly_error_message(e)


# Global instances
updater = AssetUpdater()
app_updater = AppUpdater()
