"""
YASB GUI entry point.
Initializes and starts the application.
"""

from core.application import ConfiguratorApp
from core.logger import get_logger
from winui3.microsoft.ui.xaml import Application, ApplicationInitializationCallbackParams
from winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap import (
    InitializeOptions,
    initialize,
)


def init(_: ApplicationInitializationCallbackParams):
    """Initialize the configurator app."""
    ConfiguratorApp()


def main():
    """Start the application."""
    get_logger()

    with initialize(options=InitializeOptions.ON_NO_MATCH_SHOW_UI):
        Application.start(init)


if __name__ == "__main__":
    main()
