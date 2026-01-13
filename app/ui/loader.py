"""
Loader for XAML files used in the UI.
Loads XAML from the app/xaml directory.
"""

from core.constants import APP_BASE_PATH


def load_xaml(name: str) -> str:
    xaml_path = APP_BASE_PATH / "app" / "xaml" / name
    with open(xaml_path, encoding="utf-8") as f:
        return f.read()
