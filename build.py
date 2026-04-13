#!/usr/bin/env python3
"""
Build a double-clickable Quartet Payment Calculator using PyInstaller.

For a small, clean binary (no stray hooks from a global Python install), use a
dedicated venv, then build:

  Windows:
    python -m venv build_env
    build_env\\Scripts\\activate
    pip install -r requirements-build.txt
    python build.py

  macOS / Linux:
    python3 -m venv build_env
    source build_env/bin/activate
    pip install -r requirements-build.txt
    python build.py

Windows -> dist/QuartetPaymentCalculator.exe  (one-file, no console)
macOS   -> dist/QuartetPaymentCalculator.app  (windowed bundle; Finder-friendly).
          Build must be run on a Mac — PyInstaller targets the host OS only.

Optional: add icon.icns next to build.py for the macOS app icon (Windows uses icon.ico).

After a successful build, QuartetPaymentCalculator-Release/ is filled with the
binary or .app bundle, clean data/ and exports/ folders, and README.txt for distribution.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

APP_NAME = "QuartetPaymentCalculator"
ENTRY = os.path.join("app", "quartet_payment_calculator.py")
RELEASE_DIR = "QuartetPaymentCalculator-Release"


def _icon_args(root: str) -> list[str]:
    icns = os.path.join(root, "icon.icns")
    ico = os.path.join(root, "icon.ico")
    # macOS .app BUNDLE accepts only .icns (or Pillow-assisted conversion). Do not pass .ico.
    if sys.platform == "darwin":
        if os.path.isfile(icns):
            return [f"--icon={icns}"]
        return []
    if os.path.isfile(ico):
        return [f"--icon={ico}"]
    return []


def _assemble_release(root: str) -> None:
    """
    Populate QuartetPaymentCalculator-Release/ with exe or .app, data, exports, README.
    Does not delete an existing release folder so data/ and exports/ there stay intact;
    always overwrites the bundled binary with the fresh build.
    """
    dist_dir = os.path.join(root, "dist")
    rel = os.path.join(root, RELEASE_DIR)
    os.makedirs(rel, exist_ok=True)

    exe_path = os.path.join(dist_dir, f"{APP_NAME}.exe")
    app_path = os.path.join(dist_dir, f"{APP_NAME}.app")
    mac_bin = os.path.join(dist_dir, APP_NAME)
    if os.path.isfile(exe_path):
        shutil.copy2(exe_path, os.path.join(rel, f"{APP_NAME}.exe"))
    elif sys.platform == "darwin" and os.path.isdir(app_path):
        dst_app = os.path.join(rel, f"{APP_NAME}.app")
        if os.path.isdir(dst_app):
            shutil.rmtree(dst_app)
        shutil.copytree(app_path, dst_app)
    elif sys.platform == "darwin" and os.path.isfile(mac_bin):
        # Some PyInstaller layouts emit a standalone Mach-O next to (or instead of) a .app.
        dst_bin = os.path.join(rel, APP_NAME)
        shutil.copy2(mac_bin, dst_bin)
        try:
            mode = os.stat(dst_bin).st_mode
            os.chmod(dst_bin, mode | 0o111)
        except OSError:
            pass

    data_rel = os.path.join(rel, "data")
    os.makedirs(data_rel, exist_ok=True)
    os.makedirs(os.path.join(rel, "exports"), exist_ok=True)
    for name in ("appointments.json", "payments_log.csv"):
        src = os.path.join(root, "data", name)
        dst = os.path.join(data_rel, name)
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.copy2(src, dst)

    readme = os.path.join(root, "README.txt")
    if os.path.isfile(readme):
        shutil.copy2(readme, os.path.join(rel, "README.txt"))


def main() -> int:
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    if not os.path.isfile(ENTRY):
        print(f"ERROR: {ENTRY} not found in {root}", file=sys.stderr)
        return 1

    build_dir = os.path.join(root, "build")
    dist_dir = os.path.join(root, "dist")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
    if os.path.isdir(dist_dir):
        shutil.rmtree(dist_dir)

    cmd: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--name",
        APP_NAME,
        "--distpath",
        "dist",
        "--workpath",
        "build",
        "--specpath",
        root,
    ]
    # macOS: omit --onefile so PyInstaller emits a proper .app bundle (double-click in Finder).
    # Windows / Linux: keep single-file output.
    if sys.platform != "darwin":
        cmd.append("--onefile")
    cmd.extend(_icon_args(root))

    if os.name == "nt":
        cmd.append("--noconsole")
    else:
        cmd.append("--windowed")

    cmd.append(ENTRY)

    print("Running:", " ".join(cmd))
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        print("Build failed.", file=sys.stderr)
        return r.returncode

    out: str | None = None
    if os.path.isdir(dist_dir):
        exe_path = os.path.join(dist_dir, f"{APP_NAME}.exe")
        app_bundle = os.path.join(dist_dir, f"{APP_NAME}.app")
        mac_exe = os.path.join(dist_dir, APP_NAME)
        if os.path.isfile(exe_path):
            out = exe_path
        elif sys.platform == "darwin" and os.path.isdir(app_bundle):
            out = app_bundle
        elif os.path.isfile(mac_exe):
            out = mac_exe
        else:
            names = sorted(os.listdir(dist_dir))
            if names:
                out = os.path.join(dist_dir, names[0])

    print()
    print("Build succeeded.")
    if out and os.path.exists(out):
        print(f"Output: {os.path.abspath(out)}")
    else:
        print(f"Check folder: {os.path.abspath(dist_dir)}")

    _assemble_release(root)
    print(f"Release folder: {os.path.abspath(os.path.join(root, RELEASE_DIR))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
