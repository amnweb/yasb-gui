"""
Bar configuration page for YASB GUI.

Manages bar creation, deletion, and settings.
"""

import ctypes
import re
import webbrowser
from collections import Counter, OrderedDict
from ctypes import wintypes

from core.localization import t
from core.logger import error, warning
from core.win32_types import DISPLAYCONFIG_PATH_INFO, DISPLAYCONFIG_TARGET_DEVICE_NAME
from ui.controls import UIFactory
from ui.loader import load_xaml
from winui3.microsoft.ui.xaml import FrameworkElement, Visibility
from winui3.microsoft.ui.xaml.controls import (
    Button,
    ComboBox,
    MenuFlyout,
    MenuFlyoutItem,
    MenuFlyoutSeparator,
    Page,
    StackPanel,
    TextBlock,
    TextBox,
)
from winui3.microsoft.ui.xaml.markup import XamlReader


def get_monitors():
    """Get monitor names using DisplayConfig API."""
    try:
        user32 = ctypes.windll.user32

        num_paths = wintypes.UINT()
        num_modes = wintypes.UINT()
        user32.GetDisplayConfigBufferSizes(2, ctypes.byref(num_paths), ctypes.byref(num_modes))

        paths = (DISPLAYCONFIG_PATH_INFO * num_paths.value)()
        modes = (ctypes.c_byte * (num_modes.value * 64))()
        user32.QueryDisplayConfig(2, ctypes.byref(num_paths), paths, ctypes.byref(num_modes), modes, None)

        raw_monitors = []
        for path in paths:
            info = DISPLAYCONFIG_TARGET_DEVICE_NAME()
            info.type = 2  # DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME
            info.size = ctypes.sizeof(info)
            info.adapterLUID.LowPart = path.targetLUID.LowPart
            info.adapterLUID.HighPart = path.targetLUID.HighPart
            info.id = path.targetId

            if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info)) == 0 and info.monitorFriendlyDeviceName:
                raw_monitors.append(info.monitorFriendlyDeviceName)

        counts = Counter(raw_monitors)
        name_indices = {}
        result = []
        for name in raw_monitors:
            if counts[name] > 1:
                name_indices[name] = name_indices.get(name, 0) + 1
                result.append(f"{name} ({name_indices[name]})")
            else:
                result.append(name)
        return result
    except Exception as e:
        error(f"Monitor detection error: {e}", exc_info=True)
        return []


