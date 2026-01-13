"""
Widget configuration page for YASB GUI.

Manages widget creation, deletion, and settings with card sections and context menu.
"""

import json
import re
import time
from ctypes import WinError
from types import SimpleNamespace

from core.code_editor import (
    dict_to_yaml,
    fix_yaml_indentation,
    format_yaml,
    get_code_editor_html_uri,
)
from core.constants import WEBVIEW_CACHE_DIR
from core.editor.editor_context_menu import monaco_context_menu
from core.localization import t
from core.logger import error, warning
from core.preferences import get_preferences
from core.widget_helpers import (
    delete_disabled_widget,
    delete_widget,
    disable_widget,
    duplicate_widget,
    enable_widget,
    extract_widget_options,
    move_widget,
    move_widget_order,
    parse_yaml,
    save_widget_options,
)
from ui.controls import UIFactory
from ui.loader import load_xaml
from webview2.microsoft.web.webview2.core import CoreWebView2Environment
from winrt.windows.foundation import AsyncStatus, IAsyncAction, IAsyncOperation, Uri
from winrt.windows.ui import Color
from winui3.microsoft.ui.xaml import FocusState, FrameworkElement, Thickness, Visibility
from winui3.microsoft.ui.xaml.controls import (
    Border,
    Button,
    ComboBox,
    ContentDialogButton,
    FontIcon,
    Grid,
    InfoBar,
    MenuFlyout,
    MenuFlyoutItem,
    MenuFlyoutSeparator,
    Page,
    StackPanel,
    TextBlock,
    TextBox,
    WebView2,
)
from winui3.microsoft.ui.xaml.markup import XamlReader
from winui3.microsoft.ui.xaml.media import TranslateTransform
from winui3.microsoft.ui.xaml.media.animation import Storyboard


def get_widget_registry():
    """Load widget registry from JSON."""
    from core.constants import REGISTRY_FILE

    path = REGISTRY_FILE
    registry = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                widgets_data = data.get("widgets", {})
                for key, val in widgets_data.items():
                    registry[key] = SimpleNamespace(**val)
        except Exception as e:
            error(f"Failed to load registry: {e}")
    return registry


