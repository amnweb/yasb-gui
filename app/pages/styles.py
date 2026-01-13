"""
Styles editor for YASB GUI.

Edits CSS stylesheets with Monaco editor.
"""

import json
import subprocess
import time
from ctypes import WinError

from core.code_editor import get_code_editor_html_uri
from core.constants import WEBVIEW_CACHE_DIR
from core.editor.editor_context_menu import monaco_context_menu
from core.localization import t
from core.logger import error
from core.preferences import get_preferences
from ui.controls import UIFactory
from ui.loader import load_xaml
from webview2.microsoft.web.webview2.core import CoreWebView2Environment
from winrt.windows.foundation import AsyncStatus, IAsyncAction, IAsyncOperation, Uri
from winrt.windows.ui import Color
from winui3.microsoft.ui.xaml import FrameworkElement, Visibility
from winui3.microsoft.ui.xaml.controls import FontIcon, Grid, Page, StackPanel, TextBlock, WebView2
from winui3.microsoft.ui.xaml.markup import XamlReader


class StylesPage:
    """Manages styles editor with Monaco."""

    def __init__(self, app):
        self._app = app
        self._config_manager = app._config_manager
        self._ui = UIFactory()
        self._webview = None
        self._editor_ready = False
        self._pending_content = None
        self._loader_start_time = None

    def _create_icon(self, glyph_entity):
        xaml = f'''<FontIcon xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                      Glyph="{glyph_entity}" FontFamily="Segoe Fluent Icons"/>'''
        return XamlReader.load(xaml).as_(FontIcon)

    def show(self):
        """Display styles editor page."""
        try:
            page = XamlReader.load(load_xaml("pages/StylesPage.xaml")).as_(Page)
            content = page.content.as_(FrameworkElement)

            page_title = content.find_name("PageTitle").as_(TextBlock)
            header_panel = content.find_name("HeaderPanel").as_(StackPanel)
            self._webview = content.find_name("CssEditor").as_(WebView2)
            self._loading_overlay = content.find_name("LoadingOverlay").as_(Grid)

            page_title.text = t("styles_title")

            open_btn = self._ui.create_button(t("common_open_editor"))
            open_btn.add_click(lambda s, e: subprocess.Popen(["notepad", self._config_manager.styles_path]))
            header_panel.children.append(open_btn)

            css_content = self._config_manager.load_styles()
            self._pending_content = css_content

            prefs = get_preferences()
            self._editor_font = prefs.get("editor_font", "Cascadia Code") if prefs else "Cascadia Code"
            self._editor_font_size = prefs.get("editor_font_size", 13) if prefs else 13

            editor_theme = prefs.get("editor_theme", "auto") if prefs else "auto"

            if editor_theme == "auto":
                app_theme = prefs.get("theme", "default") if prefs else "default"
                if app_theme == "light":
                    self._monaco_theme = "light"
                elif app_theme == "dark":
                    self._monaco_theme = "dark"
                else:
                    self._monaco_theme = "dark"
            else:
                self._monaco_theme = editor_theme

            self._webview.add_web_message_received(self._on_web_message)
            self._webview.add_navigation_completed(self._on_navigation_completed)

            self._init_webview()

            self._app._content_area.content = page
        except Exception as e:
            error(f"Styles page error: {e}", exc_info=True)

    def _init_webview(self):
        """Initialize WebView2 with async pattern."""
        self._loader_start_time = time.time()

        # Create WebView2 environment with shared cache dir
        env_op = CoreWebView2Environment.create_with_options_async("", WEBVIEW_CACHE_DIR, None)

        def on_env_created(op: IAsyncOperation, status: AsyncStatus):
            if status == AsyncStatus.ERROR:
                error(f"WebView2 environment creation failed: {WinError(op.error_code.value)}")
                return
            if status != AsyncStatus.COMPLETED:
                return

            env = op.get_results()
            ensure_op = self._webview.ensure_core_webview2_with_environment_async(env)

            def on_ensure_complete(ensure_op_inner: IAsyncAction, ensure_status: AsyncStatus):
                if ensure_status == AsyncStatus.ERROR:
                    error(f"WebView2 ensure failed: {WinError(ensure_op_inner.error_code.value)}")
                    return
                if ensure_status != AsyncStatus.COMPLETED:
                    return

                self._webview.default_background_color = Color(a=255, r=25, g=26, b=28)

                css_extra_items = [
                    (
                        t("common_format_css"),
                        "&#xE943;",  # AlignLeft icon
                        """if(window.editor){
                            var css = editor.getValue();
                            var formatted = '';
                            var indent = 0;
                            var inRule = false;
                            
                            // Remove existing formatting
                            css = css.replace(/\\s+/g, ' ').trim();
                            
                            for (var i = 0; i < css.length; i++) {
                                var c = css[i];
                                if (c === '{') {
                                    formatted += ' {\\n' + '  '.repeat(indent + 1);
                                    indent++;
                                    inRule = true;
                                } else if (c === '}') {
                                    indent--;
                                    formatted = formatted.trimEnd() + '\\n' + '  '.repeat(indent) + '}\\n' + (indent === 0 ? '\\n' : '');
                                    inRule = false;
                                } else if (c === ';' && inRule) {
                                    formatted += ';\\n' + '  '.repeat(indent);
                                } else if (c === ',' && !inRule) {
                                    // Multiple selectors - put each on new line
                                    formatted += ',\\n';
                                } else if (c === ' ' && (formatted.endsWith('\\n' + '  '.repeat(indent)) || formatted.endsWith(',\\n'))) {
                                    // Skip leading space after newline
                                } else {
                                    formatted += c;
                                }
                            }
                            editor.setValue(formatted.trim());
                        }""",
                    ),
                    (
                        t("common_cleanup_css"),
                        "&#xEA99;",  # Broom icon
                        """if(window.editor){
                            var content = editor.getValue();
                            // Remove block comments /* ... */
                            content = content.replace(/\\/\\*[\\s\\S]*?\\*\\//g, '');
                            editor.setValue(content);
                        }""",
                    ),
                ]

                monaco_context_menu(self._webview, self._create_icon, t, css_extra_items)

                html_uri = get_code_editor_html_uri()
                self._webview.source = Uri(html_uri)

            ensure_op.completed = on_ensure_complete

        env_op.completed = on_env_created

    def _on_navigation_completed(self, sender, args):
        """Called when WebView2 navigation is complete."""
        pass  # Monaco will send 'ready' message when initialized

    def _on_web_message(self, sender, args):
        """Handle messages from Monaco editor."""
        try:
            msg = json.loads(args.web_message_as_json)
            if msg.get("type") == "ready":
                self._editor_ready = True
                self._init_editor_content()
            elif msg.get("type") == "initialized":
                self._loading_overlay.visibility = Visibility.COLLAPSED
                self._webview.visibility = Visibility.VISIBLE
            elif msg.get("type") == "contentChanged":
                content = msg.get("content", "")
                self._app.mark_unsaved("styles", current_styles=content)
        except Exception as e:
            error(f"Web message error: {e}")

    def _init_editor_content(self):
        """Initialize editor with content after Monaco is ready."""
        try:
            elapsed = time.time() - self._loader_start_time if self._loader_start_time else 0
            elapsed_ms = int(elapsed * 1000)

            init_options = {
                "theme": self._monaco_theme,
                "language": "css",
                "fontFamily": self._editor_font,
                "fontSize": self._editor_font_size,
                "content": self._pending_content or "",
                "focus": True,
                "elapsedMs": elapsed_ms,
                "minTotalMs": 1000,
            }

            js_options = json.dumps(init_options)
            self._webview.execute_script_async(f"initEditor({js_options})")
            self._pending_content = None

            self._app._styles_webview = self._webview
        except Exception as e:
            error(f"Init editor content error: {e}")

    async def get_content(self):
        """Get CSS content from Monaco editor."""
        try:
            if self._webview and self._editor_ready:
                result = await self._webview.execute_script_async("getContent()")
                if result:
                    return json.loads(result)
        except Exception as e:
            error(f"Get content error: {e}")
        return ""