class BarsPage:
    """Manages bar configuration."""

    def __init__(self, app):
        self._app = app
        self._config_manager = app._config_manager
        self._ui = UIFactory()
        self._settings_panel = None
        self._bar_selector = None
        self._add_btn = None
        self._selected_bar = None

    def show(self):
        """Display the bars configuration page."""
        try:
            page = XamlReader.load(load_xaml("pages/BarsPage.xaml")).as_(Page)
            content = page.content.as_(FrameworkElement)
            page_title = content.find_name("PageTitle").as_(TextBlock)
            select_bar_label = content.find_name("SelectBarLabel").as_(TextBlock)
            self._bar_selector = content.find_name("BarSelector").as_(ComboBox)
            self._settings_panel = content.find_name("BarSettingsPanel").as_(StackPanel)
            self._add_btn = content.find_name("AddBarButton").as_(Button)
            self._delete_btn = content.find_name("DeleteBarButton").as_(Button)
            add_bar_text = content.find_name("AddBarText").as_(TextBlock)
            delete_bar_text = content.find_name("DeleteBarText").as_(TextBlock)

            # Apply translations
            page_title.text = t("bars_title")
            select_bar_label.text = t("bars_selection")
            add_bar_text.text = t("bars_add_new")
            delete_bar_text.text = t("bars_delete")

            self._add_btn.add_click(lambda s, e: self._add_bar())
            self._delete_btn.add_click(lambda s, e: self._delete_bar(self._selected_bar))

            def on_bar_selected(sender, e):
                if not self._bar_selector:
                    return
                idx = self._bar_selector.selected_index
                bar_names = list(self._config_manager.get_bars().keys())
                if 0 <= idx < len(bar_names):
                    self._select_bar(bar_names[idx])

            self._bar_selector.add_selection_changed(on_bar_selected)

            self._refresh_bar_selector()

            self._app._content_area.content = page
        except Exception as e:
            error(f"Bars page error: {e}", exc_info=True)

    def _select_bar(self, bar_name):
        """Select a bar and update button styles."""
        # Validate bar exists in config (handles ghost buttons from discarded changes)
        if bar_name not in self._config_manager.get_bars():
            return

        self._selected_bar = bar_name

        if self._bar_selector:
            bar_names = list(self._config_manager.get_bars().keys())
            if bar_name in bar_names:
                idx = bar_names.index(bar_name)
                if self._bar_selector.selected_index != idx:
                    self._bar_selector.selected_index = idx

        self._load_bar_settings(bar_name, self._settings_panel)

    def _refresh_bar_selector(self, target=None):
        """Populate the bar selector combo box and sync selection."""
        if not self._bar_selector:
            return

        bar_names = list(self._config_manager.get_bars().keys())
        self._bar_selector.items.clear()
        for name in bar_names:
            self._bar_selector.items.append(self._ui.create_combobox_item(name))

        if not bar_names:
            self._selected_bar = None
            self._settings_panel.children.clear()
            return

        desired = (
            target if target in bar_names else self._selected_bar if self._selected_bar in bar_names else bar_names[0]
        )
        self._selected_bar = desired
        desired_idx = bar_names.index(desired)

        if self._bar_selector.selected_index != desired_idx:
            self._bar_selector.selected_index = desired_idx
        else:
            self._select_bar(desired)

        self._update_delete_button_visibility()

    def _load_bar_settings(self, bar_name, panel):
        """Load settings for a specific bar."""
        try:
            self._app._loading = True
            self._app._current_bar_name = bar_name
            bar = self._config_manager.get_bar(bar_name)
            if not bar:
                # Bar doesn't exist (ghost button) - clear panel and return
                panel.children.clear()
                return

            panel.children.clear()

            # === General Section ===
            general_expander = self._ui.create_expander(t("bars_general"), t("bars_general_desc"))
            general_expander.horizontal_alignment = 3  # Stretch
            general_panel = self._ui.create_stack_panel(spacing=8)

            valid_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

            rename_row = self._ui.create_stack_panel(spacing=8, orientation="Horizontal")
            rename_input = TextBox()
            rename_input.text = bar_name
            rename_input.min_width = 200

            rename_save_btn = Button()
            rename_save_btn.content = self._ui.create_text_block(t("common_save"), margin="0")
            rename_save_btn.is_enabled = False

            def on_rename_text_changed(s, e):
                new_name = rename_input.text.strip()
                # Enable save only if name is valid and different
                is_valid = (
                    new_name
                    and new_name != bar_name
                    and valid_pattern.match(new_name)
                    and new_name not in self._config_manager.get_bars()
                )
                rename_save_btn.is_enabled = is_valid

            def on_rename_save(s, e):
                new_name = rename_input.text.strip()
                if new_name and new_name != bar_name:
                    if self._rename_bar(bar_name, new_name):
                        self._app.mark_unsaved()
                        self._refresh_bar_selector(new_name)
                        self._select_bar(new_name)

            rename_input.add_text_changed(on_rename_text_changed)
            rename_save_btn.add_click(on_rename_save)

            rename_row.children.append(rename_input)
            rename_row.children.append(rename_save_btn)
            general_panel.children.append(rename_row)

            enabled = self._ui.create_toggle(t("bars_enabled"), bar.get("enabled", True))
            enabled.add_toggled(lambda s, e: self._update_bar(bar_name, "enabled", enabled.is_on))
            general_panel.children.append(enabled)

            context_menu = self._ui.create_toggle(t("bars_context_menu"), bar.get("context_menu", True))
            context_menu.add_toggled(lambda s, e: self._update_bar(bar_name, "context_menu", context_menu.is_on))
            general_panel.children.append(context_menu)

            class_name = self._ui.create_textbox(t("bars_class_name"), bar.get("class_name", "yasb-bar"))
            class_name.add_text_changed(lambda s, e: self._update_bar(bar_name, "class_name", class_name.text))
            general_panel.children.append(class_name)

            screens_str = str(bar.get("screens", ["*"]))
            screens = self._ui.create_textbox(t("bars_screens"), screens_str)
            screens.add_text_changed(lambda s, e: self._update_bar_screens(bar_name, screens.text))

            # Create horizontal panel for screens input + detect button
            screens_row = self._ui.create_stack_panel(spacing=8, orientation="Horizontal")
            screens_row.children.append(screens)

            # Detect screens button with flyout menu
            detect_btn = XamlReader.load("""<Button xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                VerticalAlignment="Bottom" Margin="0,0,0,0" Padding="10,7"
                ToolTipService.ToolTip="Detect screens">
                <FontIcon Glyph="&#xE7B5;" FontSize="14"/>
            </Button>""").as_(Button)

            def show_monitors_flyout(sender, args):
                try:
                    monitors = get_monitors()
                    flyout = MenuFlyout()

                    # Add "All unassigned screens" option (*)
                    all_item = MenuFlyoutItem()
                    all_item.text = (
                        t("bars_all_screens") if t("bars_all_screens") != "bars_all_screens" else "All Screens (*)"
                    )
                    all_item.add_click(lambda s, e: self._set_screen_value(screens, '["*"]'))
                    flyout.items.append(all_item)

                    # Add "All screens including assigned" option (**)
                    all_assigned_item = MenuFlyoutItem()
                    all_assigned_item.text = (
                        t("bars_all_screens_assigned")
                        if t("bars_all_screens_assigned") != "bars_all_screens_assigned"
                        else "All Screens Including Assigned (**)"
                    )
                    all_assigned_item.add_click(lambda s, e: self._set_screen_value(screens, '["**"]'))
                    flyout.items.append(all_assigned_item)

                    if monitors:
                        flyout.items.append(MenuFlyoutSeparator())

                        for monitor_name in monitors:
                            item = MenuFlyoutItem()
                            item.text = monitor_name
                            # Capture monitor name in closure
                            item.add_click(lambda s, e, m=monitor_name: self._set_screen_value(screens, f'["{m}"]'))
                            flyout.items.append(item)
                    else:
                        no_monitors = MenuFlyoutItem()
                        no_monitors.text = (
                            t("bars_no_screens") if t("bars_no_screens") != "bars_no_screens" else "No screens detected"
                        )
                        no_monitors.is_enabled = False
                        flyout.items.append(no_monitors)

                    flyout.items.append(MenuFlyoutSeparator())
                    wiki_item = MenuFlyoutItem()
                    wiki_item.text = "More info about screens..."
                    wiki_item.add_click(
                        lambda s, e: webbrowser.open(
                            "https://github.com/amnweb/yasb/wiki/Configuration#screen-assignment-options"
                        )
                    )
                    flyout.items.append(wiki_item)

                    # Show flyout attached to button
                    flyout.placement = 5  # FlyoutPlacementMode.Bottom
                    detect_btn.flyout = flyout
                    detect_btn.flyout.show_at(detect_btn.as_(FrameworkElement))
                except Exception as e:
                    error(f"Show monitors flyout error: {e}", exc_info=True)

            detect_btn.add_click(show_monitors_flyout)
            screens_row.children.append(detect_btn)

            general_panel.children.append(screens_row)

            general_expander.content = general_panel
            panel.children.append(general_expander)

            # === Position & Alignment Section ===
            position_expander = self._ui.create_expander(t("bars_position"), t("bars_position_desc"))
            position_expander.horizontal_alignment = 3  # Stretch
            position_panel = self._ui.create_stack_panel(spacing=8)

            alignment = bar.get("alignment", {})
            position = self._ui.create_combobox(
                t("bars_position"),
                [t("bars_position_top"), t("bars_position_bottom")],
                t("bars_position_top") if alignment.get("position", "top") == "top" else t("bars_position_bottom"),
            )
            position.add_selection_changed(
                lambda s, e: self._update_bar_nested(
                    bar_name, "alignment", "position", "top" if position.selected_index == 0 else "bottom"
                )
            )
            position_panel.children.append(position)

            align_options = ["left", "center", "right"]
            current_align = alignment.get("align", "left")
            align = self._ui.create_combobox(t("bars_align"), align_options, current_align)
            align.add_selection_changed(
                lambda s, e: self._update_bar_nested(
                    bar_name, "alignment", "align", align_options[align.selected_index]
                )
            )
            position_panel.children.append(align)

            position_expander.content = position_panel
            panel.children.append(position_expander)

            # === Dimensions Section ===
            dimensions_expander = self._ui.create_expander(t("bars_dimensions"), t("bars_dimensions_desc"))
            dimensions_expander.horizontal_alignment = 3  # Stretch
            dimensions_panel = self._ui.create_stack_panel(spacing=8)

            dimensions = bar.get("dimensions", {})
            width = self._ui.create_textbox(t("bars_width"), str(dimensions.get("width", "100%")))
            width.add_text_changed(lambda s, e: self._update_bar_nested(bar_name, "dimensions", "width", width.text))
            dimensions_panel.children.append(width)

            height = self._ui.create_numberbox(t("bars_height"), dimensions.get("height", 32), min_val=10, max_val=200)
            height.add_value_changed(
                lambda s, e: self._update_bar_nested(
                    bar_name, "dimensions", "height", int(height.value) if height.value else 32
                )
            )
            dimensions_panel.children.append(height)

            dimensions_expander.content = dimensions_panel
            panel.children.append(dimensions_expander)

            # === Padding Section ===
            padding_expander = self._ui.create_expander(t("bars_padding"), t("bars_padding_desc"))
            padding_expander.horizontal_alignment = 3  # Stretch
            padding_panel = self._ui.create_stack_panel(spacing=8)

            padding = bar.get("padding", {})
            for pad_name in ["top", "bottom", "left", "right"]:
                pad_box = self._ui.create_numberbox(
                    pad_name.capitalize(), padding.get(pad_name, 0), min_val=0, max_val=100
                )
                pad_box.add_value_changed(
                    lambda s, e, pn=pad_name, pb=pad_box: self._update_bar_nested(
                        bar_name, "padding", pn, int(pb.value) if pb.value else 0
                    )
                )
                padding_panel.children.append(pad_box)

            padding_expander.content = padding_panel
            panel.children.append(padding_expander)

            # === Window Flags Section ===
            flags_expander = self._ui.create_expander(t("bars_window_flags"), t("bars_window_flags_desc"))
            flags_expander.horizontal_alignment = 3  # Stretch
            flags_panel = self._ui.create_stack_panel(spacing=8)

            window_flags = bar.get("window_flags", {})
            flag_keys = [
                ("always_on_top", "bars_always_on_top", False),
                ("windows_app_bar", "bars_windows_app_bar", True),
                ("hide_on_fullscreen", "bars_hide_on_fullscreen", False),
                ("auto_hide", "bars_auto_hide", False),
            ]
            for flag_name, flag_key, default in flag_keys:
                flag_toggle = self._ui.create_toggle(t(flag_key), window_flags.get(flag_name, default))
                flag_toggle.add_toggled(
                    lambda s, e, fn=flag_name, ft=flag_toggle: self._update_bar_nested(
                        bar_name, "window_flags", fn, ft.is_on
                    )
                )
                flags_panel.children.append(flag_toggle)

            flags_expander.content = flags_panel
            panel.children.append(flags_expander)

            # === Blur Effect Section ===
            blur_expander = self._ui.create_expander(t("bars_blur_effect"), t("bars_blur_effect_desc"))
            blur_expander.horizontal_alignment = 3  # Stretch
            blur_panel = self._ui.create_stack_panel(spacing=8)

            blur = bar.get("blur_effect", {})

            blur_enabled = self._ui.create_toggle(t("bars_enable_blur"), blur.get("enabled", False))
            blur_enabled.add_toggled(
                lambda s, e: self._update_bar_nested(bar_name, "blur_effect", "enabled", blur_enabled.is_on)
            )
            blur_panel.children.append(blur_enabled)

            blur_acrylic = self._ui.create_toggle(t("bars_acrylic_effect"), blur.get("acrylic", False))
            blur_acrylic.add_toggled(
                lambda s, e: self._update_bar_nested(bar_name, "blur_effect", "acrylic", blur_acrylic.is_on)
            )
            blur_panel.children.append(blur_acrylic)

            blur_dark = self._ui.create_toggle(t("bars_dark_mode"), blur.get("dark_mode", False))
            blur_dark.add_toggled(
                lambda s, e: self._update_bar_nested(bar_name, "blur_effect", "dark_mode", blur_dark.is_on)
            )
            blur_panel.children.append(blur_dark)

            blur_round = self._ui.create_toggle(t("bars_round_corners"), blur.get("round_corners", False))
            blur_round.add_toggled(
                lambda s, e: self._update_bar_nested(bar_name, "blur_effect", "round_corners", blur_round.is_on)
            )
            blur_panel.children.append(blur_round)

            round_type_options = ["normal", "small"]
            current_round_type = blur.get("round_corners_type", "normal")
            round_type = self._ui.create_combobox(t("bars_round_corners_type"), round_type_options, current_round_type)
            round_type.add_selection_changed(
                lambda s, e: self._update_bar_nested(
                    bar_name, "blur_effect", "round_corners_type", round_type_options[round_type.selected_index]
                )
            )
            blur_panel.children.append(round_type)

            # Border color dropdown
            border_color_options = ["None", "system"]
            current_border = blur.get("border_color", "None")
            is_custom = current_border not in border_color_options

            border_combo = self._ui.create_combobox(
                t("bars_border_color"),
                border_color_options + [t("bars_border_custom")],
                t("bars_border_custom") if is_custom else current_border,
            )
            blur_panel.children.append(border_combo)

            border_hex = self._ui.create_textbox(t("bars_border_hex"), current_border if is_custom else "#000000")
            border_hex.add_text_changed(
                lambda s, e: self._update_bar_nested(bar_name, "blur_effect", "border_color", border_hex.text)
            )
            border_hex.visibility = Visibility.VISIBLE if is_custom else Visibility.COLLAPSED
            blur_panel.children.append(border_hex)

            def on_border_color_changed(s, e):
                idx = border_combo.selected_index
                if idx == 2:  # Custom
                    border_hex.visibility = Visibility.VISIBLE
                    self._update_bar_nested(bar_name, "blur_effect", "border_color", border_hex.text)
                else:
                    border_hex.visibility = Visibility.COLLAPSED
                    self._update_bar_nested(bar_name, "blur_effect", "border_color", border_color_options[idx])

            border_combo.add_selection_changed(on_border_color_changed)

            blur_expander.content = blur_panel
            panel.children.append(blur_expander)

            # === Animation Section ===
            anim_expander = self._ui.create_expander(t("bars_animation"), t("bars_animation_desc"))
            anim_expander.horizontal_alignment = 3  # Stretch
            anim_panel = self._ui.create_stack_panel(spacing=8)

            animation = bar.get("animation", {})

            anim_enabled = self._ui.create_toggle(t("bars_enable_animation"), animation.get("enabled", True))
            anim_enabled.add_toggled(
                lambda s, e: self._update_bar_nested(bar_name, "animation", "enabled", anim_enabled.is_on)
            )
            anim_panel.children.append(anim_enabled)

            anim_duration = self._ui.create_numberbox(
                t("bars_duration_ms"), animation.get("duration", 400), min_val=0, max_val=2000, step=50
            )
            anim_duration.add_value_changed(
                lambda s, e: self._update_bar_nested(
                    bar_name, "animation", "duration", int(anim_duration.value) if anim_duration.value else 400
                )
            )
            anim_panel.children.append(anim_duration)

            anim_expander.content = anim_panel
            panel.children.append(anim_expander)

            # === Layouts Section ===
            layouts_expander = self._ui.create_expander(t("bars_layouts"), t("bars_layouts_desc"))
            layouts_expander.horizontal_alignment = 3  # Stretch
            layouts_panel = self._ui.create_stack_panel(spacing=8)

            layouts = bar.get("layouts", {})
            align_options = ["left", "center", "right"]

            # Left layout
            layouts_panel.children.append(self._ui.create_text_block(t("bars_layout_left"), "BodyStrongTextBlockStyle"))
            left_layout = layouts.get("left", {})
            left_align = self._ui.create_combobox(
                t("bars_layout_alignment"), align_options, left_layout.get("alignment", "left")
            )
            left_align.add_selection_changed(
                lambda s, e: self._update_bar_layout(
                    bar_name, "left", "alignment", align_options[left_align.selected_index]
                )
            )
            layouts_panel.children.append(left_align)

            left_stretch = self._ui.create_toggle(t("bars_layout_stretch"), left_layout.get("stretch", True))
            left_stretch.add_toggled(
                lambda s, e: self._update_bar_layout(bar_name, "left", "stretch", left_stretch.is_on)
            )
            layouts_panel.children.append(left_stretch)

            # Center layout
            layouts_panel.children.append(
                self._ui.create_text_block(t("bars_layout_center"), "BodyStrongTextBlockStyle")
            )
            center_layout = layouts.get("center", {})
            center_align = self._ui.create_combobox(
                t("bars_layout_alignment"), align_options, center_layout.get("alignment", "center")
            )
            center_align.add_selection_changed(
                lambda s, e: self._update_bar_layout(
                    bar_name, "center", "alignment", align_options[center_align.selected_index]
                )
            )
            layouts_panel.children.append(center_align)

            center_stretch = self._ui.create_toggle(t("bars_layout_stretch"), center_layout.get("stretch", True))
            center_stretch.add_toggled(
                lambda s, e: self._update_bar_layout(bar_name, "center", "stretch", center_stretch.is_on)
            )
            layouts_panel.children.append(center_stretch)

            # Right layout
            layouts_panel.children.append(
                self._ui.create_text_block(t("bars_layout_right"), "BodyStrongTextBlockStyle")
            )
            right_layout = layouts.get("right", {})
            right_align = self._ui.create_combobox(
                t("bars_layout_alignment"), align_options, right_layout.get("alignment", "right")
            )
            right_align.add_selection_changed(
                lambda s, e: self._update_bar_layout(
                    bar_name, "right", "alignment", align_options[right_align.selected_index]
                )
            )
            layouts_panel.children.append(right_align)

            right_stretch = self._ui.create_toggle(t("bars_layout_stretch"), right_layout.get("stretch", True))
            right_stretch.add_toggled(
                lambda s, e: self._update_bar_layout(bar_name, "right", "stretch", right_stretch.is_on)
            )
            layouts_panel.children.append(right_stretch)

            layouts_expander.content = layouts_panel
            panel.children.append(layouts_expander)

            self._app._loading = False
        except Exception as e:
            error(f"Load bar error: {e}", exc_info=True)
            self._app._loading = False

    def _update_bar(self, bar_name, key, value):
        """Update a bar property."""
        if self._app._loading:
            return
        bar = self._config_manager.get_bar(bar_name)
        if bar:
            bar[key] = value
            self._app.mark_unsaved()

    def _update_bar_nested(self, bar_name, section, key, value):
        """Update a nested bar property."""
        if self._app._loading:
            return
        bar = self._config_manager.get_bar(bar_name)
        if bar:
            if section not in bar:
                bar[section] = {}
            bar[section][key] = value
            self._app.mark_unsaved()

    def _update_bar_layout(self, bar_name, position, key, value):
        """Update a bar layout property."""
        if self._app._loading:
            return
        bar = self._config_manager.get_bar(bar_name)
        if bar:
            if "layouts" not in bar:
                bar["layouts"] = {}
            if position not in bar["layouts"]:
                bar["layouts"][position] = {}
            bar["layouts"][position][key] = value
            self._app.mark_unsaved()

    def _update_bar_screens(self, bar_name, text):
        """Update bar screens from text."""
        if self._app._loading:
            return
        bar = self._config_manager.get_bar(bar_name)
        if bar:
            try:
                screens = eval(text) if text.strip().startswith("[") else [text.strip()]
                bar["screens"] = screens
            except Exception as ex:
                warning(f"Screens parse error: {ex}")
                bar["screens"] = [text.strip()]
            self._app.mark_unsaved()

    def _set_screen_value(self, textbox, value):
        """Set screen value in the textbox from flyout selection."""
        textbox.text = value

    def _add_bar(self):
        """Add a new bar."""
        count = len(self._config_manager.get_bars()) + 1
        new_name = f"new-bar-{count}"
        self._config_manager.config["bars"][new_name] = {
            "enabled": True,
            "context_menu": True,
            "screens": ["*"],
            "class_name": "yasb-bar",
            "alignment": {"position": "top", "align": "center"},
            "dimensions": {"width": "100%", "height": 30},
            "padding": {"top": 0, "left": 0, "bottom": 0, "right": 0},
            "window_flags": {
                "always_on_top": False,
                "windows_app_bar": False,
                "hide_on_fullscreen": False,
                "auto_hide": False,
            },
            "blur_effect": {
                "enabled": False,
                "acrylic": False,
                "dark_mode": False,
                "round_corners": False,
                "round_corners_type": "normal",
                "border_color": "System",
            },
            "animation": {"enabled": True, "duration": 500},
            "layouts": {
                "left": {"alignment": "left", "stretch": True},
                "center": {"alignment": "center", "stretch": True},
                "right": {"alignment": "right", "stretch": True},
            },
            "widgets": {"left": [], "center": [], "right": []},
        }
        self._app.mark_unsaved()
        self._refresh_bar_selector(new_name)
        self._select_bar(new_name)

    def _rename_bar(self, old_name, new_name):
        """Rename a bar in the config."""
        try:
            bars = self._config_manager.config.get("bars", {})
            if old_name not in bars or new_name in bars:
                return False

            new_bars = OrderedDict()
            for name, config in bars.items():
                if name == old_name:
                    new_bars[new_name] = config
                else:
                    new_bars[name] = config

            self._config_manager.config["bars"] = dict(new_bars)
            return True
        except Exception as e:
            error(f"Rename bar error: {e}", exc_info=True)
            return False

    def _update_delete_button_visibility(self):
        """Show delete button only when more than one bar exists."""
        if not self._delete_btn:
            return
        bar_count = len(self._config_manager.get_bars())
        self._delete_btn.visibility = Visibility.VISIBLE if bar_count > 1 else Visibility.COLLAPSED

    def _delete_bar(self, bar_name):
        """Delete a bar."""
        # Always use currently selected bar to avoid stale closures
        bar_to_delete = self._selected_bar
        if not bar_to_delete:
            return

        if bar_to_delete in self._config_manager.config.get("bars", {}):
            del self._config_manager.config["bars"][bar_to_delete]
            self._selected_bar = None  # Clear selection
            self._app.mark_unsaved()
            self._refresh_bar_selector()
