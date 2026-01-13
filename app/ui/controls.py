"""
UI control factory for YASB GUI.

Creates WinUI 3 controls with consistent styling.
"""

from core.preferences import get_preferences
from ui.loader import load_xaml
from winui3.microsoft.ui.xaml import Application
from winui3.microsoft.ui.xaml.controls import (
    Button,
    ComboBox,
    ComboBoxItem,
    Expander,
    FontIcon,
    HyperlinkButton,
    InfoBar,
    Slider,
    StackPanel,
    TextBlock,
    TextBox,
    ToggleSwitch,
)
from winui3.microsoft.ui.xaml.markup import XamlReader
from winui3.microsoft.ui.xaml.media import FontFamily


class UIFactory:
    """Creates WinUI 3 controls with styling."""

    _common_resources_loaded = False

    @staticmethod
    def _ensure_common_resources():
        """Load shared XAML resources once."""
        if UIFactory._common_resources_loaded:
            return
        if not Application.current:
            return
        try:
            rd = XamlReader.load(load_xaml("components/Common.xaml"))
            if rd:
                Application.current.resources.merged_dictionaries.append(rd)
                UIFactory._common_resources_loaded = True
        except Exception:
            return

    @staticmethod
    def get_editor_font():
        """Get configured editor font."""
        prefs = get_preferences()
        return prefs.get("editor_font", "Cascadia Code") if prefs else "Cascadia Code"

    @staticmethod
    def get_editor_font_size():
        """Get configured editor font size."""
        prefs = get_preferences()
        return prefs.get("editor_font_size", 13) if prefs else 13

    @staticmethod
    def escape_xml(text):
        """Escape special XML characters."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    @staticmethod
    def create_button(text):
        """Create styled button."""
        safe_text = UIFactory.escape_xml(text)
        xaml = f'''<Button xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Content="{safe_text}" HorizontalAlignment="Stretch" Padding="12,8"/>'''
        return XamlReader.load(xaml).as_(Button)

    @staticmethod
    def create_text_block(text, style=None, margin="0,8,0,4", wrap=False, secondary=False):
        """Create styled text block."""
        safe_text = UIFactory.escape_xml(text)
        style_attr = f'Style="{{StaticResource {style}}}"' if style else ""
        wrap_attr = 'TextWrapping="Wrap"' if wrap else ""
        foreground_attr = 'Foreground="{ThemeResource TextFillColorSecondaryBrush}"' if secondary else ""
        xaml = f'''<TextBlock xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Text="{safe_text}" {style_attr} {wrap_attr} {foreground_attr} Margin="{margin}"/>'''
        return XamlReader.load(xaml).as_(TextBlock)

    @staticmethod
    def create_page_title(text):
        """Create standard page title."""
        safe_text = UIFactory.escape_xml(text)
        xaml = f'''<TextBlock xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Text="{safe_text}" Style="{{StaticResource TitleTextBlockStyle}}"
                    Margin="0,0,0,24"/>'''
        return XamlReader.load(xaml).as_(TextBlock)

    @staticmethod
    def create_toggle(header, is_on, on_text=None, off_text=None):
        """Create toggle switch."""
        safe_header = UIFactory.escape_xml(header)
        on_label = UIFactory.escape_xml(on_text) if on_text is not None else "On"
        off_label = UIFactory.escape_xml(off_text) if off_text is not None else "Off"
        on_str = "True" if is_on else "False"
        xaml = f'''<ToggleSwitch xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Header="{safe_header}" IsOn="{on_str}" OnContent="{on_label}" OffContent="{off_label}"/>'''
        return XamlReader.load(xaml).as_(ToggleSwitch)

    @staticmethod
    def create_textbox(header, text):
        """Create text box."""
        safe_text = UIFactory.escape_xml(text)
        safe_header = UIFactory.escape_xml(header)
        xaml = f'''<TextBox xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Header="{safe_header}" Text="{safe_text}" Width="400" HorizontalAlignment="Left"/>'''
        return XamlReader.load(xaml).as_(TextBox)

    @staticmethod
    def create_textbox_multiline(header, text):
        """Create multiline text box with dark background."""
        xaml = """<TextBox xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                    AcceptsReturn="True" TextWrapping="Wrap" MinHeight="450"
                    HorizontalAlignment="Stretch">
                    <TextBox.Resources>
                        <StaticResource x:Key="TextControlBackground" ResourceKey="LayerFillColorDefaultBrush"/>
                        <StaticResource x:Key="TextControlBackgroundPointerOver" ResourceKey="LayerFillColorDefaultBrush"/>
                        <StaticResource x:Key="TextControlBackgroundFocused" ResourceKey="LayerFillColorDefaultBrush"/>
                        <StaticResource x:Key="TextControlBackgroundDisabled" ResourceKey="LayerFillColorDefaultBrush"/>
                    </TextBox.Resources>
                </TextBox>"""
        tb = XamlReader.load(xaml).as_(TextBox)
        tb.text = text
        tb.font_family = FontFamily(UIFactory.get_editor_font())
        tb.font_size = UIFactory.get_editor_font_size()
        return tb

    @staticmethod
    def create_numberbox(header, value, min_val=0, max_val=1000, step=1):
        """Create slider for numeric input."""
        xaml = f'''<Slider xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Header="{header}" Value="{value}" Minimum="{min_val}" Maximum="{max_val}"
                    StepFrequency="{step}" Width="400" HorizontalAlignment="Left"/>'''
        return XamlReader.load(xaml).as_(Slider)

    @staticmethod
    def create_combobox(header, items, selected):
        """Create combo box with items."""
        items_xaml = "".join([f'<ComboBoxItem Content="{item}"/>' for item in items])
        xaml = f'''<ComboBox xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Header="{header}" Width="200">{items_xaml}</ComboBox>'''
        cb = XamlReader.load(xaml).as_(ComboBox)
        try:
            idx = items.index(selected)
            cb.selected_index = idx
        except ValueError:
            cb.selected_index = 0
        return cb

    @staticmethod
    def create_combobox_item(content, tag=None):
        """Create combo box item."""
        safe_content = UIFactory.escape_xml(content)
        tag_attr = f' Tag="{UIFactory.escape_xml(tag)}"' if tag is not None else ""
        xaml = f'''<ComboBoxItem xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Content="{safe_content}"{tag_attr}/>'''
        return XamlReader.load(xaml).as_(ComboBoxItem)

    @staticmethod
    def create_simple_combobox(min_width=150):
        """Create plain combo box."""
        xaml = f'''<ComboBox xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    MinWidth="{min_width}"/>'''
        return XamlReader.load(xaml).as_(ComboBox)

    @staticmethod
    def create_path_text(text):
        """Create selectable path text block."""
        safe_text = UIFactory.escape_xml(text)
        xaml = f'''<TextBlock xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Text="{safe_text}" IsTextSelectionEnabled="True" 
                    Foreground="{{ThemeResource TextFillColorSecondaryBrush}}"/>'''
        return XamlReader.load(xaml).as_(TextBlock)

    @staticmethod
    def create_expander(header, description=None):
        """Create expander with header and optional description."""
        UIFactory._ensure_common_resources()
        safe_header = UIFactory.escape_xml(header)
        style_attr = 'Style="{StaticResource SectionExpanderStyle}"'
        if description:
            safe_desc = UIFactory.escape_xml(description)
            xaml = f'''<Expander xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                        {style_attr}>
                        <Expander.Header>
                            <StackPanel Spacing="2" Margin="0,16,0,16" HorizontalAlignment="Stretch">
                                <TextBlock Text="{safe_header}" Style="{{StaticResource BodyStrongTextBlockStyle}}"/>
                                <TextBlock Text="{safe_desc}" Style="{{StaticResource CaptionTextBlockStyle}}" Foreground="{{ThemeResource TextFillColorSecondaryBrush}}"/>
                            </StackPanel>
                        </Expander.Header>
                    </Expander>'''
        else:
            xaml = f'''<Expander xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                        Header="{safe_header}" {style_attr}/>'''
        return XamlReader.load(xaml).as_(Expander)

    @staticmethod
    def create_stack_panel(spacing=8, orientation="Vertical"):
        """Create stack panel."""
        xaml = f'''<StackPanel xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
                    Spacing="{spacing}" Orientation="{orientation}"/>'''
        return XamlReader.load(xaml).as_(StackPanel)

    @staticmethod
    def create_styled_button(text, style=None, padding="12,8"):
        """Create button with optional style."""
        safe_text = UIFactory.escape_xml(text)
        style_attr = f'Style="{{StaticResource {style}}}"' if style else ""
        xaml = f'''<Button xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    Content="{safe_text}" {style_attr} Padding="{padding}"/>'''
        return XamlReader.load(xaml).as_(Button)

    @staticmethod
    def create_icon_button(glyph, padding="8,6", font_size=12):
        """Create button with icon."""
        xaml = f'''<Button xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    Padding="{padding}" VerticalAlignment="Center">
                    <FontIcon Glyph="{glyph}" FontSize="{font_size}"/>
                </Button>'''
        return XamlReader.load(xaml).as_(Button)

    @staticmethod
    def create_icon_text_button(glyph, text, spacing=8, padding="8,6", font_size=12):
        """Create button with icon and text."""
        safe_text = UIFactory.escape_xml(text)
        xaml = f'''<Button xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Padding="{padding}">
                    <StackPanel Orientation="Horizontal" Spacing="{spacing}">
                        <FontIcon Glyph="{glyph}" FontSize="{font_size}"/>
                        <TextBlock Text="{safe_text}" VerticalAlignment="Center"/>
                    </StackPanel>
                </Button>'''
        return XamlReader.load(xaml).as_(Button)

    @staticmethod
    def create_danger_button(text):
        """Create red danger button."""
        safe_text = UIFactory.escape_xml(text)
        xaml = f'''<Button xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                    Content="{safe_text}"
                    Background="#c42b1c" Foreground="White" BorderBrush="#c42b1c">
                    <Button.Resources>
                        <SolidColorBrush x:Key="ButtonBackgroundPointerOver" Color="#a12416"/>
                        <SolidColorBrush x:Key="ButtonBackgroundPressed" Color="#8a1f12"/>
                        <SolidColorBrush x:Key="ButtonBorderBrushPointerOver" Color="#a12416"/>
                        <SolidColorBrush x:Key="ButtonBorderBrushPressed" Color="#8a1f12"/>
                        <SolidColorBrush x:Key="ButtonForegroundPointerOver" Color="White"/>
                        <SolidColorBrush x:Key="ButtonForegroundPressed" Color="White"/>
                    </Button.Resources>
                </Button>'''
        return XamlReader.load(xaml).as_(Button)

    @staticmethod
    def create_info_bar(
        title="",
        message="",
        severity="Informational",
        is_closable=False,
        margin="0",
        show_icon=True,
        action_uri=None,
        action_text=None,
    ):
        """Create info bar with optional hyperlink action."""
        safe_title = UIFactory.escape_xml(title) if title else ""
        safe_message = UIFactory.escape_xml(message) if message else ""
        icon_visible = "True" if show_icon else "False"

        title_attr = f'Title="{safe_title}"' if title else ""
        message_attr = f'Message="{safe_message}"' if message else ""

        action_button = ""
        if action_uri and action_text:
            safe_action_text = UIFactory.escape_xml(action_text)
            action_button = f'''<InfoBar.ActionButton>
                <HyperlinkButton Content="{safe_action_text}" NavigateUri="{action_uri}"/>
            </InfoBar.ActionButton>'''

        xaml = f'''<InfoBar xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    IsOpen="True" {title_attr} {message_attr} IsClosable="{str(is_closable)}"
                    Severity="{severity}" Margin="{margin}" IsIconVisible="{icon_visible}">
                    {action_button}
                </InfoBar>'''
        return XamlReader.load(xaml).as_(InfoBar)

    @staticmethod
    def create_hyperlink_button(text, padding="0"):
        """Create hyperlink button."""
        safe_text = UIFactory.escape_xml(text)
        xaml = f'''<HyperlinkButton xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    Content="{safe_text}" Padding="{padding}"/>'''
        return XamlReader.load(xaml).as_(HyperlinkButton)

    @staticmethod
    def create_font_icon(glyph, font_size=14, secondary=False):
        """Create font icon."""
        foreground = 'Foreground="{ThemeResource TextFillColorSecondaryBrush}"' if secondary else ""
        xaml = f'''<FontIcon xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    Glyph="{glyph}" FontSize="{font_size}" {foreground}/>'''
        return XamlReader.load(xaml).as_(FontIcon)
