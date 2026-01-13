# YASB GUI

<p align="center">
  <img src="assets/promo.jpg" alt="YASB GUI" width="100%">
</p>

**YASB GUI** is a native configuration application for [YASB Reborn](https://github.com/amnweb/yasb) (Yet Another Status Bar). Built with WinUI 3, it provides a modern interface for managing your status bar configuration without manually editing YAML files.

> **Note:** This application is currently in **beta**. Some features may be incomplete or subject to change. Please report any issues on the [GitHub Issues](https://github.com/amnweb/yasb-gui/issues) page.

**Why a separate repository?** 
- YASB GUI is maintained separately from YASB for several reasons:
- Built with WinUI 3, which requires Windows App SDK dependencies not needed by YASB itself
- Keeps YASB lightweight and focused on its core functionality without GUI framework bloat
- Allows independent development cycles and easier maintenance for both projects
- Users who prefer manual YAML editing don't need to install unnecessary GUI dependencies

---

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
  <a href="https://github.com/amnweb/yasb-gui"><img src="https://img.shields.io/github/languages/top/amnweb/yasb-gui"></a>
  <a href="https://github.com/amnweb/yasb-gui/issues"><img src="https://img.shields.io/github/issues/amnweb/yasb-gui?label=Issues"></a>
  <a href="https://github.com/amnweb/yasb-gui/releases"><img src="https://img.shields.io/github/downloads/amnweb/yasb-gui/total?label=Total%20Downloads"></a>
  <a href="https://github.com/amnweb/yasb-gui/releases/latest"><img src="https://img.shields.io/github/v/release/amnweb/yasb-gui?label=Latest%20Release"></a>
  <a href="https://discord.gg/qkeunvBFgX" title="Discord"><img alt="Discord" src="https://img.shields.io/discord/1353495377768218654?label=Discord&cacheSeconds=600"></a>
</p>

---

## Features

**Visual Configuration Editor**
- Edit bars, widgets, and global settings through an intuitive interface
- Monaco-based code editor with YAML syntax highlighting and validation
- Real-time schema validation for configuration files

**Widget Management**
- Add, remove, and configure widgets with a visual editor
- Support for all YASB widget types
- Widget-specific settings panels

**Styles Editor**
- Built-in CSS editor for customizing your status bar appearance
- Syntax highlighting and auto-completion

**Environment Variables**
- Manage environment variables used by YASB
- Easy key-value editing interface

**Application Settings**
- Light, Dark, and System theme support
- Multiple backdrop options: Mica, Mica Alt, and Acrylic
- Multi-language support

**Safety Features**
- Export configuration as ZIP backup
- Unsaved changes detection with confirmation dialogs
- Configuration validation before save

---

## System Requirements

| Component | Requirement |
|-----------|-------------|
| Operating System | Windows 10 (Build 17763+) or Windows 11 |
| Runtime | [Windows App SDK Runtime](https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/downloads) |
| WebView | Microsoft Edge WebView2 Runtime (included with Windows 10/11) |

---

## Installation

### From Release
Download the latest release from the [Releases](https://github.com/amnweb/yasb-gui/releases) page.

### From Source
```bash
git clone https://github.com/amnweb/yasb-gui.git
cd yasb-gui
pip install -e .
python app/main.py
```

### Building Executable
```bash
pip install .[build]
python app/scripts/build.py build
```
The executable will be created in the `dist/` directory.

### Add a widget using a docs snippet (how it actually works)
1) Go to **Widgets** → **Add Widget**.
2) Pick the widget from the built-in list.
3) In the **Options** editor, paste only the options block from the docs-not the outer `widgets:` list. Real example (Weather widget) with nested options and indentation kept:
```yaml
label: "<span>{icon}</span> {temp}"
label_alt: "{location}: Min {min_temp}, Max {max_temp}"
api_key: "YOUR_API_KEY"
show_alerts: true
tooltip: true
update_interval: 600
hide_decimal: true
units: metric
menu:
  blur: true
  round_corners: true
  round_corners_type: normal
  border_color: system
  alignment: center
  direction: down
  offset_top: 6
  offset_left: 0
icons:
  sunnyDay: "\ue30d"
  clearNight: "\ue32b"
  cloudyDay: "\ue312"
  cloudyNight: "\ue311"
  rainyDay: "\ue318"
  rainyNight: "\ue318"
  snowyIcy: "\ue31a"
  default: "\ue137"
callbacks:
  on_left: toggle_menu
```
4) Save the widget, then hit **Apply** so YASB reloads the updated config.

> **Tips**
>
> Copy only the options section from the docs and paste it into the Options editor; the widget type is already set by your selection.
>
> If indentation looks off, right-click in the editor and choose **Fix indentation** from the context menu.

---

## Configuration

The application reads and writes YASB configuration from:
- `~/.config/yasb/config.yaml`
- `~/.config/yasb/styles.css`

To use a custom location, set the `YASB_CONFIG_HOME` environment variable.

---

## Contributing Translations

YASB GUI supports multiple languages. Translation files are located in `app/core/locales/`.

**To add a new language:**
1. Copy `en.json` and rename it using the language code (e.g., `fr.json` for French)
2. Update `_language_name` and `_language_code` at the top of the file
3. Translate all string values while keeping the keys unchanged
4. Do not modify placeholders (e.g., `{variable}`) within the strings
5. Do not chnage the JSON structure
6. Submit a pull request

---

## Support the Project

If you find YASB GUI useful, consider supporting its development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-ea4aaa?logo=github)](https://github.com/sponsors/amnweb)
[![Ko-fi](https://img.shields.io/badge/Support-Ko--fi-ff5e5b?logo=ko-fi)](https://ko-fi.com/amnweb)

Your support helps maintain and improve the project.