"""
Logging setup with file rotation.

Keeps logs in the app data folder with automatic rotation (max 1MB per file,
keeps 10 backups). Also catches unhandled exceptions and logs them.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from core.constants import APP_DATA_DIR, LOG_PATH

_logger = None


def get_logger() -> logging.Logger:
    """Get the app logger (creates it if needed)."""
    global _logger

    if _logger is not None:
        return _logger

    _logger = logging.getLogger("yasb-gui")
    _logger.setLevel(logging.DEBUG)

    if _logger.handlers:
        return _logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    os.makedirs(APP_DATA_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    _logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)

    _setup_exception_hook()

    return _logger


def _setup_exception_hook():
    """Catch any unhandled exceptions and log them."""

    def exception_hook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        get_logger().critical(
            f"Unhandled exception: {exc_type.__name__}: {exc_value}",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = exception_hook


def debug(msg: str, *args, **kwargs):
    get_logger().debug(msg, *args, stacklevel=2, **kwargs)


def info(msg: str, *args, **kwargs):
    get_logger().info(msg, *args, stacklevel=2, **kwargs)


def warning(msg: str, *args, **kwargs):
    get_logger().warning(msg, *args, stacklevel=2, **kwargs)


def error(msg: str, *args, **kwargs):
    get_logger().error(msg, *args, stacklevel=2, **kwargs)


def critical(msg: str, *args, **kwargs):
    get_logger().critical(msg, *args, stacklevel=2, **kwargs)


def exception(msg: str, *args, **kwargs):
    """Log exception with full traceback."""
    get_logger().exception(msg, *args, stacklevel=2, **kwargs)
