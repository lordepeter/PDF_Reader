# -*- mode: python ; coding: utf-8 -*-
"""MangaReader2000.spec - Config do PyInstaller para o app Sophia."""
import os
from PyInstaller.utils.hooks import collect_all

datas = [
    ("catalogo", "catalogo"),
    ("assets/audio", "assets/audio"),
    ("assets/icones", "assets/icones"),
    ("api_teste.py", "."),
    ("dominio", "dominio"),
    ("rotas", "rotas"),
]

hiddenimports = [
    "pymupdf",
    "fitz",
    "PIL",
    "PIL._tkinter_finder",
    "bcrypt",
    "requests",
    "requests.adapters",
    "urllib3",
    "urllib3.contrib",
    "sqlalchemy",
    "sqlalchemy.sql.default_comparator",
    "psycopg",
    "dotenv",
]

binaries = []
for pacote in ["pymupdf", "PIL"]:
    try:
        d, b, h = collect_all(pacote)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "scipy", "pandas", "pytest", "notebook", "IPython"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sophia",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icones/app.ico" if os.path.exists("assets/icones/app.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Sophia",
)
