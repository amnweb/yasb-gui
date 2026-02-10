"""
YASB GUI - Main Application Module.

Central application class handling window setup, navigation, and routing.
"""

import ctypes
import json
import threading
import time
from ctypes import POINTER, WINFUNCTYPE, c_int, c_void_p, cast, wintypes
from datetime import datetime, timedelta
from typing import Tuple, Union

from core.config_manager import ConfigManager
from core.constants import APP_ICON, IS_EXECUTABLE, LOG_PATH
from core.localization import t
from core.logger import error, warning
from core.preferences import get_preferences
from core.schema_fetcher import is_database_valid
from core.updater import app_updater, updater
from core.win32_types import GWL_WNDPROC, MINMAXINFO, OFN_EXPLORER, OFN_OVERWRITEPROMPT, OPENFILENAMEW, WM_GETMINMAXINFO
from pages.app_settings import AppSettingsPage
from pages.bars import BarsPage
from pages.env_variables import EnvVariablesPage
from pages.global_settings import GlobalSettingsPage
from pages.styles import StylesPage
from pages.widgets import WidgetsPage
from typing_extensions import override
from ui.controls import UIFactory
from ui.loader import load_xaml
from winrt.system import Array
from winrt.windows.foundation import IPropertyValue
from winrt.windows.ui.xaml.interop import TypeKind, TypeName
from winui3.microsoft.ui.composition.systembackdrops import MicaKind
from winui3.microsoft.ui.windowing import TitleBarTheme
from winui3.microsoft.ui.xaml import (
    Application,
    DispatcherTimer,
    ElementTheme,
    FrameworkElement,
    LaunchActivatedEventArgs,
    Visibility,
    Window,
)
from winui3.microsoft.ui.xaml.controls import (
    Button,
    ContentControl,
    ContentDialog,
    InfoBadge,
    InfoBar,
    NavigationView,
    NavigationViewItem,
    NavigationViewSelectionChangedEventArgs,
    ProgressBar,
    ProgressRing,
    TextBlock,
    XamlControlsResources,
)
from winui3.microsoft.ui.xaml.markup import (
    IXamlMetadataProvider,
    IXamlType,
    XamlReader,
    XmlnsDefinition,
)
from winui3.microsoft.ui.xaml.media import DesktopAcrylicBackdrop, FontFamily, MicaBackdrop
from winui3.microsoft.ui.xaml.xamltypeinfo import XamlControlsXamlMetaDataProvider


