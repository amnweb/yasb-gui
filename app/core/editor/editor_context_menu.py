import json
from typing import Callable, List, Optional, Tuple

from winrt.windows.applicationmodel.datatransfer import Clipboard, StandardDataFormats
from winrt.windows.foundation import AsyncStatus, IAsyncOperation, Point
from winui3.microsoft.ui.xaml.controls import MenuFlyout, MenuFlyoutItem, MenuFlyoutSeparator


def monaco_context_menu(
    webview,
    create_icon: Callable[[str], object],
    translate: Callable[[str], str],
    extra_items: Optional[List[Tuple[str, str, str]]] = None,
):
    """
    Attach a WinUI3 context menu that maps to Monaco copy/cut/paste/select-all.

    Args:
        webview: The WebView2 control
        create_icon: Function to create a FontIcon from a glyph entity
        translate: Translation function
        extra_items: Optional list of (label, glyph, script) tuples for additional menu items
    """
    core = webview.core_webview2
    if not core:
        return

    core.settings.are_default_context_menus_enabled = False

    menu = MenuFlyout()

    def add_item(label: str, glyph: str, script: str):
        item = MenuFlyoutItem()
        item.text = label
        item.icon = create_icon(glyph)
        item.add_click(lambda s, e, js=script: webview.execute_script_async(js))
        menu.items.append(item)

    def paste_from_clipboard():
        dispatcher = webview.dispatcher_queue

        def do_paste():
            data = Clipboard.get_content()
            if not data or not data.contains(StandardDataFormats.text):
                return

            op = data.get_text_async()

            def apply_text(text_val: str):
                js_text = json.dumps(text_val)
                webview.execute_script_async(
                    "if(window.editor){editor.focus();"
                    f"editor.executeEdits('native-paste',[{{range:editor.getSelection(),text:{js_text},forceMoveMarkers:true}}]);"
                    "editor.pushUndoStop();"
                    "if(window.fixIndentation) fixIndentation();}"
                )

            def on_text(op_inner: IAsyncOperation, status: AsyncStatus):
                if status != AsyncStatus.COMPLETED:
                    return
                text_val = op_inner.get_results() or ""
                if dispatcher and dispatcher.try_enqueue(lambda: apply_text(text_val)):
                    return
                apply_text(text_val)

            op.completed = on_text

        if dispatcher and dispatcher.try_enqueue(do_paste):
            return
        do_paste()

    add_item(
        translate("common_copy"),
        "&#xE8C8;",
        "if(window.editor){editor.focus();editor.trigger('native','editor.action.clipboardCopyAction');}",
    )
    add_item(
        translate("common_cut"),
        "&#xE8C6;",
        "if(window.editor){editor.focus();editor.trigger('native','editor.action.clipboardCutAction');}",
    )

    paste_item = MenuFlyoutItem()
    paste_item.text = translate("common_paste")
    paste_item.icon = create_icon("&#xE77F;")
    paste_item.add_click(lambda s, e: paste_from_clipboard())
    menu.items.append(paste_item)

    menu.items.append(MenuFlyoutSeparator())
    add_item(
        translate("common_select_all"),
        "&#xE8B3;",
        "if(window.editor){editor.focus();editor.trigger('native','editor.action.selectAll');}",
    )

    # Add extra items (e.g., Format CSS, Cleanup CSS)
    if extra_items:
        menu.items.append(MenuFlyoutSeparator())
        for label, glyph, script in extra_items:
            add_item(label, glyph, script)

    def show_menu_at(point: Optional[Point]):
        if point:
            menu.show_at(webview, Point(point.x, point.y))
        else:
            menu.show_at(webview)

    def on_context_menu_requested(sender, args):
        args.handled = True
        loc = getattr(args, "location", None)
        show_menu_at(loc if loc else None)

    def on_right_tapped(sender, args):
        pt = args.get_position(webview)
        show_menu_at(pt)
        args.handled = True

    core.add_context_menu_requested(on_context_menu_requested)
    webview.add_right_tapped(on_right_tapped)
    webview.context_flyout = menu
