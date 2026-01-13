"""
App settings page for YASB GUI.

Manages theme, backdrop, and language settings.
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime

from core.constants import (
    APP_DATA_DIR,
    APP_ICON,
    APP_VERSION,
    GITHUB_YASB,
    GITHUB_YASB_GUI,
    IS_EXECUTABLE,
    WEBVIEW_CACHE_DIR,
    YASB_SITE,
)
from core.localization import get_instance as get_localization
from core.localization import t
from core.logger import error
from core.preferences import get_preferences
from core.updater import app_updater, updater
from core.win32_types import FONTENUMPROC, LOGFONT  # ENUMLOGFONTEXW and NEWTEXTMETRICW used by FONTENUMPROC
from ui.controls import UIFactory
from ui.loader import load_xaml
from winrt.windows.foundation import IPropertyValue, Uri
from winui3.microsoft.ui.composition.systembackdrops import MicaKind
from winui3.microsoft.ui.xaml import FrameworkElement, Visibility
from winui3.microsoft.ui.xaml.controls import (
    Border,
    ComboBox,
    ComboBoxItem,
    Expander,
    FontIcon,
    Grid,
    HyperlinkButton,
    Image,
    Page,
    ProgressBar,
    StackPanel,
    TextBlock,
)
from winui3.microsoft.ui.xaml.markup import XamlReader
from winui3.microsoft.ui.xaml.media import DesktopAcrylicBackdrop, MicaBackdrop
from winui3.microsoft.ui.xaml.media.imaging import BitmapImage


def get_monospace_fonts():
    """Get list of monospace fonts installed on system."""
    fonts = set()

    def enum_font_callback(lpelfe, lpntme, font_type, lparam):
        try:
            # Check if it's a fixed-pitch font (bit 0 of tmPitchAndFamily is 0 for fixed pitch)
            pitch_and_family = lpntme.contents.tmPitchAndFamily
            is_fixed_pitch = (pitch_and_family & 0x01) == 0

            if is_fixed_pitch:
                face_name = lpelfe.contents.elfLogFont.lfFaceName
                if face_name and not face_name.startswith("@"):
                    fonts.add(face_name)
        except:
            pass
        return 1  # Continue enumeration

    try:
        gdi32 = ctypes.windll.gdi32
        user32 = ctypes.windll.user32

        hdc = user32.GetDC(0)

        # Set up LOGFONT to enumerate all fonts
        lf = LOGFONT()
        lf.lfCharSet = 1  # DEFAULT_CHARSET
        lf.lfPitchAndFamily = 0  # Enumerate all, we filter in callback
        lf.lfFaceName = ""

        callback = FONTENUMPROC(enum_font_callback)
        gdi32.EnumFontFamiliesExW(hdc, ctypes.byref(lf), callback, 0, 0)

        user32.ReleaseDC(0, hdc)
    except Exception as e:
        error(f"Font enumeration error: {e}")

    # If enumeration failed or returned empty, use fallback
    if not fonts:
        fonts = {
            "Cascadia Code",
            "Cascadia Mono",
            "Consolas",
            "Courier New",
            "JetBrains Mono",
            "Fira Code",
            "Source Code Pro",
            "Lucida Console",
        }

    return sorted(fonts)


class AppSettingsPage:
    """Manages the App Settings page."""

    def __init__(self, app):
        self._app = app
        self._loc = get_localization()
        self._prefs = get_preferences()
        self._language_codes = []
        self._available_fonts = []
        self._ui = UIFactory()

    def show(self):
        """Display the app settings page."""
        try:
            page = XamlReader.load(load_xaml("pages/AppSettingsPage.xaml")).as_(Page)
            root = page.content.as_(FrameworkElement)
            main_panel = root.find_name("MainPanel").as_(StackPanel)

            # Page title
            main_panel.children.append(self._ui.create_page_title(t("settings_title")))

            # App Update card
            app_update_card = self._create_app_update_card()
            main_panel.children.append(app_update_card)

            # Language setting card
            language_selector = self._ui.create_simple_combobox()
            available_languages = self._loc.get_available_languages()
            current_language = self._prefs.get("language", "en")
            self._language_codes = list(available_languages.keys())

            for code, name in available_languages.items():
                item = self._ui.create_combobox_item(name, code)
                language_selector.items.append(item)

            for i, code in enumerate(self._language_codes):
                if code == current_language:
                    language_selector.selected_index = i
                    break

            language_card = self._create_settings_card(
                "\ue8c1",  # Globe icon
                t("settings_language"),
                t("settings_language_restart"),
                language_selector,
            )
            main_panel.children.append(language_card)

            # Theme setting card
            theme_selector = self._ui.create_simple_combobox()
            theme_selector.items.append(self._ui.create_combobox_item(t("settings_theme_default"), "default"))
            theme_selector.items.append(self._ui.create_combobox_item(t("settings_theme_light"), "light"))
            theme_selector.items.append(self._ui.create_combobox_item(t("settings_theme_dark"), "dark"))

            current_theme = self._get_current_theme()
            theme_tags = ["default", "light", "dark"]
            for i, tag in enumerate(theme_tags):
                if tag == current_theme:
                    theme_selector.selected_index = i
                    break

            theme_card = self._create_settings_card(
                "\ue790",  # Color palette icon
                t("settings_theme"),
                t("settings_theme_description"),
                theme_selector,
            )
            main_panel.children.append(theme_card)

            # Backdrop setting card
            backdrop_selector = self._ui.create_simple_combobox()
            backdrop_selector.items.append(self._ui.create_combobox_item(t("settings_backdrop_mica"), "mica"))
            backdrop_selector.items.append(self._ui.create_combobox_item(t("settings_backdrop_mica_alt"), "mica_alt"))
            backdrop_selector.items.append(self._ui.create_combobox_item(t("settings_backdrop_acrylic"), "acrylic"))

            current_backdrop = self._get_current_backdrop()
            backdrop_tags = ["mica", "mica_alt", "acrylic"]
            for i, tag in enumerate(backdrop_tags):
                if tag == current_backdrop:
                    backdrop_selector.selected_index = i
                    break

            backdrop_card = self._create_settings_card(
                "\ue81e",  # Window icon
                t("settings_backdrop"),
                t("settings_backdrop_description"),
                backdrop_selector,
            )
            main_panel.children.append(backdrop_card)

            # Editor Settings Expander
            editor_expander = self._create_editor_settings_expander()
            main_panel.children.append(editor_expander)

            # Widget Schema Database card
            schema_card = self._create_schema_update_card()
            main_panel.children.append(schema_card)

            # Cache card
            cache_card = self._create_cache_card()
            main_panel.children.append(cache_card)

            # About expander
            about_expander = self._create_about_expander(APP_VERSION)
            main_panel.children.append(about_expander)

            # Event handlers
            language_selector.add_selection_changed(self._on_language_changed)
            theme_selector.add_selection_changed(self._on_theme_changed)
            backdrop_selector.add_selection_changed(self._on_backdrop_changed)

            self._app._content_area.content = page
        except Exception as e:
            error(f"App settings page error: {e}", exc_info=True)

    def _create_settings_card(self, icon, title, description, control):
        """Create a settings card using shared XAML template."""
        card = XamlReader.load(load_xaml("components/SettingsCard.xaml")).as_(Border)
        grid = card.child.as_(Grid)
        icon_el = grid.find_name("IconGlyph").as_(FontIcon)
        title_el = grid.find_name("TitleText").as_(TextBlock)
        desc_el = grid.find_name("DescriptionText").as_(TextBlock)
        container = grid.find_name("ControlContainer").as_(StackPanel)

        if icon_el:
            icon_el.glyph = icon
        title_el.text = UIFactory.escape_xml(title)
        desc_el.text = UIFactory.escape_xml(description)
        container.children.append(control)
        return card

    def _create_about_expander(self, version):
        """Create an about expander using shared XAML template."""
        expander = XamlReader.load(load_xaml("components/AboutExpander.xaml")).as_(Expander)

        icon_uri = APP_ICON.as_uri()
        copyright_text = f"© {datetime.now().year} AmN"

        header_title = expander.find_name("HeaderTitle").as_(TextBlock)
        header_subtitle = expander.find_name("HeaderSubtitle").as_(TextBlock)
        header_version = expander.find_name("HeaderVersion").as_(TextBlock)
        icon_img = expander.find_name("IconImage").as_(Image)

        header_title.text = "YASB GUI"
        header_subtitle.text = t("settings_yasb_config_tool")
        header_version.text = f"v{version}"
        icon_img.source = BitmapImage(Uri(icon_uri))

        expander.find_name("YasbSiteLabel").as_(TextBlock).text = (
            t("settings_yasb_site") if t("settings_yasb_site") != "settings_yasb_site" else "Website"
        )
        expander.find_name("YasbRepoLabel").as_(TextBlock).text = t("settings_yasb_repo")
        expander.find_name("YasbGuiRepoLabel").as_(TextBlock).text = t("settings_yasb_gui_repo")
        expander.find_name("VersionLabel").as_(TextBlock).text = t("settings_app_version")
        expander.find_name("VersionValue").as_(TextBlock).text = f"v{version}"
        expander.find_name("CopyrightLabel").as_(TextBlock).text = t("settings_app_copyright")
        expander.find_name("CopyrightValue").as_(TextBlock).text = copyright_text

        yasb_link = expander.find_name("YasbRepoLink").as_(HyperlinkButton)
        yasb_gui_link = expander.find_name("YasbGuiRepoLink").as_(HyperlinkButton)
        yasb_site_link = expander.find_name("YasbSiteLink").as_(HyperlinkButton)

        # Set content via TextBlock to satisfy IInspectable
        yasb_link.content = UIFactory.create_text_block(GITHUB_YASB, margin="0")
        yasb_gui_link.content = UIFactory.create_text_block(GITHUB_YASB_GUI, margin="0")
        yasb_site_link.content = UIFactory.create_text_block(YASB_SITE, margin="0")

        yasb_link.add_click(lambda s, e: webbrowser.open("https://github.com/amnweb/yasb"))
        yasb_gui_link.add_click(lambda s, e: webbrowser.open("https://github.com/amnweb/yasb-gui"))
        yasb_site_link.add_click(lambda s, e: webbrowser.open("https://yasb.dev"))

        return expander

    def _create_editor_settings_expander(self):
        """Create the editor settings expander with font, size, and theme options."""
        expander = XamlReader.load(load_xaml("components/EditorSettingsExpander.xaml")).as_(Expander)

        # Set header text
        header_title = expander.find_name("HeaderTitle").as_(TextBlock)
        header_subtitle = expander.find_name("HeaderSubtitle").as_(TextBlock)
        header_title.text = t("settings_editor_settings")
        header_subtitle.text = t("settings_editor_settings_description")

        content_panel = expander.find_name("ContentPanel").as_(StackPanel)

        # Editor Theme setting
        theme_selector = self._ui.create_simple_combobox()
        theme_selector.items.append(self._ui.create_combobox_item(t("settings_editor_theme_auto"), "auto"))
        theme_selector.items.append(self._ui.create_combobox_item(t("settings_editor_theme_light"), "light"))
        theme_selector.items.append(self._ui.create_combobox_item(t("settings_editor_theme_dark"), "dark"))

        current_editor_theme = self._prefs.get("editor_theme", "auto")
        theme_tags = ["auto", "light", "dark"]
        for i, tag in enumerate(theme_tags):
            if tag == current_editor_theme:
                theme_selector.selected_index = i
                break

        theme_card = self._create_settings_card(
            "\ue790",  # Color palette icon
            t("settings_editor_theme"),
            t("settings_editor_theme_description"),
            theme_selector,
        )
        content_panel.children.append(theme_card)

        # Editor Font setting
        font_selector = self._ui.create_simple_combobox()
        font_selector.min_width = 200
        self._available_fonts = get_monospace_fonts()
        current_font = self._prefs.get("editor_font", "Cascadia Code")

        selected_idx = 0
        for i, font_name in enumerate(self._available_fonts):
            item = self._ui.create_combobox_item(font_name, font_name)
            font_selector.items.append(item)
            if font_name == current_font:
                selected_idx = i

        font_selector.selected_index = selected_idx

        font_card = self._create_settings_card(
            "\ue8d2",  # Font icon
            t("settings_editor_font"),
            t("settings_editor_font_description"),
            font_selector,
        )
        content_panel.children.append(font_card)

        # Editor Font Size setting
        font_size_selector = self._ui.create_simple_combobox()
        self._available_font_sizes = list(range(10, 33))  # 10 to 32
        current_size = self._prefs.get("editor_font_size", 13)

        selected_size_idx = 0
        for i, size in enumerate(self._available_font_sizes):
            item = self._ui.create_combobox_item(str(size), str(size))
            font_size_selector.items.append(item)
            if size == current_size:
                selected_size_idx = i

        font_size_selector.selected_index = selected_size_idx

        font_size_card = self._create_settings_card(
            "\ue8e9",  # Font size icon
            t("settings_editor_font_size"),
            t("settings_editor_font_size_description"),
            font_size_selector,
        )
        content_panel.children.append(font_size_card)

        # Event handlers
        theme_selector.add_selection_changed(self._on_editor_theme_changed)
        font_selector.add_selection_changed(self._on_font_changed)
        font_size_selector.add_selection_changed(self._on_font_size_changed)

        return expander

    def _on_language_changed(self, sender, args):
        """Handle language change."""
        try:
            combo = sender.as_(ComboBox)
            idx = combo.selected_index
            if 0 <= idx < len(self._language_codes):
                lang_code = self._language_codes[idx]
                previous = self._prefs.get("language", "en")
                if lang_code != previous:
                    self._prefs.set("language", lang_code)
                    self._show_language_restart_dialog()
        except Exception as e:
            error(f"Language change error: {e}")

    def _show_language_restart_dialog(self):
        """Notify the user that a restart is required for language changes."""
        try:
            dialog_template = load_xaml("dialogs/LanguageRestartDialog.xaml")
            dialog_xaml = dialog_template.format(
                title=UIFactory.escape_xml(t("settings_language_restart_required_title")),
                primary=UIFactory.escape_xml(t("settings_language_restart_required_action")),
                body=UIFactory.escape_xml(t("settings_language_restart_required_body")),
            )
            dialog = self._app.create_dialog(dialog_xaml)
            dialog.show_async()
        except Exception as e:
            error(f"Language restart dialog error: {e}")

    def _get_tag(self, item):
        """Get tag string from ComboBoxItem."""
        try:
            return item.tag.as_(IPropertyValue).get_string()
        except:
            return str(item.tag) if item.tag else ""

    def _get_current_theme(self):
        """Get current theme from settings."""
        return self._prefs.get("theme", "default")

    def _get_current_backdrop(self):
        """Get current backdrop from settings."""
        return self._prefs.get("backdrop", "mica")

    def _on_theme_changed(self, sender, args):
        """Handle theme change."""
        try:
            combo = sender.as_(ComboBox)
            selected = combo.selected_item
            if not selected:
                return

            item = selected.as_(ComboBoxItem)
            tag = self._get_tag(item)

            # Save to settings
            self._prefs.set("theme", tag)

            # Apply theme (this also updates caption button colors)
            self._app._apply_theme(tag)
        except Exception as e:
            error(f"Theme change error: {e}")

    def _on_backdrop_changed(self, sender, args):
        """Handle backdrop change."""
        try:
            combo = sender.as_(ComboBox)
            selected = combo.selected_item
            if not selected:
                return

            item = selected.as_(ComboBoxItem)
            tag = self._get_tag(item)
            current = self._get_current_backdrop()

            if tag != current:
                # Save to settings
                self._prefs.set("backdrop", tag)
                # Reload page first to start the transition effect
                self.show()
                # Apply backdrop during/after the page transition
                self._apply_backdrop(tag)
        except Exception as e:
            error(f"Backdrop change error: {e}")

    def _apply_backdrop(self, tag):
        """Apply backdrop setting to window."""
        window = self._app._window

        # Create the new backdrop first, then apply it
        # This avoids the flash from setting to None
        if tag == "mica":
            backdrop = MicaBackdrop()
            backdrop.kind = MicaKind.BASE
            window.system_backdrop = backdrop
        elif tag == "mica_alt":
            backdrop = MicaBackdrop()
            backdrop.kind = MicaKind.BASE_ALT
            window.system_backdrop = backdrop
        elif tag == "acrylic":
            window.system_backdrop = DesktopAcrylicBackdrop()

    def _on_font_changed(self, sender, args):
        """Handle editor font change."""
        try:
            combo = sender.as_(ComboBox)
            idx = combo.selected_index
            if 0 <= idx < len(self._available_fonts):
                font_name = self._available_fonts[idx]

                # Save to settings
                self._prefs.set("editor_font", font_name)

                # Apply to any open editors
                self._app.apply_editor_font(font_name)
        except Exception as e:
            error(f"Font change error: {e}")

    def _on_font_size_changed(self, sender, args):
        """Handle editor font size change."""
        try:
            combo = sender.as_(ComboBox)
            idx = combo.selected_index
            if 0 <= idx < len(self._available_font_sizes):
                font_size = self._available_font_sizes[idx]

                # Save to settings
                self._prefs.set("editor_font_size", font_size)

                # Apply to any open editors
                self._app.apply_editor_font_size(font_size)
        except Exception as e:
            error(f"Font size change error: {e}")

    def _on_editor_theme_changed(self, sender, args):
        """Handle editor theme change."""
        try:
            combo = sender.as_(ComboBox)
            selected = combo.selected_item
            if not selected:
                return

            item = selected.as_(ComboBoxItem)
            tag = self._get_tag(item)

            # Save to settings
            self._prefs.set("editor_theme", tag)

            # Apply to any open editors
            self._app.apply_editor_theme(tag)
        except Exception as e:
            error(f"Editor theme change error: {e}")

    def _create_schema_update_card(self):
        """Create a settings card for updating widget schema database."""
        update_btn = self._ui.create_styled_button(t("common_update_now"), padding="12,6")
        update_btn.min_width = 120

        last_updated, age = updater.get_last_update_info()

        if last_updated:
            updated_str = self._format_datetime(last_updated)
            status_text = t("settings_uptodate") if age < 7 else t("settings_outdated").format(days=age)
            description = t("settings_update_db_desc").format(date=updated_str, status=status_text)
        else:
            description = t("settings_update_db_none")

        card = self._create_settings_card(
            "\ue895",  # Sync/update icon
            t("settings_update_db"),
            description,
            update_btn,
        )

        # Get reference to description text and its parent panel
        grid = card.child.as_(Grid)
        desc_panel = grid.children.get_at(1).as_(StackPanel)
        desc_text = desc_panel.find_name("DescriptionText").as_(TextBlock)

        # Create progress bar (hidden by default, will replace description when visible)
        progress_bar = XamlReader.load(
            """<ProgressBar xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                Width="200" Value="0" Minimum="0" Maximum="100" Height="16"
                Visibility="Collapsed" HorizontalAlignment="Left" Margin="0,0,0,0"/>"""
        ).as_(ProgressBar)
        desc_panel.children.append(progress_bar)

        def on_update_click(sender, args):
            """Handle schema update button click."""
            try:
                update_btn.is_enabled = False
                desc_text.visibility = Visibility.COLLAPSED
                progress_bar.visibility = Visibility.VISIBLE
                progress_bar.value = 0

                def progress_callback(current, total, message):
                    """Update progress bar from background thread."""

                    def update_progress():
                        progress_bar.value = (current / total) * 100

                    self._app._window.dispatcher_queue.try_enqueue(update_progress)

                def do_update():
                    success, message = updater.update_sync(progress_callback)

                    # Update UI on main thread
                    def update_ui():
                        progress_bar.visibility = Visibility.COLLAPSED
                        desc_text.visibility = Visibility.VISIBLE
                        update_btn.is_enabled = True
                        # Refresh the page to show new info
                        self.show()

                    self._app._window.dispatcher_queue.try_enqueue(update_ui)

                # Run in background thread
                thread = threading.Thread(target=do_update, daemon=True)
                thread.start()

            except Exception as e:
                error(f"Schema update error: {e}")
                progress_bar.visibility = Visibility.COLLAPSED
                desc_text.visibility = Visibility.VISIBLE
                update_btn.is_enabled = True

        update_btn.add_click(on_update_click)
        return card

    def _format_datetime(self, dt: datetime, prefix: str = "") -> str:
        """Format datetime with relative date descriptions.

        Args:
            dt: datetime object to format
            prefix: Optional prefix string (e.g., 'Last checked: ')

        Returns:
            Formatted string like:
            - 'Last checked: Today, 14:30'
            - 'Last checked: Yesterday, 14:30'
            - 'Last checked: 2 days ago'
            - 'Last checked: Jan 13, 14:30' (for older dates)
        """
        now = datetime.now()
        days_diff = (now.date() - dt.date()).days

        if days_diff == 0:
            # Today - show time
            time_str = f"{t('settings_today')}, {dt.strftime('%H:%M')}"
        elif days_diff == 1:
            # Yesterday - show time
            time_str = f"{t('settings_yesterday')}, {dt.strftime('%H:%M')}"
        elif 2 <= days_diff <= 6:
            # 2-6 days ago - just show relative days
            time_str = t("settings_days_ago").format(days=days_diff)
        else:
            # 7+ days - show abbreviated date with time
            time_str = dt.strftime("%b %d, %H:%M")

        return f"{prefix}{time_str}" if prefix else time_str

    def _get_last_check_time(self) -> str:
        """Get formatted last check time string."""
        from core.updater import UPDATE_METADATA_FILE

        if not UPDATE_METADATA_FILE.exists():
            return t("settings_never_checked")

        try:
            with open(UPDATE_METADATA_FILE, "r") as f:
                metadata = json.load(f)
                last_check_time = metadata.get("last_app_update_check")
                if last_check_time:
                    check_dt = datetime.fromisoformat(last_check_time)
                    return self._format_datetime(check_dt, f"{t('settings_last_checked')}: ")
        except:
            pass

        return t("settings_never_checked")

    def _create_app_update_card(self):
        """Create app update card."""
        # Check if running from source (not executable)
        if not IS_EXECUTABLE:
            # Show disabled card with explanation
            disabled_text = t("settings_update_disabled_source")
            buttons_panel = self._ui.create_stack_panel(spacing=8, orientation="Horizontal")

            check_btn = self._ui.create_styled_button(t("settings_check_updates"), padding="12,6")
            check_btn.min_width = 120
            check_btn.is_enabled = False

            buttons_panel.children.append(check_btn)

            card = self._create_settings_card(
                "\ue895",  # Update/sync icon
                t("settings_app_update"),
                disabled_text,
                buttons_panel,
            )
            return card

        # Check if update available
        available_update = app_updater.get_available_update()

        # Buttons panel (horizontal)
        buttons_panel = self._ui.create_stack_panel(spacing=8, orientation="Horizontal")

        # If update available: show release notes + install button
        # If no update: show check button
        check_btn = None
        install_btn = None
        notes_btn = None

        if available_update:
            version, url = available_update
            release_url = f"https://github.com/amnweb/yasb-gui/releases/tag/v{version}"

            # Release notes button (left)
            notes_btn = HyperlinkButton()
            notes_btn.content = UIFactory.create_text_block(t("settings_release_notes"), margin="0")
            notes_btn.navigate_uri = Uri(release_url)
            buttons_panel.children.append(notes_btn)

            # Install button (right)
            install_btn = self._ui.create_styled_button(
                t("settings_download_update"), style="AccentButtonStyle", padding="12,6"
            )
            install_btn.min_width = 140
            buttons_panel.children.append(install_btn)

            description = t("settings_update_available")
        else:
            # Check button
            check_btn = self._ui.create_styled_button(t("settings_check_updates"), padding="12,6")
            check_btn.min_width = 120
            buttons_panel.children.append(check_btn)

            description = self._get_last_check_time()

        card = self._create_settings_card(
            "\ue895",  # Update/sync icon
            t("settings_app_update"),
            description,
            buttons_panel,
        )

        # Get reference to description text and its parent panel
        grid = card.child.as_(Grid)
        desc_panel = grid.children.get_at(1).as_(StackPanel)
        desc_text = desc_panel.find_name("DescriptionText").as_(TextBlock)

        # Create progress bar (hidden by default, will replace description when visible)
        progress_bar = XamlReader.load(
            """<ProgressBar xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                Width="200" Value="0" Minimum="0" Maximum="100" Height="16"
                Visibility="Collapsed" HorizontalAlignment="Left" Margin="0,0,0,0"/>"""
        ).as_(ProgressBar)
        desc_panel.children.append(progress_bar)

        # Event handlers
        if check_btn:

            def on_check_click(sender, args):
                """Handle check for updates button click."""
                try:
                    check_btn.is_enabled = False
                    desc_text.visibility = Visibility.COLLAPSED
                    progress_bar.visibility = Visibility.VISIBLE
                    progress_bar.is_indeterminate = True
                    progress_bar.show_paused = False
                    progress_bar.show_error = False

                    def do_check():
                        import time

                        # Show progress for 3 seconds before checking
                        time.sleep(3)

                        # Check for updates (skip rate limit for manual checks)
                        success, message, version, url = app_updater.check_for_update(skip_rate_limit=True)

                        def update_ui():
                            progress_bar.visibility = Visibility.COLLAPSED
                            desc_text.visibility = Visibility.VISIBLE
                            check_btn.is_enabled = True

                            # Check if update was found
                            new_update = app_updater.get_available_update()

                            if new_update:
                                # Add badge if not already added
                                if not self._app._update_badge_added:
                                    self._app._add_update_badge()
                                # Refresh entire page to show install button and release notes
                                self.show()
                            else:
                                # Just update timestamp text
                                desc_text.text = self._get_last_check_time()

                        self._app._window.dispatcher_queue.try_enqueue(update_ui)

                    threading.Thread(target=do_check, daemon=True).start()

                except Exception as e:
                    error(f"Check update error: {e}")
                    progress_bar.visibility = Visibility.COLLAPSED
                    desc_text.visibility = Visibility.VISIBLE
                    check_btn.is_enabled = True

            check_btn.add_click(on_check_click)

        # Install button handler (if available)
        if install_btn:

            def on_install_click(sender, args):
                """Handle download and install button click."""
                try:
                    version, url = available_update
                    install_btn.is_enabled = False
                    if notes_btn:
                        notes_btn.is_enabled = False

                    # Hide description, show indeterminate progress
                    desc_text.visibility = Visibility.COLLAPSED
                    progress_bar.visibility = Visibility.VISIBLE
                    progress_bar.is_indeterminate = True

                    def do_download():
                        import time

                        time.sleep(1)  # Brief delay before starting download

                        # Switch to determinate progress
                        def start_download_progress():
                            progress_bar.is_indeterminate = False
                            progress_bar.value = 0

                        self._app._window.dispatcher_queue.try_enqueue(start_download_progress)

                        def progress_callback(downloaded, total, msg):
                            def update_progress():
                                if total > 0:
                                    progress_bar.value = (downloaded / total) * 100

                            self._app._window.dispatcher_queue.try_enqueue(update_progress)

                        success, message, installer_path = app_updater.download_update(url, progress_callback)

                        def after_download():
                            if success and installer_path:
                                # Install and close app
                                install_success, install_msg = app_updater.install_update(installer_path)
                                if install_success:
                                    # Close the app - installer will update it
                                    self._app._window.close()
                                else:
                                    progress_bar.visibility = Visibility.COLLAPSED
                                    desc_text.visibility = Visibility.VISIBLE
                                    install_btn.is_enabled = True
                                    if notes_btn:
                                        notes_btn.is_enabled = True
                            else:
                                progress_bar.visibility = Visibility.COLLAPSED
                                desc_text.visibility = Visibility.VISIBLE
                                install_btn.is_enabled = True
                                if notes_btn:
                                    notes_btn.is_enabled = True

                        self._app._window.dispatcher_queue.try_enqueue(after_download)

                    threading.Thread(target=do_download, daemon=True).start()

                except Exception as e:
                    error(f"Install update error: {e}")
                    progress_bar.visibility = Visibility.COLLAPSED
                    desc_text.visibility = Visibility.VISIBLE
                    install_btn.is_enabled = True
                    if notes_btn:
                        notes_btn.is_enabled = True

            install_btn.add_click(on_install_click)

        return card

    def _get_cache_size(self):
        """Calculate total cache size in bytes."""
        total_size = 0
        for dir_path in [APP_DATA_DIR, WEBVIEW_CACHE_DIR]:
            if os.path.exists(dir_path):
                for dirpath, dirnames, filenames in os.walk(dir_path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            total_size += os.path.getsize(filepath)
                        except (OSError, IOError):
                            pass
        return total_size

    def _format_size(self, size_bytes):
        """Format bytes into human-readable size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def _create_cache_card(self):
        """Create a settings card for clearing cache."""
        # Calculate cache size
        cache_size = self._get_cache_size()
        size_text = self._format_size(cache_size)

        # Create clear button
        clear_btn = self._ui.create_styled_button(t("settings_clear_cache"), padding="12,6")
        clear_btn.min_width = 120

        card = self._create_settings_card(
            "\ue74d",  # Delete icon
            t("settings_cache"),
            f"{t('settings_cache_desc')} • {size_text}",
            clear_btn,
        )

        def on_clear_click(sender, args):
            """Handle clear cache button click with confirmation."""
            dialog_xaml = f"""<ContentDialog 
                xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                Title="{UIFactory.escape_xml(t("settings_clear_cache_confirm_title"))}"
                PrimaryButtonText="{UIFactory.escape_xml(t("settings_clear_cache"))}"
                CloseButtonText="{UIFactory.escape_xml(t("common_cancel"))}"
                DefaultButton="Close">
                <TextBlock TextWrapping="Wrap" Text="{UIFactory.escape_xml(t("settings_clear_cache_confirm_desc"))}" />
            </ContentDialog>"""

            dialog = self._app.create_dialog(dialog_xaml)

            def on_dialog_closed(d, result):
                if result.result == 1:  # Primary button clicked
                    self._clear_cache_and_restart()

            dialog.add_closed(on_dialog_closed)
            dialog.show_async()

        clear_btn.add_click(on_clear_click)
        return card

    def _clear_cache_and_restart(self):
        """Clear all cache directories and restart the app."""
        # Get the current executable path
        if getattr(sys, "frozen", False):
            exe_path = sys.executable
        else:
            exe_path = sys.executable
            script_path = os.path.abspath(sys.argv[0])

        # Clear directories - delete files individually to skip locked ones
        for dir_path in [APP_DATA_DIR, WEBVIEW_CACHE_DIR]:
            if os.path.exists(dir_path):
                for root, dirs, files in os.walk(dir_path, topdown=False):
                    for name in files:
                        filepath = os.path.join(root, name)
                        try:
                            os.remove(filepath)
                        except (OSError, PermissionError):
                            pass  # Skip locked files (e.g., app.log)
                    for name in dirs:
                        dirpath = os.path.join(root, name)
                        try:
                            os.rmdir(dirpath)
                        except (OSError, PermissionError):
                            pass  # Skip non-empty or locked dirs

        # Restart the app
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([exe_path])
            else:
                subprocess.Popen([exe_path, script_path])
        except Exception as e:
            error(f"Failed to restart app: {e}")

        # Exit current instance
        self._app._window.close()