class ConfiguratorApp(Application, IXamlMetadataProvider):
    """Main application class for YASB GUI."""

    def __init__(self):
        super().__init__()
        self._provider = XamlControlsXamlMetaDataProvider()
        self._config_manager = ConfigManager()
        self._window = None
        self._nav_view = None
        self._content_area = None
        self._unsaved_changes = False
        self._unsaved_styles = False  # Track if styles changed
        self._unsaved_config = False  # Track if config changed
        self._styles_editor = None  # Legacy TextBox reference (deprecated)
        self._styles_webview = None  # Monaco editor WebView2 reference
        self._current_bar_name = None
        self._current_widget_name = None
        self._widgets_selected_bar = None
        self._loading = False
        self._nav_items = {}  # Store nav items by tag for updating labels
        self._unsaved_infobar = None  # InfoBar for unsaved changes
        self._config_load_error = None

        # App update state
        self._update_available = False
        self._update_badge_added = False

        # Page handlers
        self._global_page = GlobalSettingsPage(self)
        self._bars_page = BarsPage(self)
        self._widgets_page = WidgetsPage(self)
        self._styles_page = StylesPage(self)
        self._env_page = EnvVariablesPage(self)
        self._app_settings_page = AppSettingsPage(self)

    @override
    def _on_launched(self, args: LaunchActivatedEventArgs):
        """Handle application launch."""
        self._loading_start_time = time.time()

        resources = XamlControlsResources()
        self.resources.merged_dictionaries.append(resources)

        # Flag to prevent navigation during loading
        self._is_loading = True

        self._window = XamlReader.load(load_xaml("MainWindow.xaml")).as_(Window)
        self._window.title = t("app_title")
        self._window.extends_content_into_title_bar = True

        # Set window icon
        self._set_window_icon()

        # Apply saved appearance settings
        self._apply_saved_settings()

        self._nav_view = self._window.content.as_(NavigationView)
        self._content_area = self._nav_view.find_name("ContentArea").as_(ContentControl)
        self._loading_spinner = self._nav_view.find_name("LoadingSpinner")
        self._nav_view.add_selection_changed(self._on_nav_selection_changed)
        self._nav_view.add_item_invoked(self._on_nav_item_invoked)

        # Setup unsaved changes footer
        self._setup_unsaved_footer()

        # Store nav items and apply translations
        self._cache_nav_items()
        self.update_nav_labels()

        # Add window close handler
        self._window.add_closed(self._on_window_closed)

        # Register loaded handler BEFORE activate
        self._nav_view.add_loaded(self._on_nav_view_loaded)

        # Show window immediately with spinner
        self._window.activate()

        # Set minimum window size
        self._set_min_window_size(960, 720)

    def get_element_theme(self):
        """Get the current element theme based on app preferences."""
        prefs = get_preferences()
        theme_setting = prefs.get("theme", "default") if prefs else "default"

        if theme_setting == "light":
            return ElementTheme.LIGHT
        elif theme_setting == "dark":
            return ElementTheme.DARK
        else:
            return ElementTheme.DEFAULT

    def create_dialog(self, xaml_content: str) -> ContentDialog:
        """Create a ContentDialog with proper root and theme settings.

        Args:
            xaml_content: The XAML string content for the dialog

        Returns:
            The configured ContentDialog instance
        """
        dialog = XamlReader.load(xaml_content).as_(ContentDialog)
        dialog.xaml_root = self._window.content.xaml_root
        dialog.requested_theme = self.get_element_theme()
        return dialog

    def _on_nav_view_loaded(self, sender, args):
        """Handle NavigationView loaded - check config and load if valid."""
        # First check if YASB config files exist
        is_valid, missing = self._config_manager.is_config_valid()
        if not is_valid:
            self._show_missing_config_dialog(missing)
            return

        def load_in_background():
            try:
                self._config_manager.load_config()
            except Exception as e:
                self._config_load_error = str(e)
                error(f"Failed to load config: {e}", exc_info=True)
            finally:
                self._config_loaded = True

        self._config_loaded = False
        self._schema_check_done = False
        threading.Thread(target=load_in_background, daemon=True).start()

        # Start a timer to check when loading is complete
        self._load_check_timer = DispatcherTimer()
        self._load_check_timer.interval = timedelta(milliseconds=50)

        def check_loaded(s, e):
            if self._config_loaded:
                # Ensure minimum 1 second spinner time
                elapsed = time.time() - self._loading_start_time
                if elapsed >= 1.0:
                    self._load_check_timer.stop()
                    if self._config_load_error:
                        self._show_config_error_dialog(self._config_load_error)
                        return
                    # Check schema database before showing content
                    self._check_schema_database()

        self._load_check_timer.add_tick(check_loaded)
        self._load_check_timer.start()

    def _show_missing_config_dialog(self, missing: str):
        """Show dialog when YASB config files are missing."""
        # Hide spinner
        spinner = self._loading_spinner.as_(ProgressRing)
        spinner.is_active = False
        spinner.visibility = Visibility.COLLAPSED

        template = load_xaml("dialogs/MissingConfigDialog.xaml")
        dialog_xaml = template.format(
            title=UIFactory.escape_xml(t("missing_config_title")),
            message=UIFactory.escape_xml(t("missing_config_message")),
            hint=UIFactory.escape_xml(t("missing_config_hint")),
            primary=UIFactory.escape_xml(t("common_exit")),
        )
        dialog = self.create_dialog(dialog_xaml)

        def on_primary(s, e):
            self._window.close()

        dialog.add_primary_button_click(on_primary)
        dialog.show_async()

    def _show_config_error_dialog(self, error_message: str):
        """Show dialog when config fails to load and exit on close."""
        spinner = self._loading_spinner.as_(ProgressRing)
        spinner.is_active = False
        spinner.visibility = Visibility.COLLAPSED

        template = load_xaml("dialogs/MissingConfigDialog.xaml")
        dialog_xaml = template.format(
            title=UIFactory.escape_xml(t("config_load_error_title")),
            message=UIFactory.escape_xml(t("config_load_error_message").format(error=error_message)),
            hint=UIFactory.escape_xml(t("config_load_error_hint").format(log_path=str(LOG_PATH))),
            primary=UIFactory.escape_xml(t("common_exit")),
        )
        dialog = self.create_dialog(dialog_xaml)

        def on_primary(s, e):
            self._window.close()

        dialog.add_primary_button_click(on_primary)
        dialog.show_async()

    def _check_schema_database(self):
        """Check if schema database exists and is up to date."""
        # Check files existence
        if not is_database_valid() or not updater.is_registry_present():
            self._show_schema_dialog(mode="required")
            return

        # Check metadata age
        _, age = updater.get_last_update_info()
        if age >= 7:
            # Database is old - prompt user
            self._show_schema_dialog(mode="outdated", age_days=age)
        else:
            # Database is valid and up to date
            self._show_initial_content()
            # Check for app updates in background after initial content is shown (only for executables)
            if IS_EXECUTABLE:
                self._check_app_updates_background()

    def _show_schema_dialog(self, mode: str = "required", age_days: int = 0, error_msg: str = ""):
        """
        Show unified schema dialog for all states.

        Modes:
            - "required": First start, must download (Update Now / Exit)
            - "outdated": Database old, optional update (Update Now / Later)
            - "failed": Download failed (Retry / Continue Anyway)
        """

        # Determine title, status text, and buttons based on mode
        if mode == "required":
            title = t("schema_download_title")
            status = t("schema_download_required")
            primary = t("common_update_now")
            secondary = t("common_exit")
        elif mode == "outdated":
            title = t("schema_outdated_title")
            status = t("schema_outdated_message").format(days=age_days)
            primary = t("common_update_now")
            secondary = t("common_later")
        elif mode == "failed":
            title = t("schema_download_failed_title")
            status = f"{t('schema_download_failed_message')}\n\n{error_msg}"
            primary = t("common_retry")
            secondary = t("common_continue_anyway")
        else:
            title = t("schema_update_title")
            status = t("schema_downloading")
            primary = t("common_update_now")
            secondary = t("common_later")

        template = load_xaml("dialogs/SchemaDatabaseUpdateDialog.xaml")
        dialog_xaml = template.format(
            title=UIFactory.escape_xml(title),
            status=UIFactory.escape_xml(status),
            primary=UIFactory.escape_xml(primary),
            secondary=UIFactory.escape_xml(secondary),
        )
        dialog = self.create_dialog(dialog_xaml)

        self._schema_dialog = dialog
        self._schema_status_text = dialog.find_name("StatusText").as_(TextBlock)
        self._schema_progress_bar = dialog.find_name("ProgressBar").as_(ProgressBar)
        self._schema_mode = mode
        self._schema_downloading = False
        self._schema_is_required = mode in ("required", "failed")

        def on_closing(sender, args):
            # Prevent dialog from closing while downloading
            if self._schema_downloading:
                args.cancel = True

        def on_primary(s, e):
            if mode in ("required", "outdated", "failed"):
                # Start download - mark as downloading to prevent close
                self._schema_downloading = True
                self._start_schema_download()

        def on_secondary(s, e):
            if mode == "required":
                # Exit app
                self._window.close()
            elif mode == "outdated":
                # Skip update
                self._show_initial_content()
            elif mode == "failed":
                # Continue anyway
                self._show_initial_content()

        dialog.add_closing(on_closing)
        dialog.add_primary_button_click(on_primary)
        dialog.add_secondary_button_click(on_secondary)
        dialog.show_async()

    def _start_schema_download(self):
        """Start downloading schemas, updating the current dialog."""
        # Disable buttons and show progress bar
        self._schema_progress_bar.visibility = Visibility.VISIBLE
        self._schema_dialog.is_primary_button_enabled = False
        self._schema_dialog.is_secondary_button_enabled = False

        def download_schemas():
            def progress_callback(current, total, message):
                def update_ui():
                    self._schema_progress_bar.value = (current / total) * 100

                self._window.dispatcher_queue.try_enqueue(update_ui)

            success, message = updater.update_sync(progress_callback)

            def on_complete():
                # Allow dialog to close now
                self._schema_downloading = False
                self._schema_dialog.hide()

                if success:
                    # Reload registry in widgets page as it might have been missing/empty
                    self._widgets_page.reload_registry()
                    self._show_initial_content()
                elif self._schema_is_required:
                    # Failed but required - show error dialog
                    self._window.dispatcher_queue.try_enqueue(
                        lambda: self._show_schema_dialog(mode="failed", error_msg=message)
                    )
                else:
                    # Failed optional - just continue
                    self._show_initial_content()

            self._window.dispatcher_queue.try_enqueue(on_complete)

        threading.Thread(target=download_schemas, daemon=True).start()

    def _show_initial_content(self):
        """Show the initial content after loading is complete."""
        # Hide spinner
        spinner = self._loading_spinner.as_(ProgressRing)
        spinner.is_active = False
        spinner.visibility = Visibility.COLLAPSED

        # Show content area
        self._content_area.visibility = Visibility.VISIBLE

        # Loading complete - allow navigation
        self._is_loading = False

        # Select first item - this triggers _on_nav_selection_changed which shows the page
        if self._nav_view.menu_items.size > 0:
            self._nav_view.selected_item = self._nav_view.menu_items.get_at(0)

    def _check_app_updates_background(self):
        """Check for app updates in background (non-blocking)."""
        app_updater.start_background_check(self._on_update_found)

    def _on_update_found(self):
        """Callback when update is found - must run on UI thread."""
        self._update_available = True
        self._window.dispatcher_queue.try_enqueue(self._add_update_badge)

    def _add_update_badge(self):
        """Add update badge to Settings navigation item."""
        if self._update_badge_added:
            return

        try:
            # Find the settings navigation item (in footer)
            for i in range(self._nav_view.footer_menu_items.size):
                item = self._nav_view.footer_menu_items.get_at(i).as_(NavigationViewItem)
                if item:
                    tag = self._get_tag(item)

                    if tag == "app_settings":
                        # Create InfoBadge with count
                        badge = InfoBadge()
                        badge.value = 1
                        item.info_badge = badge

                        self._update_badge_added = True
                        break
        except Exception as e:
            error(f"Failed to add update badge: {e}")

    def has_app_update(self) -> bool:
        """Check if app update is available."""
        return self._update_available

    def _setup_unsaved_footer(self):
        """Setup the unsaved changes InfoBar."""
        self._unsaved_infobar = self._nav_view.find_name("UnsavedInfoBar").as_(InfoBar)
        save_btn = self._nav_view.find_name("SaveButton").as_(Button)
        later_btn = self._nav_view.find_name("LaterButton").as_(Button)

        # Set translated title
        self._unsaved_infobar.title = t("unsaved_footer")

        # Set button content via TextBlock (WinUI3 requirement)
        save_btn.content = UIFactory.create_text_block(t("unsaved_save"), margin="0")
        later_btn.content = UIFactory.create_text_block(t("unsaved_discard"), margin="0")

        # Add click handlers
        save_btn.add_click(lambda s, e: self._save_and_hide_footer())
        later_btn.add_click(lambda s, e: self._discard_and_hide_footer())

    def _save_and_hide_footer(self):
        """Save config and hide footer."""
        self._save_config()

    def _discard_and_hide_footer(self):
        """Hide footer without discarding - user will save later."""
        self._unsaved_infobar.is_open = False

    def _apply_saved_settings(self):
        """Apply saved theme and backdrop settings on startup."""
        prefs = get_preferences()

        theme = prefs.get("theme", "default")
        self._apply_theme(theme)

        backdrop = prefs.get("backdrop", "mica")
        if backdrop == "mica":
            mica = MicaBackdrop()
            mica.kind = MicaKind.BASE
            self._window.system_backdrop = mica
        elif backdrop == "mica_alt":
            mica = MicaBackdrop()
            mica.kind = MicaKind.BASE_ALT
            self._window.system_backdrop = mica
        elif backdrop == "acrylic":
            self._window.system_backdrop = DesktopAcrylicBackdrop()
        else:
            self._window.system_backdrop = None

    def _set_min_window_size(self, min_width: int, min_height: int):
        """Set minimum window size using WM_GETMINMAXINFO."""
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, self._window.title)
        if not hwnd:
            return

        # Get DPI scale
        scale = user32.GetDpiForWindow(hwnd) / 96.0
        self._min_w = int(min_width * scale)
        self._min_h = int(min_height * scale)

        WNDPROC = WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        user32.GetWindowLongPtrW.restype = c_void_p
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, c_int]
        user32.SetWindowLongPtrW.restype = c_void_p
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, c_int, c_void_p]
        user32.CallWindowProcW.restype = ctypes.c_longlong
        user32.CallWindowProcW.argtypes = [c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

        orig_proc = user32.GetWindowLongPtrW(hwnd, GWL_WNDPROC)

        def wnd_proc(h, msg, wp, lp):
            if msg == WM_GETMINMAXINFO:
                info = cast(lp, POINTER(MINMAXINFO)).contents
                info.ptMinTrackSize.x = self._min_w
                info.ptMinTrackSize.y = self._min_h
            return user32.CallWindowProcW(orig_proc, h, msg, wp, lp)

        self._wnd_proc = WNDPROC(wnd_proc)  # prevent GC
        user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, cast(self._wnd_proc, c_void_p))

    def _set_window_icon(self):
        try:
            self._window.app_window.set_icon(str(APP_ICON))
        except Exception as e:
            warning(f"Failed to set window icon: {e}")

    def _apply_theme(self, theme):
        """Apply theme to the application and title bar."""
        root = self._window.content.as_(FrameworkElement)
        title_bar = self._window.app_window.title_bar

        if theme == "light":
            root.requested_theme = ElementTheme.LIGHT
            title_bar.preferred_theme = TitleBarTheme.LIGHT
        elif theme == "dark":
            root.requested_theme = ElementTheme.DARK
            title_bar.preferred_theme = TitleBarTheme.DARK
        else:
            root.requested_theme = ElementTheme.DEFAULT
            title_bar.preferred_theme = TitleBarTheme.USE_DEFAULT_APP_MODE

    def _cache_nav_items(self):
        """Cache navigation items by their tag for later updates."""
        tag_to_translation = {
            "global": "nav_global",
            "bars": "nav_bars",
            "widgets": "nav_widgets",
            "styles": "nav_styles",
            "environment": "nav_environment",
            "backup": "nav_backup",
            "app_settings": "nav_settings",
        }

        # Menu items
        for i in range(self._nav_view.menu_items.size):
            try:
                item = self._nav_view.menu_items.get_at(i).as_(NavigationViewItem)
                tag = self._get_tag(item)
                if tag and tag in tag_to_translation:
                    self._nav_items[tag_to_translation[tag]] = item
            except Exception:
                pass

        # Footer items
        for i in range(self._nav_view.footer_menu_items.size):
            try:
                item = self._nav_view.footer_menu_items.get_at(i).as_(NavigationViewItem)
                tag = self._get_tag(item)
                if tag and tag in tag_to_translation:
                    self._nav_items[tag_to_translation[tag]] = item
            except Exception:
                pass  # Skip separators

    def update_nav_labels(self):
        """Update navigation labels with current language translations."""
        for translation_key, nav_item in self._nav_items.items():
            try:
                translated = t(translation_key)
                # Create a TextBlock with the translated text
                nav_item.content = UIFactory.create_text_block(translated, margin="0")
            except Exception as e:
                error(f"Error updating nav label {translation_key}: {e}")

        # Update window title too
        if self._window:
            self._window.title = t("app_title")

    def _get_tag(self, nav_item):
        """Extract tag string from navigation item."""
        try:
            # Cast to NavigationViewItem if needed
            if hasattr(nav_item, "as_"):
                nav_item = nav_item.as_(NavigationViewItem)
            tag_obj = nav_item.tag
            if tag_obj is None:
                return None
            return tag_obj.as_(IPropertyValue).get_string()
        except:
            return None

    def _on_nav_selection_changed(self, sender, args: NavigationViewSelectionChangedEventArgs):
        """Handle navigation selection changes."""
        # Skip navigation while still loading
        if self._is_loading:
            return

        try:
            selected = args.selected_item
            if not selected:
                return

            nav_item = selected.as_(NavigationViewItem)
            tag = self._get_tag(nav_item)
            if not tag:
                return

            routes = {
                "global": self._global_page.show,
                "bars": self._bars_page.show,
                "widgets": self._widgets_page.show,
                "styles": self._styles_page.show,
                "environment": self._env_page.show,
                "app_settings": self._app_settings_page.show,
            }

            handler = routes.get(tag)
            if handler:
                handler()
        except Exception as e:
            error(f"Navigation error: {e}", exc_info=True)

    def _on_nav_item_invoked(self, sender, args):
        """Handle footer button clicks (actions)."""
        try:
            item = args.invoked_item_container
            if not item:
                return

            nav_item = item.as_(NavigationViewItem)
            tag = self._get_tag(nav_item)
            if not tag:
                return

            actions = {
                "backup": self._backup_config,
            }

            handler = actions.get(tag)
            if handler:
                handler()
        except Exception as e:
            error(f"Footer action error: {e}", exc_info=True)

    def _save_config(self):
        """Save configuration to disk - only saves what has changed."""
        try:
            saved_something = False

            # Only save styles if styles changed
            if self._unsaved_styles:
                # Try Monaco editor (WebView2) first
                if self._styles_webview:
                    try:

                        def save_styles_content(content):
                            if content:
                                self._config_manager.save_styles(content)

                        # Use callback pattern to get content and save
                        self._styles_webview.execute_script_async("getContent()").completed = lambda op, status: (
                            save_styles_content(json.loads(op.get_results())) if status.value == 1 else None
                        )
                        saved_something = True
                    except Exception as e:
                        error(f"Error saving styles from Monaco: {e}")
                # Fallback to legacy TextBox
                elif self._styles_editor:
                    self._config_manager.save_styles(self._styles_editor.text)
                    saved_something = True

            # Only save config if config changed
            if self._unsaved_config:
                result = self._config_manager.save_config()
                if result:
                    saved_something = True
                else:
                    return

            if saved_something:
                self.mark_saved()
        except Exception as e:
            error(f"Save error: {e}", exc_info=True)

    def mark_unsaved(self, change_type="config", current_styles=None):
        """Mark unsaved changes, checking if content actually differs from original.

        Args:
            change_type: "config" for config changes, "styles" for CSS changes
            current_styles: Current CSS content (required for styles comparison)
        """
        if change_type == "styles":
            if current_styles is not None:
                self._unsaved_styles = self._config_manager.has_styles_changed(current_styles)
            else:
                self._unsaved_styles = True
        else:
            self._unsaved_config = self._config_manager.has_config_changed()

        self._unsaved_changes = self._unsaved_config or self._unsaved_styles
        self._update_save_button_style()

    def mark_saved(self):
        """Mark that changes have been saved and reset save button style."""
        self._unsaved_changes = False
        self._unsaved_styles = False
        self._unsaved_config = False
        self._update_save_button_style()

    def _update_save_button_style(self):
        """Show or hide the unsaved changes InfoBar."""
        if self._unsaved_infobar is None:
            return
        try:
            if self._unsaved_changes:
                self._unsaved_infobar.is_open = True
            else:
                self._unsaved_infobar.is_open = False
        except Exception as e:
            error(f"Error updating InfoBar visibility: {e}")

    def _on_window_closed(self, sender, args):
        """Handle window close event - show dialog if unsaved changes."""
        if self._unsaved_changes:
            # Prevent close and show dialog
            args.handled = True
            self._show_unsaved_dialog()

    def _show_unsaved_dialog(self):
        """Show unsaved changes dialog."""
        template = load_xaml("dialogs/UnsavedChangesDialog.xaml")
        dialog_xaml = template.format(
            title=UIFactory.escape_xml(t("unsaved_title")),
            primary=UIFactory.escape_xml(t("unsaved_save")),
            secondary=UIFactory.escape_xml(t("unsaved_dont_save")),
            close=UIFactory.escape_xml(t("unsaved_cancel")),
            body=UIFactory.escape_xml(t("unsaved_message")),
        )
        dialog = self.create_dialog(dialog_xaml)

        def on_primary(s, e):
            # Save and close
            self._save_config()
            self._window.close()

        def on_secondary(s, e):
            # Discard and close
            self._unsaved_changes = False
            self._window.close()

        dialog.add_primary_button_click(on_primary)
        dialog.add_secondary_button_click(on_secondary)
        dialog.show_async()

    def _backup_config(self):
        """Backup config folder as a zip file."""

        file_buffer = ctypes.create_unicode_buffer(260)
        file_buffer.value = f"yasb_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = ctypes.windll.user32.GetActiveWindow()
        ofn.lpstrFilter = "ZIP Archive (*.zip)\0*.zip\0"
        ofn.lpstrFile = ctypes.cast(file_buffer, wintypes.LPWSTR)
        ofn.nMaxFile = 260
        ofn.lpstrTitle = "Export Config"
        ofn.Flags = OFN_EXPLORER | OFN_OVERWRITEPROMPT
        ofn.lpstrDefExt = "zip"

        if ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn)):
            self._config_manager.export_config(file_buffer.value)

    def apply_editor_font(self, font_name):
        """Apply font to all code editors (CSS and YAML)."""
        try:
            # Apply to Monaco styles editor if it exists
            if self._styles_webview:
                js_font = json.dumps(font_name)
                self._styles_webview.execute_script_async(f"setFont({js_font}, null)")
            # Fallback to legacy TextBox
            elif self._styles_editor:
                font_family = FontFamily(font_name)
                self._styles_editor.font_family = font_family
        except Exception as e:
            error(f"Error applying editor font: {e}")

    def apply_editor_font_size(self, font_size):
        """Apply font size to all code editors (CSS and YAML)."""
        try:
            # Apply to Monaco styles editor if it exists
            if self._styles_webview:
                self._styles_webview.execute_script_async(f"setFont(null, {font_size})")
            # Fallback to legacy TextBox
            elif self._styles_editor:
                self._styles_editor.font_size = font_size
        except Exception as e:
            error(f"Error applying editor font size: {e}")

    def apply_editor_theme(self, theme):
        """Apply theme to all code editors (CSS and YAML).

        Args:
            theme: 'auto', 'light', or 'dark'
        """
        try:
            # Determine actual theme if 'auto'
            if theme == "auto":
                prefs = get_preferences()
                app_theme = prefs.get("theme", "default") if prefs else "default"
                if app_theme == "light":
                    actual_theme = "light"
                elif app_theme == "dark":
                    actual_theme = "dark"
                else:
                    # Follow system - default to dark
                    actual_theme = "dark"
            else:
                actual_theme = theme

            # Apply to Monaco styles editor
            if self._styles_webview:
                js_theme = json.dumps(actual_theme)
                self._styles_webview.execute_script_async(f"setTheme({js_theme})")
        except Exception as e:
            error(f"Error applying editor theme: {e}")

    @override
    def get_xaml_type(self, type: Union[TypeName, Tuple[str, TypeKind]]) -> IXamlType:
        return self._provider.get_xaml_type(type)

    @override
    def get_xaml_type_by_full_name(self, full_name: str) -> IXamlType:
        return self._provider.get_xaml_type_by_full_name(full_name)

    @override
    def get_xmlns_definitions(self) -> Array[XmlnsDefinition]:
        return self._provider.get_xmlns_definitions()