class WidgetsPage:
    """Manages widgets configuration with card sections and context menu."""

    def __init__(self, app):
        self._app = app
        self._config_manager = app._config_manager
        self._ui = UIFactory()
        self._add_widget_data = None
        self._widget_registry = get_widget_registry()
        self._sections_panel = None
        self._widget_panels = {}
        self._section_expanders = {}  # Store expanders by position
        self._disabled_widgets_panel = None

    def reload_registry(self):
        """Reload widget registry from disk."""
        self._widget_registry = get_widget_registry()

    def show(self):
        """Display widgets configuration page."""
        try:
            page = XamlReader.load(load_xaml("pages/WidgetsPage.xaml")).as_(Page)
            content = page.content.as_(FrameworkElement)

            page_title = content.find_name("PageTitle").as_(TextBlock)
            select_bar_label = content.find_name("SelectBarLabel").as_(TextBlock)
            bar_selector = content.find_name("BarSelector").as_(ComboBox)
            self._sections_panel = content.find_name("SectionsPanel").as_(StackPanel)

            page_title.text = t("widgets_title")
            select_bar_label.text = t("bars_selection")

            self._create_sections()

            bars = self._config_manager.get_bars()
            bar_names = list(bars.keys())

            for bar_name in bar_names:
                bar_selector.items.append(self._ui.create_combobox_item(bar_name))

            self._app._widgets_selected_bar = bar_names[0] if bar_names else None

            def on_bar_selected(sender, e):
                idx = bar_selector.selected_index
                if 0 <= idx < len(bar_names):
                    self._app._widgets_selected_bar = bar_names[idx]
                    self._load_widgets()

            bar_selector.add_selection_changed(on_bar_selected)
            self._setup_widget_data()

            if bar_selector.items.size > 0:
                bar_selector.selected_index = 0

            self._load_widgets()
            self._app._content_area.content = page
        except Exception as e:
            error(f"Widgets page error: {e}", exc_info=True)

    def _create_icon(self, glyph_entity):
        """Create a FontIcon using a glyph entity (e.g., &#xE710;)."""
        xaml = f'''<FontIcon xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                      Glyph="{glyph_entity}" FontFamily="Segoe Fluent Icons"/>'''
        return XamlReader.load(xaml).as_(FontIcon)

    def _create_sections(self):
        """Create expander sections for Left, Center, Right positions."""
        positions = [
            ("left", t("widgets_left"), t("widgets_left_desc")),
            ("center", t("widgets_center"), t("widgets_center_desc")),
            ("right", t("widgets_right"), t("widgets_right_desc")),
        ]

        for pos_key, title, desc in positions:
            section = self._ui.create_expander(title, desc)

            widgets_container = self._ui.create_stack_panel(spacing=4)
            section.content = widgets_container

            menu = MenuFlyout()
            add_item = MenuFlyoutItem()
            add_item.text = t("widgets_add")
            add_item.icon = self._create_icon("&#xE710;")  # Add
            add_item.add_click(lambda s, e, p=pos_key: self._show_add_widget_dialog(p))
            menu.items.append(add_item)
            section.context_flyout = menu

            self._widget_panels[pos_key] = widgets_container
            self._section_expanders[pos_key] = section
            self._sections_panel.children.append(section)

        disabled_expander = self._ui.create_expander(t("widgets_disabled"), t("widgets_disabled_desc"))
        disabled_expander.margin = Thickness(0, 16, 0, 0)

        self._disabled_widgets_panel = self._ui.create_stack_panel(spacing=4)
        disabled_expander.content = self._disabled_widgets_panel

        self._sections_panel.children.append(disabled_expander)

    def _load_widgets(self):
        """Load widgets for all positions."""
        try:
            bar_name = self._app._widgets_selected_bar
            if not bar_name:
                return

            bar = self._config_manager.get_bar(bar_name)
            if not bar:
                return

            widgets_data = bar.get("widgets", {})

            for position in ["left", "center", "right"]:
                container = self._widget_panels.get(position)
                if not container:
                    continue

                container.children.clear()
                widget_list = widgets_data.get(position) or []

                if not widget_list:
                    empty_text = self._ui.create_text_block(t("widgets_empty_hint"), None)
                    empty_text.opacity = 0.6
                    container.children.append(empty_text)
                    continue

                for idx, widget_name in enumerate(widget_list):
                    item = self._create_widget_item(widget_name, position, idx, len(widget_list))
                    container.children.append(item)

            # Load disabled widgets (widgets in config but not in any bar position)
            self._load_disabled_widgets(bar)

        except Exception as e:
            error(f"Load widgets error: {e}", exc_info=True)

    def _load_disabled_widgets(self, bar):
        """Load widgets that exist in config but are not in the current bar."""
        if not self._disabled_widgets_panel:
            return

        self._disabled_widgets_panel.children.clear()

        widgets_data = bar.get("widgets", {})
        active_widgets = set()
        for position in ["left", "center", "right"]:
            for widget_name in widgets_data.get(position) or []:
                active_widgets.add(widget_name)

        all_widgets = self._config_manager.get_widgets() or {}

        disabled_widgets = [name for name in all_widgets.keys() if name not in active_widgets]

        if not disabled_widgets:
            empty_text = self._ui.create_text_block(t("widgets_disabled_empty"), None)
            empty_text.opacity = 0.6
            self._disabled_widgets_panel.children.append(empty_text)
            return

        for widget_name in disabled_widgets:
            item = self._create_disabled_widget_item(widget_name)
            self._disabled_widgets_panel.children.append(item)

    def _create_disabled_widget_item(self, widget_name):
        """Create a disabled widget item with dimmed appearance."""
        widget = self._config_manager.get_widget(widget_name)
        widget_type = widget.get("type", "unknown") if widget else "unknown"

        category = "Unknown"
        description = ""
        for wid, info in self._widget_registry.items():
            if info.type_path == widget_type:
                category = info.category
                description = info.description
                break

        subtext = f"{category} · {description}" if description else category

        btn_xaml = f'''<Button xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                        HorizontalAlignment="Stretch" HorizontalContentAlignment="Left"
                        Padding="12,8" Opacity="0.7">
            <StackPanel Spacing="2">
                <TextBlock Text="{UIFactory.escape_xml(widget_name)}" FontWeight="SemiBold"/>
                <TextBlock Text="{UIFactory.escape_xml(subtext)}" FontSize="11" Opacity="0.6" TextWrapping="Wrap"/>
            </StackPanel>
        </Button>'''
        btn = XamlReader.load(btn_xaml).as_(Button)

        menu = self._create_disabled_widget_context_menu(widget_name)
        btn.context_flyout = menu

        btn.add_click(lambda s, e, name=widget_name: self._show_edit_widget_dialog(name, None))

        return btn

    def _create_disabled_widget_context_menu(self, widget_name):
        """Create context menu for a disabled widget."""
        menu = MenuFlyout()

        # Add to position options
        move_icons = {
            "left": "&#xE72B;",
            "center": "&#xE8E3;",
            "right": "&#xE72A;",
        }
        for pos_key, pos_label in [
            ("left", t("widgets_left")),
            ("center", t("widgets_center")),
            ("right", t("widgets_right")),
        ]:
            add_item = MenuFlyoutItem()
            add_item.text = f"{t('widgets_add_to')} {pos_label}"
            add_item.icon = self._create_icon(move_icons.get(pos_key, "&#xE710;"))
            add_item.add_click(lambda s, e, p=pos_key, n=widget_name: self._enable_widget(n, p))
            menu.items.append(add_item)

        menu.items.append(MenuFlyoutSeparator())

        edit_item = MenuFlyoutItem()
        edit_item.text = t("widgets_edit")
        edit_item.icon = self._create_icon("&#xE70F;")
        edit_item.add_click(lambda s, e: self._show_edit_widget_dialog(widget_name, None))
        menu.items.append(edit_item)

        rename_item = MenuFlyoutItem()
        rename_item.text = t("widgets_rename")
        rename_item.icon = self._create_icon("&#xE8AC;")
        rename_item.add_click(lambda s, e: self._show_rename_widget_dialog(widget_name))
        menu.items.append(rename_item)

        delete_item = MenuFlyoutItem()
        delete_item.text = t("widgets_delete")
        delete_item.icon = self._create_icon("&#xE74D;")
        delete_item.add_click(lambda s, e: self._delete_disabled_widget(widget_name))
        menu.items.append(delete_item)

        return menu

    def _enable_widget(self, widget_name, position):
        """Enable a widget by adding it to a bar position."""
        if enable_widget(self._config_manager, self._app._widgets_selected_bar, widget_name, position):
            self._app.mark_unsaved()
            self._load_widgets()

    def _delete_disabled_widget(self, widget_name):
        """Delete a disabled widget from config entirely."""
        if delete_disabled_widget(self._config_manager, widget_name):
            self._app.mark_unsaved()
            self._load_widgets()

    def _create_widget_item(self, widget_name, position, index, total):
        """Create a widget item with name, category · description, and up/down arrow buttons."""
        widget = self._config_manager.get_widget(widget_name)
        widget_type = widget.get("type", "unknown") if widget else "unknown"

        category, description = "Unknown", ""
        for wid, info in self._widget_registry.items():
            if info.type_path == widget_type:
                category, description = info.category, info.description
                break

        container = XamlReader.load(load_xaml("components/WidgetItemRow.xaml")).as_(Grid)
        container.find_name("NameText").as_(TextBlock).text = widget_name
        container.find_name("SubText").as_(TextBlock).text = f"{category} · {description}" if description else category

        main_btn = container.find_name("MainButton").as_(Button)
        up_btn = container.find_name("UpButton").as_(Button)
        down_btn = container.find_name("DownButton").as_(Button)

        main_btn.context_flyout = self._create_widget_context_menu(widget_name, position, index, total)

        up_btn.add_click(lambda s, e: self._animate_and_move_widget(widget_name, position, -1, index))
        down_btn.add_click(lambda s, e: self._animate_and_move_widget(widget_name, position, 1, index))

        if index == 0:
            up_btn.is_enabled, up_btn.opacity = False, 0.6
        if index == total - 1:
            down_btn.is_enabled, down_btn.opacity = False, 0.6

        return container

    def _create_widget_context_menu(self, widget_name, position, index, total):
        """Create context menu for a widget."""
        menu = MenuFlyout()

        edit_item = MenuFlyoutItem()
        edit_item.text = t("widgets_edit")
        edit_item.icon = self._create_icon("&#xE70F;")
        edit_item.add_click(lambda s, e: self._show_edit_widget_dialog(widget_name, position))
        menu.items.append(edit_item)

        menu.items.append(MenuFlyoutSeparator())

        add_item = MenuFlyoutItem()
        add_item.text = t("widgets_add")
        add_item.icon = self._create_icon("&#xE710;")
        add_item.add_click(lambda s, e: self._show_add_widget_dialog(position))
        menu.items.append(add_item)

        menu.items.append(MenuFlyoutSeparator())

        if index > 0:
            up_item = MenuFlyoutItem()
            up_item.text = t("widgets_move_up")
            up_item.icon = self._create_icon("&#xE74A;")  # Up arrow
            up_item.add_click(lambda s, e: self._move_widget_order(widget_name, position, -1))
            menu.items.append(up_item)

        if index < total - 1:
            down_item = MenuFlyoutItem()
            down_item.text = t("widgets_move_down")
            down_item.icon = self._create_icon("&#xE74B;")  # Down arrow
            down_item.add_click(lambda s, e: self._move_widget_order(widget_name, position, 1))
            menu.items.append(down_item)

        if index > 0 or index < total - 1:
            menu.items.append(MenuFlyoutSeparator())

        # Move to position submenu items
        move_icons = {
            "left": "&#xE72B;",  # Back arrow
            "center": "&#xE8E3;",  # Align center
            "right": "&#xE72A;",  # Forward arrow
        }
        for pos_key, pos_label in [
            ("left", t("widgets_left")),
            ("center", t("widgets_center")),
            ("right", t("widgets_right")),
        ]:
            if pos_key != position:
                move_item = MenuFlyoutItem()
                move_item.text = f"{t('widgets_move_to')} {pos_label}"
                move_item.icon = self._create_icon(move_icons.get(pos_key, "&#xE8FD;"))
                move_item.add_click(lambda s, e, p=pos_key: self._move_widget(widget_name, position, p))
                menu.items.append(move_item)

        menu.items.append(MenuFlyoutSeparator())

        duplicate_item = MenuFlyoutItem()
        duplicate_item.text = t("widgets_duplicate")
        duplicate_item.icon = self._create_icon("&#xE8C8;")
        duplicate_item.add_click(lambda s, e: self._duplicate_widget(widget_name, position))
        menu.items.append(duplicate_item)

        rename_item = MenuFlyoutItem()
        rename_item.text = t("widgets_rename")
        rename_item.icon = self._create_icon("&#xE8AC;")
        rename_item.add_click(lambda s, e: self._show_rename_widget_dialog(widget_name))
        menu.items.append(rename_item)

        disable_item = MenuFlyoutItem()
        disable_item.text = t("widgets_disable")
        disable_item.icon = self._create_icon("&#xE711;")
        disable_item.add_click(lambda s, e: self._disable_widget(widget_name, position))
        menu.items.append(disable_item)

        delete_item = MenuFlyoutItem()
        delete_item.text = t("widgets_delete")
        delete_item.icon = self._create_icon("&#xE74D;")
        delete_item.add_click(lambda s, e: self._delete_widget(widget_name, position))
        menu.items.append(delete_item)

        return menu

    def _move_widget_order(self, widget_name, position, direction):
        """Move widget up or down in the list."""
        if move_widget_order(self._config_manager, self._app._widgets_selected_bar, widget_name, position, direction):
            self._app.mark_unsaved()
            self._load_widgets()

    def _animate_and_move_widget(self, widget_name, position, direction, current_index):
        """Move widget with smooth animation."""
        container = self._widget_panels.get(position)
        target_index = current_index + direction

        if not container or target_index < 0 or target_index >= container.children.size:
            self._move_widget_order(widget_name, position, direction)
            return

        try:
            current_item = container.children.get_at(current_index).as_(Grid)
            target_item = container.children.get_at(target_index).as_(Grid)
            current_tf = current_item.find_name("ContainerTransform").as_(TranslateTransform)
            target_tf = target_item.find_name("ContainerTransform").as_(TranslateTransform)

            if not (current_tf and target_tf):
                self._move_widget_order(widget_name, position, direction)
                return

            dist1 = (target_item.actual_height + 4) * direction
            dist2 = (current_item.actual_height + 4) * -direction

            def create_storyboard(to_value):
                xaml = f'<Storyboard xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"><DoubleAnimation Storyboard.TargetProperty="Y" To="{to_value}" Duration="0:0:0.2"/></Storyboard>'
                return XamlReader.load(xaml).as_(Storyboard)

            sb1, sb2 = create_storyboard(dist1), create_storyboard(dist2)
            sb1.add_completed(
                lambda s, e: (
                    setattr(current_tf, "y", 0),
                    setattr(target_tf, "y", 0),
                    self._move_widget_order(widget_name, position, direction),
                )
            )
            Storyboard.set_target(sb1.children.get_at(0), current_tf)
            Storyboard.set_target(sb2.children.get_at(0), target_tf)
            sb1.begin()
            sb2.begin()
        except Exception as e:
            error(f"Animation error: {e}", exc_info=True)
            self._move_widget_order(widget_name, position, direction)

    def _move_widget(self, widget_name, old_position, new_position):
        """Move widget to a different position."""
        if move_widget(self._config_manager, self._app._widgets_selected_bar, widget_name, old_position, new_position):
            self._app.mark_unsaved()
            self._load_widgets()

    def _duplicate_widget(self, widget_name, position):
        """Duplicate a widget."""
        if duplicate_widget(self._config_manager, self._app._widgets_selected_bar, widget_name, position):
            self._app.mark_unsaved()
            self._load_widgets()

    def _show_rename_widget_dialog(self, widget_name):
        """Show dialog to rename a widget."""
        try:
            # Validation pattern: only letters, numbers, underscore, hyphen
            valid_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

            dialog_template = load_xaml("dialogs/RenameWidgetDialog.xaml")
            dialog_xaml = dialog_template.format(
                title=UIFactory.escape_xml(t("widgets_rename_title")),
                primary=UIFactory.escape_xml(t("common_ok")),
                close=UIFactory.escape_xml(t("common_cancel")),
                name=UIFactory.escape_xml(widget_name),
                placeholder=UIFactory.escape_xml(t("widgets_rename_placeholder")),
            )

            dialog = self._app.create_dialog(dialog_xaml)

            content = dialog.content.as_(StackPanel)
            name_input = content.find_name("NameInput").as_(TextBox)
            error_text = content.find_name("ErrorText").as_(TextBlock)

            def validate_name():
                new_name = name_input.text.strip()
                if not new_name:
                    error_text.text = t("widgets_rename_invalid")
                    error_text.visibility = 0  # Visible
                    dialog.is_primary_button_enabled = False
                    return False
                if not valid_pattern.match(new_name):
                    error_text.text = t("widgets_rename_invalid")
                    error_text.visibility = 0  # Visible
                    dialog.is_primary_button_enabled = False
                    return False
                if new_name != widget_name and new_name in self._config_manager.get_widgets():
                    error_text.text = t("widgets_rename_exists")
                    error_text.visibility = 0  # Visible
                    dialog.is_primary_button_enabled = False
                    return False
                error_text.visibility = 1  # Collapsed
                dialog.is_primary_button_enabled = True
                return True

            def on_text_changed(sender, e):
                validate_name()

            name_input.add_text_changed(on_text_changed)

            def on_dialog_closed(sender, args):
                if args.result == ContentDialogButton.PRIMARY:
                    new_name = name_input.text.strip()
                    if new_name and new_name != widget_name and valid_pattern.match(new_name):
                        if self._config_manager.rename_widget(widget_name, new_name):
                            self._app.mark_unsaved()
                            self._load_widgets()

            dialog.add_closed(on_dialog_closed)
            dialog.show_async()

        except Exception as e:
            error(f"Rename widget dialog error: {e}", exc_info=True)

    def _disable_widget(self, widget_name, position):
        """Disable a widget by removing it from the bar (keeps config)."""
        if disable_widget(self._config_manager, self._app._widgets_selected_bar, widget_name, position):
            self._app.mark_unsaved()
            self._load_widgets()

    def _delete_widget(self, widget_name, position):
        """Delete a widget from bar and config."""
        if delete_widget(self._config_manager, self._app._widgets_selected_bar, widget_name, position):
            self._app.mark_unsaved()
            self._load_widgets()

    def _show_edit_widget_dialog(self, widget_name, position):
        """Show dialog to edit an existing widget."""
        widget = self._config_manager.get_widget(widget_name)
        if not widget:
            warning(f"Widget not found: {widget_name}")
            return
        self._show_widget_editor_dialog(
            widget_name=widget_name,
            widget_type=widget.get("type", "unknown"),
            options=widget.get("options", {}),
            position=position,
            is_new=False,
        )

    def _show_new_widget_dialog(self, widget_info, position):
        """Show dialog to configure a new widget before adding it."""
        # Generate unique name
        base_name = widget_info["id"]
        existing = self._config_manager.get_widgets()
        name = base_name
        counter = 1
        while name in existing:
            name = f"{base_name}_{counter}"
            counter += 1

        self._show_widget_editor_dialog(
            widget_name=name,
            widget_type=widget_info["type_path"],
            options=widget_info["defaults"].copy() if widget_info["defaults"] else {},
            position=position,
            is_new=True,
        )

    def _show_widget_editor_dialog(self, widget_name, widget_type, options, position, is_new):
        """Show dialog to edit or create a widget's options using Monaco editor.

        Args:
            widget_name: Current or proposed widget name
            widget_type: Full widget type path (e.g., "yasb.clock.ClockWidget")
            options: Widget options dict
            position: Bar position ("left", "center", "right") or None
            is_new: True if creating new widget, False if editing existing
        """
        try:
            self._app._loading = True

            # Options as YAML
            try:
                options_text = dict_to_yaml(options) if options else ""
            except Exception:
                options_text = str(options)

            # Validation pattern for widget names
            valid_name_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

            # Load dialog from XAML template
            dialog_template = load_xaml("dialogs/YamlEditorDialog.xaml")
            dialog_xaml = dialog_template.format(
                title=UIFactory.escape_xml(t("widgets_add_dialog_title") if is_new else t("widgets_edit")),
                save=UIFactory.escape_xml(t("common_add") if is_new else t("common_save")),
                cancel=UIFactory.escape_xml(t("common_cancel")),
                error_title=UIFactory.escape_xml(t("widgets_yaml_error_title")),
                name_label=UIFactory.escape_xml(t("widgets_name")),
                name=UIFactory.escape_xml(widget_name),
                type_label=UIFactory.escape_xml(t("widgets_type") + ":"),
            )
            dialog = self._app.create_dialog(dialog_xaml)

            # Get dialog elements
            dialog_content = dialog.content.as_(StackPanel)
            error_infobar = dialog_content.find_name("ErrorInfoBar").as_(InfoBar)
            name_input = dialog_content.find_name("NameInput").as_(TextBox)
            name_error = dialog_content.find_name("NameError").as_(TextBlock)
            type_text = dialog_content.find_name("TypeText").as_(TextBlock)
            options_label = dialog_content.find_name("OptionsLabel").as_(TextBlock)
            webview = dialog_content.find_name("EditorWebView").as_(WebView2)
            loading_overlay = dialog_content.find_name("LoadingOverlay").as_(Grid)
            editor_border = dialog_content.find_name("EditorBorder").as_(Border)

            type_text.text = widget_type
            options_label.text = t("widgets_options")

            # Name validation state
            editor_state_name = {"valid": True, "original_name": widget_name}

            def validate_name():
                """Validate the widget name and show/hide error."""
                new_name = name_input.text.strip()
                if not new_name:
                    name_error.text = t("widgets_rename_invalid")
                    name_error.visibility = Visibility.VISIBLE
                    editor_state_name["valid"] = False
                    return False
                if not valid_name_pattern.match(new_name):
                    name_error.text = t("widgets_rename_invalid")
                    name_error.visibility = Visibility.VISIBLE
                    editor_state_name["valid"] = False
                    return False
                # For edit: allow same name; for new: name must not exist
                existing_widgets = self._config_manager.get_widgets()
                if is_new:
                    if new_name in existing_widgets:
                        name_error.text = t("widgets_rename_exists")
                        name_error.visibility = Visibility.VISIBLE
                        editor_state_name["valid"] = False
                        return False
                else:
                    if new_name != widget_name and new_name in existing_widgets:
                        name_error.text = t("widgets_rename_exists")
                        name_error.visibility = Visibility.VISIBLE
                        editor_state_name["valid"] = False
                        return False
                name_error.visibility = Visibility.COLLAPSED
                editor_state_name["valid"] = True
                return True

            name_input.add_text_changed(lambda s, e: validate_name())

            # Get preferences for theme and font
            prefs = get_preferences()
            editor_font = prefs.get("editor_font", "Cascadia Code") if prefs else "Cascadia Code"
            editor_font_size = prefs.get("editor_font_size", 13) if prefs else 13
            editor_theme = prefs.get("editor_theme", "auto") if prefs else "auto"

            if editor_theme == "auto":
                app_theme = prefs.get("theme", "default") if prefs else "default"
                monaco_theme = "light" if app_theme == "light" else "dark"
            else:
                monaco_theme = editor_theme

            # Store editor state
            editor_state = {"content": options_text, "editor_ready": False, "loader_start_time": None}

            def init_editor_content():
                """Initialize editor with content after Monaco is ready."""
                try:
                    start_time = editor_state.get("loader_start_time") or time.time()
                    elapsed = time.time() - start_time
                    init_options = {
                        "theme": monaco_theme,
                        "language": "yaml",
                        "fontFamily": editor_font,
                        "fontSize": editor_font_size,
                        "content": options_text,
                        "focus": True,
                        "elapsedMs": int(elapsed * 1000),
                        "minTotalMs": 1000,
                    }
                    webview.execute_script_async(f"initEditor({json.dumps(init_options)})")
                except Exception as e:
                    error(f"WebView script error: {e}")

            def show_editor():
                """Show the editor and hide the loading overlay."""
                loading_overlay.visibility = Visibility.COLLAPSED
                editor_border.visibility = Visibility.VISIBLE

            def on_web_message(sender, args):
                """Handle messages from Monaco editor."""
                try:
                    msg = json.loads(args.web_message_as_json)
                    if msg.get("type") == "ready":
                        editor_state["editor_ready"] = True
                        init_editor_content()
                    elif msg.get("type") == "initialized":
                        show_editor()
                    elif msg.get("type") == "contentChanged":
                        editor_state["content"] = msg.get("content", editor_state["content"])
                    elif msg.get("type") == "format":
                        content = msg.get("content", "")
                        formatted, err = format_yaml(content)
                        if err:
                            error_infobar.message = err
                            error_infobar.is_open = True
                        else:
                            error_infobar.is_open = False
                            webview.execute_script_async(f"setFormattedContent({json.dumps(formatted)})")
                            editor_state["content"] = formatted
                    elif msg.get("type") == "fix_indentation":
                        content = msg.get("content", "")
                        fixed, err = fix_yaml_indentation(content, widget_type)
                        webview.execute_script_async(f"setFormattedContent({json.dumps(fixed)})")
                        editor_state["content"] = fixed
                        if err:
                            error_infobar.message = err
                            error_infobar.is_open = True
                        else:
                            error_infobar.is_open = False
                except Exception as e:
                    error(f"Web message error: {e}")

            webview.add_web_message_received(on_web_message)
            webview.add_navigation_completed(lambda s, a: None)

            self._app._loading = False

            def on_dialog_opened(sender, args):
                """Called when dialog is opened - initialize WebView2 properly."""
                editor_state["loader_start_time"] = time.time()
                env_op = CoreWebView2Environment.create_with_options_async("", WEBVIEW_CACHE_DIR, None)

                def on_env_created(op: IAsyncOperation, status: AsyncStatus):
                    if status == AsyncStatus.ERROR:
                        error(f"WebView2 environment creation failed: {WinError(op.error_code.value)}")
                        return
                    if status != AsyncStatus.COMPLETED:
                        return

                    env = op.get_results()
                    ensure_op = webview.ensure_core_webview2_with_environment_async(env)

                    def on_ensure_complete(ensure_op_inner: IAsyncAction, ensure_status: AsyncStatus):
                        if ensure_status == AsyncStatus.ERROR:
                            error(f"WebView2 ensure failed: {WinError(ensure_op_inner.error_code.value)}")
                            return
                        if ensure_status != AsyncStatus.COMPLETED:
                            return
                        webview.default_background_color = Color(a=255, r=25, g=26, b=28)

                        yaml_extra_items = [
                            (t("common_fix_indentation"), "&#xE90F;", "if(window.fixIndentation) fixIndentation();"),
                            (t("common_format_yaml"), "&#xE943;", "if(window.formatContent) formatContent();"),
                        ]
                        monaco_context_menu(webview, self._create_icon, t, yaml_extra_items)

                        html_uri = get_code_editor_html_uri()
                        webview.source = Uri(html_uri)

                    ensure_op.completed = on_ensure_complete

                env_op.completed = on_env_created

            def on_dialog_closing(sender, args):
                """Handle dialog closing - validate and save."""
                if args.result != ContentDialogButton.PRIMARY:
                    return

                try:
                    if not validate_name():
                        args.cancel = True
                        name_input.focus(FocusState.PROGRAMMATIC)
                        return

                    content = editor_state["content"]
                    webview.execute_script_async("clearError()")
                    new_name = name_input.text.strip()

                    # Parse and validate YAML
                    parsed, err = parse_yaml(content)
                    if err:
                        args.cancel = True
                        error_infobar.message = err
                        error_infobar.is_open = True
                        match = re.match(r"Line (\d+), Column (\d+):", err)
                        if match:
                            line, col = int(match.group(1)), int(match.group(2))
                            webview.execute_script_async(f"showError({line}, {col}, {json.dumps(err)})")
                        return

                    # Extract options (validate type if present)
                    new_options, extract_err = extract_widget_options(parsed, widget_type)
                    if extract_err:
                        args.cancel = True
                        error_infobar.message = extract_err
                        error_infobar.is_open = True
                        return

                    if is_new:
                        # Create new widget
                        bar = self._config_manager.get_bar(self._app._widgets_selected_bar)
                        if not bar:
                            args.cancel = True
                            error_infobar.message = "Bar not found"
                            error_infobar.is_open = True
                            return

                        if "widgets" not in self._config_manager.config:
                            self._config_manager.config["widgets"] = {}

                        self._config_manager.config["widgets"][new_name] = {
                            "type": widget_type,
                            "options": new_options,
                        }

                        if "widgets" not in bar:
                            bar["widgets"] = {"left": [], "center": [], "right": []}
                        if position not in bar["widgets"]:
                            bar["widgets"][position] = []

                        bar["widgets"][position].append(new_name)
                        self._app.mark_unsaved()

                        # Expand the section where widget was added
                        if position in self._section_expanders:
                            self._section_expanders[position].is_expanded = True
                    else:
                        # Update existing widget
                        widget = self._config_manager.get_widget(widget_name)
                        if widget:
                            widget["options"] = new_options
                            self._app.mark_unsaved()

                        # Handle rename
                        if new_name != widget_name:
                            if self._config_manager.rename_widget(widget_name, new_name):
                                self._app.mark_unsaved()

                    error_infobar.is_open = False
                    self._load_widgets()

                except Exception as e:
                    error(f"Save error: {e}")
                    args.cancel = True
                    error_infobar.message = str(e)
                    error_infobar.is_open = True

            dialog.add_opened(on_dialog_opened)
            dialog.add_closing(on_dialog_closing)
            dialog.show_async()

        except Exception as e:
            error(f"Show widget editor dialog error: {e}", exc_info=True)
            self._app._loading = False

    def _save_widget_options(self, widget_name, options_text):
        """Save widget options from dialog.

        Returns:
            tuple: (success: bool, error_message: str | None)
        """
        success, error_msg = save_widget_options(self._config_manager, widget_name, options_text)
        if success:
            self._app.mark_unsaved()
        return success, error_msg

    def _format_yaml_text(self, text):
        """Format YAML text and return result."""
        formatted, err = format_yaml(text)
        return formatted if not err else text

    def _setup_widget_data(self):
        """Setup widget data for add dialog."""
        try:
            all_widgets = []
            for widget_id, info in self._widget_registry.items():
                all_widgets.append(
                    {
                        "id": widget_id,
                        "name": info.name,
                        "category": info.category,
                        "description": info.description,
                        "type_path": info.type_path,
                        "defaults": getattr(info, "defaults", {}),
                    }
                )
            all_widgets.sort(key=lambda x: (x["category"], x["name"]))
            self._add_widget_data = {"all_widgets": all_widgets}
        except Exception as e:
            error(f"Setup widget data error: {e}", exc_info=True)

    def _show_add_widget_dialog(self, position):
        """Show the add widget dialog for a specific position."""
        try:
            data = self._add_widget_data
            all_widgets = data["all_widgets"]

            dialog_template = load_xaml("dialogs/AddWidgetDialog.xaml")
            dialog_xaml = dialog_template.format(
                title=UIFactory.escape_xml(t("widgets_add_dialog_title")),
                close=UIFactory.escape_xml(t("common_cancel")),
                position_label=UIFactory.escape_xml(t("widgets_position")),
                search_placeholder=UIFactory.escape_xml(t("widgets_search")),
            )
            dialog = self._app.create_dialog(dialog_xaml)

            dialog_content = dialog.content.as_(StackPanel)
            position_combo = dialog_content.find_name("PositionCombo").as_(ComboBox)
            search_box = dialog_content.find_name("SearchBox").as_(TextBox)
            widgets_list = dialog_content.find_name("WidgetsList").as_(StackPanel)
            widgets_list.horizontal_alignment = 3  # Stretch

            position_combo.items.append(self._ui.create_combobox_item(t("widgets_left"), "left"))
            position_combo.items.append(self._ui.create_combobox_item(t("widgets_center"), "center"))
            position_combo.items.append(self._ui.create_combobox_item(t("widgets_right"), "right"))

            # Set position based on which section triggered dialog
            pos_to_index = {"left": 0, "center": 1, "right": 2}
            position_combo.selected_index = pos_to_index.get(position, 0)

            def populate_widgets(filter_text=""):
                widgets_list.children.clear()
                filter_lower = filter_text.lower().strip()
                current_category = None

                for widget in all_widgets:
                    if filter_lower:
                        if (
                            filter_lower not in widget["name"].lower()
                            and filter_lower not in widget["category"].lower()
                            and filter_lower not in widget["description"].lower()
                        ):
                            continue

                    if widget["category"] != current_category:
                        current_category = widget["category"]
                        header = self._ui.create_text_block(current_category, "BodyStrongTextBlockStyle")
                        widgets_list.children.append(header)

                    btn = Button()
                    btn.horizontal_alignment = 3  # Stretch
                    btn.horizontal_content_alignment = 3  # Stretch
                    btn.padding = Thickness(12, 8, 12, 8)

                    content_stack = self._ui.create_stack_panel(spacing=0)
                    content_stack.horizontal_alignment = 3  # Stretch
                    name_tb = self._ui.create_text_block(widget["name"], style=None, margin="0")
                    try:
                        name_tb.font_weight = "SemiBold"
                    except Exception:
                        pass

                    desc_tb = self._ui.create_text_block(widget["description"][:60], style=None, margin="0")
                    desc_tb.font_size = 11
                    desc_tb.opacity = 0.7
                    desc_tb.text_wrapping = 1  # Wrap

                    content_stack.children.append(name_tb)
                    content_stack.children.append(desc_tb)
                    btn.content = content_stack

                    def on_widget_click(s, e, w=widget):
                        dialog.hide()
                        self._add_widget_to_bar(w, position_combo.selected_index)

                    btn.add_click(on_widget_click)
                    widgets_list.children.append(btn)

            populate_widgets()
            search_box.add_text_changed(lambda s, e: populate_widgets(search_box.text))
            dialog.show_async()

        except Exception as e:
            error(f"Show add widget dialog error: {e}", exc_info=True)

    def _add_widget_to_bar(self, widget_info, position_idx):
        """Add a widget to the selected bar - opens editor first, only saves on confirm."""
        positions = ["left", "center", "right"]
        position = positions[position_idx] if position_idx < len(positions) else "left"

        self._show_new_widget_dialog(widget_info, position)
