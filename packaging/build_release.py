"""Build Windows release executable with PyInstaller."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def main() -> int:
    os.chdir(str(ROOT))

    # Clean previous builds
    for p in [DIST, BUILD]:
        if p.exists():
            shutil.rmtree(p)

    # Ensure PyInstaller is installed
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyinstaller"],
        check=True, capture_output=True,
    )

    # Build the executable
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "FlowerVending",
        "--onefile",
        "--windowed",
        "--add-data", f"config{os.pathsep}config",
        "--add-data", f"src/flower_vending/ui/assets{os.pathsep}flower_vending/ui/assets",
        "--hidden-import", "flower_vending.devices.dbv300sd.protocol.jcm_serial",
        "--hidden-import", "flower_vending.devices.arduino",
        "--hidden-import", "flower_vending.devices.printer",
        "--hidden-import", "flower_vending.runtime.production",
        "--hidden-import", "flower_vending.runtime.discover",
        "--hidden-import", "serial",
        "--hidden-import", "serial.tools.list_ports",
        "--collect-all", "flower_vending",
        "src/flower_vending/__main__.py",
    ]

    print("Building FlowerVending executable...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("Build failed!")
        return 1

    print(f"Executable created: {DIST / 'FlowerVending.exe'}")
    print(f"Size: {os.path.getsize(DIST / 'FlowerVending.exe') / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
