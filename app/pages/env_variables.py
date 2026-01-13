"""
Environment variables page for YASB GUI.

Manages .env file for YASB configuration.
"""

import os
import webbrowser
from pathlib import Path

from core.localization import t
from core.logger import error
from ui.controls import UIFactory
from ui.loader import load_xaml
from winui3.microsoft.ui.xaml import FrameworkElement, Thickness
from winui3.microsoft.ui.xaml.controls import Button, CheckBox, Grid, Page, StackPanel, TextBox
from winui3.microsoft.ui.xaml.markup import XamlReader

# Wiki URL for environment variables documentation
ENV_WIKI_URL = "https://github.com/amnweb/yasb/wiki/Configuration#environment-variables-support"

# Common YASB environment variables with defaults and descriptions
COMMON_VARIABLES = [
    ("YASB_FONT_ENGINE", "native", "env_font_engine_desc"),
    ("YASB_WEATHER_API_KEY", "", "env_weather_api_desc"),
    ("YASB_GITHUB_TOKEN", "", "env_github_token_desc"),
    ("YASB_WEATHER_LOCATION", "", "env_weather_location_desc"),
    ("QT_SCREEN_SCALE_FACTORS", "1", "env_qt_scale_desc"),
    ("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough", "env_qt_rounding_desc"),
]


