"""
Build script for YASB GUI.
Placed under app/scripts to avoid project-root pyproject metadata being picked up by cx_Freeze.
"""

import datetime
import os
import platform
import sys
from pathlib import Path

from cx_Freeze import Executable, setup

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
APP_DIR = PROJECT_ROOT / "app"
ASSETS_DIR = PROJECT_ROOT / "assets"
DIST_DIR = PROJECT_ROOT / "dist"

# Ensure the app package is importable regardless of current working directory.
sys.path.insert(0, str(APP_DIR))

from core.constants import APP_VERSION  # noqa: E402


def detect_architecture():
    """Detect the system architecture for build purposes."""
    machine = platform.machine().lower()
    if machine in ["arm64", "aarch64"]:
        return "aarch64"
    if machine in ["amd64", "x86_64", "x64"]:
        return "x64"
    if platform.architecture()[0] == "64bit":
        return "x64"
    return None


def main():
    arch_info = detect_architecture()
    if not arch_info:
        raise RuntimeError("Unsupported or undetected architecture. Cannot build.")

    # Avoid reading project-root metadata (pyproject.toml) by building from the script directory.
    os.chdir(SCRIPT_DIR)

    build_options = {
        "includes": [
            "winui3.microsoft.ui.composition.systembackdrops",
            "winui3.microsoft.ui.xaml",
            "winui3.microsoft.ui.xaml.controls",
            "winui3.microsoft.ui.xaml.controls.primitives",
            "winui3.microsoft.ui.xaml.markup",
            "winui3.microsoft.ui.xaml.media",
            "winui3.microsoft.ui.xaml.input",
            "winui3.microsoft.ui.windowing",
            "winui3.microsoft.ui.dispatching",
            "winui3.microsoft.ui.xaml.media.imaging",
            "winui3.microsoft.ui.xaml.media.animation",
            "winui3.microsoft.ui.xaml.xamltypeinfo",
            "winui3.microsoft.ui.xaml.automation.peers",
            "winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap",
        ],
        "excludes": ["tkinter", "unittest", "pydoc", "test", "tests", "pytest"],
        "include_files": [
            (str(APP_DIR / "core" / "locales"), "lib/core/locales/"),
            (str(APP_DIR / "core" / "editor"), "lib/core/editor/"),
            (str(APP_DIR / "xaml"), "app/xaml/"),
            (str(ASSETS_DIR / "app.ico"), "assets/app.ico"),
        ],
        "zip_exclude_packages": [
            "core",
            "webview2",
        ],
        "zip_include_packages": ["*"],
        "no_compress": True,
        "zip_filename": "library.zip",
        "build_exe": str(DIST_DIR),
        "silent_level": 1,
        "silent": True,
        "include_msvcr": True,
        "optimize": 2,
    }

    directory_table = [
        ("ProgramMenuFolder", "TARGETDIR", "."),
        ("MyProgramMenu", "ProgramMenuFolder", "."),
    ]

    msi_data = {
        "Directory": directory_table,
        "ProgId": [
            ("Prog.Id", None, None, "GUI application for YASB Reborn.", "IconId", None),
        ],
        "Icon": [
            ("IconId", str(ASSETS_DIR / "app.ico")),
        ],
    }

    bdist_msi_options = {
        "data": msi_data,
        "install_icon": str(ASSETS_DIR / "app.ico"),
        "upgrade_code": "{7e4f9c2a-3b81-4d56-a9e7-1f8c5d2b0a34}",
        "add_to_path": False,
        "dist_dir": str(DIST_DIR / "out"),
        "all_users": False,
        "skip_build": True,
        "target_name": f"yasb-gui-{APP_VERSION}-{arch_info}.msi",
        "summary_data": {
            "author": "AmN",
            "comments": "YASB GUI",
            "keywords": "yasb; configurator; gui; windows",
        },
    }

    executables = [
        Executable(
            script=str(APP_DIR / "main.py"),
            base="gui",
            target_name="ygui",
            icon=str(ASSETS_DIR / "app.ico"),
            shortcut_name="YASB GUI",
            shortcut_dir="MyProgramMenu",
            copyright=f"Copyright (C) {datetime.datetime.now().year} AmN",
        )
    ]

    setup(
        name="YASB GUI",
        version=APP_VERSION,
        author="AmN",
        description="YASB GUI",
        executables=executables,
        options={
            "build_exe": build_options,
            "bdist_msi": bdist_msi_options,
        },
    )


if __name__ == "__main__":
    main()
