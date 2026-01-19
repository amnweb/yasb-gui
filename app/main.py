"""
YASB GUI entry point.
Initializes and starts the application.
"""

from core.application import ConfiguratorApp
from core.logger import get_logger
from winrt.windows.applicationmodel import Package
from winui3.microsoft.ui.xaml import Application, ApplicationInitializationCallbackParams


def is_packaged() -> bool:
    """Check if running as a packaged MSIX app."""
    try:
        Package.current
        return True
    except Exception:
        return False


def init(_: ApplicationInitializationCallbackParams):
    """Initialize the configurator app."""
    ConfiguratorApp()


def main():
    """Start the application."""
    get_logger()

    if is_packaged():
        # Packaged MSIX app - runtime provided by framework dependency
        Application.start(init)
    else:
        # Unpackaged app - need to bootstrap the runtime
        from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import (
            InitializeOptions,
            initialize,
        )

        with initialize(options=InitializeOptions.ON_NO_MATCH_SHOW_UI):
            Application.start(init)


if __name__ == "__main__":
    main()