class EnvVariablesPage:
    """Manages the Environment Variables page."""

    def __init__(self, app):
        self._app = app
        self._config_manager = app._config_manager
        self._ui = UIFactory()
        self._main_panel = None
        self._variables_panel = None
        self._env_path = self._get_env_path()
        self._variables = []

    def _get_env_path(self):
        """Get path to .env file."""
        config_home = os.getenv("YASB_CONFIG_HOME", ".config\\yasb")
        config_dir = os.path.join(Path.home(), config_home)
        return os.path.join(config_dir, ".env")

    def _load_env_file(self):
        """Load variables from .env file."""
        self._variables = []
        if not os.path.isfile(self._env_path):
            return

        try:
            with open(self._env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or "=" not in line:
                        if line.startswith("#") and "=" in line:
                            line = line[1:].strip()
                            self._parse_variable_line(line, enabled=False)
                        continue

                    if line.startswith("#"):
                        line = line[1:].strip()
                        self._parse_variable_line(line, enabled=False)
                    else:
                        self._parse_variable_line(line, enabled=True)
        except Exception as e:
            error(f"Error loading .env file: {e}")

    def _parse_variable_line(self, line, enabled):
        """Parse single variable line."""
        if "=" not in line:
            return
        parts = line.split("=", 1)
        if len(parts) == 2:
            name = parts[0].strip()
            value = parts[1].strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            self._variables.append([name, value, enabled])

    def _save_env_file(self):
        """Save variables to .env file."""
        try:
            lines = []
            for name, value, enabled in self._variables:
                if not name.strip():
                    continue
                if " " in value:
                    value = f'"{value}"'
                line = f"{name}={value}"
                if not enabled:
                    line = f"# {line}"
                lines.append(line)

            with open(self._env_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
                if lines:
                    f.write("\n")
            return True
        except Exception as e:
            error(f"Error saving .env file: {e}")
            return False

    def _create_env_file(self):
        """Create an empty .env file."""
        try:
            os.makedirs(os.path.dirname(self._env_path), exist_ok=True)
            with open(self._env_path, "w", encoding="utf-8") as f:
                f.write("# YASB Environment Variables\n")
            return True
        except Exception as e:
            error(f"Error creating .env file: {e}")
            return False

    def _delete_env_file(self):
        """Delete the .env file."""
        try:
            if os.path.isfile(self._env_path):
                os.remove(self._env_path)
            return True
        except Exception as e:
            error(f"Error deleting .env file: {e}")
            return False

    def show(self):
        """Display the environment variables page."""
        try:
            self._app._loading = True

            page = XamlReader.load(load_xaml("pages/EnvVariablesPage.xaml")).as_(Page)
            root = page.content.as_(FrameworkElement)
            self._main_panel = root.find_name("MainPanel").as_(StackPanel)

            self._main_panel.children.append(self._ui.create_page_title(t("env_title")))

            if os.path.isfile(self._env_path):
                self._show_variables_ui()
            else:
                self._show_no_file_ui()

            self._add_footer_section()

            self._app._content_area.content = page
            self._app._loading = False
        except Exception as e:
            error(f"Environment variables page error: {e}", exc_info=True)
            self._app._loading = False

    def _show_no_file_ui(self):
        """Show UI when .env file doesn't exist."""
        info_expander = self._ui.create_expander(t("env_no_file"), t("env_no_file_desc"))
        info_expander.horizontal_alignment = 3  # Stretch
        info_expander.is_expanded = True

        info_panel = self._ui.create_stack_panel(spacing=12)

        info_panel.children.append(self._ui.create_text_block(t("env_create_desc"), margin="0,0,0,8", wrap=True))

        create_btn = self._ui.create_styled_button(t("env_create_file"), style="AccentButtonStyle")
        create_btn.add_click(lambda s, e: self._on_create_file())
        info_panel.children.append(create_btn)

        info_expander.content = info_panel
        self._main_panel.children.append(info_expander)

    def _show_variables_ui(self):
        """Show UI when .env file exists."""
        self._load_env_file()

        vars_expander = self._ui.create_expander(t("env_variables"), t("env_variables_desc"))
        vars_expander.horizontal_alignment = 3
        vars_expander.is_expanded = True

        self._variables_panel = self._ui.create_stack_panel(spacing=8)
        self._rebuild_variables_list()

        vars_expander.content = self._variables_panel
        self._main_panel.children.append(vars_expander)

        self._add_common_variables_section()

        self._add_danger_zone_section()

    def _add_common_variables_section(self):
        """Add the common variables expander."""
        common_expander = self._ui.create_expander(t("env_common"), t("env_common_desc"))
        common_expander.horizontal_alignment = 3

        common_panel = self._ui.create_stack_panel(spacing=8)

        for var_name, default_value, desc_key in COMMON_VARIABLES:
            exists = any(v[0] == var_name for v in self._variables)
            row = self._ui.create_stack_panel(spacing=4, orientation="Horizontal")

            add_btn = self._ui.create_icon_button("\ue710", padding="8,4")
            add_btn.is_enabled = not exists
            add_btn.add_click(lambda s, e, n=var_name, v=default_value: self._add_common_variable(n, v))

            name_text = self._ui.create_text_block(var_name, margin="8,0,0,0")
            desc_text = self._ui.create_text_block(
                t(desc_key), style="CaptionTextBlockStyle", margin="8,0,0,0", secondary=True
            )

            row.children.append(add_btn)
            row.children.append(name_text)
            row.children.append(desc_text)
            common_panel.children.append(row)

        common_expander.content = common_panel
        self._main_panel.children.append(common_expander)

    def _add_danger_zone_section(self):
        """Add the danger zone expander."""
        danger_expander = self._ui.create_expander(t("env_danger_zone"), t("env_danger_zone_desc"))
        danger_expander.horizontal_alignment = 3

        danger_panel = self._ui.create_stack_panel(spacing=8)

        delete_btn = self._ui.create_danger_button(t("env_delete_file"))
        delete_btn.add_click(lambda s, e: self._on_delete_file())
        danger_panel.children.append(delete_btn)

        danger_expander.content = danger_panel
        self._main_panel.children.append(danger_expander)

    def _add_footer_section(self):
        """Add footer with file path, wiki link, and restart notice."""
        path_panel = self._ui.create_stack_panel(spacing=4, orientation="Horizontal")
        path_panel.margin = Thickness(0, 16, 0, 0)
        path_panel.children.append(self._ui.create_font_icon("\ue8b7", font_size=14, secondary=True))
        path_panel.children.append(self._ui.create_path_text(self._env_path))
        self._main_panel.children.append(path_panel)

        link_panel = self._ui.create_stack_panel(spacing=4, orientation="Horizontal")
        link_panel.margin = Thickness(0, 8, 0, 0)
        link_btn = self._ui.create_hyperlink_button(t("env_wiki_link"))
        link_btn.add_click(lambda s, e: webbrowser.open(ENV_WIKI_URL))
        link_panel.children.append(link_btn)
        self._main_panel.children.append(link_panel)

        notice = self._ui.create_info_bar(t("env_restart_notice"), margin="0,16,0,0")
        self._main_panel.children.append(notice)

    def _rebuild_variables_list(self):
        """Rebuild the variables list UI."""
        self._variables_panel.children.clear()

        for idx, (name, value, enabled) in enumerate(self._variables):
            row = self._create_variable_row(idx, name, value, enabled)
            self._variables_panel.children.append(row)

        add_row = self._ui.create_stack_panel(spacing=8, orientation="Horizontal")
        add_btn = self._ui.create_icon_text_button("\ue710", t("env_add_variable"))
        add_btn.add_click(lambda s, e: self._add_variable())
        add_row.children.append(add_btn)
        self._variables_panel.children.append(add_row)

    def _create_variable_row(self, idx, name, value, enabled):
        """Create a row for a single variable."""
        row = XamlReader.load(load_xaml("components/EnvVariableRow.xaml")).as_(Grid)

        checkbox = row.find_name("EnableCheckbox").as_(CheckBox)
        checkbox.is_checked = enabled
        checkbox.add_checked(lambda s, e, i=idx: self._update_variable_enabled(i, True))
        checkbox.add_unchecked(lambda s, e, i=idx: self._update_variable_enabled(i, False))

        name_box = row.find_name("NameTextbox").as_(TextBox)
        name_box.text = name
        name_box.add_text_changed(lambda s, e, i=idx: self._update_variable_name(i, name_box.text))

        value_box = row.find_name("ValueTextbox").as_(TextBox)
        value_box.text = value
        value_box.add_text_changed(lambda s, e, i=idx: self._update_variable_value(i, value_box.text))

        delete_btn = row.find_name("DeleteButton").as_(Button)
        delete_btn.add_click(lambda s, e, i=idx: self._delete_variable(i))

        return row

    def _update_variable_enabled(self, idx, enabled):
        """Update variable enabled state."""
        if idx < len(self._variables):
            self._variables[idx][2] = enabled
            self._save_env_file()

    def _update_variable_name(self, idx, name):
        """Update variable name."""
        if idx < len(self._variables):
            self._variables[idx][0] = name
            self._save_env_file()

    def _update_variable_value(self, idx, value):
        """Update variable value."""
        if idx < len(self._variables):
            self._variables[idx][1] = value
            self._save_env_file()

    def _delete_variable(self, idx):
        """Delete a variable."""
        if idx < len(self._variables):
            del self._variables[idx]
            self._save_env_file()
            self._rebuild_variables_list()

    def _add_variable(self):
        """Add a new empty variable."""
        self._variables.append(["", "", True])
        self._save_env_file()
        self._rebuild_variables_list()

    def _add_common_variable(self, name, default_value):
        """Add a common variable."""
        if any(v[0] == name for v in self._variables):
            return
        self._variables.append([name, default_value, True])
        self._save_env_file()
        self.show()  # Refresh to update common vars buttons

    def _on_create_file(self):
        """Handle create file button click."""
        if self._create_env_file():
            self.show()

    def _on_delete_file(self):
        """Handle delete file button click."""
        if self._delete_env_file():
            self._variables = []
            self.show()
