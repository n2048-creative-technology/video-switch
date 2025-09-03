import os
import sys
import sysconfig
import glob
from PyInstaller.utils.hooks import collect_submodules

project_root = os.path.abspath(os.getcwd())
pathex = [project_root]

hidden = ['serial.tools.list_ports'] + collect_submodules('PyATEMMax')

def _find_python_shared():
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    libdir = sysconfig.get_config_var('LIBDIR') or ''
    ldlib = sysconfig.get_config_var('LDLIBRARY') or ''
    candidates = []
    if libdir and ldlib:
        candidates.append(os.path.join(libdir, ldlib))
    candidates.extend(sorted(glob.glob(f"/lib/*/libpython{ver}.so*")))
    candidates.extend(sorted(glob.glob(f"/usr/lib/*/libpython{ver}.so*")))
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

_py_shared = _find_python_shared()
extra_bins = []  # Rely on PyInstaller's own python shared library handling to avoid dupes

block_cipher = None

a = Analysis(
    ['run_mpv.py'],
    pathex=pathex,
    binaries=extra_bins,
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
    name='karel-switcher-mpv',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
)
