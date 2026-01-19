"""
MSIX packager for YASB GUI.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent.resolve()
APP_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = APP_DIR.parent
ASSETS_DIR = PROJECT_ROOT / "assets"

# Add app directory to path for imports
sys.path.insert(0, str(APP_DIR))
from core.constants import APP_VERSION


def find_makeappx() -> str | None:
    """Find makeappx.exe in Windows SDK."""
    kits_root = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    if not kits_root.exists():
        return None

    candidates = []
    for version_dir in kits_root.glob("*"):
        if not version_dir.is_dir():
            continue
        for arch in ("x64", "arm64"):
            candidate = version_dir / arch / "makeappx.exe"
            if candidate.exists():
                candidates.append(candidate)

    return str(sorted(candidates)[-1]) if candidates else None


def find_makepri() -> str | None:
    """Find makepri.exe in Windows SDK."""
    kits_root = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    if not kits_root.exists():
        return None

    candidates = []
    for version_dir in kits_root.glob("*"):
        if not version_dir.is_dir():
            continue
        for arch in ("x64", "arm64"):
            candidate = version_dir / arch / "makepri.exe"
            if candidate.exists():
                candidates.append(candidate)

    return str(sorted(candidates)[-1]) if candidates else None


def build_msix(
    dist_dir: Path,
    output_dir: Path,
    identity_name: str,
    publisher: str,
    publisher_display_name: str,
    display_name: str,
    description: str,
    executable: str,
    arch: str,
) -> Path:
    """Build MSIX package from dist directory."""
    if not dist_dir.exists():
        raise FileNotFoundError(f"dist directory not found: {dist_dir}")

    # Windows only accepts: x86, x64, arm, arm64, neutral
    manifest_arch = "arm64" if arch == "aarch64" else arch

    # Prepare layout directory
    layout_dir = output_dir / "layout"
    if layout_dir.exists():
        shutil.rmtree(layout_dir)
    layout_dir.mkdir(parents=True, exist_ok=True)

    # Copy dist contents
    shutil.copytree(dist_dir, layout_dir, dirs_exist_ok=True)

    # Copy MSIX assets (icon.png, StoreLogo.png, and unplated variants for taskbar)
    assets_out = layout_dir / "assets"
    assets_out.mkdir(parents=True, exist_ok=True)
    for asset in ASSETS_DIR.glob("*.png"):
        shutil.copy2(asset, assets_out / asset.name)

    # Generate resources.pri from layout directory (indexes unplated assets with correct paths)
    makepri = find_makepri()
    if makepri:
        priconfig = layout_dir / "priconfig.xml"
        subprocess.run([makepri, "createconfig", "/cf", str(priconfig), "/dq", "en-US", "/o"], check=True)
        subprocess.run(
            [
                makepri,
                "new",
                "/pr",
                str(layout_dir),
                "/cf",
                str(priconfig),
                "/of",
                str(layout_dir / "resources.pri"),
                "/in",
                identity_name,
                "/o",
            ],
            check=True,
        )
        priconfig.unlink(missing_ok=True)

    # Ensure version has 4 parts
    parts = APP_VERSION.split(".")
    while len(parts) < 4:
        parts.append("0")
    version = ".".join(parts[:4])

    # Write minimal manifest - use base names without qualifiers so PRI can resolve variants
    manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap rescap">
  <Identity Name="{identity_name}" Publisher="{publisher}" Version="{version}" ProcessorArchitecture="{manifest_arch}" />
  <Properties>
    <DisplayName>{display_name}</DisplayName>
    <PublisherDisplayName>{publisher_display_name}</PublisherDisplayName>
    <Logo>assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0" />
    <PackageDependency Name="Microsoft.WindowsAppRuntime.1.7" MinVersion="7000.498.2246.0" Publisher="CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, S=Washington, C=US" />
  </Dependencies>
  <Resources>
    <Resource Language="en-us" />
  </Resources>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
    <rescap:Capability Name="unvirtualizedResources" />
  </Capabilities>
  <Applications>
    <Application Id="App" Executable="{executable}" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="{display_name}"
                          Description="{description}"
                          BackgroundColor="transparent"
                          Square150x150Logo="assets\\Square150x150Logo.png"
                          Square44x44Logo="assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="assets\\Wide310x150Logo.png"
                         Square71x71Logo="assets\\Square71x71Logo.png"
                         Square310x310Logo="assets\\Square310x310Logo.png">
          <uap:ShowNameOnTiles>
            <uap:ShowOn Tile="square150x150Logo"/>
            <uap:ShowOn Tile="wide310x150Logo"/>
            <uap:ShowOn Tile="square310x310Logo"/>
          </uap:ShowNameOnTiles>
        </uap:DefaultTile>
        <uap:SplashScreen Image="assets\\SplashScreen.png"/>
      </uap:VisualElements>
    </Application>
  </Applications>
</Package>
'''
    (layout_dir / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    # Create MSIX
    output_dir.mkdir(parents=True, exist_ok=True)
    msix_path = output_dir / f"yasb-gui-{APP_VERSION}-{arch}.msix"

    makeappx = find_makeappx()
    if not makeappx:
        raise RuntimeError("makeappx.exe not found. Install Windows SDK.")

    subprocess.run([makeappx, "pack", "/d", str(layout_dir), "/p", str(msix_path), "/o"], check=True)

    return msix_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MSIX package for YASB GUI")
    parser.add_argument("--dist", default=str(PROJECT_ROOT / "dist"), help="Path to cx_Freeze dist output")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "msix"), help="Output directory for MSIX")
    parser.add_argument("--arch", default="x64", choices=["x64", "aarch64"], help="Target architecture")
    parser.add_argument("--identity-name", default="YASB.GUI", help="Package identity name")
    parser.add_argument(
        "--publisher",
        default="CN=SignPath Foundation, O=SignPath Foundation, L=Lewes, S=Delaware, C=US",
        help="Publisher DN",
    )
    parser.add_argument("--publisher-display-name", default="SignPath Foundation", help="Publisher display name")
    parser.add_argument("--display-name", default="YASB GUI", help="Application display name")
    parser.add_argument("--description", default="YASB Reborn GUI", help="Application description")
    parser.add_argument("--executable", default="ygui.exe", help="Main executable name")

    args = parser.parse_args()

    msix_path = build_msix(
        dist_dir=Path(args.dist),
        output_dir=Path(args.output),
        identity_name=args.identity_name,
        publisher=args.publisher,
        publisher_display_name=args.publisher_display_name,
        display_name=args.display_name,
        description=args.description,
        executable=args.executable,
        arch=args.arch,
    )

    print(f"MSIX created at: {msix_path}")


if __name__ == "__main__":
    main()
