# PyInstaller spec for macOS one-file build (non-mpv variant)

import os
from PyInstaller.utils.hooks import collect_submodules

project_root = os.path.abspath(os.getcwd())
pathex = [project_root]

hidden = ['serial.tools.list_ports'] + collect_submodules('PyATEMMax')

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=pathex,
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='karel-switcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed app (Tkinter) but as one-file binary
)

