# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path
from PyInstaller.building.datastruct import TOC

service_root = Path(SPECPATH).resolve().parent
fixture_root = Path(os.environ["DYNAMISSCIENCE_FIXTURE_DIR"]).resolve()
if not fixture_root.is_dir():
    raise RuntimeError(f"Synthetic fixture directory is unavailable: {fixture_root}")
repo_root = service_root.parents[1]
license_notice = repo_root / "docs" / "desktop" / "THIRD_PARTY_LICENSES.md"
datas = [(str(fixture_root), "data")]
if license_notice.is_file():
    datas.append((str(license_notice), "."))
third_party_notices = Path(os.environ["DYNAMISSCIENCE_THIRD_PARTY_NOTICES"]).resolve()
if third_party_notices.is_file():
    datas.append((str(third_party_notices), "."))
lgpl_notice = repo_root / "docs" / "desktop" / "licenses" / "LGPL-3.0.txt"
if lgpl_notice.is_file():
    datas.append((str(lgpl_notice), "licenses"))
r_reference = service_root / "scripts" / "real_mixedlm.R"
if r_reference.is_file():
    datas.append((str(r_reference), "scripts"))

a = Analysis(
    [str(service_root / "scripts" / "desktop_entry.py")],
    pathex=[str(service_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "dynamis_science.desktop.worker",
        "scripts.res647_walkthrough",
        "dynamis_science.qualification_real",
        "dynamis_science.performance",
        "scripts.sqlite_recovery",
        "matplotlib.backends.backend_agg",
        "matplotlib.backends.backend_pdf",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.backends.backend_svg",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        # 3D trajectories: workbench/interactive.py imports these lazily
        "pyqtgraph.opengl",
        "OpenGL",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PIL._avif",
        "PySide6.QtNetwork",
        "PySide6.QtTest",
    ],
    noarchive=False,
    optimize=0,
)
# These ICU DLLs came from an unrelated host Poppler installation on the first
# build. Qt resolves its unsuffixed ICU interface from Windows; keep the
# incompatible versioned ICU bundle out of the application.
a.binaries = TOC(
    entry
    for entry in a.binaries
    if Path(entry[1]).name.lower() not in {"icuuc.dll", "icudt78.dll"}
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DynamisScience',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DynamisScience',
)
