# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from pathlib import Path

# Add spec directory and the workspace root to path to allow absolute imports
if 'SPECPATH' in globals():
  # PyInstaller sets SPECPATH globally, avoiding NameError on __file__ in some runtimes
  spec_path = SPECPATH
else:
  # Fallback for manual python run, where standard __file__ is guaranteed
  spec_path = str(Path(__file__).parent.resolve())

# Locate the workspace tools container (parent of google3/) dynamically,
# allowing PyInstaller to successfully resolve 'google3' absolute
# package namespaces.
spec_path_obj = Path(spec_path).resolve()
tools_root = str(spec_path_obj.parent.parent.parent.parent)

sys.path.insert(0, spec_path)
sys.path.insert(0, tools_root)

from common.pyinstaller_utils import exclude_glib_gio

block_cipher = None

a = Analysis(
    ['pcm2pwle/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt6',
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_pdf',
        'matplotlib.backends.backend_svg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# By default, bundle GLib/GIO (PYI_EXCLUDE_GLIB=0) and rely on GIO_USE_VFS=local
# runtime override to avoid GVFS ABI mismatch crashes. This also prevents
# PyQt6/Qt6 from segfaulting on exit due to mismatches with host GLib.
# Set PYI_EXCLUDE_GLIB to '1' to explicitly force GLib/GIO exclusions.
if os.environ.get('PYI_EXCLUDE_GLIB', '0') != '0':
  print("--- PyInstaller Build: Executing GLib/GIO Exclusions ---")
  a = exclude_glib_gio(a)
else:
  print("--- PyInstaller Build: Bypassing GLib/GIO Exclusions (Leaving Bundled) ---")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='pcm2pwle',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
