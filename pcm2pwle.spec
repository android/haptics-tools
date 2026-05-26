# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Add spec directory to path (supports pyinstaller execution and direct python run)
if 'SPECPATH' in globals():
  # PyInstaller sets SPECPATH globally, avoiding NameError on __file__ in some runtimes
  spec_path = SPECPATH
else:
  # Fallback for manual python run, where standard __file__ is guaranteed
  spec_path = str(Path(__file__).parent.resolve())

sys.path.insert(0, spec_path)

block_cipher = None

a = Analysis(
    ['pcm2pwle/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'matplotlib.backends.backend_pdf',
        'matplotlib.backends.backend_svg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6'],
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
